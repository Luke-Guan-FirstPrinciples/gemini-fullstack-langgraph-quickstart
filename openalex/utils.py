from __future__ import annotations

import datetime
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from .schemas import (
    AppliedQueryModifier,
    ExactOpenAlexQuery,
    KeywordCandidate,
    OpenAlexRunResult,
    SelectedKeyword,
    SelectedTopic,
    TopicCandidate,
)

STOPWORDS = {
    "about",
    "advances",
    "analysis",
    "and",
    "development",
    "developments",
    "for",
    "from",
    "important",
    "into",
    "latest",
    "literature",
    "methods",
    "papers",
    "physics",
    "recent",
    "research",
    "review",
    "state",
    "studies",
    "study",
    "survey",
    "techniques",
    "the",
    "their",
    "using",
    "with",
}

TEXT_FILTER_KEYS = {
    "abstract.search",
    "default.search",
    "fulltext.search",
    "title.search",
    "title_and_abstract.search",
}

TOPIC_FILTER_KEYS = {"topics.id", "primary_topic.id"}
AUTHOR_SUPPORTED_FILTER_KEYS = {"cited_by_count"}

YEAR_RANGE_PATTERN = re.compile(
    r"\b(?:published\s+)?(?P<relation>after|since|from)\s+(?P<year>20\d{2})\b",
    flags=re.IGNORECASE,
)
CITATION_COMPARISON_PATTERN = re.compile(
    r"\b(?:citation count|citations?|cited(?:\s+by)?\s+count)\s*"
    r"(?P<operator>>=|<=|>|<|=)\s*(?P<count>\d+)\b",
    flags=re.IGNORECASE,
)
CITATION_WORD_COMPARISON_PATTERN = re.compile(
    r"\b(?:citation count|citations?|cited(?:\s+by)?\s+count)\s+"
    r"(?P<operator>greater than|more than|less than|under|over|at least)\s+"
    r"(?P<count>\d+)\b",
    flags=re.IGNORECASE,
)
TOPIC_FOCUS_CLEANUP_PATTERNS = (
    r"\b(?:get|find|show me|give me|retrieve)\b",
    r"\btop\s+\d+\s+(?:papers?|works?|articles?|studies?)\b",
    r"\btop\s+\d+\b",
    r"\b(?:papers?|works?|articles?|studies?)\b",
    r"\brelated\b",
    r"\b(?:has to be|must be|should be)\b",
    r"\b(?:ranked|sorted)\s+by\b[^,.;]*",
)


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def normalize_alias(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def slugify(text: str) -> str:
    return normalize_alias(text)


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOPWORDS]


def short_openalex_id(value: str | None) -> str | None:
    if not value:
        return None
    if "/" not in value:
        return value
    return value.rsplit("/", 1)[-1]


def openalex_topic_id(topic_id: int) -> str:
    return f"T{topic_id}"


def openalex_keyword_id(alias: str) -> str:
    normalized = normalize_alias(alias)
    if not normalized:
        raise ValueError("OpenAlex keyword alias cannot be empty")
    return normalized


def _score_phrase_match(query_norm: str, candidate_norm: str) -> float:
    if not query_norm or not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 125.0
    if candidate_norm in query_norm:
        return 60.0
    if query_norm in candidate_norm:
        return 45.0
    return 0.0


def _score_token_overlap(tokens: list[str], text: str, *, full_weight: float) -> float:
    normalized = normalize_text(text)
    candidate_tokens = normalized.split()
    score = 0.0
    for token in tokens:
        if f" {token} " in f" {normalized} ":
            score += full_weight
        elif token in normalized:
            score += full_weight / 2.0
        else:
            best_ratio = max(
                (
                    SequenceMatcher(None, token, candidate).ratio()
                    for candidate in candidate_tokens
                ),
                default=0.0,
            )
            if best_ratio >= 0.82:
                score += full_weight * 0.45
    return score


def extract_query_modifiers(query: str) -> list[AppliedQueryModifier]:
    lowered = normalize_text(query)
    modifiers: list[AppliedQueryModifier] = []

    if "recent" in lowered.split():
        modifiers.append(
            AppliedQueryModifier(
                source_phrase="recent",
                filter_fragment="from_publication_date:2020-01-01",
                reason="Interpret recency language as papers published on or after January 1, 2020.",
            )
        )

    if "important" in lowered.split():
        modifiers.append(
            AppliedQueryModifier(
                source_phrase="important",
                filter_fragment="fwci:>5",
                reason="Interpret importance language as Field-weighted Citation Impact greater than 5.",
            )
        )

    for match in YEAR_RANGE_PATTERN.finditer(query):
        relation = match.group("relation").lower()
        year = int(match.group("year"))
        start_year = year + 1 if relation == "after" else year
        modifiers.append(
            AppliedQueryModifier(
                source_phrase=match.group(0),
                filter_fragment=f"from_publication_date:{start_year:04d}-01-01",
                reason=(
                    "Interpret publication-year language as a lower bound on "
                    "publication date."
                ),
            )
        )

    for match in CITATION_COMPARISON_PATTERN.finditer(query):
        operator = match.group("operator")
        count = int(match.group("count"))
        modifiers.append(
            AppliedQueryModifier(
                source_phrase=match.group(0),
                filter_fragment=_citation_filter_fragment(operator, count),
                reason="Interpret citation-count language as an OpenAlex cited_by_count filter.",
            )
        )

    for match in CITATION_WORD_COMPARISON_PATTERN.finditer(query):
        operator = match.group("operator").lower()
        count = int(match.group("count"))
        modifiers.append(
            AppliedQueryModifier(
                source_phrase=match.group(0),
                filter_fragment=_citation_filter_fragment(operator, count),
                reason="Interpret citation-count language as an OpenAlex cited_by_count filter.",
            )
        )

    return modifiers


