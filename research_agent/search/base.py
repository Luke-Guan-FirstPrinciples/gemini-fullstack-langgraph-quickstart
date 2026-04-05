"""Abstract base class that every search provider implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

from research_agent.models import SearchResult


class SearchProvider(ABC):
    """Uniform interface for web-search backends."""

    @abstractmethod
    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Execute *query* and return up to *num_results* items."""

    # ------------------------------------------------------------------
    # Helpers shared across providers
    # ------------------------------------------------------------------

    @staticmethod
    def _domain_from_url(url: str) -> str:
        """Extract a short source label from a URL."""
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower().removeprefix("www.")
        # Map common academic domains to short labels
        mapping = {
            "arxiv.org": "arxiv",
            "inspirehep.net": "inspirehep",
            "nature.com": "nature",
            "science.org": "science",
            "journals.aps.org": "aps",
            "link.aps.org": "aps",
            "scholar.google.com": "google_scholar",
            "pubmed.ncbi.nlm.nih.gov": "pubmed",
            "ieeexplore.ieee.org": "ieee",
        }
        for domain, label in mapping.items():
            if domain in host:
                return label
        return host
