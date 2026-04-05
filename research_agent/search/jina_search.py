"""Jina AI search provider."""

from __future__ import annotations

import logging

import httpx

from research_agent.models import SearchResult
from research_agent.search.base import SearchProvider

logger = logging.getLogger("research_agent.search.jina")

_ENDPOINT = "https://s.jina.ai/"


class JinaProvider(SearchProvider):
    """Search via Jina AI Search API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "X-Retain-Images": "none",
        }
        logger.debug("Jina request: q=%r", query)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_ENDPOINT}{query}",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        items = data.get("data", [])[:num_results]
        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", r.get("content", ""))[:500],
                source=self._domain_from_url(r.get("url", "")),
            )
            for r in items
        ]
        logger.info("Jina returned %d results for: %s", len(results), query)
        return results
