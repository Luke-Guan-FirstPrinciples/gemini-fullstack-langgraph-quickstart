"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """All configurable knobs for the research agent."""

    # LLM -----------------------------------------------------------------
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    google_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Search ---------------------------------------------------------------
    search_provider: str = os.getenv("SEARCH_PROVIDER", "google_cse")
    openai_search_model: str = os.getenv("OPENAI_SEARCH_MODEL", "gpt-5.4-mini")
    google_cse_api_key: str = os.getenv("GOOGLE_CSE_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    google_cse_id: str = os.getenv("GOOGLE_CSE_ID", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    jina_api_key: str = os.getenv("JINA_API_KEY", "")

    # Pipeline -------------------------------------------------------------
    max_iterations: int = int(os.getenv("RESEARCH_MAX_ITERATIONS", "2"))
    results_per_query: int = int(os.getenv("RESEARCH_RESULTS_PER_QUERY", "10"))

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


settings = Settings()
