"""LangGraph research pipeline — the core graph definition and node functions.

Graph topology:
    parse_query → execute_search → structure_results → enrich_results → rerank_results → assess_coverage
                      ↑                                                                  │
                      └────────────────────── (sub-queries, if gaps found) ─────────────┘
"""

import asyncio
import json
import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from research_agent.config import Settings, settings
from research_agent.deduplication import (
    dedupe_papers,
    dedupe_search_results,
    dedupe_structured_papers,
)
from research_agent.enrichment import OpenAlexEnricher, SemanticScholarEnricher
from research_agent.llm import create_llm, with_structured_output
from research_agent.logging_config import setup_logging
from research_agent.models import (
    CoverageAssessment,
    Lab,
    ParsedQuery,
    RankedResults,
    ResearchOutput,
    ResearchState,
    StructuredPaper,
    StructuredResearchOutput,
)
from research_agent.prompts import (
    ASSESS_COVERAGE_HUMAN,
    ASSESS_COVERAGE_SYSTEM,
    PARSE_QUERY_HUMAN,
    PARSE_QUERY_SYSTEM,
    STRUCTURE_RESULTS_HUMAN,
    STRUCTURE_RESULTS_SYSTEM,
)
from research_agent.ranking import rerank_papers
from research_agent.search import create_search_provider

logger = logging.getLogger("research_agent.graph")


def _get_settings(config: Optional[RunnableConfig]) -> Settings:
    """Extract Settings from LangGraph config, falling back to global settings."""
    if config:
        configurable = config.get("configurable", {})
        if configurable and "settings" in configurable:
            return configurable["settings"]
    return settings


# ======================================================================
# Node functions
# ======================================================================


