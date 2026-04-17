"""Deduplication helpers for search results and enriched paper records."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from research_agent.models import (
    Paper,
    PaperOpenAlexEnrichment,
    PaperRanking,
    PaperSemanticScholarEnrichment,
    SemanticScholarPublicationVenue,
)

logger = logging.getLogger("research_agent.deduplication")

_TITLE_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_NAMES = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}


def dedupe_search_results(
    existing_results: list[dict[str, Any]],
    new_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop repeated search results across and within iterations."""
    if not new_results:
        return []

    seen: set[str] = set()
    for result in existing_results:
        seen.update(_search_result_keys(result))

    unique_results: list[dict[str, Any]] = []
    for result in new_results:
        identity_keys = _search_result_keys(result)
        if identity_keys and any(key in seen for key in identity_keys):
            continue

        unique_results.append(dict(result))
        seen.update(identity_keys)

    logger.info(
        "Search-result deduplication kept %d/%d new results",
        len(unique_results),
        len(new_results),
    )
    return unique_results


def dedupe_papers(papers: list[Paper]) -> list[Paper]:
    """Merge duplicate papers after enrichment using canonical paper identifiers."""
    if not papers:
        return []

    buckets: list[Paper | None] = []
    key_to_bucket: dict[str, int] = {}

    for paper in papers:
        incoming = paper.model_copy(deep=True)
        matching_indexes = sorted(
            {
                key_to_bucket[key]
                for key in _paper_identity_keys(incoming)
                if key in key_to_bucket and buckets[key_to_bucket[key]] is not None
            }
        )

        if not matching_indexes:
            bucket_index = len(buckets)
            buckets.append(incoming)
        else:
            bucket_index = matching_indexes[0]
            merged = buckets[bucket_index] or incoming

            for extra_index in matching_indexes[1:]:
                extra_paper = buckets[extra_index]
                if extra_paper is None:
                    continue
                merged = _merge_papers(merged, extra_paper)
                buckets[extra_index] = None
                for key, mapped_index in list(key_to_bucket.items()):
                    if mapped_index == extra_index:
                        key_to_bucket[key] = bucket_index

            merged = _merge_papers(merged, incoming)
            buckets[bucket_index] = merged

        current = buckets[bucket_index]
        if current is not None:
            for key in _paper_identity_keys(current):
                key_to_bucket[key] = bucket_index

    deduped = [paper for paper in buckets if paper is not None]
    logger.info(
        "Paper deduplication reduced %d papers to %d unique papers",
        len(papers),
        len(deduped),
    )
    return deduped


