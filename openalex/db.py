from __future__ import annotations

from typing import Any

from .config import settings
from .schemas import KeywordCandidate, TopicCandidate


class OpenAlexCatalogRepository:
    def __init__(self) -> None:
        self._conn: Any = None

    def _require_db_value(self, value: str | None, name: str) -> str:
        if not value:
            raise RuntimeError(
                f"{name} is required for Postgres-backed OpenAlex catalog lookup. "
                "Set the database settings in .env before using keyword/topic modes."
            )
        return value

    async def connect(self) -> None:
        if self._conn is not None:
            return
        try:
            import asyncpg
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "asyncpg is required for Postgres-backed catalog access. "
                "Install it or use a JSON catalog via OPENALEX_CATALOG_PATH."
            ) from exc

        self._conn = await asyncpg.connect(
            user=self._require_db_value(settings.db_user, "DB_USER"),
            password=self._require_db_value(settings.db_password, "DB_PASSWORD"),
            host=self._require_db_value(settings.db_host, "DB_HOST"),
            port=settings.db_port,
            database=self._require_db_value(settings.db_name, "DB_NAME"),
        )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "OpenAlexCatalogRepository":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    def _require_conn(self) -> Any:
        if self._conn is None:
            raise RuntimeError(
                "OpenAlexCatalogRepository.connect() must be called first"
            )
        return self._conn

    async def fetch_keyword_catalog(self) -> list[KeywordCandidate]:
        conn = self._require_conn()
        rows = await conn.fetch(
            """
            select
                e.keyword_id,
                e.keyword,
                e.alias,
                coalesce(k.topic_count, 0) as topic_count
            from openalex.oa_physics_related_keyword_embeddings e
            left join openalex.oa_physics_related_keywords k
              on k.keyword_id = e.keyword_id
            order by k.topic_count desc nulls last, e.keyword asc
            """
        )
        return [
            KeywordCandidate(
                keyword_id=row["keyword_id"],
                keyword=row["keyword"],
                alias=row["alias"],
                topic_count=row["topic_count"],
            )
            for row in rows
        ]

    async def fetch_topic_catalog(self) -> list[TopicCandidate]:
        conn = self._require_conn()
        rows = await conn.fetch(
            """
            select
                e.topic_id,
                e.topic_name,
                e.summary,
                f.field_name,
                f.subfield_name,
                f.keywords
            from openalex.oa_physics_related_topic_summary_embeddings e
            left join openalex.oa_physics_related_fields_only f
              on f.topic_id = e.topic_id
            order by e.topic_name asc
            """
        )
        return [
            TopicCandidate(
                topic_id=row["topic_id"],
                topic_name=row["topic_name"],
                summary=row["summary"],
                field_name=row["field_name"],
                subfield_name=row["subfield_name"],
                keywords=row["keywords"],
            )
            for row in rows
        ]

    async def resolve_topic_names(self, topic_ids: list[int]) -> dict[int, str]:
        if not topic_ids:
            return {}
        conn = self._require_conn()
        rows = await conn.fetch(
            """
            select topic_id, topic_name
            from openalex.oa_physics_related_topic_summary_embeddings
            where topic_id = any($1::bigint[])
            """,
            topic_ids,
        )
        return {int(row["topic_id"]): str(row["topic_name"]) for row in rows}