def _citation_filter_fragment(operator: str, count: int) -> str:
    operator_map = {
        ">": f"cited_by_count:>{count}",
        ">=": f"cited_by_count:{count}-",
        "=": f"cited_by_count:{count}",
        "<": f"cited_by_count:<{count}",
        "<=": f"cited_by_count:<{count + 1}",
        "greater than": f"cited_by_count:>{count}",
        "more than": f"cited_by_count:>{count}",
        "over": f"cited_by_count:>{count}",
        "less than": f"cited_by_count:<{count}",
        "under": f"cited_by_count:<{count}",
        "at least": f"cited_by_count:{count}-",
    }
    try:
        return operator_map[operator]
    except KeyError as exc:
        raise ValueError(f"Unsupported citation-count operator: {operator}") from exc


def extract_query_topic_focus(query: str) -> str:
    focused_query = query
    for modifier in extract_query_modifiers(query):
        if modifier.source_phrase:
            focused_query = re.sub(
                re.escape(modifier.source_phrase),
                " ",
                focused_query,
                flags=re.IGNORECASE,
            )
    for pattern in TOPIC_FOCUS_CLEANUP_PATTERNS:
        focused_query = re.sub(pattern, " ", focused_query, flags=re.IGNORECASE)
    focused_query = re.sub(r"\b(?:and|or)\b", " ", focused_query, flags=re.IGNORECASE)
    focused_query = re.sub(r"[^A-Za-z0-9]+", " ", focused_query)
    focused_query = re.sub(r"\s+", " ", focused_query).strip()
    return focused_query or query.strip()


def build_keyword_candidates(
    query: str,
    catalog: list[KeywordCandidate],
    limit: int,
) -> list[KeywordCandidate]:
    query_norm = normalize_text(query)
    query_alias = normalize_alias(query)
    query_tokens = tokenize(query)
    ranked: list[KeywordCandidate] = []

    for item in catalog:
        candidate_tokens = tokenize(item.keyword)
        matching_tokens = sum(1 for token in query_tokens if token in candidate_tokens)
        score = _score_phrase_match(query_norm, normalize_text(item.keyword))
        if query_alias and query_alias == item.alias:
            score += 55.0
        score += _score_token_overlap(query_tokens, item.keyword, full_weight=12.0)
        score += _score_token_overlap(
            query_tokens, item.alias.replace("-", " "), full_weight=8.0
        )
        score += matching_tokens * 8.0
        score += max(len(candidate_tokens) - 1, 0) * 6.0
        if len(candidate_tokens) == 1 and len(query_tokens) > 1:
            score -= 35.0
        if matching_tokens <= 1 and len(query_tokens) >= 3:
            score -= 12.0
        score += min(item.topic_count, 10)
        if score > 0:
            ranked.append(item.model_copy(update={"lexical_score": score}))

    if not ranked:
        fallback = sorted(catalog, key=lambda item: item.topic_count, reverse=True)
        return [
            item.model_copy(update={"lexical_score": float(item.topic_count)})
            for item in fallback[:limit]
        ]

    ranked.sort(
        key=lambda item: (item.lexical_score, item.topic_count, item.keyword.lower()),
        reverse=True,
    )
    return ranked[:limit]


def build_topic_candidates(
    query: str,
    catalog: list[TopicCandidate],
    limit: int,
) -> list[TopicCandidate]:
    query_norm = normalize_text(query)
    query_tokens = tokenize(query)
    ranked: list[TopicCandidate] = []

    for item in catalog:
        topic_name = item.topic_name
        summary = item.summary or ""
        keywords = item.keywords or ""
        score = _score_phrase_match(query_norm, normalize_text(topic_name))
        score += _score_token_overlap(query_tokens, topic_name, full_weight=16.0)
        score += _score_token_overlap(query_tokens, keywords, full_weight=7.0)
        score += _score_token_overlap(query_tokens, summary, full_weight=4.0)
        score += _score_token_overlap(
            query_tokens, item.subfield_name or "", full_weight=4.0
        )
        score += _score_token_overlap(
            query_tokens, item.field_name or "", full_weight=3.0
        )
        if score > 0:
            ranked.append(item.model_copy(update={"lexical_score": score}))

    if not ranked:
        fallback = sorted(catalog, key=lambda item: item.topic_name.lower())
        return [
            item.model_copy(update={"lexical_score": 0.0}) for item in fallback[:limit]
        ]

    ranked.sort(
        key=lambda item: (item.lexical_score, item.topic_name.lower()),
        reverse=True,
    )
    return ranked[:limit]


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


def split_filter_components(filter_value: str | None) -> list[str]:
    if not filter_value:
        return []
    return [
        component.strip() for component in filter_value.split(",") if component.strip()
    ]


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


def append_filter(base_filter: str | None, new_component: str) -> str:
    if not base_filter:
        return new_component
    return f"{base_filter},{new_component}"


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


def create_output_dir(query: str, output_dir: str | None = None) -> Path:
    slug = slugify(query) or "openalex"
    slug = slug[:50]
    if output_dir:
        base_dir = Path(output_dir)
    else:
        from .config import settings

        base_dir = Path(settings.output_root) if settings.output_root else Path.cwd() / "out"
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    task_dir = base_dir / f"{timestamp}_openalex_{slug}"
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def save_run_result(result: OpenAlexRunResult, file_path: Path) -> None:
    with open(file_path, "w", encoding="utf-8") as handle:
        json.dump(result.model_dump(mode="json"), handle, indent=2, ensure_ascii=False)
