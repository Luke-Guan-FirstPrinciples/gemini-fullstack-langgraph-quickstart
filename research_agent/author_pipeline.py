"""OpenAlex-backed author enrichment and ranking for the research agent."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote_plus

import httpx

from research_agent.config import Settings
from research_agent.models import (
    Author,
    AuthorOpenAlexEnrichment,
    AuthorRanking,
    Paper,
    ResearchOutput,
)

logger = logging.getLogger("research_agent.author_pipeline")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_AUTHOR_SOURCE_PAPER_LIMIT = 20
_AUTHOR_RANKING_WEIGHTS = {
    "query_topic_overlap": 0.4,
    "paper_support": 0.35,
    "citation_count": 0.25,
}


async def build_ranked_authors(
    query: str,
    output: ResearchOutput,
    ranked_papers: list[Paper],
    cfg: Settings,
) -> tuple[list[Author], dict[str, float], dict[str, str]]:
    """Build, enrich, and rank author candidates from the paper results."""
    paper_pool = (ranked_papers or output.papers)[:_AUTHOR_SOURCE_PAPER_LIMIT]
    candidates, paper_support = _build_author_candidates(output, paper_pool)
    if not candidates:
        return [], _normalize_weights(_AUTHOR_RANKING_WEIGHTS), _normalization_meta()

    enriched_authors = await _enrich_authors(query, candidates, cfg)
    ranked_authors = _rank_authors(query, enriched_authors, paper_support)
    return ranked_authors, _normalize_weights(_AUTHOR_RANKING_WEIGHTS), _normalization_meta()


def _build_author_candidates(
    output: ResearchOutput,
    ranked_papers: list[Paper],
) -> tuple[list[Author], dict[str, float]]:
    by_key: dict[str, Author] = {}
    paper_support: dict[str, float] = defaultdict(float)

    def _get_or_create(author_name: str) -> Author | None:
        key = _normalize_name(author_name)
        if not key:
            return None

        author = by_key.get(key)
        if author is None:
            author = Author(name=author_name.strip())
            by_key[key] = author
        return author

    for author in output.authors:
        candidate = _get_or_create(author.name)
        if candidate is None:
            continue
        candidate.affiliations = _merge_unique_strings(
            candidate.affiliations,
            author.affiliations,
        )
        candidate.research_areas = _merge_unique_strings(
            candidate.research_areas,
            author.research_areas,
        )

    for paper in ranked_papers:
        paper_score = float(paper.ranking.score or 0.0) if paper.ranking else 0.0
        for author_name in paper.authors:
            candidate = _get_or_create(author_name)
            if candidate is None:
                continue
            key = _normalize_name(candidate.name)
            candidate.matched_paper_count += 1
            candidate.matched_paper_titles = _merge_unique_strings(
                candidate.matched_paper_titles,
                [paper.title],
            )
            paper_support[key] += paper_score

    candidates = sorted(
        by_key.values(),
        key=lambda author: (-author.matched_paper_count, author.name.lower()),
    )
    return candidates, dict(paper_support)


async def _enrich_authors(
    query: str,
    authors: list[Author],
    cfg: Settings,
) -> list[Author]:
    if not authors:
        return []

    query_tokens = set(_TOKEN_RE.findall(query.lower()))
    semaphore = asyncio.Semaphore(max(1, cfg.openalex_parallelism))
    lookup_to_enrichment: dict[str, AuthorOpenAlexEnrichment] = {}

    async with httpx.AsyncClient(
        base_url=cfg.openalex_base_url.rstrip("/"),
        timeout=cfg.openalex_timeout_seconds,
        headers={"User-Agent": "research-agent/0.1"},
    ) as client:

        async def _fetch_one(author: Author) -> None:
            key = _normalize_name(author.name)
            async with semaphore:
                lookup_to_enrichment[key] = await _fetch_author_enrichment(
                    client,
                    author,
                    query_tokens,
                    cfg,
                )

        await asyncio.gather(*[_fetch_one(author) for author in authors])

    enriched: list[Author] = []
    for author in authors:
        enrichment = lookup_to_enrichment.get(_normalize_name(author.name))
        if enrichment is None:
            enriched.append(author.model_copy(deep=True))
            continue
        enriched.append(_apply_author_enrichment(author, enrichment))

    matched_count = sum(
        1 for author in enriched if author.openalex and author.openalex.status == "matched"
    )
    logger.info("OpenAlex enrichment matched %d/%d author candidates", matched_count, len(enriched))
    return enriched


async def _fetch_author_enrichment(
    client: httpx.AsyncClient,
    candidate: Author,
    query_tokens: set[str],
    cfg: Settings,
) -> AuthorOpenAlexEnrichment:
    if not candidate.name.strip():
        return AuthorOpenAlexEnrichment(status="not_found")

    params = {
        **_openalex_request_params(cfg),
        "search": f'"{candidate.name}"',
        "per-page": str(max(1, cfg.openalex_author_search_limit)),
    }

    try:
        response = await client.get("/authors", params=params)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.exception("OpenAlex author lookup failed for %s", candidate.name)
        return AuthorOpenAlexEnrichment(status="error", error=str(exc))

    results = payload.get("results", [])
    if not isinstance(results, list) or not results:
        return AuthorOpenAlexEnrichment(status="not_found")

    best_author: dict[str, Any] | None = None
    best_name_similarity = 0.0
    best_score = 0.0

    for author in results:
        if not isinstance(author, dict):
            continue

        name_similarity = _author_name_similarity(candidate.name, author)
        topic_overlap = _topic_overlap_score(
            query_tokens,
            candidate.research_areas,
            _extract_topic_names(author),
        )
        affiliation_overlap = _affiliation_overlap_score(
            candidate.affiliations,
            _extract_affiliations(author),
        )
        search_relevance = _clamp_score(_coerce_float(author.get("relevance_score")) or 0.0)
        exact_bonus = 0.15 if _has_exact_name_match(candidate.name, author) else 0.0
        match_score = min(
            1.0,
            (0.55 * name_similarity)
            + (0.2 * topic_overlap)
            + (0.15 * affiliation_overlap)
            + (0.1 * search_relevance)
            + exact_bonus,
        )

        if match_score > best_score:
            best_author = author
            best_name_similarity = name_similarity
            best_score = match_score

    if not best_author or best_name_similarity < 0.84 or best_score < 0.7:
        return AuthorOpenAlexEnrichment(status="not_found")

    return _build_author_enrichment(best_author, candidate.name, best_name_similarity)


def _apply_author_enrichment(
    author: Author,
    enrichment: AuthorOpenAlexEnrichment,
) -> Author:
    enriched = author.model_copy(deep=True)
    enriched.openalex = enrichment

    if enrichment.status == "matched":
        if enrichment.affiliations:
            enriched.affiliations = _merge_unique_strings(
                enriched.affiliations,
                enrichment.affiliations,
            )
        if enrichment.topics:
            enriched.research_areas = _merge_unique_strings(
                enriched.research_areas,
                enrichment.topics,
            )

    return enriched


def _rank_authors(
    query: str,
    authors: list[Author],
    paper_support: dict[str, float],
) -> list[Author]:
    if not authors:
        return []

    weights = _normalize_weights(_AUTHOR_RANKING_WEIGHTS)
    query_tokens = set(_TOKEN_RE.findall(query.lower()))
    support_scale = max((paper_support.get(_normalize_name(author.name), 0.0) for author in authors), default=0.0)
    citation_scale = _max_log_signal(
        [
            float(author.openalex.citation_count or 0)
            for author in authors
            if author.openalex and author.openalex.citation_count is not None
        ]
    )

    ranked_authors: list[Author] = []
    for author in authors:
        author_copy = author.model_copy(deep=True)
        support_value = paper_support.get(_normalize_name(author.name), 0.0)
        citation_count = float(author.openalex.citation_count or 0) if author.openalex else 0.0
        topic_overlap = _topic_overlap_score(
            query_tokens,
            author_copy.research_areas,
            author_copy.openalex.topics if author_copy.openalex else [],
        )
        normalized_signals = {
            "query_topic_overlap": round(_clamp_score(topic_overlap), 6),
            "paper_support": round(
                _clamp_score(support_value / support_scale) if support_scale > 0 else 0.0,
                6,
            ),
            "citation_count": round(_normalize_log_signal(citation_count, citation_scale), 6),
        }
        explanation_chips = _build_author_explanation_chips(author_copy, normalized_signals)
        author_copy.ranking = AuthorRanking(
            score=round(_weighted_score(normalized_signals, weights), 6),
            normalized_signals=normalized_signals,
            explanation=_build_explanation(explanation_chips),
            explanation_chips=explanation_chips,
        )
        ranked_authors.append(author_copy)

    ranked_authors.sort(
        key=lambda author: (
            -(author.ranking.score if author.ranking else 0.0),
            -author.matched_paper_count,
            -(author.openalex.citation_count or 0) if author.openalex else 0,
            author.name.lower(),
        )
    )

    for index, author in enumerate(ranked_authors, start=1):
        if author.ranking:
            author.ranking.rank = index

    logger.info("Ranked %d authors", len(ranked_authors))
    return ranked_authors


def _build_author_enrichment(
    author: dict[str, Any],
    candidate_name: str,
    name_similarity: float,
) -> AuthorOpenAlexEnrichment:
    display_name = _coerce_str(author.get("display_name"))
    ids = author.get("ids")
    ids_map = ids if isinstance(ids, dict) else {}
    personal_website_url = _first_non_empty(
        _coerce_str(author.get("homepage_url")),
        _coerce_str(ids_map.get("homepage")),
        _coerce_str(ids_map.get("website")),
        _coerce_str(ids_map.get("personal_website")),
    )
    personal_blog_url = _first_non_empty(
        _coerce_str(ids_map.get("blog")),
        _coerce_str(ids_map.get("substack")),
        _coerce_str(ids_map.get("medium")),
    )
    google_scholar_url = _first_non_empty(
        _coerce_str(ids_map.get("google_scholar")),
        _coerce_str(ids_map.get("googlescholar")),
        _coerce_str(ids_map.get("google-scholar")),
    )
    if not google_scholar_url and display_name:
        google_scholar_url = (
            f"https://scholar.google.com/scholar?q={quote_plus(display_name)}"
        )

    semantic_scholar_id = _extract_semantic_scholar_id(ids_map)
    social_media_url = _first_non_empty(
        _coerce_str(ids_map.get("twitter")),
        _coerce_str(ids_map.get("x")),
        _coerce_str(ids_map.get("mastodon")),
        _coerce_str(ids_map.get("linkedin")),
        _coerce_str(ids_map.get("bluesky")),
    )

    return AuthorOpenAlexEnrichment(
        status="matched",
        openalex_id=_coerce_str(author.get("id")),
        matched_name=display_name or candidate_name,
        name_similarity=name_similarity,
        search_relevance_score=_coerce_float(author.get("relevance_score")),
        citation_count=_coerce_int(author.get("cited_by_count")),
        works_count=_coerce_int(author.get("works_count")),
        orcid=_normalize_orcid(
            _coerce_str(author.get("orcid")) or _coerce_str(ids_map.get("orcid"))
        ),
        affiliations=_extract_affiliations(author),
        topics=_extract_topic_names(author),
        personal_website_url=personal_website_url,
        personal_blog_url=personal_blog_url,
        google_scholar_url=google_scholar_url,
        social_media_url=social_media_url,
        semantic_scholar_id=semantic_scholar_id,
    )


def _extract_affiliations(author: dict[str, Any]) -> list[str]:
    institutions: list[str] = []
    for key in ("last_known_institutions", "affiliations"):
        records = author.get(key, [])
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            display_name = _coerce_str(record.get("display_name"))
            country_code = _coerce_str(record.get("country_code"))
            label = " ".join(part for part in [display_name, country_code] if part)
            if label:
                institutions.append(label)
    return _merge_unique_strings([], institutions)


def _extract_topic_names(author: dict[str, Any]) -> list[str]:
    topics: list[str] = []
    topics_data = author.get("topics", [])
    if not isinstance(topics_data, list):
        return topics

    for topic in topics_data[:5]:
        if not isinstance(topic, dict):
            continue
        display_name = _coerce_str(topic.get("display_name"))
        if display_name:
            topics.append(display_name)
    return _merge_unique_strings([], topics)


def _author_name_similarity(candidate_name: str, author: dict[str, Any]) -> float:
    names = [
        _coerce_str(author.get("display_name")),
        _coerce_str(author.get("full_name")),
    ]
    alternatives = author.get("display_name_alternatives", [])
    if isinstance(alternatives, list):
        names.extend(_coerce_str(value) for value in alternatives)

    normalized_candidate = _normalize_name(candidate_name)
    best = 0.0
    for name in names:
        if not name:
            continue
        best = max(
            best,
            SequenceMatcher(None, normalized_candidate, _normalize_name(name)).ratio(),
        )
    return best


def _has_exact_name_match(candidate_name: str, author: dict[str, Any]) -> bool:
    normalized_candidate = _normalize_name(candidate_name)
    names = [
        _coerce_str(author.get("display_name")),
        _coerce_str(author.get("full_name")),
    ]
    alternatives = author.get("display_name_alternatives", [])
    if isinstance(alternatives, list):
        names.extend(_coerce_str(value) for value in alternatives)
    return any(_normalize_name(name or "") == normalized_candidate for name in names if name)


def _topic_overlap_score(
    query_tokens: set[str],
    research_areas: list[str],
    openalex_topics: list[str],
) -> float:
    if not query_tokens:
        return 0.0

    topic_tokens = set(
        _TOKEN_RE.findall(" ".join([*research_areas, *openalex_topics]).lower())
    )
    if not topic_tokens:
        return 0.0

    return len(query_tokens & topic_tokens) / len(query_tokens)


def _affiliation_overlap_score(
    current_affiliations: list[str],
    openalex_affiliations: list[str],
) -> float:
    if not current_affiliations or not openalex_affiliations:
        return 0.0

    current_tokens = set(_TOKEN_RE.findall(" ".join(current_affiliations).lower()))
    openalex_tokens = set(_TOKEN_RE.findall(" ".join(openalex_affiliations).lower()))
    if not current_tokens or not openalex_tokens:
        return 0.0

    return len(current_tokens & openalex_tokens) / len(current_tokens)


def _build_author_explanation_chips(
    author: Author,
    normalized_signals: dict[str, float],
) -> list[str]:
    chips: list[str] = []
    topic_overlap = normalized_signals.get("query_topic_overlap", 0.0)
    paper_support = normalized_signals.get("paper_support", 0.0)
    citation_signal = normalized_signals.get("citation_count", 0.0)

    if topic_overlap >= 0.75:
        chips.append("Strong topic match")
    elif topic_overlap >= 0.5:
        chips.append("Relevant research focus")

    if author.matched_paper_count >= 3:
        chips.append(f"Appears across {author.matched_paper_count} top papers")
    elif paper_support >= 0.45:
        chips.append("Supported by top-ranked papers")

    if citation_signal >= 0.72:
        chips.append("Highly cited author")
    elif author.openalex and (author.openalex.citation_count or 0) > 0:
        chips.append("Meaningful citation footprint")

    if not chips:
        chips.append("Author surfaced from this result set")

    deduped: list[str] = []
    seen: set[str] = set()
    for chip in chips:
        if chip in seen:
            continue
        seen.add(chip)
        deduped.append(chip)
        if len(deduped) == 3:
            break
    return deduped


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {name: max(float(value), 0.0) for name, value in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return {
            "query_topic_overlap": 1.0,
            "paper_support": 0.0,
            "citation_count": 0.0,
        }
    return {name: round(value / total, 6) for name, value in cleaned.items()}


def _weighted_score(signals: dict[str, float], weights: dict[str, float]) -> float:
    return sum(weights.get(name, 0.0) * signals.get(name, 0.0) for name in weights)


def _max_log_signal(values: list[float]) -> float:
    if not values:
        return 0.0
    return max(math.log1p(max(value, 0.0)) for value in values)


def _normalize_log_signal(value: float, scale: float) -> float:
    if value <= 0 or scale <= 0:
        return 0.0
    return _clamp_score(math.log1p(value) / scale)


def _build_explanation(chips: list[str]) -> str:
    if not chips:
        return ""
    if len(chips) == 1:
        return chips[0]

    tail = [f"{chip[:1].lower()}{chip[1:]}" if chip else chip for chip in chips[1:]]
    return ", ".join([chips[0], *tail])


def _normalization_meta() -> dict[str, str]:
    return {
        "query_topic_overlap": "token overlap between the query and author topics/research areas",
        "paper_support": "sum of supporting paper ranking scores scaled by the max author support in run",
        "citation_count": "log1p(citation_count) scaled by max author citation count in run",
    }


def _openalex_request_params(cfg: Settings) -> dict[str, str]:
    params: dict[str, str] = {}
    if cfg.openalex_api_key:
        params["api_key"] = cfg.openalex_api_key
    if cfg.openalex_email:
        params["mailto"] = cfg.openalex_email
    return params


def _extract_semantic_scholar_id(ids_map: dict[str, Any]) -> str | None:
    for key in (
        "semantic_scholar",
        "semantic-scholar",
        "semanticscholar",
        "semanticScholar",
    ):
        value = _coerce_str(ids_map.get(key))
        if not value:
            continue
        if "/" in value:
            return value.rstrip("/").split("/")[-1] or value
        return value
    return None


def _normalize_orcid(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").split("/")[-1] or None


def _merge_unique_strings(existing: list[str], new_values: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*existing, *new_values]:
        text = (value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return merged


def _normalize_name(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.lower()))


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        text = _coerce_str(value)
        if text:
            return text
    return None


def _clamp_score(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
