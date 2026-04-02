from __future__ import annotations

import json
from pathlib import Path

from .config import settings
from .db import OpenAlexCatalogRepository
from .ports import CatalogRepositoryFactory
from .schemas import KeywordCandidate, TopicCandidate
from .text import normalize_alias


class StaticOpenAlexCatalogRepository:
    def __init__(
        self,
        *,
        keywords: list[KeywordCandidate] | None = None,
        topics: list[TopicCandidate] | None = None,
    ) -> None:
        self._keywords = keywords or []
        self._topics = topics or []

    async def __aenter__(self) -> "StaticOpenAlexCatalogRepository":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def fetch_keyword_catalog(self) -> list[KeywordCandidate]:
        return [item.model_copy(deep=True) for item in self._keywords]

    async def fetch_topic_catalog(self) -> list[TopicCandidate]:
        return [item.model_copy(deep=True) for item in self._topics]

    async def resolve_topic_names(self, topic_ids: list[int]) -> dict[int, str]:
        if not topic_ids:
            return {}
        lookup = {item.topic_id: item.topic_name for item in self._topics}
        return {
            topic_id: lookup[topic_id] for topic_id in topic_ids if topic_id in lookup
        }


class JsonOpenAlexCatalogRepository(StaticOpenAlexCatalogRepository):
    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._path = Path(path).expanduser()
        self._loaded = False

    async def __aenter__(self) -> "JsonOpenAlexCatalogRepository":
        if not self._loaded:
            self._load()
        return self

    def _load(self) -> None:
        if not self._path.is_absolute():
            self._path = Path.cwd() / self._path
        if not self._path.exists():
            raise RuntimeError(
                "OpenAlex catalog file does not exist: "
                f"{self._path}. Provide a JSON catalog at that path, or switch to "
                "--catalog-backend postgres after installing asyncpg and configuring "
                "DB_* settings."
            )

        payload = json.loads(self._path.read_text(encoding="utf-8"))
        raw_keywords = payload.get("keywords", [])
        raw_topics = payload.get("topics", [])

        if not isinstance(raw_keywords, list) or not isinstance(raw_topics, list):
            raise RuntimeError(
                "OpenAlex catalog JSON must contain list fields 'keywords' and 'topics'."
            )

        self._keywords = [_parse_keyword_record(item) for item in raw_keywords]
        self._topics = [_parse_topic_record(item) for item in raw_topics]
        self._loaded = True


class UnavailableCatalogRepository:
    def __init__(self, message: str) -> None:
        self._message = message

    async def __aenter__(self) -> "UnavailableCatalogRepository":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def fetch_keyword_catalog(self) -> list[KeywordCandidate]:
        raise RuntimeError(self._message)

    async def fetch_topic_catalog(self) -> list[TopicCandidate]:
        raise RuntimeError(self._message)

    async def resolve_topic_names(self, topic_ids: list[int]) -> dict[int, str]:
        del topic_ids
        raise RuntimeError(self._message)


def build_catalog_repository_factory(
    backend: str | None = None,
    catalog_path: str | None = None,
) -> CatalogRepositoryFactory:
    resolved_backend = (backend or settings.catalog_backend or "auto").lower()
    resolved_path = catalog_path or settings.catalog_path

    if resolved_backend == "json":
        if not resolved_path:
            return lambda: UnavailableCatalogRepository(
                "OPENALEX_CATALOG_PATH is required when catalog_backend='json'."
            )
        return lambda: JsonOpenAlexCatalogRepository(resolved_path)

    if resolved_backend == "postgres":
        return OpenAlexCatalogRepository

    if resolved_backend != "auto":
        raise ValueError(
            "catalog_backend must be one of: auto, json, postgres"
        )

    if resolved_path:
        return lambda: JsonOpenAlexCatalogRepository(resolved_path)

    if settings.db_host and settings.db_name and settings.db_user:
        return OpenAlexCatalogRepository

    return lambda: UnavailableCatalogRepository(
        "Natural-language keyword/topic modes require a catalog. "
        "Configure Postgres DB_* settings or set OPENALEX_CATALOG_PATH to a JSON "
        "catalog file."
    )


def _parse_keyword_record(raw: object) -> KeywordCandidate:
    if not isinstance(raw, dict):
        raise RuntimeError("Each keyword catalog record must be a JSON object.")
    keyword = str(raw.get("keyword", "")).strip()
    if not keyword:
        raise RuntimeError("Keyword catalog records must include 'keyword'.")
    alias = str(raw.get("alias") or normalize_alias(keyword)).strip()
    if not alias:
        raise RuntimeError("Keyword catalog records must include a valid alias.")
    return KeywordCandidate(
        keyword_id=int(raw.get("keyword_id")),
        keyword=keyword,
        alias=alias,
        topic_count=int(raw.get("topic_count", 0) or 0),
    )


def _parse_topic_record(raw: object) -> TopicCandidate:
    if not isinstance(raw, dict):
        raise RuntimeError("Each topic catalog record must be a JSON object.")
    topic_name = str(raw.get("topic_name", "")).strip()
    if not topic_name:
        raise RuntimeError("Topic catalog records must include 'topic_name'.")
    return TopicCandidate(
        topic_id=int(raw.get("topic_id")),
        topic_name=topic_name,
        summary=_optional_string(raw.get("summary")),
        field_name=_optional_string(raw.get("field_name")),
        subfield_name=_optional_string(raw.get("subfield_name")),
        keywords=_optional_string(raw.get("keywords")),
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
