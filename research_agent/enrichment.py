"""Academic metadata enrichment helpers for research-agent papers."""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx

from research_agent.config import Settings
from research_agent.models import (
    Paper,
    PaperOpenAlexEnrichment,
    PaperSemanticScholarEnrichment,
    SemanticScholarPublicationVenue,
)

logger = logging.getLogger("research_agent.enrichment")

_TITLE_TOKEN_RE = re.compile(r"[^a-z0-9]+")


class _AsyncRateLimiter:
    """Simple async minimum-interval limiter shared across concurrent tasks.

    Ensures that at most one request passes through every ``min_interval``
    seconds, regardless of how many coroutines call :meth:`acquire`.
    """

    def __init__(self, requests_per_second: float) -> None:
        rps = max(float(requests_per_second), 0.0)
        self._min_interval = (1.0 / rps) if rps > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next_allowed_monotonic = 0.0

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait_for = self._next_allowed_monotonic - now
            if wait_for > 0:
                await asyncio.sleep(wait_for)
                now = time.monotonic()
            self._next_allowed_monotonic = now + self._min_interval

    async def delay_until(self, seconds_from_now: float) -> None:
        """Push the next-allowed slot at least ``seconds_from_now`` into the future."""
        if seconds_from_now <= 0:
            return
        async with self._lock:
            candidate = time.monotonic() + seconds_from_now
            if candidate > self._next_allowed_monotonic:
                self._next_allowed_monotonic = candidate


class OpenAlexEnricher:
    """Enrich papers with OpenAlex metadata, preferring DOI over title search."""

    def __init__(self, cfg: Settings) -> None:
        self._cfg = cfg

    async def enrich_papers(self, papers: list[Paper]) -> list[Paper]:
        """Resolve OpenAlex metadata for each unique DOI or title."""
        if not papers:
            return []

        unique_lookups: dict[str, tuple[str, str | None]] = {}
        for paper in papers:
            lookup_key = _lookup_key_for_paper(paper)
            if not lookup_key or lookup_key in unique_lookups:
                continue
            unique_lookups[lookup_key] = (paper.title, _normalize_doi(paper.doi))

        lookup_to_enrichment: dict[str, PaperOpenAlexEnrichment] = {}
        semaphore = asyncio.Semaphore(max(1, self._cfg.openalex_parallelism))

        async with httpx.AsyncClient(
            base_url=self._cfg.openalex_base_url.rstrip("/"),
            timeout=self._cfg.openalex_timeout_seconds,
            headers={"User-Agent": "research-agent/0.1"},
        ) as client:

            async def _fetch_one(lookup_key: str, title: str, doi: str | None) -> None:
                async with semaphore:
                    lookup_to_enrichment[lookup_key] = await self._fetch_enrichment(
                        client,
                        title,
                        doi=doi,
                    )

            await asyncio.gather(
                *[
                    _fetch_one(lookup_key, title, doi)
                    for lookup_key, (title, doi) in unique_lookups.items()
                ]
            )

        enriched_papers: list[Paper] = []
        for paper in papers:
            lookup_key = _lookup_key_for_paper(paper)
            enrichment = lookup_to_enrichment.get(lookup_key or "") or PaperOpenAlexEnrichment()
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
        doi: str | None = None,
    ) -> PaperOpenAlexEnrichment:
        normalized_doi = _normalize_doi(doi)
        doi_error: str | None = None
        if normalized_doi:
            doi_enrichment = await self._fetch_by_doi(client, normalized_doi)
            if doi_enrichment.status == "matched":
                return doi_enrichment
            if doi_enrichment.status == "error":
                doi_error = doi_enrichment.error

        if not title.strip():
            if doi_error:
                return PaperOpenAlexEnrichment(status="error", error=doi_error)
            return PaperOpenAlexEnrichment(status="not_found")

        title_enrichment = await self._fetch_by_title(client, title)
        if title_enrichment.status == "matched":
            return title_enrichment
        if title_enrichment.status == "error":
            return title_enrichment
        if doi_error:
            return PaperOpenAlexEnrichment(status="error", error=doi_error)
        return title_enrichment

    async def _fetch_by_doi(
        self,
        client: httpx.AsyncClient,
        doi: str,
    ) -> PaperOpenAlexEnrichment:
        request_params = _openalex_request_params(self._cfg)
        errors: list[str] = []
        for doi_filter in _doi_filters(doi):
            params = {
                **request_params,
                "filter": doi_filter,
                "per-page": "1",
            }
            try:
                response = await client.get("/works", params=params)
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                logger.exception("OpenAlex DOI lookup failed for doi: %s", doi)
                errors.append(str(exc))
                continue

            works = payload.get("results", [])
            if isinstance(works, list) and works:
                first_work = works[0]
                if isinstance(first_work, dict):
                    return _build_enrichment(first_work, title_similarity=1.0)

        if errors:
            return PaperOpenAlexEnrichment(status="error", error=errors[0])
        return PaperOpenAlexEnrichment(status="not_found")

    async def _fetch_by_title(
        self,
        client: httpx.AsyncClient,
        title: str,
    ) -> PaperOpenAlexEnrichment:
        if not title.strip():
            return PaperOpenAlexEnrichment(status="not_found")

        params = {
            **_openalex_request_params(self._cfg),
            "search": f'"{title}"',
            "per-page": str(max(1, self._cfg.openalex_title_search_limit)),
        }

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