async def parse_query(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Use the LLM to decompose the user query into structured search queries."""
    cfg = _get_settings(config)
    llm = create_llm(cfg.llm_provider, cfg.resolved_llm_model())
    structured_llm = with_structured_output(llm, ParsedQuery, provider=cfg.llm_provider)

    query = state["query"]
    logger.info("Parsing query: %s", query)

    result: ParsedQuery = await structured_llm.ainvoke([
        SystemMessage(content=PARSE_QUERY_SYSTEM),
        HumanMessage(content=PARSE_QUERY_HUMAN.format(query=query)),
    ])

    logger.info("Extracted %d search queries, fields=%s", len(result.search_queries), result.fields)
    logger.debug("Parsed query detail: %s", result.model_dump_json(indent=2))

    return {
        "parsed_query": result.model_dump(),
        "search_queries": result.search_queries,
    }


async def execute_search(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Run all current search queries through the configured search provider."""
    cfg = _get_settings(config)
    provider = create_search_provider(cfg)

    queries = state["search_queries"]
    logger.info("Executing %d search queries (iteration %d)", len(queries), state.get("iteration", 0))

    async def _run(q: str):
        try:
            return await provider.search(q, num_results=cfg.results_per_query)
        except Exception:
            logger.exception("Search failed for query: %s", q)
            return []

    batches = await asyncio.gather(*[_run(q) for q in queries])
    raw_results = [r.model_dump() for batch in batches for r in batch]
    new_results = dedupe_search_results(
        state.get("all_search_results", []),
        raw_results,
    )

    logger.info(
        "Search returned %d raw results; %d new unique results",
        len(raw_results),
        len(new_results),
    )
    return {"all_search_results": new_results}


async def structure_results(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Have the LLM structure raw search results into papers, labs, and metadata.

    Hits are processed in small batches so the LLM can emit a Paper record for
    every plausible hit instead of silently summarising 50+ results into a
    handful. Outputs from all batches are merged and deduplicated before the
    node returns.
    """

    cfg = _get_settings(config)
    llm = create_llm(cfg.llm_provider, cfg.resolved_llm_model())
    structured_llm = with_structured_output(
        llm,
        StructuredResearchOutput,
        provider=cfg.llm_provider,
    )

    all_results = state["all_search_results"]
    query = state["query"]
    total_hits = len(all_results)

    batch_size = max(1, cfg.structure_batch_size)
    batches: list[list[dict[str, Any]]] = [
        all_results[i : i + batch_size] for i in range(0, total_hits, batch_size)
    ] or [[]]
    batch_count = len(batches)

    logger.info(
        "Structuring %d search results in %d batch(es) of up to %d",
        total_hits,
        batch_count,
        batch_size,
    )

    semaphore = asyncio.Semaphore(max(1, cfg.structure_parallelism))

    async def run_batch(
        batch_index: int,
        batch_hits: list[dict[str, Any]],
    ) -> StructuredResearchOutput:
        range_start = batch_index * batch_size + 1
        range_end = range_start + len(batch_hits) - 1 if batch_hits else range_start
        lines = []
        for offset, hit in enumerate(batch_hits):
            idx = range_start + offset
            lines.append(
                f"[{idx}] {hit.get('title', '')}\n"
                f"    URL: {hit.get('url', '')}\n"
                f"    Snippet: {hit.get('snippet', '')}\n"
            )
        results_text = "\n".join(lines) if lines else "(no results)"

        async with semaphore:
            try:
                return await structured_llm.ainvoke([
                    SystemMessage(content=STRUCTURE_RESULTS_SYSTEM),
                    HumanMessage(content=STRUCTURE_RESULTS_HUMAN.format(
                        query=query,
                        batch_index=batch_index + 1,
                        batch_count=batch_count,
                        range_start=range_start,
                        range_end=range_end,
                        total_hits=total_hits,
                        results_text=results_text,
                    )),
                ])
            except Exception:
                logger.exception(
                    "Structuring batch %d/%d failed", batch_index + 1, batch_count
                )
                return StructuredResearchOutput()

    batch_outputs = await asyncio.gather(
        *(run_batch(i, hits) for i, hits in enumerate(batches))
    )

    merged_papers: list[StructuredPaper] = []
    merged_labs: list[Lab] = []
    fields_seen: dict[str, None] = {}
    keywords_seen: dict[str, None] = {}
    sub_queries_seen: dict[str, None] = {}
    lab_keys_seen: set[str] = set()

    for batch_output in batch_outputs:
        merged_papers.extend(batch_output.papers)
        for lab in batch_output.labs:
            key = f"{lab.name.strip().casefold()}|{lab.institution.strip().casefold()}"
            if key in lab_keys_seen:
                continue
            lab_keys_seen.add(key)
            merged_labs.append(lab)
        for field_name in batch_output.fields:
            value = (field_name or "").strip()
            if value:
                fields_seen.setdefault(value, None)
        for keyword in batch_output.keywords:
            value = (keyword or "").strip()
            if value:
                keywords_seen.setdefault(value, None)
        for sub_query in batch_output.sub_queries:
            value = (sub_query or "").strip()
            if value:
                sub_queries_seen.setdefault(value, None)

    deduped_papers = dedupe_structured_papers(merged_papers)

    output = ResearchOutput(
        papers=[paper.model_dump() for paper in deduped_papers],
        labs=[lab.model_dump() for lab in merged_labs],
        fields=list(fields_seen.keys()),
        keywords=list(keywords_seen.keys()),
        sub_queries=list(sub_queries_seen.keys()),
    )

    logger.info(
        "Structured: %d papers (from %d across %d batches), %d labs, %d keywords",
        len(output.papers),
        len(merged_papers),
        batch_count,
        len(output.labs),
        len(output.keywords),
    )
    return {"structured_output": output.model_dump()}


async def enrich_results(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Enrich structured papers with OpenAlex and Semantic Scholar metadata."""
    cfg = _get_settings(config)
    structured = state.get("structured_output") or {}
    output = ResearchOutput.model_validate(structured)

    logger.info("Enriching %d papers with OpenAlex", len(output.papers))
    openalex_enricher = OpenAlexEnricher(cfg)
    enriched_papers = await openalex_enricher.enrich_papers(output.papers)

    logger.info("Enriching %d papers with Semantic Scholar", len(enriched_papers))
    semantic_scholar_enricher = SemanticScholarEnricher(cfg)
    enriched_with_semantic_scholar = await semantic_scholar_enricher.enrich_papers(
        enriched_papers
    )
    output.papers = dedupe_papers(enriched_with_semantic_scholar)

    return {"structured_output": output.model_dump()}


async def rerank_results(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Rerank structured papers using semantic and bibliometric signals."""
    cfg = _get_settings(config)
    structured = state.get("structured_output") or {}
    output = ResearchOutput.model_validate(structured)

    logger.info("Reranking %d papers", len(output.papers))
    ranked: RankedResults = await rerank_papers(state["query"], output.papers, cfg)

    return {"ranked_output": ranked.model_dump()}


async def assess_coverage(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Evaluate whether the results cover the query; generate sub-queries if not."""
    cfg = _get_settings(config)
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", cfg.max_iterations)

    # Skip assessment on last allowed iteration
    if iteration >= max_iter:
        logger.info("Max iterations (%d) reached — skipping coverage assessment", max_iter)
        return {"iteration": iteration + 1, "search_queries": []}

    llm = create_llm(cfg.llm_provider, cfg.resolved_llm_model())
    structured_llm = with_structured_output(
        llm,
        CoverageAssessment,
        provider=cfg.llm_provider,
    )

    structured_text = json.dumps(state.get("structured_output") or {}, indent=2, default=str)

    assessment: CoverageAssessment = await structured_llm.ainvoke([
        SystemMessage(content=ASSESS_COVERAGE_SYSTEM),
        HumanMessage(content=ASSESS_COVERAGE_HUMAN.format(
            query=state["query"],
            structured_text=structured_text[:8000],  # truncate to avoid token limits
        )),
    ])

    logger.info(
        "Coverage sufficient=%s, gaps=%d, sub_queries=%d",
        assessment.is_sufficient, len(assessment.gaps), len(assessment.sub_queries),
    )

    return {
        "iteration": iteration + 1,
        "search_queries": assessment.sub_queries if not assessment.is_sufficient else [],
    }


# ======================================================================
# Conditional edge
# ======================================================================


def should_continue(state: ResearchState) -> str:
    """Decide whether to loop back to search or finish."""
    queries = state.get("search_queries", [])
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", settings.max_iterations)

    if queries and iteration < max_iter:
        logger.info("Looping back to search — %d sub-queries pending", len(queries))
        return "execute_search"
    logger.info("Pipeline complete after %d iteration(s)", iteration)
    return END


# ======================================================================
# Graph builder
# ======================================================================


def build_graph() -> StateGraph:
    """Construct and compile the research agent LangGraph."""
    graph = StateGraph(ResearchState)

    # Nodes
    graph.add_node("parse_query", parse_query)
    graph.add_node("execute_search", execute_search)
    graph.add_node("structure_results", structure_results)
    graph.add_node("enrich_results", enrich_results)
    graph.add_node("rerank_results", rerank_results)
    graph.add_node("assess_coverage", assess_coverage)

    # Edges
    graph.add_edge(START, "parse_query")
    graph.add_edge("parse_query", "execute_search")
    graph.add_edge("execute_search", "structure_results")
    graph.add_edge("structure_results", "enrich_results")
    graph.add_edge("enrich_results", "rerank_results")
    graph.add_edge("rerank_results", "assess_coverage")

    # Conditional: loop or finish
    graph.add_conditional_edges("assess_coverage", should_continue)

    return graph.compile()


# ======================================================================
# Convenience runner
# ======================================================================


async def run_research(
    query: str,
    *,
    cfg: Optional[Settings] = None,
    max_iterations: Optional[int] = None,
) -> dict:
    """Run the full research pipeline and return the final state."""
    setup_logging()
    cfg = cfg or settings
    graph = build_graph()

    initial_state: ResearchState = {
        "query": query,
        "parsed_query": None,
        "search_queries": [],
        "all_search_results": [],
        "structured_output": None,
        "ranked_output": None,
        "iteration": 0,
        "max_iterations": cfg.max_iterations if max_iterations is None else max_iterations,
    }

    logger.info("Starting research pipeline for: %s", query)
    final_state = await graph.ainvoke(
        initial_state,
        config={"configurable": {"settings": cfg}},
    )
    logger.info("Pipeline finished — %d total search results collected", len(final_state["all_search_results"]))

    return final_state
