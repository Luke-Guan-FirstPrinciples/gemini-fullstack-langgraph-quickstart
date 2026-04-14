"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """All configurable knobs for the research agent."""

    # LLM -----------------------------------------------------------------
    configured_llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini"),
        repr=False,
    )
    configured_llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", ""),
        repr=False,
    )
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    gemini_llm_model: str = os.getenv("GEMINI_LLM_MODEL", "gemini-2.5-flash")
    openai_llm_model: str = os.getenv("OPENAI_LLM_MODEL", "gpt-5.4-mini")
    anthropic_llm_model: str = os.getenv(
        "ANTHROPIC_LLM_MODEL",
        "claude-3-5-sonnet-latest",
    )
    google_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Search ---------------------------------------------------------------
    search_provider: str = os.getenv("SEARCH_PROVIDER", "google_cse")
    openai_search_model: str = os.getenv("OPENAI_SEARCH_MODEL", "gpt-5.4-mini")
    google_cse_api_key: str = field(
        default_factory=lambda: os.getenv(
            "GOOGLE_CSE_API_KEY",
            os.getenv("GOOGLE_API_KEY", ""),
        )
    )
    google_cse_id: str = field(
        default_factory=lambda: os.getenv(
            "GOOGLE_CSE_ID",
            os.getenv("GOOGLE_SEARCH_ENGINE_ID", ""),
        )
    )
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    jina_api_key: str = os.getenv("JINA_API_KEY", "")
    openalex_base_url: str = os.getenv("OPENALEX_BASE_URL", "https://api.openalex.org")
    openalex_api_key: str = os.getenv("OPENALEX_API_KEY", "")
    openalex_email: str = os.getenv("OPENALEX_EMAIL", "")

    # Pipeline -------------------------------------------------------------
    max_iterations: int = int(os.getenv("RESEARCH_MAX_ITERATIONS", "2"))
    results_per_query: int = int(os.getenv("RESEARCH_RESULTS_PER_QUERY", "10"))
    openalex_title_search_limit: int = int(os.getenv("RESEARCH_OPENALEX_TITLE_SEARCH_LIMIT", "5"))
    openalex_parallelism: int = int(os.getenv("RESEARCH_OPENALEX_PARALLELISM", "4"))
    openalex_timeout_seconds: float = float(os.getenv("RESEARCH_OPENALEX_TIMEOUT_SECONDS", "30"))
    openalex_min_title_similarity: float = float(os.getenv("RESEARCH_OPENALEX_MIN_TITLE_SIMILARITY", "0.82"))
    rerank_batch_size: int = int(os.getenv("RESEARCH_RERANK_BATCH_SIZE", "12"))
    rerank_model: str = os.getenv("RESEARCH_RERANK_MODEL", "")
    semantic_relevance_weight: float = float(
        os.getenv("RESEARCH_WEIGHT_SEMANTIC_RELEVANCE", "0.6")
    )
    citation_count_weight: float = float(
        os.getenv("RESEARCH_WEIGHT_CITATION_COUNT", "0.25")
    )
    fwci_weight: float = float(os.getenv("RESEARCH_WEIGHT_FWCI", "0.15"))

    # Preferred academic sources (used in query generation prompts)
    preferred_sources: list[str] = field(default_factory=lambda: [
        "arxiv.org",
        "inspirehep.net",
        "nature.com",
        "science.org",
        "journals.aps.org",
    ])

    # Logging --------------------------------------------------------------
    log_dir: str = os.getenv("RESEARCH_LOG_DIR", "logs/research_agent")
    log_level: str = os.getenv("RESEARCH_LOG_LEVEL", "DEBUG")

    # LangSmith (set these env vars to enable tracing) ---------------------
    # LANGCHAIN_TRACING_V2=true
    # LANGCHAIN_API_KEY=...
    # LANGCHAIN_PROJECT=research-agent

    def ranking_weights(self) -> dict[str, float]:
        """Return the currently configured ranking weights."""
        return {
            "semantic_relevance": self.semantic_relevance_weight,
            "citation_count": self.citation_count_weight,
            "fwci": self.fwci_weight,
        }

    def default_llm_model_for_provider(self, provider: str | None = None) -> str:
        """Return the provider-specific default chat model."""
        resolved_provider = provider or self.llm_provider
        if resolved_provider == "gemini":
            return self.gemini_llm_model
        if resolved_provider == "openai":
            return self.openai_llm_model
        if resolved_provider == "anthropic":
            return self.anthropic_llm_model

        raise ValueError(
            f"Unknown LLM provider: {resolved_provider!r}. "
            "Supported: gemini, openai, anthropic"
        )

    def resolved_llm_model(self, provider: str | None = None) -> str:
        """Use an explicit model override when set, else the provider default."""
        resolved_provider = provider or self.llm_provider
        if self.llm_model and (
            self.llm_model != self.configured_llm_model
            or resolved_provider == self.configured_llm_provider
        ):
            return self.llm_model
        return self.default_llm_model_for_provider(resolved_provider)

    def rerank_model_name(self) -> str:
        """Use a dedicated rerank model when configured, else the main LLM model."""
        return self.rerank_model or self.resolved_llm_model()


settings = Settings()
