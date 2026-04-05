"""Google Custom Search Engine (CSE) provider."""

from __future__ import annotations

import logging

import httpx

from research_agent.models import SearchResult
from research_agent.search.base import SearchProvider

logger = logging.getLogger("research_agent.search.google_cse")

_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


class GoogleCSEProvider(SearchProvider):
    """Search via Google Custom Search JSON API."""

    def __init__(self, api_key: str, cse_id: str) -> None:
        self._api_key = api_key
        self._cse_id = cse_id

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        # Google CSE returns max 10 per request; paginate if needed
        results: list[SearchResult] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for start in range(1, num_results + 1, 10):
                count = min(10, num_results - start + 1)
                params = {
                    "key": self._api_key,
                    "cx": self._cse_id,
                    "q": query,
                    "num": count,
                    "start": start,
                }
                logger.debug("Google CSE request: q=%r start=%d num=%d", query, start, count)
                resp = await client.get(_ENDPOINT, params=params)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("items", []):
                    results.append(
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("link", ""),
                            snippet=item.get("snippet", ""),
                            source=self._domain_from_url(item.get("link", "")),
                        )
                    )
        logger.info("Google CSE returned %d results for: %s", len(results), query)
        return results
