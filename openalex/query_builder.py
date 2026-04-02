from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlparse

from .schemas import (
    ExactOpenAlexQuery,
    QueryBundle,
    SelectedKeyword,
    SelectedTopic,
)
from .text import normalize_alias, openalex_keyword_id

TEXT_FILTER_KEYS = {
    "abstract.search",
    "default.search",
    "fulltext.search",
    "title.search",
    "title_and_abstract.search",
}

TOPIC_FILTER_KEYS = {"topics.id", "primary_topic.id"}
AUTHOR_SUPPORTED_FILTER_KEYS = {"cited_by_count"}


def split_filter_components(filter_value: str | None) -> list[str]:
    if not filter_value:
        return []
    return [
        component.strip() for component in filter_value.split(",") if component.strip()
    ]


def append_filter(base_filter: str | None, new_component: str) -> str:
    if not base_filter:
        return new_component
    return f"{base_filter},{new_component}"


def strip_text_constraints(query: ExactOpenAlexQuery) -> ExactOpenAlexQuery:
    components = split_filter_components(query.filter)
    filtered_components = [
        component
        for component in components
        if component.split(":", 1)[0] not in TEXT_FILTER_KEYS
    ]
    return query.model_copy(
        update={
            "search": None,
            "filter": ",".join(filtered_components) if filtered_components else None,
            "page": None,
            "cursor": None,
        }
    )


def extract_topic_ids(filter_value: str | None) -> list[int]:
    topic_ids: list[int] = []
    for component in split_filter_components(filter_value):
        key, _, value = component.partition(":")
        if key not in TOPIC_FILTER_KEYS or not value:
            continue
        for raw_id in value.split("|"):
            candidate = raw_id.strip()
            lowered = candidate.lower()
            if lowered.startswith("https://openalex.org/t"):
                candidate = candidate.rsplit("/", 1)[-1]
            if candidate.lower().startswith("t"):
                candidate = candidate[1:]
            if candidate.isdigit():
                topic_ids.append(int(candidate))
    return topic_ids


def extract_query_intent(
    query: ExactOpenAlexQuery,
    topic_lookup: dict[int, str] | None = None,
) -> str:
    fragments: list[str] = []
    if query.search:
        fragments.append(query.search)

    for component in split_filter_components(query.filter):
        key, _, value = component.partition(":")
        if key in TEXT_FILTER_KEYS and value:
            fragments.append(value)

    if not fragments and topic_lookup:
        for topic_id in extract_topic_ids(query.filter):
            topic_name = topic_lookup.get(topic_id)
            if topic_name:
                fragments.append(topic_name)

    if fragments:
        return " ".join(fragment for fragment in fragments if fragment)

    return query.original_input or ""


def filter_components_for_authors(components: list[str] | None) -> list[str]:
    filtered: list[str] = []
    for component in components or []:
        key, _, _ = component.partition(":")
        if key in AUTHOR_SUPPORTED_FILTER_KEYS:
            filtered.append(component)
    return filtered


def build_query_for_keyword(
    keyword: SelectedKeyword,
    *,
    base_query: ExactOpenAlexQuery | None,
    generated_sort: str,
    extra_filter_components: list[str] | None = None,
) -> ExactOpenAlexQuery:
    keyword_filter = f"keywords.id:{openalex_keyword_id(keyword.alias)}"
    if base_query is None:
        filter_value = keyword_filter
        for filter_component in extra_filter_components or []:
            filter_value = append_filter(filter_value, filter_component)
        return ExactOpenAlexQuery(filter=filter_value, sort=generated_sort)

    query = base_query.model_copy(deep=True)
    query.search = None
    query.filter = append_filter(query.filter, keyword_filter)
    for filter_component in extra_filter_components or []:
        query.filter = append_filter(query.filter, filter_component)
    query.sort = query.sort or generated_sort
    query.page = None
    query.cursor = None
    return query


def build_query_for_author_topic(
    topic: SelectedTopic,
    *,
    generated_sort: str,
    extra_filter_components: list[str] | None = None,
) -> ExactOpenAlexQuery:
    filter_value = f"topics.id:{topic.openalex_id}"
    for filter_component in filter_components_for_authors(extra_filter_components):
        filter_value = append_filter(filter_value, filter_component)
    return ExactOpenAlexQuery(
        endpoint="/authors",
        filter=filter_value,
        sort=generated_sort,
    )


