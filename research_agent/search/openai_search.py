"""OpenAI web search provider using the Responses API with web_search tool."""

from __future__ import annotations

import logging

import httpx

from research_agent.models import SearchResult
from research_agent.search.base import SearchProvider

logger = logging.getLogger("research_agent.search.openai")

_ENDPOINT = "https://api.openai.com/v1/responses"


class OpenAISearchProvider(SearchProvider):
    """Search via OpenAI Responses API with the built-in web_search_preview tool."""

    def __init__(self, api_key: str, model: str = "gpt-5.4-mini") -> None:
        self._api_key = api_key
        self._model = model

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "tools": [{"type": "web_search_preview"}],
            "input": (
                f"Search for academic papers and research on: {query}\n"
                f"Return up to {num_results} relevant results with titles, URLs, and summaries."
            ),
        }

        logger.debug("OpenAI web search request: q=%r model=%s", query, self._model)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(_ENDPOINT, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []

        # Extract URLs and annotations from the response output items
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for content_block in item.get("content", []):
                if content_block.get("type") != "output_text":
                    continue
                # Collect URL citations from annotations
                for annotation in content_block.get("annotations", []):
                    if annotation.get("type") == "url_citation":
                        results.append(
                            SearchResult(
                                title=annotation.get("title", ""),
                                url=annotation.get("url", ""),
                                snippet=annotation.get("title", ""),
                                source=self._domain_from_url(annotation.get("url", "")),
                            )
                        )

        # Deduplicate by URL, preserving order
        seen: set[str] = set()
        unique: list[SearchResult] = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)

        results = unique[:num_results]
        logger.info("OpenAI web search returned %d results for: %s", len(results), query)
        return results
