"""Factory for instantiating the configured search provider."""

from __future__ import annotations

from research_agent.config import Settings, settings
from research_agent.search.base import SearchProvider


def create_search_provider(cfg: Settings | None = None) -> SearchProvider:
    """Return a :class:`SearchProvider` based on ``cfg.search_provider``."""
    cfg = cfg or settings
    name = cfg.search_provider.lower()

    if name == "google_cse":
        from research_agent.search.google_cse import GoogleCSEProvider

        if not cfg.google_cse_api_key or not cfg.google_cse_id:
            raise ValueError(
                "Google CSE requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID env vars"
            )
        return GoogleCSEProvider(api_key=cfg.google_cse_api_key, cse_id=cfg.google_cse_id)

    if name == "tavily":
        from research_agent.search.tavily_search import TavilyProvider

        if not cfg.tavily_api_key:
            raise ValueError("Tavily requires TAVILY_API_KEY env var")
        return TavilyProvider(api_key=cfg.tavily_api_key)

    if name == "jina":
        from research_agent.search.jina_search import JinaProvider

        if not cfg.jina_api_key:
            raise ValueError("Jina requires JINA_API_KEY env var")
        return JinaProvider(api_key=cfg.jina_api_key)

    if name == "openai":
        from research_agent.search.openai_search import OpenAISearchProvider

        if not cfg.openai_api_key:
            raise ValueError("OpenAI search requires OPENAI_API_KEY env var")
        return OpenAISearchProvider(
            api_key=cfg.openai_api_key,
            model=cfg.openai_search_model,
        )

    raise ValueError(
        f"Unknown search provider: {name!r}. Supported: google_cse, tavily, jina, openai"
    )
