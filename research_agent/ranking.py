"""Paper reranking helpers for the research-agent pipeline."""

from __future__ import annotations

import logging
import math
import re

from research_agent.config import Settings
from research_agent.llm import create_llm, with_structured_output
from research_agent.models import Paper, PaperRanking, PaperRelevanceBatch, RankedResults
from research_agent.prompts import RERANK_RESULTS_HUMAN, RERANK_RESULTS_SYSTEM

logger = logging.getLogger("research_agent.ranking")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


async def rerank_papers(
    query: str,
    papers: list[Paper],
    cfg: Settings,
) -> RankedResults:
    """Score and rank papers using semantic relevance plus bibliometric signals."""
    if not papers:
        return RankedResults(
            query=query,
            weights=_normalize_weights(cfg.ranking_weights()),
            normalization=_normalization_meta(),
            papers=[],
        )

    semantic_scores = await _score_semantic_relevance(query, papers, cfg)
    weights = _normalize_weights(cfg.ranking_weights())

    citation_scale = _max_log_signal(
        [
            float(paper.openalex.citation_count or 0)
            for paper in papers
            if paper.openalex and paper.openalex.citation_count is not None
        ]
    )
    fwci_scale = _max_log_signal(
        [
            float(paper.openalex.fwci or 0.0)
            for paper in papers
            if paper.openalex and paper.openalex.fwci is not None
        ]
    )

    ranked_papers: list[Paper] = []
    for paper, semantic_score in zip(papers, semantic_scores):
        paper_copy = paper.model_copy(deep=True)
        citation_count = float(paper.openalex.citation_count or 0) if paper.openalex else 0.0
        fwci = float(paper.openalex.fwci or 0.0) if paper.openalex else 0.0
        normalized_signals = {
            "semantic_relevance": _clamp_score(semantic_score),
            "citation_count": _normalize_log_signal(citation_count, citation_scale),
            "fwci": _normalize_log_signal(max(fwci, 0.0), fwci_scale),
        }
        paper_copy.ranking = PaperRanking(
            score=round(_weighted_score(normalized_signals, weights), 6),
            normalized_signals={
                name: round(value, 6) for name, value in normalized_signals.items()
            },
        )
        ranked_papers.append(paper_copy)

    ranked_papers.sort(
        key=lambda paper: (
            -(paper.ranking.score if paper.ranking else 0.0),
            -(paper.ranking.normalized_signals.get("semantic_relevance", 0.0) if paper.ranking else 0.0),
            -(paper.openalex.citation_count or 0) if paper.openalex else 0,
            paper.title.lower(),
        )
    )

    for index, paper in enumerate(ranked_papers, start=1):
        if paper.ranking:
            paper.ranking.rank = index

    logger.info("Ranked %d papers", len(ranked_papers))
    return RankedResults(
        query=query,
        weights=weights,
        normalization=_normalization_meta(),
        papers=ranked_papers,
    )


async def _score_semantic_relevance(
    query: str,
    papers: list[Paper],
    cfg: Settings,
) -> list[float]:
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = create_llm(cfg.llm_provider, cfg.rerank_model_name(), temperature=0)
    structured_llm = with_structured_output(
        llm,
        PaperRelevanceBatch,
        provider=cfg.llm_provider,
    )
    scores: list[float] = []
    batch_size = max(1, cfg.rerank_batch_size)

    for start in range(0, len(papers), batch_size):
        batch = papers[start : start + batch_size]
        paper_lines = []
        for offset, paper in enumerate(batch, start=1):
            summary = paper.key_finding or paper.abstract or ""
            paper_lines.append(
                (
                    f"[{offset}] {paper.title}\n"
                    f"    Year: {paper.year or 'unknown'}\n"
                    f"    Source: {paper.source or 'unknown'}\n"
                    f"    Authors: {', '.join(paper.authors) if paper.authors else 'unknown'}\n"
                    f"    Summary: {summary or 'n/a'}"
                )
            )

        fallback_scores = [_fallback_semantic_relevance(query, paper) for paper in batch]

        try:
            result: PaperRelevanceBatch = await structured_llm.ainvoke(
                [
                    SystemMessage(content=RERANK_RESULTS_SYSTEM),
                    HumanMessage(
                        content=RERANK_RESULTS_HUMAN.format(
                            query=query,
                            papers_text="\n\n".join(paper_lines),
                        )
                    ),
                ]
            )
            batch_scores = list(fallback_scores)
            for item in result.scores:
                if 1 <= item.paper_index <= len(batch_scores):
                    batch_scores[item.paper_index - 1] = _clamp_score(item.semantic_relevance)
            scores.extend(batch_scores)
        except Exception:
            logger.exception(
                "Semantic reranking failed for papers %d-%d; using fallback scores",
                start + 1,
                start + len(batch),
            )
            scores.extend(fallback_scores)

    return scores


def _fallback_semantic_relevance(query: str, paper: Paper) -> float:
    query_tokens = set(_TOKEN_RE.findall(query.lower()))
    text = " ".join(
        value
        for value in [paper.title, paper.abstract, paper.key_finding, " ".join(paper.authors)]
        if value
    ).lower()
    paper_tokens = set(_TOKEN_RE.findall(text))
    if not query_tokens or not paper_tokens:
        return 0.0

    overlap = len(query_tokens & paper_tokens) / len(query_tokens)
    title_overlap = len(query_tokens & set(_TOKEN_RE.findall(paper.title.lower()))) / len(query_tokens)
    return _clamp_score((0.65 * overlap) + (0.35 * title_overlap))


def _weighted_score(signals: dict[str, float], weights: dict[str, float]) -> float:
    return sum(weights.get(name, 0.0) * signals.get(name, 0.0) for name in weights)


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {name: max(float(value), 0.0) for name, value in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return {
            "semantic_relevance": 1.0,
            "citation_count": 0.0,
            "fwci": 0.0,
        }
    return {name: round(value / total, 6) for name, value in cleaned.items()}


def _max_log_signal(values: list[float]) -> float:
    if not values:
        return 0.0
    return max(math.log1p(max(value, 0.0)) for value in values)


def _normalize_log_signal(value: float, scale: float) -> float:
    if value <= 0 or scale <= 0:
        return 0.0
    return _clamp_score(math.log1p(value) / scale)


def _clamp_score(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _normalization_meta() -> dict[str, str]:
    return {
        "semantic_relevance": "llm score in [0,1] with lexical fallback",
        "citation_count": "log1p(citation_count) scaled by max paper citation count in run",
        "fwci": "log1p(fwci) scaled by max paper fwci in run",
    }
