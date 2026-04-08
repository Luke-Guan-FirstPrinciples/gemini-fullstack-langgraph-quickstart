"""Small FastAPI wrapper around the research agent pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from research_agent.config import Settings
from research_agent.graph import run_research

app = FastAPI(title="Research Agent Backend", version="0.1.0")


class ResearchAgentRunRequest(BaseModel):
    """HTTP request body for launching a research-agent run."""

    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(min_length=3)
    llm_provider: str | None = Field(default=None, alias="llmProvider")
    llm_model: str | None = Field(default=None, alias="llmModel")
    search_provider: str | None = Field(default=None, alias="searchProvider")
    max_iterations: int | None = Field(default=None, alias="maxIterations", ge=0, le=6)
    results_per_query: int | None = Field(default=None, alias="resultsPerQuery", ge=1, le=20)
    semantic_weight: float | None = Field(default=None, alias="semanticWeight", ge=0)
    citation_weight: float | None = Field(default=None, alias="citationWeight", ge=0)
    fwci_weight: float | None = Field(default=None, alias="fwciWeight", ge=0)

    @model_validator(mode="after")
    def validate_weights(self) -> "ResearchAgentRunRequest":
        """If any ranking weight is provided, require at least one positive weight."""
        weights = [
            value
            for value in [
                self.semantic_weight,
                self.citation_weight,
                self.fwci_weight,
            ]
            if value is not None
        ]
        if weights and sum(weights) <= 0:
            raise ValueError("At least one ranking weight must be greater than zero.")
        return self


def _build_settings(payload: ResearchAgentRunRequest) -> Settings:
    cfg = Settings()
    if payload.llm_provider:
        cfg.llm_provider = payload.llm_provider
    if payload.llm_model:
        cfg.llm_model = payload.llm_model
        cfg.configured_llm_model = ""
    if payload.search_provider:
        cfg.search_provider = payload.search_provider
    if payload.results_per_query is not None:
        cfg.results_per_query = payload.results_per_query
    if payload.semantic_weight is not None:
        cfg.semantic_relevance_weight = payload.semantic_weight
    if payload.citation_weight is not None:
        cfg.citation_count_weight = payload.citation_weight
    if payload.fwci_weight is not None:
        cfg.fwci_weight = payload.fwci_weight
    return cfg


def _build_meta(
    payload: ResearchAgentRunRequest,
    cfg: Settings,
    final_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "query": payload.query,
        "llm_provider": cfg.llm_provider,
        "llm_model": cfg.resolved_llm_model(),
        "search_provider": cfg.search_provider,
        "ranking_weights": cfg.ranking_weights(),
        "iterations": final_state.get("iteration", 0),
        "total_raw_results": len(final_state.get("all_search_results", [])),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/")
def healthcheck() -> dict[str, str]:
    """Return a basic health payload."""
    return {"status": "ok"}


@app.post("/run", response_model=None)
async def run_pipeline(payload: ResearchAgentRunRequest) -> Any:
    """Run the research agent and return both structured and ranked outputs."""
    cfg = _build_settings(payload)

    try:
        final_state = await run_research(
            payload.query,
            cfg=cfg,
            max_iterations=payload.max_iterations,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Research agent run failed: {exc}",
        ) from exc

    meta = _build_meta(payload, cfg, final_state)
    structured_output = dict(final_state.get("structured_output") or {})
    ranked_output = dict(final_state.get("ranked_output") or {})
    structured_output["_meta"] = meta
    if ranked_output:
        ranked_output["_meta"] = meta

    return {
        "parsed_query": final_state.get("parsed_query"),
        "structured_output": structured_output,
        "ranked_output": ranked_output,
        "meta": meta,
    }
