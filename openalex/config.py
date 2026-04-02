from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

TRUTHY_VALUES = {"1", "true", "yes", "on"}
FALSEY_VALUES = {"0", "false", "no", "off"}


def _read_env_file(path: str | None) -> dict[str, str]:
    if not path:
        return {}

    env_path = Path(path).expanduser()
    if not env_path.is_absolute():
        env_path = Path.cwd() / env_path
    if not env_path.exists():
        return {}

    parsed: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        parsed[key] = value
    return parsed


def _lookup_value(name: str, env_file_values: dict[str, str]) -> str | None:
    if name in os.environ:
        return os.environ[name]
    return env_file_values.get(name)


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in TRUTHY_VALUES:
        return True
    if lowered in FALSEY_VALUES:
        return False
    raise ValueError(f"Invalid boolean value: {raw!r}")


def _parse_int(raw: str | None, default: int) -> int:
    if raw is None or raw == "":
        return default
    return int(raw)


def _parse_float(raw: str | None, default: float) -> float:
    if raw is None or raw == "":
        return default
    return float(raw)


def _parse_optional_str(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


@dataclass(slots=True)
class OpenAlexWorkflowSettings:
    db_host: str | None = None
    db_port: int = 5432
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None

    openalex_base_url: str = "https://api.openalex.org"
    openalex_api_key: str | None = None
    openalex_email: str | None = None
    gemini_api_key: str | None = None

    selector_model: str | None = None
    selector_strategy: str = "heuristic"
    selector_temperature: float = 0.0
    fallback_to_heuristic: bool = True
    verify_candidate_relevance: bool = True
    verifier_model: str = "gemini-2.5-flash"
    verifier_temperature: float = 0.0
    fallback_to_unverified_candidates: bool = True

    candidate_limit: int = 30
    selection_limit: int = 5
    max_results_per_query: int = 20
    per_page: int = 200
    top_k: int = 25
    parallel: int = 4
    max_author_topics_per_keyword: int = 1
    generated_query_sort: str = "cited_by_count:desc"
    request_timeout_seconds: float = 30.0
    max_authors_per_paper: int = 12
    check_valid_topic: bool = True

    save_output: bool = True
    output_filename: str = "results.json"
    output_root: str | None = None

    catalog_backend: str = "auto"
    catalog_path: str | None = None

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "OpenAlexWorkflowSettings":
        env_file_path = env_file or os.environ.get("OPENALEX_ENV_FILE") or ".env"
        env_file_values = _read_env_file(env_file_path)

        return cls(
            db_host=_parse_optional_str(_lookup_value("DB_HOST", env_file_values)),
            db_port=_parse_int(_lookup_value("DB_PORT", env_file_values), 5432),
            db_name=_parse_optional_str(_lookup_value("DB_NAME", env_file_values)),
            db_user=_parse_optional_str(_lookup_value("DB_USER", env_file_values)),
            db_password=_parse_optional_str(
                _lookup_value("DB_PASSWORD", env_file_values)
            ),
            openalex_base_url=(
                _parse_optional_str(
                    _lookup_value("OPENALEX_BASE_URL", env_file_values)
                )
                or "https://api.openalex.org"
            ),
            openalex_api_key=_parse_optional_str(
                _lookup_value("OPENALEX_API_KEY", env_file_values)
            ),
            openalex_email=_parse_optional_str(
                _lookup_value("OPENALEX_EMAIL", env_file_values)
            ),
            gemini_api_key=(
                _parse_optional_str(_lookup_value("GEMINI_API_KEY", env_file_values))
                or _parse_optional_str(
                    _lookup_value("GOOGLE_API_KEY", env_file_values)
                )
            ),
            selector_model=_parse_optional_str(
                _lookup_value("OPENALEX_SELECTOR_MODEL", env_file_values)
            ),
            selector_strategy=(
                _parse_optional_str(
                    _lookup_value("OPENALEX_SELECTOR_STRATEGY", env_file_values)
                )
                or "heuristic"
            ),
            selector_temperature=_parse_float(
                _lookup_value("OPENALEX_SELECTOR_TEMPERATURE", env_file_values),
                0.0,
            ),
            fallback_to_heuristic=_parse_bool(
                _lookup_value("OPENALEX_FALLBACK_TO_HEURISTIC", env_file_values),
                True,
            ),
            verify_candidate_relevance=_parse_bool(
                _lookup_value(
                    "OPENALEX_VERIFY_CANDIDATE_RELEVANCE", env_file_values
                ),
                True,
            ),
            verifier_model=(
                _parse_optional_str(
                    _lookup_value("OPENALEX_VERIFIER_MODEL", env_file_values)
                )
                or "gemini-2.5-flash"
            ),
            verifier_temperature=_parse_float(
                _lookup_value("OPENALEX_VERIFIER_TEMPERATURE", env_file_values),
                0.0,
            ),
            fallback_to_unverified_candidates=_parse_bool(
                _lookup_value(
                    "OPENALEX_FALLBACK_TO_UNVERIFIED_CANDIDATES",
                    env_file_values,
                ),
                True,
            ),
            candidate_limit=_parse_int(
                _lookup_value("OPENALEX_CANDIDATE_LIMIT", env_file_values),
                30,
            ),
            selection_limit=_parse_int(
                _lookup_value("OPENALEX_SELECTION_LIMIT", env_file_values),
                5,
            ),
            max_results_per_query=_parse_int(
                _lookup_value("OPENALEX_MAX_RESULTS_PER_QUERY", env_file_values)
                or _lookup_value("OPENALEX_PAPERS_PER_QUERY", env_file_values),
                20,
            ),
            per_page=_parse_int(
                _lookup_value("OPENALEX_PER_PAGE", env_file_values),
                200,
            ),
            top_k=_parse_int(_lookup_value("OPENALEX_TOP_K", env_file_values), 25),
            parallel=_parse_int(
                _lookup_value("OPENALEX_PARALLEL", env_file_values),
                4,
            ),
            max_author_topics_per_keyword=_parse_int(
                _lookup_value(
                    "OPENALEX_MAX_AUTHOR_TOPICS_PER_KEYWORD", env_file_values
                ),
                1,
            ),
            generated_query_sort=(
                _parse_optional_str(
                    _lookup_value("OPENALEX_GENERATED_QUERY_SORT", env_file_values)
                )
                or "cited_by_count:desc"
            ),
            request_timeout_seconds=_parse_float(
                _lookup_value(
                    "OPENALEX_REQUEST_TIMEOUT_SECONDS", env_file_values
                ),
                30.0,
            ),
            max_authors_per_paper=_parse_int(
                _lookup_value("OPENALEX_MAX_AUTHORS_PER_PAPER", env_file_values),
                12,
            ),
            check_valid_topic=_parse_bool(
                _lookup_value("OPENALEX_CHECK_VALID_TOPIC", env_file_values),
                True,
            ),
            save_output=_parse_bool(
                _lookup_value("SAVE_OUTPUT_OPENALEX_WORKFLOW", env_file_values),
                True,
            ),
            output_filename=(
                _parse_optional_str(
                    _lookup_value("OPENALEX_OUTPUT_FILENAME", env_file_values)
                )
                or "results.json"
            ),
            output_root=_parse_optional_str(
                _lookup_value("OPENALEX_OUTPUT_ROOT", env_file_values)
            ),
            catalog_backend=(
                _parse_optional_str(
                    _lookup_value("OPENALEX_CATALOG_BACKEND", env_file_values)
                )
                or "auto"
            ),
            catalog_path=_parse_optional_str(
                _lookup_value("OPENALEX_CATALOG_PATH", env_file_values)
            ),
        )


settings = OpenAlexWorkflowSettings.from_env()
