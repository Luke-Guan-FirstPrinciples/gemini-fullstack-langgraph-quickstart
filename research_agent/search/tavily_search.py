"""Tavily search provider."""

from __future__ import annotations

import logging

import httpx

from research_agent.models import SearchResult
from research_agent.search.base import SearchProvider

logger = logging.getLogger("research_agent.search.tavily")

_ENDPOINT = "https://api.tavily.com/search"


class TavilyProvider(SearchProvider):
    """Search via Tavily REST API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": num_results,
            "search_depth": "advanced",
            "include_answer": False,
        }
        logger.debug("Tavily request: q=%r max_results=%d", query, num_results)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(_ENDPOINT, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
                source=self._domain_from_url(r.get("url", "")),
            )
            for r in data.get("results", [])
        ]
        logger.info("Tavily returned %d results for: %s", len(results), query)
        return results
