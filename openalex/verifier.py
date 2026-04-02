from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from .config import settings
from .prompts import SYSTEM_OPENALEX_VERIFIER
from .schemas import (
    CandidateVerificationItem,
    CandidateVerificationResponse,
    OpenAlexPipelineOptions,
    SelectedKeyword,
    SelectedTopic,
)

logger = logging.getLogger(__name__)


def _serialize_candidate(
    candidate: SelectedKeyword | SelectedTopic,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": (
            candidate.keyword_id
            if isinstance(candidate, SelectedKeyword)
            else candidate.topic_id
        ),
        "label": (
            candidate.keyword
            if isinstance(candidate, SelectedKeyword)
            else candidate.topic_name
        ),
        "lexical_score": candidate.lexical_score,
        "selection_rank": candidate.selection_rank,
        "selection_reason": candidate.selection_reason,
    }
    if isinstance(candidate, SelectedKeyword):
        payload["source_value"] = candidate.alias
        payload["topic_count"] = candidate.topic_count
    else:
        payload["source_value"] = candidate.openalex_id
        payload["field_name"] = candidate.field_name
        payload["subfield_name"] = candidate.subfield_name
    return payload


def _build_prompt(
    *,
    original_query: str,
    query_focus: str | None,
    candidate_type: Literal["keyword", "topic", "author_topic"],
    candidates: list[SelectedKeyword] | list[SelectedTopic],
) -> str:
    prompt_parts = [
        SYSTEM_OPENALEX_VERIFIER,
        "",
        f"Original query: {original_query}",
        f"Normalized topical focus: {query_focus or original_query}",
        f"Candidate type: {candidate_type}",
        "Candidates:",
        json.dumps(
            [_serialize_candidate(candidate) for candidate in candidates],
            indent=2,
            ensure_ascii=True,
        ),
        "",
        (
            "Return one decision per candidate. Set include=true only when the "
            "candidate would improve OpenAlex precision for this query."
        ),
    ]
    return "\n".join(prompt_parts)


@dataclass(slots=True)
class GeminiCandidateVerifier:
    model: str | None = None
    temperature: float = 0.0
    api_key: str | None = None

    async def verify(
        self,
        *,
        original_query: str,
        query_focus: str | None,
        candidate_type: Literal["keyword", "topic", "author_topic"],
        candidates: list[SelectedKeyword] | list[SelectedTopic],
        options: OpenAlexPipelineOptions,
    ) -> list[CandidateVerificationItem]:
        if not candidates:
            return []

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "langchain_google_genai is required for Gemini candidate "
                "verification."
            ) from exc

        api_key = self.api_key or settings.gemini_api_key
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY or GOOGLE_API_KEY is required for candidate "
                "verification."
            )

        model_name = self.model or options.verifier_model or settings.verifier_model
        logger.info(
            "Verifying %s OpenAlex candidates with Gemini model %s",
            candidate_type,
            model_name,
        )
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=(
                options.verifier_temperature
                if options.verifier_temperature is not None
                else self.temperature
            ),
            max_retries=2,
            api_key=api_key,
        )
        structured_llm = llm.with_structured_output(CandidateVerificationResponse)
        result = await structured_llm.ainvoke(
            _build_prompt(
                original_query=original_query,
                query_focus=query_focus,
                candidate_type=candidate_type,
                candidates=candidates,
            )
        )

        candidate_ids = [
            candidate.keyword_id
            if isinstance(candidate, SelectedKeyword)
            else candidate.topic_id
            for candidate in candidates
        ]
        decision_map: dict[int, CandidateVerificationItem] = {}
        for item in result.items:
            if item.candidate_id not in candidate_ids:
                continue
            if item.candidate_id in decision_map:
                continue
            decision_map[item.candidate_id] = CandidateVerificationItem(
                candidate_id=item.candidate_id,
                include=item.include,
                reason=item.reason.strip() or "No reason provided.",
            )

        missing_ids = [
            candidate_id
            for candidate_id in candidate_ids
            if candidate_id not in decision_map
        ]
        if missing_ids:
            raise RuntimeError(
                "Candidate verification returned incomplete decisions. "
                f"Missing IDs: {missing_ids}"
            )

        return [decision_map[candidate_id] for candidate_id in candidate_ids]