def _search_result_keys(result: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()

    normalized_url = _normalize_url(_coerce_str(result.get("url")))
    if normalized_url:
        seen.add(f"url:{normalized_url}")
        keys.append(f"url:{normalized_url}")

    normalized_title = _normalize_title(_coerce_str(result.get("title")))
    normalized_source = _normalize_title(_coerce_str(result.get("source")))
    if normalized_title and normalized_source:
        key = f"title-source:{normalized_source}:{normalized_title}"
        if key not in seen:
            seen.add(key)
            keys.append(key)
    elif normalized_title:
        key = f"title:{normalized_title}"
        if key not in seen:
            keys.append(key)

    return keys


def _paper_identity_keys(paper: Paper) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()

    for doi in _paper_dois(paper):
        key = f"doi:{doi}"
        if key not in seen:
            seen.add(key)
            keys.append(key)

    openalex_id = _coerce_str(paper.openalex.openalex_id) if paper.openalex else ""
    if openalex_id:
        key = f"openalex:{openalex_id}"
        if key not in seen:
            seen.add(key)
            keys.append(key)

    semantic_scholar_id = (
        _coerce_str(paper.semantic_scholar.paper_id) if paper.semantic_scholar else ""
    )
    if semantic_scholar_id:
        key = f"s2:{semantic_scholar_id}"
        if key not in seen:
            seen.add(key)
            keys.append(key)

    normalized_titles = _paper_titles(paper)
    years = _paper_years(paper)
    if years:
        for title in normalized_titles:
            for year in years:
                key = f"title-year:{year}:{title}"
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
    else:
        for title in normalized_titles:
            if not _is_strong_title(title):
                continue
            key = f"title:{title}"
            if key not in seen:
                seen.add(key)
                keys.append(key)

    return keys


def _paper_dois(paper: Paper) -> list[str]:
    candidates = [
        _normalize_doi(paper.doi),
        _normalize_doi(paper.openalex.doi) if paper.openalex else None,
        _normalize_doi(paper.semantic_scholar.doi) if paper.semantic_scholar else None,
    ]
    return _unique_non_empty(candidates)


def _paper_titles(paper: Paper) -> list[str]:
    candidates = [
        _normalize_title(paper.title),
        _normalize_title(paper.openalex.matched_title) if paper.openalex else "",
        _normalize_title(paper.semantic_scholar.matched_title)
        if paper.semantic_scholar
        else "",
    ]
    return _unique_non_empty(candidates)


def _paper_years(paper: Paper) -> list[int]:
    values = [
        paper.year,
        paper.openalex.publication_year if paper.openalex else None,
        paper.semantic_scholar.publication_year if paper.semantic_scholar else None,
    ]
    years: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value is None:
            continue
        try:
            year = int(value)
        except (TypeError, ValueError):
            continue
        if year <= 0 or year in seen:
            continue
        seen.add(year)
        years.append(year)
    return years


def _merge_papers(left: Paper, right: Paper) -> Paper:
    merged = left.model_copy(deep=True)
    merged.title = _prefer_text(left.title, right.title, prefer_longer=True) or left.title
    merged.authors = _merge_string_lists(left.authors, right.authors)
    merged.source = _prefer_text(left.source, right.source)
    merged.url = _prefer_url(left.url, right.url)
    merged.abstract = _prefer_text(left.abstract, right.abstract, prefer_longer=True)
    merged.key_finding = _prefer_text(
        left.key_finding,
        right.key_finding,
        prefer_longer=True,
    )
    merged.openalex = _merge_openalex(left.openalex, right.openalex)
    merged.semantic_scholar = _merge_semantic_scholar(
        left.semantic_scholar,
        right.semantic_scholar,
    )
    merged.doi = _first_non_empty(
        _normalize_doi(merged.openalex.doi) if merged.openalex else None,
        _normalize_doi(merged.semantic_scholar.doi) if merged.semantic_scholar else None,
        _normalize_doi(left.doi),
        _normalize_doi(right.doi),
    )
    merged.year = _first_non_none(
        merged.openalex.publication_year if merged.openalex else None,
        merged.semantic_scholar.publication_year if merged.semantic_scholar else None,
        left.year,
        right.year,
    )
    merged.authors = _merge_string_lists(
        merged.authors,
        merged.openalex.authors if merged.openalex else [],
        merged.semantic_scholar.authors if merged.semantic_scholar else [],
    )
    merged.ranking = _merge_ranking(left.ranking, right.ranking)
    return merged


def _merge_openalex(
    left: PaperOpenAlexEnrichment | None,
    right: PaperOpenAlexEnrichment | None,
) -> PaperOpenAlexEnrichment | None:
    if left is None:
        return right.model_copy(deep=True) if right else None
    if right is None:
        return left.model_copy(deep=True)

    primary, secondary = (left, right)
    if _openalex_score(right) > _openalex_score(left):
        primary, secondary = right, left

    data = primary.model_dump()
    for field in (
        "openalex_id",
        "matched_title",
        "title_similarity",
        "search_relevance_score",
        "citation_count",
        "fwci",
        "citation_normalized_percentile",
        "is_in_top_1_percent",
        "is_in_top_10_percent",
        "doi",
        "publication_year",
        "source_display_name",
        "landing_page_url",
        "error",
    ):
        if _is_empty_value(data.get(field)) and not _is_empty_value(getattr(secondary, field)):
            data[field] = getattr(secondary, field)

    data["status"] = _merge_status(left.status, right.status)
    data["authors"] = _merge_string_lists(left.authors, right.authors)
    return PaperOpenAlexEnrichment.model_validate(data)


def _merge_semantic_scholar(
    left: PaperSemanticScholarEnrichment | None,
    right: PaperSemanticScholarEnrichment | None,
) -> PaperSemanticScholarEnrichment | None:
    if left is None:
        return right.model_copy(deep=True) if right else None
    if right is None:
        return left.model_copy(deep=True)

    primary, secondary = (left, right)
    if _semantic_scholar_score(right) > _semantic_scholar_score(left):
        primary, secondary = right, left

    data = primary.model_dump()
    for field in (
        "paper_id",
        "corpus_id",
        "matched_title",
        "title_similarity",
        "match_score",
        "citation_count",
        "influential_citation_count",
        "venue",
        "publication_venue_name",
        "doi",
        "publication_year",
        "url",
        "error",
    ):
        if _is_empty_value(data.get(field)) and not _is_empty_value(getattr(secondary, field)):
            data[field] = getattr(secondary, field)

    data["status"] = _merge_status(left.status, right.status)
    data["authors"] = _merge_string_lists(left.authors, right.authors)
    publication_venue = _merge_publication_venue(
        left.publication_venue,
        right.publication_venue,
    )
    data["publication_venue"] = (
        publication_venue.model_dump() if publication_venue else None
    )
    return PaperSemanticScholarEnrichment.model_validate(data)


def _merge_publication_venue(
    left: SemanticScholarPublicationVenue | None,
    right: SemanticScholarPublicationVenue | None,
) -> SemanticScholarPublicationVenue | None:
    if left is None:
        return right.model_copy(deep=True) if right else None
    if right is None:
        return left.model_copy(deep=True)

    primary, secondary = (left, right)
    if _publication_venue_score(right) > _publication_venue_score(left):
        primary, secondary = right, left

    data = primary.model_dump()
    for field in ("venue_id", "name", "type", "url"):
        if _is_empty_value(data.get(field)) and not _is_empty_value(getattr(secondary, field)):
            data[field] = getattr(secondary, field)
    data["alternate_names"] = _merge_string_lists(
        left.alternate_names,
        right.alternate_names,
    )
    return SemanticScholarPublicationVenue.model_validate(data)


def _merge_ranking(
    left: PaperRanking | None,
    right: PaperRanking | None,
) -> PaperRanking | None:
    if left is None:
        return right.model_copy(deep=True) if right else None
    if right is None:
        return left.model_copy(deep=True)

    primary, secondary = (left, right)
    if _ranking_score(right) > _ranking_score(left):
        primary, secondary = right, left

    data = primary.model_dump()
    if _is_empty_value(data.get("normalized_signals")) and secondary.normalized_signals:
        data["normalized_signals"] = secondary.normalized_signals
    if _is_empty_value(data.get("explanation")) and secondary.explanation:
        data["explanation"] = secondary.explanation
    data["explanation_chips"] = _merge_string_lists(
        left.explanation_chips,
        right.explanation_chips,
    )
    if data.get("rank") is None and secondary.rank is not None:
        data["rank"] = secondary.rank
    return PaperRanking.model_validate(data)


def _openalex_score(value: PaperOpenAlexEnrichment) -> tuple[int, int]:
    return (
        _status_score(value.status),
        _count_non_empty(
            value.openalex_id,
            value.matched_title,
            value.citation_count,
            value.fwci,
            value.doi,
            value.publication_year,
            value.source_display_name,
            value.landing_page_url,
            value.authors,
        ),
    )


def _semantic_scholar_score(value: PaperSemanticScholarEnrichment) -> tuple[int, int]:
    return (
        _status_score(value.status),
        _count_non_empty(
            value.paper_id,
            value.corpus_id,
            value.matched_title,
            value.citation_count,
            value.influential_citation_count,
            value.venue,
            value.publication_venue_name,
            value.doi,
            value.publication_year,
            value.url,
            value.authors,
            value.publication_venue,
        ),
    )


def _publication_venue_score(value: SemanticScholarPublicationVenue) -> tuple[int, int]:
    return (
        1,
        _count_non_empty(
            value.venue_id,
            value.name,
            value.type,
            value.url,
            value.alternate_names,
        ),
    )


def _ranking_score(value: PaperRanking) -> tuple[float, int]:
    return (
        float(value.score or 0.0),
        _count_non_empty(
            value.rank,
            value.normalized_signals,
            value.explanation,
            value.explanation_chips,
        ),
    )


def _status_score(status: str) -> int:
    return {
        "matched": 2,
        "not_found": 1,
        "error": 0,
    }.get(status, -1)


def _merge_status(*statuses: str) -> str:
    for candidate in ("matched", "not_found", "error"):
        if candidate in statuses:
            return candidate
    return "not_found"


def _count_non_empty(*values: Any) -> int:
    return sum(0 if _is_empty_value(value) else 1 for value in values)


def _prefer_text(*values: str | None, prefer_longer: bool = False) -> str:
    best = ""
    for value in values:
        candidate = (value or "").strip()
        if not candidate:
            continue
        if not best:
            best = candidate
            continue
        if prefer_longer and len(candidate) > len(best) + 8:
            best = candidate
    return best


def _prefer_url(left: str | None, right: str | None) -> str:
    left_clean = (left or "").strip()
    right_clean = (right or "").strip()
    if not left_clean:
        return right_clean
    if not right_clean:
        return left_clean

    return left_clean if _url_score(left_clean) >= _url_score(right_clean) else right_clean


def _url_score(value: str) -> tuple[int, int]:
    normalized = _normalize_url(value)
    lowered = normalized.lower()
    return (
        0 if lowered.endswith(".pdf") else 1,
        1 if "?" not in normalized else 0,
        -len(normalized),
    )


def _merge_string_lists(*lists: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for values in lists:
        for value in values:
            candidate = (value or "").strip()
            if not candidate:
                continue
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
    return merged


def _unique_non_empty(values: list[str | None]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = (value or "").strip()
        if not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        candidate = (value or "").strip()
        if candidate:
            return candidate
    return None


def _first_non_none(*values: int | None) -> int | None:
    for value in values:
        if value is not None:
            return value
    return None


def _normalize_title(value: str | None) -> str:
    lowered = (value or "").lower().strip()
    normalized = _TITLE_TOKEN_RE.sub(" ", lowered)
    return " ".join(normalized.split())


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    normalized = normalized.removeprefix("https://doi.org/")
    normalized = normalized.removeprefix("http://doi.org/")
    normalized = normalized.removeprefix("https://dx.doi.org/")
    normalized = normalized.removeprefix("http://dx.doi.org/")
    normalized = normalized.removeprefix("doi:")
    normalized = normalized.strip()
    return normalized.lower() or None


def _normalize_url(value: str | None) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""

    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return candidate.lower().rstrip("/")

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = re.sub(r"/{2,}", "/", parsed.path or "").rstrip("/")
    filtered_query_pairs = [
        (key, query_value)
        for key, query_value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _should_drop_query_param(key)
    ]
    query = urlencode(sorted(filtered_query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def _should_drop_query_param(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith(_TRACKING_QUERY_PREFIXES) or lowered in _TRACKING_QUERY_NAMES


def _is_strong_title(value: str) -> bool:
    return len(value.split()) >= 5 or len(value) >= 30


def _coerce_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False
