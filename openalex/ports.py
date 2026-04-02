from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal, Protocol

from .schemas import (
    CandidateSelection,
    CandidateVerificationItem,
    KeywordCandidate,
    OpenAlexPipelineOptions,
    SelectedKeyword,
    SelectedTopic,
    TopicCandidate,
)

if TYPE_CHECKING:
    from .validation import QueryValidationResult


class CandidateSelector(Protocol):
    async def select(
        self,
        *,
        query: str,
        candidate_type: Literal["keyword", "topic"],
        candidates: list[KeywordCandidate] | list[TopicCandidate],
        options: OpenAlexPipelineOptions,
    ) -> list[CandidateSelection]: ...


class CandidateVerifier(Protocol):
    async def verify(
        self,
        *,
        original_query: str,
        query_focus: str | None,
        candidate_type: Literal["keyword", "topic", "author_topic"],
        candidates: list[SelectedKeyword] | list[SelectedTopic],
        options: OpenAlexPipelineOptions,
    ) -> list[CandidateVerificationItem]: ...


class CatalogRepository(Protocol):
    async def __aenter__(self) -> "CatalogRepository": ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    async def fetch_keyword_catalog(self) -> list[KeywordCandidate]: ...

    async def fetch_topic_catalog(self) -> list[TopicCandidate]: ...

    async def resolve_topic_names(self, topic_ids: list[int]) -> dict[int, str]: ...


class QueryValidator(Protocol):
    async def validate(self, query: str) -> "QueryValidationResult": ...


CatalogRepositoryFactory = Callable[[], CatalogRepository]


@dataclass(slots=True)
class OpenAlexDependencies:
    candidate_selector: CandidateSelector | None = None
    candidate_verifier: CandidateVerifier | None = None
    catalog_repository_factory: CatalogRepositoryFactory | None = None
    query_validator: QueryValidator | None = None
