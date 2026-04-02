from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from .config import settings
from .prompts import SYSTEM_OPENALEX_VERIFIER
from .schemas import (
    CandidateVerificationItem,
    CandidateVerificationResponse,
    LlmCallRecord,
    LlmTokenUsage,
    OpenAlexPipelineOptions,
    SelectedKeyword,
    SelectedTopic,
)

logger = logging.getLogger(__name__)

MODEL_PRICING_PER_MILLION_TOKENS_USD: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (2.25, 18.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
}


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


def _normalize_model_name(model_name: str | None) -> str | None:
    if model_name is None:
        return None
    return model_name.removeprefix("models/").strip() or None


def _resolve_token_pricing(
    model_name: str | None,
) -> tuple[float | None, float | None]:
    if (
        settings.verifier_input_price_per_million_tokens_usd is not None
        and settings.verifier_output_price_per_million_tokens_usd is not None
    ):
        return (
            settings.verifier_input_price_per_million_tokens_usd,
            settings.verifier_output_price_per_million_tokens_usd,
        )

    normalized_model_name = _normalize_model_name(model_name)
    if normalized_model_name is None:
        return None, None
    if normalized_model_name in MODEL_PRICING_PER_MILLION_TOKENS_USD:
        return MODEL_PRICING_PER_MILLION_TOKENS_USD[normalized_model_name]
    for model_prefix, pricing in MODEL_PRICING_PER_MILLION_TOKENS_USD.items():
        if normalized_model_name.startswith(model_prefix):
            return pricing
    return None, None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_usage(raw_message: object | None) -> LlmTokenUsage:
    usage_metadata = getattr(raw_message, "usage_metadata", None)
    if not isinstance(usage_metadata, Mapping):
        usage_metadata = {}

    input_tokens = _coerce_int(usage_metadata.get("input_tokens"))
    output_tokens = _coerce_int(usage_metadata.get("output_tokens"))
    total_tokens = _coerce_int(usage_metadata.get("total_tokens"))
    if total_tokens is None and (
        input_tokens is not None or output_tokens is not None
    ):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    return LlmTokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _estimate_cost_usd(
    usage: LlmTokenUsage,
    *,
    input_price_per_million_tokens_usd: float | None,
    output_price_per_million_tokens_usd: float | None,
) -> float | None:
    if (
        usage.input_tokens is None
        or usage.output_tokens is None
        or input_price_per_million_tokens_usd is None
        or output_price_per_million_tokens_usd is None
    ):
        return None

    input_cost = (usage.input_tokens / 1_000_000) * input_price_per_million_tokens_usd
    output_cost = (
        usage.output_tokens / 1_000_000
    ) * output_price_per_million_tokens_usd
    return round(input_cost + output_cost, 8)


def _extract_structured_result(
    invocation_result: object,
) -> tuple[CandidateVerificationResponse, object | None]:
    if isinstance(invocation_result, CandidateVerificationResponse):
        return invocation_result, None
    if isinstance(invocation_result, Mapping):
        raw_message = invocation_result.get("raw")
        parsed = invocation_result.get("parsed")
        if isinstance(parsed, CandidateVerificationResponse):
            return parsed, raw_message
        if parsed is not None:
            return CandidateVerificationResponse.model_validate(parsed), raw_message
    return CandidateVerificationResponse.model_validate(invocation_result), None


@dataclass(slots=True)
class GeminiCandidateVerifier:
    model: str | None = None
    temperature: float = 0.0
    api_key: str | None = None
    _llm_call_records: list[LlmCallRecord] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def drain_llm_call_records(self) -> list[LlmCallRecord]:
        records = list(self._llm_call_records)
        self._llm_call_records.clear()
        return records

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
        prompt = _build_prompt(
            original_query=original_query,
            query_focus=query_focus,
            candidate_type=candidate_type,
            candidates=candidates,
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
        try:
            structured_llm = llm.with_structured_output(
                CandidateVerificationResponse,
                include_raw=True,
            )
        except TypeError:
            structured_llm = llm.with_structured_output(CandidateVerificationResponse)
        invocation_result = await structured_llm.ainvoke(prompt)
        result, raw_message = _extract_structured_result(invocation_result)

        usage = _extract_usage(raw_message)
        input_price_per_million_tokens_usd, output_price_per_million_tokens_usd = (
            _resolve_token_pricing(model_name)
        )
        self._llm_call_records.append(
            LlmCallRecord(
                provider="google",
                purpose="candidate_verification",
                stage=f"{candidate_type}_verification",
                model=_normalize_model_name(model_name) or model_name,
                original_query=original_query,
                query_focus=query_focus,
                candidate_type=candidate_type,
                candidate_count=len(candidates),
                prompt=prompt,
                parsed_item_count=len(result.items),
                usage=usage,
                input_price_per_million_tokens_usd=input_price_per_million_tokens_usd,
                output_price_per_million_tokens_usd=output_price_per_million_tokens_usd,
                estimated_cost_usd=_estimate_cost_usd(
                    usage,
                    input_price_per_million_tokens_usd=(
                        input_price_per_million_tokens_usd
                    ),
                    output_price_per_million_tokens_usd=(
                        output_price_per_million_tokens_usd
                    ),
                ),
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
