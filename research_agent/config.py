"""Configuration loaded from YAML, environment variables, and code defaults.

Precedence (highest wins):

1. Environment variables
2. ``config.yaml`` (see ``_config_file_candidates``)
3. Hard-coded defaults in this module

The YAML file is optional. Copy ``config.sample.yaml`` to ``config.yaml`` at
the repo root and tweak only the knobs you care about — everything else falls
back to the existing env-var / code defaults.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:  # PyYAML is part of our requirements but guard for stripped-down installs.
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

load_dotenv()

_logger = logging.getLogger("research_agent.config")


# Mapping from nested YAML path -> flat ``Settings`` attribute name. Keeping
# this explicit keeps the YAML schema stable even if internal attribute names
# change in the future.
_YAML_KEY_MAP: dict[tuple[str, ...], str] = {
    # Ranking weights --------------------------------------------------------
    ("ranking", "semantic_relevance"): "semantic_relevance_weight",
    ("ranking", "citation_count"): "citation_count_weight",
    # LLM --------------------------------------------------------------------
    ("llm", "provider"): "llm_provider",
    ("llm", "model"): "llm_model",
    ("llm", "gemini_model"): "gemini_llm_model",
    ("llm", "openai_model"): "openai_llm_model",
    ("llm", "anthropic_model"): "anthropic_llm_model",
    # Search -----------------------------------------------------------------
    ("search", "provider"): "search_provider",
    ("search", "openai_search_model"): "openai_search_model",
    # Pipeline ---------------------------------------------------------------
    ("pipeline", "max_iterations"): "max_iterations",
    ("pipeline", "results_per_query"): "results_per_query",
    ("pipeline", "openalex_parallelism"): "openalex_parallelism",
    ("pipeline", "openalex_timeout_seconds"): "openalex_timeout_seconds",
    ("pipeline", "openalex_min_title_similarity"): "openalex_min_title_similarity",
    ("pipeline", "openalex_title_search_limit"): "openalex_title_search_limit",
    ("pipeline", "rerank_batch_size"): "rerank_batch_size",
    ("pipeline", "rerank_model"): "rerank_model",
    ("pipeline", "preferred_sources"): "preferred_sources",
    # Semantic Scholar -------------------------------------------------------
    ("semantic_scholar", "use_api_key"): "semantic_scholar_use_api_key",
    ("semantic_scholar", "parallelism"): "semantic_scholar_parallelism",
    ("semantic_scholar", "timeout_seconds"): "semantic_scholar_timeout_seconds",
    (
        "semantic_scholar",
        "requests_per_second",
    ): "semantic_scholar_requests_per_second",
    ("semantic_scholar", "max_retries"): "semantic_scholar_max_retries",
    (
        "semantic_scholar",
        "initial_backoff_seconds",
    ): "semantic_scholar_initial_backoff_seconds",
    (
        "semantic_scholar",
        "max_backoff_seconds",
    ): "semantic_scholar_max_backoff_seconds",
    (
        "semantic_scholar",
        "min_title_similarity",
    ): "semantic_scholar_min_title_similarity",
    # Logging ----------------------------------------------------------------
    ("logging", "dir"): "log_dir",
    ("logging", "level"): "log_level",
}


# Mapping from flat attribute -> environment variable. Used to decide whether
# a YAML override should be applied (YAML only wins when the env var is unset).
_ATTR_ENV_MAP: dict[str, str] = {
    "semantic_relevance_weight": "RESEARCH_WEIGHT_SEMANTIC_RELEVANCE",
    "citation_count_weight": "RESEARCH_WEIGHT_CITATION_COUNT",
    "llm_provider": "LLM_PROVIDER",
    "llm_model": "LLM_MODEL",
    "gemini_llm_model": "GEMINI_LLM_MODEL",
    "openai_llm_model": "OPENAI_LLM_MODEL",
    "anthropic_llm_model": "ANTHROPIC_LLM_MODEL",
    "search_provider": "SEARCH_PROVIDER",
    "openai_search_model": "OPENAI_SEARCH_MODEL",
    "max_iterations": "RESEARCH_MAX_ITERATIONS",
    "results_per_query": "RESEARCH_RESULTS_PER_QUERY",
    "openalex_title_search_limit": "RESEARCH_OPENALEX_TITLE_SEARCH_LIMIT",
    "openalex_parallelism": "RESEARCH_OPENALEX_PARALLELISM",
    "openalex_timeout_seconds": "RESEARCH_OPENALEX_TIMEOUT_SECONDS",
    "openalex_min_title_similarity": "RESEARCH_OPENALEX_MIN_TITLE_SIMILARITY",
    "semantic_scholar_use_api_key": "RESEARCH_SEMANTIC_SCHOLAR_USE_API_KEY",
    "semantic_scholar_parallelism": "RESEARCH_SEMANTIC_SCHOLAR_PARALLELISM",
    "semantic_scholar_timeout_seconds": "RESEARCH_SEMANTIC_SCHOLAR_TIMEOUT_SECONDS",
    "semantic_scholar_min_title_similarity": (
        "RESEARCH_SEMANTIC_SCHOLAR_MIN_TITLE_SIMILARITY"
    ),
    "semantic_scholar_requests_per_second": (
        "RESEARCH_SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND"
    ),
    "semantic_scholar_max_retries": "RESEARCH_SEMANTIC_SCHOLAR_MAX_RETRIES",
    "semantic_scholar_initial_backoff_seconds": (
        "RESEARCH_SEMANTIC_SCHOLAR_INITIAL_BACKOFF_SECONDS"
    ),
    "semantic_scholar_max_backoff_seconds": (
        "RESEARCH_SEMANTIC_SCHOLAR_MAX_BACKOFF_SECONDS"
    ),
    "rerank_batch_size": "RESEARCH_RERANK_BATCH_SIZE",
    "rerank_model": "RESEARCH_RERANK_MODEL",
    "log_dir": "RESEARCH_LOG_DIR",
    "log_level": "RESEARCH_LOG_LEVEL",
    # ``preferred_sources`` has no canonical env var; set it via YAML.
    "preferred_sources": "",
}


def _config_file_candidates() -> list[Path]:
    """Return candidate locations for ``config.yaml``, in priority order."""

    env_path = os.getenv("RESEARCH_CONFIG_FILE")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())

    cwd = Path.cwd()
    module_dir = Path(__file__).resolve().parent
    repo_root = module_dir.parent

    candidates.extend(
        [
            cwd / "config.yaml",
            cwd / "config.yml",
            repo_root / "config.yaml",
            repo_root / "config.yml",
            module_dir / "config.yaml",
            module_dir / "config.yml",
        ]
    )

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        key = path.resolve() if path.exists() else path
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _load_yaml_overrides() -> tuple[dict[str, Any], Path | None]:
    """Load the first ``config.yaml`` we find and flatten it to attr overrides."""

    if yaml is None:
        return {}, None

    for path in _config_file_candidates():
        if not path.is_file():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # pragma: no cover
            _logger.exception("Failed to parse config YAML at %s", path)
            return {}, path
        if not isinstance(raw, dict):
            _logger.warning(
                "Ignoring %s: top-level YAML must be a mapping, got %s",
                path,
                type(raw).__name__,
            )
            return {}, path

        flat: dict[str, Any] = {}
        for keys, attr in _YAML_KEY_MAP.items():
            value: Any = raw
            found = True
            for key in keys:
                if not isinstance(value, dict) or key not in value:
                    found = False
                    break
                value = value[key]
            if found:
                flat[attr] = value
        _logger.info("Loaded config overrides from %s (%d keys)", path, len(flat))
        return flat, path

    return {}, None


_YAML_OVERRIDES, _YAML_CONFIG_PATH = _load_yaml_overrides()


def config_file_path() -> Path | None:
    """Return the YAML config file that was loaded, if any."""
    return _YAML_CONFIG_PATH


def _coerce_to_field_type(value: Any, field_type: Any) -> Any:
    """Best-effort coercion of YAML values into the dataclass field's type."""

    if value is None:
        return value

    type_name = getattr(field_type, "__name__", str(field_type)).lower()

    if type_name.startswith("bool"):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    if type_name.startswith("int"):
        return int(value)

    if type_name.startswith("float"):
        return float(value)

    if type_name.startswith("str"):
        return str(value)

    if type_name.startswith("list"):
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]

    return value


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    gemini_llm_model: str = os.getenv("GEMINI_LLM_MODEL", "gemini-3.1-pro-preview")
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
    semantic_scholar_base_url: str = os.getenv(
        "SEMANTIC_SCHOLAR_BASE_URL",
        "https://api.semanticscholar.org/graph/v1",
    )
    semantic_scholar_api_key: str = os.getenv(
        "SEMANTIC_SCHOLAR_API_KEY",
        os.getenv("S2_API_KEY", ""),
    )
    semantic_scholar_use_api_key: bool = _env_flag(
        "RESEARCH_SEMANTIC_SCHOLAR_USE_API_KEY",
        default=False,
    )

    # Pipeline -------------------------------------------------------------
    max_iterations: int = int(os.getenv("RESEARCH_MAX_ITERATIONS", "2"))
    results_per_query: int = int(os.getenv("RESEARCH_RESULTS_PER_QUERY", "10"))
    openalex_title_search_limit: int = int(os.getenv("RESEARCH_OPENALEX_TITLE_SEARCH_LIMIT", "5"))
    openalex_parallelism: int = int(os.getenv("RESEARCH_OPENALEX_PARALLELISM", "4"))
    openalex_timeout_seconds: float = float(os.getenv("RESEARCH_OPENALEX_TIMEOUT_SECONDS", "30"))
    openalex_min_title_similarity: float = float(os.getenv("RESEARCH_OPENALEX_MIN_TITLE_SIMILARITY", "0.82"))
    semantic_scholar_parallelism: int = int(
        os.getenv("RESEARCH_SEMANTIC_SCHOLAR_PARALLELISM", "1")
    )
    semantic_scholar_timeout_seconds: float = float(
        os.getenv("RESEARCH_SEMANTIC_SCHOLAR_TIMEOUT_SECONDS", "30")
    )
    semantic_scholar_min_title_similarity: float = float(
        os.getenv("RESEARCH_SEMANTIC_SCHOLAR_MIN_TITLE_SIMILARITY", "0.82")
    )
    # Unauthenticated Semantic Scholar traffic is shared-pool throttled to
    # roughly 1 request per second. The defaults below keep us safely below
    # that ceiling; bump them when an API key is configured.
    semantic_scholar_requests_per_second: float = float(
        os.getenv("RESEARCH_SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND", "1.0")
    )
    semantic_scholar_max_retries: int = int(
        os.getenv("RESEARCH_SEMANTIC_SCHOLAR_MAX_RETRIES", "1")
    )
    semantic_scholar_initial_backoff_seconds: float = float(
        os.getenv("RESEARCH_SEMANTIC_SCHOLAR_INITIAL_BACKOFF_SECONDS", "2.0")
    )
    semantic_scholar_max_backoff_seconds: float = float(
        os.getenv("RESEARCH_SEMANTIC_SCHOLAR_MAX_BACKOFF_SECONDS", "30.0")
    )
    rerank_batch_size: int = int(os.getenv("RESEARCH_RERANK_BATCH_SIZE", "12"))
    rerank_model: str = os.getenv("RESEARCH_RERANK_MODEL", "")
    semantic_relevance_weight: float = float(
        os.getenv("RESEARCH_WEIGHT_SEMANTIC_RELEVANCE", "0.6")
    )
    citation_count_weight: float = float(
        os.getenv("RESEARCH_WEIGHT_CITATION_COUNT", "0.25")
    )

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

    def __post_init__(self) -> None:
        """Re-apply overrides so precedence (env > yaml > default) holds at runtime.

        Dataclass field defaults for simple types are evaluated once at class
        definition, which means env vars set after import would otherwise be
        ignored. Walking the known knobs here also lets us layer YAML on top
        of code defaults cleanly.
        """

        field_types = {f.name: f.type for f in fields(self)}

        for attr, env_name in _ATTR_ENV_MAP.items():
            if attr not in field_types:
                continue
            env_value = os.getenv(env_name) if env_name else None
            if env_value is not None:
                value: Any = env_value
            elif attr in _YAML_OVERRIDES:
                value = _YAML_OVERRIDES[attr]
            else:
                continue
            try:
                setattr(self, attr, _coerce_to_field_type(value, field_types[attr]))
            except (TypeError, ValueError):
                _logger.warning(
                    "Ignoring config value for %s=%r (type coercion failed)",
                    attr,
                    value,
                )

    def ranking_weights(self) -> dict[str, float]:
        """Return the currently configured ranking weights."""
        return {
            "semantic_relevance": self.semantic_relevance_weight,
            "citation_count": self.citation_count_weight,
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
