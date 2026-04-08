"""Pydantic models for the research agent pipeline."""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Search provider models
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    """A single result from a search provider."""

    title: str = ""
    url: str = ""
    snippet: str = ""
    source: str = ""  # e.g. "arxiv", "nature", derived from URL domain


# ---------------------------------------------------------------------------
# LLM structured-output models
# ---------------------------------------------------------------------------

class ParsedQuery(BaseModel):
    """LLM-extracted intent from the user's natural language query."""

    intent: str = Field(default="", description="What the user is looking for")
    fields: list[str] = Field(default_factory=list, description="Research fields/topics")
    key_terms: list[str] = Field(default_factory=list, description="Important search terms and synonyms")
    date_constraint: str | None = Field(default=None, description="Date filter, e.g. 'after:2024'")
    search_queries: list[str] = Field(
        default_factory=list,
        description="3-5 search queries with site: operators targeting academic sources",
    )


class Paper(BaseModel):
    """An academic paper extracted from search results."""

    title: str
    authors: list[str] = Field(default_factory=list)
    source: str = Field(default="", description="Publisher/platform: arxiv, nature, etc.")
    url: str = ""
    year: int | None = None
    abstract: str = ""
    doi: str | None = None
    key_finding: str = Field(default="", description="One-sentence summary of the main contribution")
    openalex: "PaperOpenAlexEnrichment | None" = None
    ranking: "PaperRanking | None" = None


class StructuredPaper(BaseModel):
    """LLM-only paper schema before enrichment and reranking."""

    title: str
    authors: list[str] = Field(default_factory=list)
    source: str = Field(default="", description="Publisher/platform: arxiv, nature, etc.")
    url: str = ""
    year: int | None = None
    abstract: str = ""
    doi: str | None = None
    key_finding: str = Field(default="", description="One-sentence summary of the main contribution")


class PaperOpenAlexEnrichment(BaseModel):
    """Normalized metadata pulled from OpenAlex for a paper."""

    status: Literal["matched", "not_found", "error"] = "not_found"
    openalex_id: str | None = None
    matched_title: str | None = None
    title_similarity: float | None = None
    search_relevance_score: float | None = None
    citation_count: int | None = None
    fwci: float | None = None
    citation_normalized_percentile: float | None = None
    is_in_top_1_percent: bool | None = None
    is_in_top_10_percent: bool | None = None
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    publication_year: int | None = None
    source_display_name: str | None = None
    landing_page_url: str | None = None
    error: str | None = None


class PaperRanking(BaseModel):
    """Ranking metadata assigned after enrichment."""

    rank: int | None = None
    score: float = 0.0
    normalized_signals: dict[str, float] = Field(default_factory=dict)


class Author(BaseModel):
    """A researcher identified from the search results."""

    name: str
    affiliations: list[str] = Field(default_factory=list)
    research_areas: list[str] = Field(default_factory=list)


class Lab(BaseModel):
    """A research lab or institution."""

    name: str
    institution: str = ""
    url: str | None = None
    key_researchers: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)


class ResearchOutput(BaseModel):
    """The full structured output of the research pipeline."""

    papers: list[Paper] = Field(default_factory=list)
    authors: list[Author] = Field(default_factory=list)
    labs: list[Lab] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    sub_queries: list[str] = Field(default_factory=list, description="Suggested follow-up queries")


class StructuredResearchOutput(BaseModel):
    """LLM-only structured output before enrichment and reranking."""

    papers: list[StructuredPaper] = Field(default_factory=list)
    authors: list[Author] = Field(default_factory=list)
    labs: list[Lab] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    sub_queries: list[str] = Field(default_factory=list, description="Suggested follow-up queries")


class CoverageAssessment(BaseModel):
    """LLM assessment of whether the search results sufficiently cover the query."""

    is_sufficient: bool = True
    gaps: list[str] = Field(default_factory=list, description="Topics/areas not yet covered")
    sub_queries: list[str] = Field(default_factory=list, description="Queries to fill the gaps")


class PaperRelevanceScore(BaseModel):
    """Semantic-relevance score for one paper in a reranking batch."""

    paper_index: int
    semantic_relevance: float = Field(
        default=0.0,
        description="Relevance from 0.0 to 1.0 based only on semantic fit to the query.",
    )


class PaperRelevanceBatch(BaseModel):
    """Batch of semantic-relevance scores returned by the LLM."""

    scores: list[PaperRelevanceScore] = Field(default_factory=list)


class RankedResults(BaseModel):
    """Final ranked paper list plus ranking metadata."""

    query: str
    weights: dict[str, float] = Field(default_factory=dict)
    normalization: dict[str, str] = Field(default_factory=dict)
    papers: list[Paper] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------

class ResearchState(TypedDict):
    """LangGraph state for the research pipeline."""

    query: str
    parsed_query: dict | None
    search_queries: list[str]
    # Annotated with `add` so results accumulate across loop iterations
    all_search_results: Annotated[list[dict], add]
    structured_output: dict | None
    ranked_output: dict | None
    iteration: int
    max_iterations: int
