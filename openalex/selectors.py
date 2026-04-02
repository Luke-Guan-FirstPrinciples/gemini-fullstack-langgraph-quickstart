from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from .ports import CandidateSelector
from .schemas import (
    CandidateSelection,
    KeywordCandidate,
    OpenAlexPipelineOptions,
    TopicCandidate,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HeuristicCandidateSelector:
    reason_template: str = "Selected by lexical fallback ranking."

    async def select(
        self,
        *,
        query: str,
        candidate_type: Literal["keyword", "topic"],
        candidates: list[KeywordCandidate] | list[TopicCandidate],
        options: OpenAlexPipelineOptions,
    ) -> list[CandidateSelection]:
        del query, candidate_type
        candidate_ids = [
            candidate.keyword_id
            if isinstance(candidate, KeywordCandidate)
            else candidate.topic_id
            for candidate in candidates
        ]
        return [
            CandidateSelection(
                candidate_id=candidate_id,
                selection_reason=self.reason_template,
            )
            for candidate_id in candidate_ids[: options.selection_limit]
        ]


async def select_candidates(
    *,
    query: str,
    candidate_type: Literal["keyword", "topic"],
    candidates: list[KeywordCandidate] | list[TopicCandidate],
    options: OpenAlexPipelineOptions,
    selector: CandidateSelector | None = None,
) -> tuple[list[CandidateSelection], str]:
    heuristic_selector = HeuristicCandidateSelector()
    requested_strategy = (options.selector_strategy or "heuristic").lower()

    if requested_strategy == "heuristic":
        return (
            await heuristic_selector.select(
                query=query,
                candidate_type=candidate_type,
                candidates=candidates,
                options=options,
            ),
            "heuristic",
        )

    if selector is None:
        if not options.fallback_to_heuristic:
            raise RuntimeError(
                "Selector strategy requires an injected candidate selector. "
                "Provide one via OpenAlexDependencies(candidate_selector=...) or "
                "switch to selector_strategy='heuristic'."
            )
        fallback_selector = HeuristicCandidateSelector(
            reason_template=(
                "Selected by lexical fallback ranking because no external selector "
                "was configured."
            )
        )
        return (
            await fallback_selector.select(
                query=query,
                candidate_type=candidate_type,
                candidates=candidates,
                options=options,
            ),
            "heuristic",
        )

    try:
        return (
            await selector.select(
                query=query,
                candidate_type=candidate_type,
                candidates=candidates,
                options=options,
            ),
            requested_strategy,
        )
    except Exception as exc:
        if not options.fallback_to_heuristic:
            raise
        logger.warning(
            "Candidate selector failed, falling back to heuristic ranking: %s",
            exc,
        )
        fallback_selector = HeuristicCandidateSelector(
            reason_template=(
                "Selected by lexical fallback ranking after the external selector "
                "failed."
            )
        )
        return (
            await fallback_selector.select(
                query=query,
                candidate_type=candidate_type,
                candidates=candidates,
                options=options,
            ),
            "heuristic",
        )
