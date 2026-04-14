"""OpenAI web search provider using the Responses API with web_search tool."""

from __future__ import annotations

import logging

import httpx

from research_agent.models import SearchResult
from research_agent.search.base import SearchProvider

logger = logging.getLogger("research_agent.search.openai")

_ENDPOINT = "https://api.openai.com/v1/responses"


def _extract_snippet(
    full_text: str,
    annotation: dict,
    all_annotations: list[dict],
) -> str:
    """Extract the text surrounding a url_citation annotation as a snippet.

    Uses the annotation's start_index to find the beginning of the enclosing
    sentence/paragraph, and the next annotation's start_index (or a reasonable
    window) to find the end.  Falls back to the annotation title if indices
    are missing or the text is empty.
    """
    title = annotation.get("title", "")
    start = annotation.get("start_index")
    end = annotation.get("end_index")

    if not full_text or start is None:
        return title

    # Walk backwards from the citation start to find the beginning of the
    # surrounding context (previous newline or start of text).
    ctx_start = max(full_text.rfind("\n", 0, start), 0)

    # Walk forwards to find the end of the context: use the start of the
    # next annotation, or up to 300 chars after citation end, whichever is
    # shorter. This avoids bleeding into the next citation's description.
    next_starts = sorted(
        a.get("start_index", len(full_text))
        for a in all_annotations
        if a is not annotation
        and a.get("start_index") is not None
        and a["start_index"] > start
    )
    boundary = next_starts[0] if next_starts else len(full_text)
    ctx_end = min(boundary, (end or start) + 300, len(full_text))

    snippet = full_text[ctx_start:ctx_end].strip()
    return snippet if snippet else title


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
                full_text = content_block.get("text", "")
                annotations = content_block.get("annotations", [])

                # Build a snippet for each citation from the surrounding text
                for annotation in annotations:
                    if annotation.get("type") != "url_citation":
                        continue
                    snippet = _extract_snippet(
                        full_text, annotation, annotations,
                    )
                    results.append(
                        SearchResult(
                            title=annotation.get("title", ""),
                            url=annotation.get("url", ""),
                            snippet=snippet,
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
