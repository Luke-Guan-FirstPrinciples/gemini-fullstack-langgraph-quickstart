from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PipelineMode(str, Enum):
    NATURAL_LANGUAGE_KEYWORDS_AND_TOPICS = "natural_language_keywords_and_topics"
    NATURAL_LANGUAGE_KEYWORDS = "natural_language_keywords"
    NATURAL_LANGUAGE_TOPICS = "natural_language_topics"
    OPENALEX_QUERY_KEYWORDS = "openalex_query_keywords"
    EXACT_OPENALEX_QUERY = "exact_openalex_query"


class RetrievalTarget(str, Enum):
    WORKS = "works"
    AUTHORS = "authors"
    WORKS_AND_AUTHORS = "works_and_authors"


class KeywordCandidate(BaseModel):
    keyword_id: int
    keyword: str
    alias: str
    topic_count: int = 0
    lexical_score: float = 0.0


class TopicCandidate(BaseModel):
    topic_id: int
    topic_name: str
    summary: str | None = None
    field_name: str | None = None
    subfield_name: str | None = None
    keywords: str | None = None
    lexical_score: float = 0.0


class CandidateSelection(BaseModel):
    candidate_id: int
    selection_reason: str


class CandidateSelectionResponse(BaseModel):
    items: list[CandidateSelection] = Field(default_factory=list)


class CandidateVerificationItem(BaseModel):
    candidate_id: int
    include: bool
    reason: str


class CandidateVerificationResponse(BaseModel):
    items: list[CandidateVerificationItem] = Field(default_factory=list)


class CandidateVerificationRecord(BaseModel):
    candidate_type: Literal["keyword", "topic", "author_topic"]
    candidate_id: int
    label: str
    source_value: str
    included: bool
    verified: bool
    verifier: str
    reason: str
    lexical_score: float | None = None
    selection_rank: int | None = None
    selection_reason: str | None = None


class PipelineLogEntry(BaseModel):
    stage: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class LlmTokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class LlmCallRecord(BaseModel):
    provider: str
    purpose: str
    stage: str
    model: str
    original_query: str
    query_focus: str | None = None
    candidate_type: Literal["keyword", "topic", "author_topic"]
    candidate_count: int
    prompt: str
    parsed_item_count: int | None = None
    usage: LlmTokenUsage = Field(default_factory=LlmTokenUsage)
    input_price_per_million_tokens_usd: float | None = None
    output_price_per_million_tokens_usd: float | None = None
    estimated_cost_usd: float | None = None


class LlmUsageSummary(BaseModel):
    total_calls: int = 0
    calls_with_usage: int = 0
    calls_with_estimated_cost: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_estimated_cost_usd: float | None = None
    currency: str = "USD"


class AppliedQueryModifier(BaseModel):
    source_phrase: str
    filter_fragment: str
    reason: str


class ExactOpenAlexQuery(BaseModel):
    endpoint: str = "/works"
    search: str | None = None
    filter: str | None = None
    sort: str | None = None
    per_page: int | None = None
    page: int | None = None
    cursor: str | None = None
    extra_params: dict[str, str] = Field(default_factory=dict)
    original_input: str | None = None

    def to_query_params(
        self,
        *,
        per_page_override: int | None = None,
        cursor_override: str | None = None,
    ) -> dict[str, str]:
        params: dict[str, str] = dict(self.extra_params)
        if self.search:
            params["search"] = self.search
        if self.filter:
            params["filter"] = self.filter
        if self.sort:
            params["sort"] = self.sort
        effective_per_page = per_page_override or self.per_page
        if effective_per_page is not None:
            params["per-page"] = str(effective_per_page)
        if self.page is not None and cursor_override is None and self.cursor is None:
            params["page"] = str(self.page)
        effective_cursor = cursor_override or self.cursor
        if effective_cursor is not None:
            params["cursor"] = effective_cursor
            params.pop("page", None)
        return params


class QueryBundle(BaseModel):
    label: str
    source_kind: str
    source_value: str
    query: ExactOpenAlexQuery


class SelectedKeyword(BaseModel):
    keyword_id: int
    keyword: str
    alias: str
    topic_count: int
    lexical_score: float
    selection_rank: int
    selection_reason: str


class SelectedTopic(BaseModel):
    topic_id: int
    openalex_id: str
    topic_name: str
    field_name: str | None = None
    subfield_name: str | None = None
    lexical_score: float
    selection_rank: int
    selection_reason: str


class QueryExecution(BaseModel):
    entity_type: str
    label: str
    source_kind: str
    source_value: str
    query: ExactOpenAlexQuery
    max_results_requested: int
    per_page_requested: int
    request_params: dict[str, str]
    request_urls: list[str]
    api_result_count: int | None = None
    returned_count: int = 0
    result_ids: list[str] = Field(default_factory=list)


