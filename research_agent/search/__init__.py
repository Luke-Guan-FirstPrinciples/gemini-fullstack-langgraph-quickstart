"""Search provider abstraction — swap Google CSE / Tavily / Jina with one config change."""

from research_agent.search.base import SearchProvider
from research_agent.search.factory import create_search_provider

__all__ = ["SearchProvider", "create_search_provider"]