class SemanticScholarEnricher:
    """Enrich papers with Semantic Scholar metadata, preferring DOI over title search."""

    def __init__(self, cfg: Settings) -> None:
        self._cfg = cfg
        self._rate_limiter = _AsyncRateLimiter(cfg.semantic_scholar_requests_per_second)

    async def enrich_papers(self, papers: list[Paper]) -> list[Paper]:
        """Resolve Semantic Scholar metadata for each unique DOI or title."""
        if not papers:
            return []

        unique_lookups: dict[str, tuple[str, str | None]] = {}
        for paper in papers:
            lookup_key = _lookup_key_for_paper(paper)
            if not lookup_key or lookup_key in unique_lookups:
                continue
            unique_lookups[lookup_key] = (paper.title, _normalize_doi(paper.doi))

        lookup_to_enrichment: dict[str, PaperSemanticScholarEnrichment] = {}
        semaphore = asyncio.Semaphore(max(1, self._cfg.semantic_scholar_parallelism))

        async with httpx.AsyncClient(
            base_url=self._cfg.semantic_scholar_base_url.rstrip("/"),
            timeout=self._cfg.semantic_scholar_timeout_seconds,
            headers={"User-Agent": "research-agent/0.1"},
        ) as client:

            async def _fetch_one(lookup_key: str, title: str, doi: str | None) -> None:
                async with semaphore:
                    lookup_to_enrichment[lookup_key] = await self._fetch_enrichment(
                        client,
                        title,
                        doi=doi,
                    )

            await asyncio.gather(
                *[
                    _fetch_one(lookup_key, title, doi)
                    for lookup_key, (title, doi) in unique_lookups.items()
                ]
            )

        enriched_papers: list[Paper] = []
        for paper in papers:
            lookup_key = _lookup_key_for_paper(paper)
            enrichment = (
                lookup_to_enrichment.get(lookup_key or "")
                or PaperSemanticScholarEnrichment()
            )
            enriched_papers.append(_apply_semantic_scholar_enrichment(paper, enrichment))

        matched_count = sum(
            1
            for paper in enriched_papers
            if paper.semantic_scholar and paper.semantic_scholar.status == "matched"
        )
        logger.info(
            "Semantic Scholar enrichment matched %d/%d papers",
            matched_count,
            len(enriched_papers),
        )
        return enriched_papers

    async def _fetch_enrichment(
        self,
        client: httpx.AsyncClient,
        title: str,
        doi: str | None = None,
    ) -> PaperSemanticScholarEnrichment:
        normalized_doi = _normalize_doi(doi)
        doi_error: str | None = None
        if normalized_doi:
            doi_enrichment = await self._fetch_by_identifier(client, f"DOI:{normalized_doi}")
            if doi_enrichment.status == "matched":
                return doi_enrichment
            if doi_enrichment.status == "error":
                doi_error = doi_enrichment.error

        if not title.strip():
            if doi_error:
                return PaperSemanticScholarEnrichment(status="error", error=doi_error)
            return PaperSemanticScholarEnrichment(status="not_found")

        title_enrichment = await self._fetch_by_title(client, title)
        if title_enrichment.status == "matched":
            return title_enrichment
        if title_enrichment.status == "error":
            return title_enrichment
        if doi_error:
            return PaperSemanticScholarEnrichment(status="error", error=doi_error)
        return title_enrichment

    async def _fetch_by_identifier(
        self,
        client: httpx.AsyncClient,
        identifier: str,
    ) -> PaperSemanticScholarEnrichment:
        try:
            payload = await self._request(
                client,
                f"paper/{quote(identifier, safe=':')}",
                params={"fields": _semantic_scholar_request_fields()},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return PaperSemanticScholarEnrichment(status="not_found")
            logger.exception("Semantic Scholar identifier lookup failed for %s", identifier)
            return PaperSemanticScholarEnrichment(status="error", error=str(exc))
        except Exception as exc:
            logger.exception("Semantic Scholar identifier lookup failed for %s", identifier)
            return PaperSemanticScholarEnrichment(status="error", error=str(exc))

        return _build_semantic_scholar_enrichment(payload, title_similarity=1.0)

    async def _fetch_by_title(
        self,
        client: httpx.AsyncClient,
        title: str,
    ) -> PaperSemanticScholarEnrichment:
        if not title.strip():
            return PaperSemanticScholarEnrichment(status="not_found")

        try:
            payload = await self._request(
                client,
                "paper/search/match",
                params={
                    "query": title,
                    "fields": _semantic_scholar_request_fields(),
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return PaperSemanticScholarEnrichment(status="not_found")
            logger.exception("Semantic Scholar title lookup failed for %s", title)
            return PaperSemanticScholarEnrichment(status="error", error=str(exc))
        except Exception as exc:
            logger.exception("Semantic Scholar title lookup failed for %s", title)
            return PaperSemanticScholarEnrichment(status="error", error=str(exc))

        matches = payload.get("data", [])
        if not isinstance(matches, list) or not matches:
            return PaperSemanticScholarEnrichment(status="not_found")

        best_match = matches[0]
        if not isinstance(best_match, dict):
            return PaperSemanticScholarEnrichment(status="not_found")

        candidate_title = _coerce_str(best_match.get("title")) or ""
        title_similarity = _title_similarity(title, candidate_title)
        if title_similarity < self._cfg.semantic_scholar_min_title_similarity:
            return PaperSemanticScholarEnrichment(status="not_found")

        return _build_semantic_scholar_enrichment(
            best_match,
            title_similarity=title_similarity,
        )

    async def _request(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: dict[str, str],
    ) -> dict[str, Any]:
        headers = _semantic_scholar_headers(self._cfg)
        max_retries = max(0, self._cfg.semantic_scholar_max_retries)
        initial_backoff = max(0.1, self._cfg.semantic_scholar_initial_backoff_seconds)
        max_backoff = max(initial_backoff, self._cfg.semantic_scholar_max_backoff_seconds)

        attempt = 0
        while True:
            await self._rate_limiter.acquire()
            try:
                response = await client.get(path, params=params, headers=headers)
            except httpx.TransportError as exc:
                if attempt >= max_retries:
                    raise
                backoff = _compute_backoff(attempt, initial_backoff, max_backoff)
                logger.warning(
                    "Semantic Scholar transport error for %s (attempt %d/%d): %s; "
                    "retrying in %.2fs",
                    path,
                    attempt + 1,
                    max_retries,
                    exc,
                    backoff,
                )
                await self._rate_limiter.delay_until(backoff)
                attempt += 1
                continue

            # Fall back to anonymous request when the configured key is rejected.
            if response.status_code == 403 and headers:
                await self._rate_limiter.acquire()
                response = await client.get(path, params=params)

            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= max_retries:
                    response.raise_for_status()
                retry_after = _retry_after_seconds(response)
                backoff = retry_after if retry_after is not None else _compute_backoff(
                    attempt, initial_backoff, max_backoff
                )
                logger.warning(
                    "Semantic Scholar %d for %s (attempt %d/%d); backing off %.2fs",
                    response.status_code,
                    path,
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                await self._rate_limiter.delay_until(backoff)
                attempt += 1
                continue

            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}


def _lookup_key_for_paper(paper: Paper) -> str | None:
    normalized_doi = _normalize_doi(paper.doi)
    if normalized_doi:
        return f"doi:{normalized_doi}"

    normalized_title = _normalize_title(paper.title)
    if normalized_title:
        return f"title:{normalized_title}"

    return None


def _openalex_request_params(cfg: Settings) -> dict[str, str]:
    params: dict[str, str] = {}
    if cfg.openalex_api_key:
        params["api_key"] = cfg.openalex_api_key
    if cfg.openalex_email:
        params["mailto"] = cfg.openalex_email
    return params


def _doi_filters(doi: str) -> list[str]:
    candidates = [f"doi:{doi}", f"doi:https://doi.org/{doi}"]
    seen: set[str] = set()
    filters: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            filters.append(candidate)
    return filters


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


def _semantic_scholar_request_fields() -> str:
    return ",".join(
        [
        "title",
        "authors",
        "year",
        "citationCount",
        "influentialCitationCount",
        "venue",
        "publicationVenue",
        "url",
        "externalIds",
        ]
    )


def _semantic_scholar_headers(cfg: Settings) -> dict[str, str]:
    if not cfg.semantic_scholar_use_api_key or not cfg.semantic_scholar_api_key:
        return {}
    return {"x-api-key": cfg.semantic_scholar_api_key}


def _compute_backoff(attempt: int, initial: float, maximum: float) -> float:
    """Exponential backoff with jitter, capped at ``maximum`` seconds."""
    base = initial * (2 ** max(0, attempt))
    capped = min(base, maximum)
    jitter = random.uniform(0.0, capped * 0.25)
    return capped + jitter


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse a ``Retry-After`` header as either seconds or an HTTP-date."""
    header = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if not header:
        return None
    header = header.strip()
    try:
        return max(0.0, float(header))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if retry_at is None:
        return None
    now_ts = time.time()
    delta = retry_at.timestamp() - now_ts
    return max(0.0, delta)


def _apply_semantic_scholar_enrichment(
    paper: Paper,
    enrichment: PaperSemanticScholarEnrichment,
) -> Paper:
    enriched = paper.model_copy(deep=True)
    enriched.semantic_scholar = enrichment

    if enrichment.status == "matched":
        if not enriched.authors and enrichment.authors:
            enriched.authors = enrichment.authors
        if enriched.year is None and enrichment.publication_year is not None:
            enriched.year = enrichment.publication_year
        if not enriched.doi and enrichment.doi:
            enriched.doi = enrichment.doi

    return enriched


def _build_semantic_scholar_enrichment(
    paper_data: dict[str, Any],
    *,
    title_similarity: float,
) -> PaperSemanticScholarEnrichment:
    authors: list[str] = []
    raw_authors = paper_data.get("authors", [])
    if isinstance(raw_authors, list):
        for author in raw_authors:
            if not isinstance(author, dict):
                continue
            name = _coerce_str(author.get("name"))
            if name:
                authors.append(name)

    publication_venue = _build_semantic_scholar_publication_venue(
        paper_data.get("publicationVenue")
    )
    publication_venue_name = (
        publication_venue.name if publication_venue and publication_venue.name else None
    )

    return PaperSemanticScholarEnrichment(
        status="matched",
        paper_id=_coerce_str(paper_data.get("paperId")),
        corpus_id=_coerce_int(paper_data.get("corpusId")),
        matched_title=_coerce_str(paper_data.get("title")),
        title_similarity=title_similarity,
        match_score=_coerce_float(paper_data.get("matchScore")),
        citation_count=_coerce_int(paper_data.get("citationCount")),
        influential_citation_count=_coerce_int(paper_data.get("influentialCitationCount")),
        venue=_coerce_str(paper_data.get("venue")),
        publication_venue=publication_venue,
        publication_venue_name=publication_venue_name or _coerce_str(paper_data.get("venue")),
        authors=authors,
        doi=_extract_semantic_scholar_doi(paper_data.get("externalIds")),
        publication_year=_coerce_int(paper_data.get("year")),
        url=_coerce_str(paper_data.get("url")),
    )


def _build_semantic_scholar_publication_venue(
    value: Any,
) -> SemanticScholarPublicationVenue | None:
    if not isinstance(value, dict):
        return None

    alternate_names = value.get("alternate_names", [])
    normalized_alternate_names: list[str] = []
    if isinstance(alternate_names, list):
        for item in alternate_names:
            name = _coerce_str(item)
            if name:
                normalized_alternate_names.append(name)

    venue = SemanticScholarPublicationVenue(
        venue_id=_coerce_str(value.get("id")),
        name=_coerce_str(value.get("name")),
        type=_coerce_str(value.get("type")),
        alternate_names=normalized_alternate_names,
        url=_coerce_str(value.get("url")),
    )
    if any(
        [
            venue.venue_id,
            venue.name,
            venue.type,
            venue.alternate_names,
            venue.url,
        ]
    ):
        return venue
    return None


def _extract_semantic_scholar_doi(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("DOI", "doi"):
        doi = _normalize_doi(_coerce_str(value.get(key)))
        if doi:
            return doi
    return None


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
    normalized = value.strip()
    normalized = normalized.removeprefix("https://doi.org/")
    normalized = normalized.removeprefix("http://doi.org/")
    normalized = normalized.removeprefix("https://dx.doi.org/")
    normalized = normalized.removeprefix("http://dx.doi.org/")
    normalized = normalized.removeprefix("doi:")
    normalized = normalized.strip()
    return normalized.lower() or None


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