def build_query_for_topic(
    topic: SelectedTopic,
    *,
    base_query: ExactOpenAlexQuery | None,
    generated_sort: str,
    extra_filter_components: list[str] | None = None,
) -> ExactOpenAlexQuery:
    topic_filter = f"primary_topic.id:{topic.openalex_id}"
    if base_query is None:
        filter_value = topic_filter
        for filter_component in extra_filter_components or []:
            filter_value = append_filter(filter_value, filter_component)
        return ExactOpenAlexQuery(filter=filter_value, sort=generated_sort)

    query = base_query.model_copy(deep=True)
    query.filter = append_filter(query.filter, topic_filter)
    for filter_component in extra_filter_components or []:
        query.filter = append_filter(query.filter, filter_component)
    query.sort = query.sort or generated_sort
    query.page = None
    query.cursor = None
    return query


def parse_openalex_query_input(
    raw_query: str,
    *,
    default_endpoint: str = "/works",
) -> ExactOpenAlexQuery:
    stripped = raw_query.strip()
    if not stripped:
        raise ValueError("OpenAlex query input cannot be empty")

    if stripped.startswith("{"):
        payload = json.loads(stripped)
        endpoint = str(payload.get("endpoint", default_endpoint))
        _validate_endpoint(endpoint)
        extra_params = {
            str(key): str(value)
            for key, value in payload.items()
            if key
            not in {
                "endpoint",
                "search",
                "filter",
                "sort",
                "per_page",
                "page",
                "cursor",
            }
        }
        return ExactOpenAlexQuery(
            endpoint=endpoint,
            search=_maybe_str(payload.get("search")),
            filter=_maybe_str(payload.get("filter")),
            sort=_maybe_str(payload.get("sort")),
            per_page=_maybe_int(payload.get("per_page")),
            page=_maybe_int(payload.get("page")),
            cursor=_maybe_str(payload.get("cursor")),
            extra_params=extra_params,
            original_input=raw_query,
        )

    if stripped.startswith("http://") or stripped.startswith("https://"):
        parsed = urlparse(stripped)
        endpoint = parsed.path or "/works"
        _validate_endpoint(endpoint)
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        return _build_query_from_pairs(endpoint, query_pairs, raw_query)

    if stripped.startswith("/works?") or stripped.startswith("works?"):
        raw_url = stripped if stripped.startswith("/") else f"/{stripped}"
        parsed = urlparse(raw_url)
        endpoint = parsed.path
        _validate_endpoint(endpoint)
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        return _build_query_from_pairs(endpoint, query_pairs, raw_query)

    if "=" in stripped or "&" in stripped or stripped.startswith("?"):
        query_pairs = parse_qsl(stripped.lstrip("?"), keep_blank_values=True)
        return _build_query_from_pairs(default_endpoint, query_pairs, raw_query)

    _validate_endpoint(default_endpoint)
    return ExactOpenAlexQuery(
        endpoint=default_endpoint,
        filter=stripped,
        original_input=raw_query,
    )


def _build_query_from_pairs(
    endpoint: str, query_pairs: list[tuple[str, str]], raw_query: str
) -> ExactOpenAlexQuery:
    params: dict[str, str] = {}
    for key, value in query_pairs:
        params[key] = value

    extra_params = {
        key: value
        for key, value in params.items()
        if key not in {"search", "filter", "sort", "per-page", "page", "cursor"}
    }
    return ExactOpenAlexQuery(
        endpoint=endpoint,
        search=params.get("search"),
        filter=params.get("filter"),
        sort=params.get("sort"),
        per_page=_maybe_int(params.get("per-page")),
        page=_maybe_int(params.get("page")),
        cursor=params.get("cursor"),
        extra_params=extra_params,
        original_input=raw_query,
    )


def _validate_endpoint(endpoint: str) -> None:
    normalized = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    if normalized not in {"/works", "/authors"}:
        raise ValueError(
            "Only the OpenAlex /works and /authors endpoints are supported right "
            f"now, got {endpoint!r}"
        )


def _maybe_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"Cannot coerce value to int: {value!r}")


def _maybe_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
