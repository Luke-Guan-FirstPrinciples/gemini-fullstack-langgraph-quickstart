"""OpenAlex enrichment helpers for research-agent papers."""

from __future__ import annotations

import asyncio
import logging
import re
from difflib import SequenceMatcher
from typing import Any

import httpx

from research_agent.config import Settings
from research_agent.models import Paper, PaperOpenAlexEnrichment

logger = logging.getLogger("research_agent.enrichment")

_TITLE_TOKEN_RE = re.compile(r"[^a-z0-9]+")


class OpenAlexEnricher:
    """Enrich papers with OpenAlex metadata looked up by title."""

    def __init__(self, cfg: Settings) -> None:
        self._cfg = cfg

    async def enrich_papers(self, papers: list[Paper]) -> list[Paper]:
        """Resolve OpenAlex metadata for each unique paper title."""
        if not papers:
            return []

        unique_titles: dict[str, str] = {}
        for paper in papers:
            normalized = _normalize_title(paper.title)
            if normalized and normalized not in unique_titles:
                unique_titles[normalized] = paper.title

        title_to_enrichment: dict[str, PaperOpenAlexEnrichment] = {}
        semaphore = asyncio.Semaphore(max(1, self._cfg.openalex_parallelism))

        async with httpx.AsyncClient(
            base_url=self._cfg.openalex_base_url.rstrip("/"),
            timeout=self._cfg.openalex_timeout_seconds,
            headers={"User-Agent": "research-agent/0.1"},
        ) as client:

            async def _fetch_one(normalized_title: str, title: str) -> None:
                async with semaphore:
                    title_to_enrichment[normalized_title] = await self._fetch_enrichment(
                        client,
                        title,
                    )

            await asyncio.gather(
                *[
                    _fetch_one(normalized_title, title)
                    for normalized_title, title in unique_titles.items()
                ]
            )

        enriched_papers: list[Paper] = []
        for paper in papers:
            normalized = _normalize_title(paper.title)
            enrichment = title_to_enrichment.get(normalized) or PaperOpenAlexEnrichment()
            enriched_papers.append(_apply_enrichment(paper, enrichment))

        matched_count = sum(
            1 for paper in enriched_papers if paper.openalex and paper.openalex.status == "matched"
        )
        logger.info(
            "OpenAlex enrichment matched %d/%d papers",
            matched_count,
            len(enriched_papers),
        )
        return enriched_papers

    async def _fetch_enrichment(
        self,
        client: httpx.AsyncClient,
        title: str,
    ) -> PaperOpenAlexEnrichment:
        if not title.strip():
            return PaperOpenAlexEnrichment(status="not_found")

        params = {
            "search": f'"{title}"',
            "per-page": str(max(1, self._cfg.openalex_title_search_limit)),
        }
        if self._cfg.openalex_api_key:
            params["api_key"] = self._cfg.openalex_api_key
        if self._cfg.openalex_email:
            params["mailto"] = self._cfg.openalex_email

        try:
            response = await client.get("/works", params=params)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.exception("OpenAlex lookup failed for title: %s", title)
            return PaperOpenAlexEnrichment(status="error", error=str(exc))

        works = payload.get("results", [])
        if not isinstance(works, list) or not works:
            return PaperOpenAlexEnrichment(status="not_found")

        best_work: dict[str, Any] | None = None
        best_title_similarity = 0.0
        best_match_score = 0.0

        for work in works:
            if not isinstance(work, dict):
                continue
            candidate_title = str(work.get("display_name") or "")
            title_similarity = _title_similarity(title, candidate_title)
            search_relevance = _coerce_float(work.get("relevance_score")) or 0.0
            exact_bonus = 0.2 if _normalize_title(title) == _normalize_title(candidate_title) else 0.0
            match_score = min(1.0, (0.7 * title_similarity) + (0.15 * search_relevance) + exact_bonus)
            if match_score > best_match_score:
                best_work = work
                best_title_similarity = title_similarity
                best_match_score = match_score

        if not best_work or best_title_similarity < self._cfg.openalex_min_title_similarity:
            return PaperOpenAlexEnrichment(status="not_found")

        return _build_enrichment(best_work, best_title_similarity)


def _apply_enrichment(paper: Paper, enrichment: PaperOpenAlexEnrichment) -> Paper:
    enriched = paper.model_copy(deep=True)
    enriched.openalex = enrichment

    if enrichment.status == "matched":
        if enrichment.authors:
            enriched.authors = enrichment.authors
        if enriched.year is None and enrichment.publication_year is not None:
            enriched.year = enrichment.publication_year
        if not enriched.doi and enrichment.doi:
            enriched.doi = enrichment.doi

    return enriched


def _build_enrichment(work: dict[str, Any], title_similarity: float) -> PaperOpenAlexEnrichment:
    authors: list[str] = []
    authorships = work.get("authorships", [])
    if isinstance(authorships, list):
        for authorship in authorships:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author")
            if not isinstance(author, dict):
                continue
            display_name = author.get("display_name")
            if isinstance(display_name, str) and display_name:
                authors.append(display_name)

    source_display_name = None
    landing_page_url = None
    primary_location = work.get("primary_location")
    if isinstance(primary_location, dict):
        landing_page_url = _coerce_str(primary_location.get("landing_page_url"))
        source = primary_location.get("source")
        if isinstance(source, dict):
            source_display_name = _coerce_str(source.get("display_name"))

    citation_percentile = work.get("citation_normalized_percentile")
    percentile_value = None
    is_in_top_1_percent = None
    is_in_top_10_percent = None
    if isinstance(citation_percentile, dict):
        percentile_value = _coerce_float(citation_percentile.get("value"))
        is_in_top_1_percent = _coerce_bool(citation_percentile.get("is_in_top_1_percent"))
        is_in_top_10_percent = _coerce_bool(citation_percentile.get("is_in_top_10_percent"))
    else:
        percentile_value = _coerce_float(citation_percentile)

    return PaperOpenAlexEnrichment(
        status="matched",
        openalex_id=_coerce_str(work.get("id")),
        matched_title=_coerce_str(work.get("display_name")),
        title_similarity=title_similarity,
        search_relevance_score=_coerce_float(work.get("relevance_score")),
        citation_count=_coerce_int(work.get("cited_by_count")),
        fwci=_coerce_float(work.get("fwci")),
        citation_normalized_percentile=percentile_value,
        is_in_top_1_percent=is_in_top_1_percent,
        is_in_top_10_percent=is_in_top_10_percent,
        authors=authors,
        doi=_normalize_doi(_coerce_str(work.get("doi"))),
        publication_year=_coerce_int(work.get("publication_year")),
        source_display_name=source_display_name,
        landing_page_url=landing_page_url,
    )


def _normalize_title(value: str) -> str:
    lowered = value.lower().strip()
    normalized = _TITLE_TOKEN_RE.sub(" ", lowered)
    return " ".join(normalized.split())


def _title_similarity(left: str, right: str) -> float:
    normalized_left = _normalize_title(left)
    normalized_right = _normalize_title(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    return value.removeprefix("https://doi.org/")


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


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