class MatchedQuery(BaseModel):
    label: str
    source_kind: str
    source_value: str


class PaperAuthor(BaseModel):
    name: str
    openalex_id: str | None = None


class PaperLocation(BaseModel):
    source_display_name: str | None = None
    source_openalex_id: str | None = None
    landing_page_url: str | None = None
    pdf_url: str | None = None
    is_oa: bool | None = None


class OpenAlexPaper(BaseModel):
    openalex_id: str
    title: str
    cited_by_count: int = 0
    publication_year: int | None = None
    publication_date: str | None = None
    doi: str | None = None
    work_type: str | None = None
    primary_location: PaperLocation | None = None
    authors: list[PaperAuthor] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    matched_queries: list[MatchedQuery] = Field(default_factory=list)
    matched_query_count: int = 0
    overlap_type: str = "unique"


class AuthorInstitution(BaseModel):
    display_name: str
    openalex_id: str | None = None
    country_code: str | None = None
    institution_type: str | None = None


class AuthorSummaryStats(BaseModel):
    two_year_mean_citedness: float | None = None
    h_index: int | None = None
    i10_index: int | None = None


class AuthorTopic(BaseModel):
    openalex_id: str
    display_name: str
    count: int | None = None


class OpenAlexAuthor(BaseModel):
    openalex_id: str
    display_name: str
    orcid: str | None = None
    works_count: int = 0
    cited_by_count: int = 0
    summary_stats: AuthorSummaryStats | None = None
    last_known_institutions: list[AuthorInstitution] = Field(default_factory=list)
    topics: list[AuthorTopic] = Field(default_factory=list)
    matched_queries: list[MatchedQuery] = Field(default_factory=list)
    matched_query_count: int = 0
    overlap_type: str = "unique"


class QuerySummary(BaseModel):
    label: str
    source_kind: str
    returned_count: int
    unique_count: int
    overlap_count: int


class RunSummary(BaseModel):
    total_queries_executed: int
    total_results_retrieved: int
    total_unique_results: int
    overlap_results: int
    unique_only_results: int
    top_k_returned: int
    query_summaries: list[QuerySummary] = Field(default_factory=list)


class OpenAlexPipelineOptions(BaseModel):
    mode: PipelineMode = PipelineMode.NATURAL_LANGUAGE_KEYWORDS_AND_TOPICS
    target: RetrievalTarget = RetrievalTarget.WORKS
    candidate_limit: int = 30
    selection_limit: int = 5
    max_results_per_query: int = 20
    per_page: int = 200
    top_k: int = 25
    parallel: int = 4
    max_author_topics_per_keyword: int = 1
    selector_model: str | None = None
    selector_strategy: str = "heuristic"
    selector_temperature: float = 1.0
    fallback_to_heuristic: bool = True
    verify_candidate_relevance: bool = True
    verifier_model: str | None = None
    verifier_temperature: float = 0.0
    fallback_to_unverified_candidates: bool = True
    generated_query_sort: str = "cited_by_count:desc"
    request_timeout_seconds: float = 30.0
    max_authors_per_paper: int = 12
    check_valid_topic: bool = True
    save_output: bool = True
    output_dir: str | None = None
    output_filename: str = "results.json"


class OpenAlexRunResult(BaseModel):
    workflow_name: str = "openalex"
    mode: PipelineMode
    target: RetrievalTarget = RetrievalTarget.WORKS
    input_query: str
    selector_model: str | None = None
    selector_strategy: str
    exact_query: ExactOpenAlexQuery | None = None
    query_modifiers: list[AppliedQueryModifier] = Field(default_factory=list)
    selected_keywords: list[SelectedKeyword] = Field(default_factory=list)
    selected_topics: list[SelectedTopic] = Field(default_factory=list)
    selected_author_topics: list[SelectedTopic] = Field(default_factory=list)
    candidate_verifications: list[CandidateVerificationRecord] = Field(
        default_factory=list
    )
    logs: list[PipelineLogEntry] = Field(default_factory=list)
    llm_calls: list[LlmCallRecord] = Field(default_factory=list)
    llm_usage_summary: LlmUsageSummary | None = None
    executions: list[QueryExecution] = Field(default_factory=list)
    summary: RunSummary | None = None
    author_executions: list[QueryExecution] = Field(default_factory=list)
    author_summary: RunSummary | None = None
    papers: list[OpenAlexPaper] = Field(default_factory=list)
    authors: list[OpenAlexAuthor] = Field(default_factory=list)
    output_path: str | None = None
    logs_output_path: str | None = None
    llm_calls_output_path: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
