from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Literal

from .api import OpenAlexApiClient
from .catalog import build_catalog_repository_factory
from .config import settings
from .ports import (
    CandidateSelector,
    CandidateVerifier,
    CatalogRepositoryFactory,
    OpenAlexDependencies,
    QueryValidator,
)
from .schemas import (
    AppliedQueryModifier,
    AuthorInstitution,
    AuthorSummaryStats,
    AuthorTopic,
    CandidateVerificationRecord,
    ExactOpenAlexQuery,
    KeywordCandidate,
    MatchedQuery,
    OpenAlexAuthor,
    OpenAlexPaper,
    OpenAlexPipelineOptions,
    OpenAlexRunResult,
    PaperAuthor,
    PaperLocation,
    PipelineMode,
    PipelineLogEntry,
    QueryExecution,
    QuerySummary,
    RetrievalTarget,
    RunSummary,
    SelectedKeyword,
    SelectedTopic,
    TopicCandidate,
)
from .selectors import select_candidates
from .utils import (
    build_keyword_candidates,
    build_query_for_author_topic,
    build_query_for_keyword,
    build_query_for_topic,
    build_topic_candidates,
    create_output_dir,
    extract_query_intent,
    extract_query_modifiers,
    extract_query_topic_focus,
    extract_topic_ids,
    openalex_topic_id,
    parse_openalex_query_input,
    save_run_result,
    short_openalex_id,
    strip_text_constraints,
)
from .validation import LenientQueryValidator
from .verifier import GeminiCandidateVerifier

logger = logging.getLogger(__name__)


def _select_keywords_from_ids(
    candidate_map: dict[int, KeywordCandidate],
    selected_ids: list[int],
    selection_reasons: dict[int, str],
) -> list[SelectedKeyword]:
    out: list[SelectedKeyword] = []
    for rank, candidate_id in enumerate(selected_ids, start=1):
        candidate = candidate_map.get(candidate_id)
        if candidate is None:
            continue
        out.append(
            SelectedKeyword(
                keyword_id=candidate.keyword_id,
                keyword=candidate.keyword,
                alias=candidate.alias,
                topic_count=candidate.topic_count,
                lexical_score=candidate.lexical_score,
                selection_rank=rank,
                selection_reason=selection_reasons.get(
                    candidate_id, "Selected by workflow."
                ),
            )
        )
    return out


def _select_topics_from_ids(
    candidate_map: dict[int, TopicCandidate],
    selected_ids: list[int],
    selection_reasons: dict[int, str],
) -> list[SelectedTopic]:
    out: list[SelectedTopic] = []
    for rank, candidate_id in enumerate(selected_ids, start=1):
        candidate = candidate_map.get(candidate_id)
        if candidate is None:
            continue
        out.append(
            SelectedTopic(
                topic_id=candidate.topic_id,
                openalex_id=openalex_topic_id(candidate.topic_id),
                topic_name=candidate.topic_name,
                field_name=candidate.field_name,
                subfield_name=candidate.subfield_name,
                lexical_score=candidate.lexical_score,
                selection_rank=rank,
                selection_reason=selection_reasons.get(
                    candidate_id, "Selected by workflow."
                ),
            )
        )
    return out


def _derive_author_topics_from_keywords(
    selected_keywords: list[SelectedKeyword],
    topic_catalog: list[TopicCandidate],
    *,
    query_context: str | None = None,
    max_topics_per_keyword: int,
) -> list[SelectedTopic]:
    author_topics: list[SelectedTopic] = []
    seen_topic_ids: set[int] = set()
    rank = 1

    for keyword in selected_keywords:
        derivation_query = (
            f"{query_context} {keyword.keyword}".strip()
            if query_context
            else keyword.keyword
        )
        topic_candidates = build_topic_candidates(
            derivation_query,
            topic_catalog,
            max_topics_per_keyword,
        )
        for topic_candidate in topic_candidates:
            if topic_candidate.lexical_score <= 0:
                continue
            if topic_candidate.topic_id in seen_topic_ids:
                continue
            seen_topic_ids.add(topic_candidate.topic_id)
            author_topics.append(
                SelectedTopic(
                    topic_id=topic_candidate.topic_id,
                    openalex_id=openalex_topic_id(topic_candidate.topic_id),
                    topic_name=topic_candidate.topic_name,
                    field_name=topic_candidate.field_name,
                    subfield_name=topic_candidate.subfield_name,
                    lexical_score=topic_candidate.lexical_score,
                    selection_rank=rank,
                    selection_reason=(
                        f"Derived from keyword '{keyword.keyword}' for author search."
                    ),
                )
            )
            rank += 1

    return author_topics


def _merge_selected_topics(
    *groups: list[SelectedTopic],
) -> list[SelectedTopic]:
    merged: list[SelectedTopic] = []
    seen_topic_ids: set[int] = set()
    rank = 1
    for group in groups:
        for topic in group:
            if topic.topic_id in seen_topic_ids:
                continue
            seen_topic_ids.add(topic.topic_id)
            merged.append(topic.model_copy(update={"selection_rank": rank}))
            rank += 1
    return merged


def _merge_query_bundles(
    *groups: list[tuple[str, str, str, ExactOpenAlexQuery]],
) -> list[tuple[str, str, str, ExactOpenAlexQuery]]:
    merged: list[tuple[str, str, str, ExactOpenAlexQuery]] = []
    seen: set[tuple[str, str, str, str | None, str | None, str | None]] = set()
    for group in groups:
        for label, source_kind, source_value, query in group:
            key = (
                query.endpoint,
                label,
                source_kind,
                query.filter,
                query.search,
                query.sort,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append((label, source_kind, source_value, query))
    return merged


def _append_log(
    logs: list[PipelineLogEntry],
    *,
    stage: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    entry = PipelineLogEntry(
        stage=stage,
        message=message,
        details=details or {},
    )
    logs.append(entry)
    logger.info("%s: %s", stage, message)


def _candidate_id(candidate: SelectedKeyword | SelectedTopic) -> int:
    if isinstance(candidate, SelectedKeyword):
        return candidate.keyword_id
    return candidate.topic_id


def _candidate_label(candidate: SelectedKeyword | SelectedTopic) -> str:
    if isinstance(candidate, SelectedKeyword):
        return candidate.keyword
    return candidate.topic_name


def _candidate_source_value(candidate: SelectedKeyword | SelectedTopic) -> str:
    if isinstance(candidate, SelectedKeyword):
        return candidate.alias
    return candidate.openalex_id


def _candidate_preview(candidate: SelectedKeyword | SelectedTopic) -> dict[str, Any]:
    preview: dict[str, Any] = {
        "candidate_id": _candidate_id(candidate),
        "label": _candidate_label(candidate),
        "source_value": _candidate_source_value(candidate),
        "lexical_score": candidate.lexical_score,
        "selection_rank": candidate.selection_rank,
        "selection_reason": candidate.selection_reason,
    }
    if isinstance(candidate, SelectedKeyword):
        preview["topic_count"] = candidate.topic_count
    else:
        preview["field_name"] = candidate.field_name
        preview["subfield_name"] = candidate.subfield_name
    return preview


def _catalog_candidate_preview(
    candidate: KeywordCandidate | TopicCandidate,
) -> dict[str, Any]:
    if isinstance(candidate, KeywordCandidate):
        return {
            "candidate_id": candidate.keyword_id,
            "label": candidate.keyword,
            "source_value": candidate.alias,
            "lexical_score": candidate.lexical_score,
            "topic_count": candidate.topic_count,
        }
    return {
        "candidate_id": candidate.topic_id,
        "label": candidate.topic_name,
        "source_value": openalex_topic_id(candidate.topic_id),
        "lexical_score": candidate.lexical_score,
        "field_name": candidate.field_name,
        "subfield_name": candidate.subfield_name,
    }


def _query_bundle_preview(
    bundles: list[tuple[str, str, str, ExactOpenAlexQuery]],
) -> list[dict[str, Any]]:
    return [
        {
            "label": label,
            "source_kind": source_kind,
            "source_value": source_value,
            "endpoint": query.endpoint,
            "filter": query.filter,
            "search": query.search,
            "sort": query.sort,
        }
        for label, source_kind, source_value, query in bundles
    ]


async def _verify_candidates(
    *,
    original_query: str,
    query_focus: str | None,
    candidate_type: Literal["keyword", "topic", "author_topic"],
    candidates: list[SelectedKeyword] | list[SelectedTopic],
    options: OpenAlexPipelineOptions,
    verifier: CandidateVerifier | None,
    logs: list[PipelineLogEntry],
) -> tuple[
    list[SelectedKeyword] | list[SelectedTopic],
    list[CandidateVerificationRecord],
]:
    if not candidates:
        _append_log(
            logs,
            stage=f"{candidate_type}_verification",
            message="No candidates to verify.",
            details={"candidate_type": candidate_type},
        )
        return candidates, []

    if not options.verify_candidate_relevance:
        records = [
            CandidateVerificationRecord(
                candidate_type=candidate_type,
                candidate_id=_candidate_id(candidate),
                label=_candidate_label(candidate),
                source_value=_candidate_source_value(candidate),
                included=True,
                verified=False,
                verifier="disabled",
                reason="Candidate relevance verification disabled.",
                lexical_score=candidate.lexical_score,
                selection_rank=candidate.selection_rank,
                selection_reason=candidate.selection_reason,
            )
            for candidate in candidates
        ]
        _append_log(
            logs,
            stage=f"{candidate_type}_verification",
            message="Candidate relevance verification disabled; keeping selected candidates.",
            details={
                "candidate_type": candidate_type,
                "kept_candidates": [_candidate_preview(candidate) for candidate in candidates],
            },
        )
        return candidates, records

    if verifier is None:
        records = [
            CandidateVerificationRecord(
                candidate_type=candidate_type,
                candidate_id=_candidate_id(candidate),
                label=_candidate_label(candidate),
                source_value=_candidate_source_value(candidate),
                included=True,
                verified=False,
                verifier="unavailable",
                reason=(
                    "No candidate verifier was configured or could be created; "
                    "keeping selected candidates."
                ),
                lexical_score=candidate.lexical_score,
                selection_rank=candidate.selection_rank,
                selection_reason=candidate.selection_reason,
            )
            for candidate in candidates
        ]
        _append_log(
            logs,
            stage=f"{candidate_type}_verification",
            message="No candidate verifier available; keeping selected candidates without LLM filtering.",
            details={
                "candidate_type": candidate_type,
                "kept_candidates": [_candidate_preview(candidate) for candidate in candidates],
            },
        )
        return candidates, records

    try:
        decisions = await verifier.verify(
            original_query=original_query,
            query_focus=query_focus,
            candidate_type=candidate_type,
            candidates=candidates,
            options=options,
        )
    except Exception as exc:
        logger.warning("Candidate verification failed for %s: %s", candidate_type, exc)
        if not options.fallback_to_unverified_candidates:
            raise
        records = [
            CandidateVerificationRecord(
                candidate_type=candidate_type,
                candidate_id=_candidate_id(candidate),
                label=_candidate_label(candidate),
                source_value=_candidate_source_value(candidate),
                included=True,
                verified=False,
                verifier=type(verifier).__name__,
                reason=(
                    "Candidate verification failed, so the workflow kept the "
                    f"selected candidate. Error: {exc}"
                ),
                lexical_score=candidate.lexical_score,
                selection_rank=candidate.selection_rank,
                selection_reason=candidate.selection_reason,
            )
            for candidate in candidates
        ]
        _append_log(
            logs,
            stage=f"{candidate_type}_verification",
            message=(
                "Candidate verification failed; keeping selected candidates "
                "because fallback_to_unverified_candidates is enabled."
            ),
            details={
                "candidate_type": candidate_type,
                "error": str(exc),
                "kept_candidates": [_candidate_preview(candidate) for candidate in candidates],
            },
        )
        return candidates, records

    decision_map = {decision.candidate_id: decision for decision in decisions}
    kept_candidates: list[SelectedKeyword] | list[SelectedTopic] = []
    records: list[CandidateVerificationRecord] = []
    rejected_preview: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_id = _candidate_id(candidate)
        decision = decision_map[candidate_id]
        record = CandidateVerificationRecord(
            candidate_type=candidate_type,
            candidate_id=candidate_id,
            label=_candidate_label(candidate),
            source_value=_candidate_source_value(candidate),
            included=decision.include,
            verified=True,
            verifier=type(verifier).__name__,
            reason=decision.reason,
            lexical_score=candidate.lexical_score,
            selection_rank=candidate.selection_rank,
            selection_reason=candidate.selection_reason,
        )
        records.append(record)
        if decision.include:
            kept_candidates.append(candidate)
            continue
        rejected = _candidate_preview(candidate)
        rejected["verification_reason"] = decision.reason
        rejected_preview.append(rejected)

    _append_log(
        logs,
        stage=f"{candidate_type}_verification",
        message=(
            f"Verified {len(candidates)} {candidate_type} candidates and kept "
            f"{len(kept_candidates)}."
        ),
        details={
            "candidate_type": candidate_type,
            "verifier": type(verifier).__name__,
            "kept_candidates": [_candidate_preview(candidate) for candidate in kept_candidates],
            "rejected_candidates": rejected_preview,
        },
    )
    return kept_candidates, records


def _normalize_paper(
    work: dict[str, Any],
    matches: list[MatchedQuery],
    *,
    max_authors_per_paper: int,
) -> OpenAlexPaper:
    authorships = work.get("authorships", [])
    authors: list[PaperAuthor] = []
    if isinstance(authorships, list):
        for authorship in authorships[:max_authors_per_paper]:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author")
            if not isinstance(author, dict):
                continue
            authors.append(
                PaperAuthor(
                    name=str(author.get("display_name", "Unknown Author")),
                    openalex_id=short_openalex_id(author.get("id")),
                )
            )

    primary_location_data = work.get("primary_location")
    primary_location: PaperLocation | None = None
    if isinstance(primary_location_data, dict):
        source = primary_location_data.get("source")
        primary_location = PaperLocation(
            source_display_name=source.get("display_name")
            if isinstance(source, dict)
            else None,
            source_openalex_id=short_openalex_id(source.get("id"))
            if isinstance(source, dict)
            else None,
            landing_page_url=primary_location_data.get("landing_page_url"),
            pdf_url=primary_location_data.get("pdf_url"),
            is_oa=primary_location_data.get("is_oa"),
        )

    topics_data = work.get("topics", [])
    topics: list[str] = []
    if isinstance(topics_data, list):
        for topic in topics_data[:5]:
            if isinstance(topic, dict):
                display_name = topic.get("display_name")
                if isinstance(display_name, str) and display_name:
                    topics.append(display_name)

    matched_queries = sorted(matches, key=lambda item: item.label.lower())
    return OpenAlexPaper(
        openalex_id=short_openalex_id(work.get("id")) or "unknown",
        title=str(work.get("display_name", "Untitled")),
        cited_by_count=int(work.get("cited_by_count", 0) or 0),
        publication_year=(
            int(work["publication_year"]) if work.get("publication_year") else None
        ),
        publication_date=(
            str(work["publication_date"]) if work.get("publication_date") else None
        ),
        doi=work.get("doi"),
        work_type=work.get("type"),
        primary_location=primary_location,
        authors=authors,
        topics=topics,
        matched_queries=matched_queries,
        matched_query_count=len(matched_queries),
        overlap_type="overlap" if len(matched_queries) > 1 else "unique",
    )


def _normalize_author(
    author: dict[str, Any],
    matches: list[MatchedQuery],
) -> OpenAlexAuthor:
    summary_stats_data = author.get("summary_stats")
    summary_stats: AuthorSummaryStats | None = None
    if isinstance(summary_stats_data, dict):
        summary_stats = AuthorSummaryStats(
            two_year_mean_citedness=(
                float(summary_stats_data["2yr_mean_citedness"])
                if summary_stats_data.get("2yr_mean_citedness") is not None
                else None
            ),
            h_index=(
                int(summary_stats_data["h_index"])
                if summary_stats_data.get("h_index") is not None
                else None
            ),
            i10_index=(
                int(summary_stats_data["i10_index"])
                if summary_stats_data.get("i10_index") is not None
                else None
            ),
        )

    institutions: list[AuthorInstitution] = []
    last_known_institutions = author.get("last_known_institutions", [])
    if isinstance(last_known_institutions, list):
        for institution in last_known_institutions[:3]:
            if not isinstance(institution, dict):
                continue
            institutions.append(
                AuthorInstitution(
                    display_name=str(
                        institution.get("display_name", "Unknown Institution")
                    ),
                    openalex_id=short_openalex_id(institution.get("id")),
                    country_code=(
                        str(institution["country_code"])
                        if institution.get("country_code") is not None
                        else None
                    ),
                    institution_type=(
                        str(institution["type"])
                        if institution.get("type") is not None
                        else None
                    ),
                )
            )

    topics: list[AuthorTopic] = []
    topics_data = author.get("topics", [])
    if isinstance(topics_data, list):
        for topic in topics_data[:5]:
            if not isinstance(topic, dict):
                continue
            display_name = topic.get("display_name")
            topic_id = short_openalex_id(topic.get("id"))
            if not isinstance(display_name, str) or not topic_id:
                continue
            topics.append(
                AuthorTopic(
                    openalex_id=topic_id,
                    display_name=display_name,
                    count=(
                        int(topic["count"]) if topic.get("count") is not None else None
                    ),
                )
            )

    matched_queries = sorted(matches, key=lambda item: item.label.lower())
    return OpenAlexAuthor(
        openalex_id=short_openalex_id(author.get("id")) or "unknown",
        display_name=str(author.get("display_name", "Unknown Author")),
        orcid=(
            str(author["orcid"]) if author.get("orcid") is not None else None
        ),
        works_count=int(author.get("works_count", 0) or 0),
        cited_by_count=int(author.get("cited_by_count", 0) or 0),
        summary_stats=summary_stats,
        last_known_institutions=institutions,
        topics=topics,
        matched_queries=matched_queries,
        matched_query_count=len(matched_queries),
        overlap_type="overlap" if len(matched_queries) > 1 else "unique",
    )


def _merge_entity_results(
    executions_and_results: list[tuple[QueryExecution, list[dict[str, Any]]]],
    *,
    normalize_record: Callable[[dict[str, Any], list[MatchedQuery]], Any],
    sort_key: Callable[[Any], tuple[Any, ...]],
) -> tuple[list[Any], list[QuerySummary]]:
    record_index: dict[str, dict[str, Any]] = {}
    match_index: dict[str, list[MatchedQuery]] = {}

    for execution, records in executions_and_results:
        for record in records:
            record_id = short_openalex_id(record.get("id"))
            if not record_id:
                continue
            record_index[record_id] = record
            matches = match_index.setdefault(record_id, [])
            if any(match.label == execution.label for match in matches):
                continue
            matches.append(
                MatchedQuery(
                    label=execution.label,
                    source_kind=execution.source_kind,
                    source_value=execution.source_value,
                )
            )

    items = [
        normalize_record(record, match_index[record_id])
        for record_id, record in record_index.items()
    ]
    items.sort(key=sort_key, reverse=True)

    query_summaries: list[QuerySummary] = []
    for execution, _ in executions_and_results:
        unique_count = 0
        overlap_count = 0
        for item in items:
            labels = {match.label for match in item.matched_queries}
            if execution.label not in labels:
                continue
            if item.matched_query_count > 1:
                overlap_count += 1
            else:
                unique_count += 1
        query_summaries.append(
            QuerySummary(
                label=execution.label,
                source_kind=execution.source_kind,
                returned_count=execution.returned_count,
                unique_count=unique_count,
                overlap_count=overlap_count,
            )
        )

    return items, query_summaries


def _build_run_summary(
    executions_and_results: list[tuple[QueryExecution, list[dict[str, Any]]]],
    items: list[Any],
    query_summaries: list[QuerySummary],
    *,
    top_k_returned: int,
) -> RunSummary:
    overlap_results = sum(1 for item in items if item.matched_query_count > 1)
    unique_only_results = sum(1 for item in items if item.matched_query_count == 1)
    return RunSummary(
        total_queries_executed=len(executions_and_results),
        total_results_retrieved=sum(
            execution.returned_count for execution, _ in executions_and_results
        ),
        total_unique_results=len(items),
        overlap_results=overlap_results,
        unique_only_results=unique_only_results,
        top_k_returned=top_k_returned,
        query_summaries=query_summaries,
    )


async def _execute_query_bundle(
    *,
    entity_type: str,
    label: str,
    source_kind: str,
    source_value: str,
    query: ExactOpenAlexQuery,
    options: OpenAlexPipelineOptions,
    api_client: OpenAlexApiClient,
    semaphore: asyncio.Semaphore,
) -> tuple[QueryExecution, list[dict[str, Any]]]:
    async with semaphore:
        response = await api_client.fetch_results(
            query,
            limit=options.max_results_per_query,
            per_page=options.per_page,
        )
        result_ids = [
            short_openalex_id(record.get("id")) or "unknown"
            for record in response.results
        ]
        execution = QueryExecution(
            entity_type=entity_type,
            label=label,
            source_kind=source_kind,
            source_value=source_value,
            query=query,
            max_results_requested=options.max_results_per_query,
            per_page_requested=min(options.per_page, 200),
            request_params=query.to_query_params(
                per_page_override=min(options.per_page, 200)
            ),
            request_urls=response.request_urls,
            api_result_count=response.total_count,
            returned_count=len(response.results),
            result_ids=result_ids,
        )
        return execution, response.results


async def _ensure_valid_natural_language_query(
    input_query: str,
    *,
    mode: PipelineMode,
    check_valid_topic: bool,
    validator: QueryValidator,
) -> None:
    if not check_valid_topic:
        return
    if mode not in {
        PipelineMode.NATURAL_LANGUAGE_KEYWORDS_AND_TOPICS,
        PipelineMode.NATURAL_LANGUAGE_KEYWORDS,
        PipelineMode.NATURAL_LANGUAGE_TOPICS,
    }:
        return

    validation_query = extract_query_topic_focus(input_query)
    validation = await validator.validate(validation_query)
    if validation.valid:
        return

    suggestions = (
        f" Suggestions: {', '.join(validation.suggestions[:3])}."
        if validation.suggestions
        else ""
    )
    why_not_valid = validation.why_not_valid or "Query is too vague to run safely."
    raise ValueError(f"OpenAlex query validation failed: {why_not_valid}.{suggestions}")


def _should_fetch_works(target: RetrievalTarget) -> bool:
    return target in {RetrievalTarget.WORKS, RetrievalTarget.WORKS_AND_AUTHORS}


def _should_fetch_authors(target: RetrievalTarget) -> bool:
    return target in {RetrievalTarget.AUTHORS, RetrievalTarget.WORKS_AND_AUTHORS}


async def _prepare_keyword_mode(
    input_query: str,
    *,
    options: OpenAlexPipelineOptions,
    extra_filter_components: list[str],
    query_focus: str | None = None,
    selector: CandidateSelector | None,
    verifier: CandidateVerifier | None,
    catalog_repository_factory: CatalogRepositoryFactory,
    logs: list[PipelineLogEntry],
) -> tuple[
    list[SelectedKeyword],
    list[SelectedTopic],
    list[CandidateVerificationRecord],
    list[tuple[str, str, str, ExactOpenAlexQuery]],
    list[tuple[str, str, str, ExactOpenAlexQuery]],
    ExactOpenAlexQuery | None,
    str,
]:
    async with catalog_repository_factory() as repo:
        keyword_catalog = await repo.fetch_keyword_catalog()
        exact_query: ExactOpenAlexQuery | None = None
        base_query: ExactOpenAlexQuery | None = None
        if options.mode == PipelineMode.OPENALEX_QUERY_KEYWORDS:
            exact_query = parse_openalex_query_input(input_query)
            if exact_query.endpoint != "/works":
                raise RuntimeError(
                    "openalex_query_keywords only supports /works queries."
                )
            topic_names = await repo.resolve_topic_names(
                extract_topic_ids(exact_query.filter)
            )
            query_intent = extract_query_intent(exact_query, topic_names)
            base_query = strip_text_constraints(exact_query)
        else:
            query_intent = query_focus or input_query

        candidates = build_keyword_candidates(
            query_intent, keyword_catalog, options.candidate_limit
        )
        _append_log(
            logs,
            stage="keyword_candidates",
            message=f"Built {len(candidates)} keyword candidates.",
            details={
                "query_intent": query_intent,
                "top_candidates": [
                    _catalog_candidate_preview(candidate) for candidate in candidates[:10]
                ],
            },
        )
        selections, selector_strategy = await select_candidates(
            query=query_intent,
            candidate_type="keyword",
            candidates=candidates,
            options=options,
            selector=selector,
        )
        candidate_map = {candidate.keyword_id: candidate for candidate in candidates}
        selection_ids = [item.candidate_id for item in selections]
        selection_reasons = {
            item.candidate_id: item.selection_reason for item in selections
        }
        selected_keywords = _select_keywords_from_ids(
            candidate_map, selection_ids, selection_reasons
        )
        _append_log(
            logs,
            stage="keyword_selection",
            message=(
                f"Selected {len(selected_keywords)} keyword candidates before verification."
            ),
            details={
                "selector_strategy": selector_strategy,
                "selected_candidates": [
                    _candidate_preview(candidate) for candidate in selected_keywords
                ],
            },
        )
        verified_keywords, keyword_verifications = await _verify_candidates(
            original_query=input_query,
            query_focus=query_focus,
            candidate_type="keyword",
            candidates=selected_keywords,
            options=options,
            verifier=verifier,
            logs=logs,
        )
        selected_keywords = [
            candidate
            for candidate in verified_keywords
            if isinstance(candidate, SelectedKeyword)
        ]

        work_query_bundles = [
            (
                selected.keyword,
                "keyword",
                selected.keyword,
                build_query_for_keyword(
                    selected,
                    base_query=base_query,
                    generated_sort=options.generated_query_sort,
                    extra_filter_components=extra_filter_components,
                ),
            )
            for selected in selected_keywords
        ]

        author_topics: list[SelectedTopic] = []
        author_query_bundles: list[tuple[str, str, str, ExactOpenAlexQuery]] = []
        author_topic_verifications: list[CandidateVerificationRecord] = []
        if _should_fetch_authors(options.target):
            topic_catalog = await repo.fetch_topic_catalog()
            author_topics = _derive_author_topics_from_keywords(
                selected_keywords,
                topic_catalog,
                query_context=query_focus or input_query,
                max_topics_per_keyword=options.max_author_topics_per_keyword,
            )
            _append_log(
                logs,
                stage="author_topic_derivation",
                message=(
                    f"Derived {len(author_topics)} author-topic candidates from "
                    f"{len(selected_keywords)} verified keywords."
                ),
                details={
                    "verified_keywords": [
                        _candidate_preview(candidate) for candidate in selected_keywords
                    ],
                    "derived_candidates": [
                        _candidate_preview(candidate) for candidate in author_topics
                    ],
                },
            )
            verified_author_topics, author_topic_verifications = await _verify_candidates(
                original_query=input_query,
                query_focus=query_focus,
                candidate_type="author_topic",
                candidates=author_topics,
                options=options,
                verifier=verifier,
                logs=logs,
            )
            author_topics = [
                candidate
                for candidate in verified_author_topics
                if isinstance(candidate, SelectedTopic)
            ]
            author_query_bundles = [
                (
                    selected.topic_name,
                    "topic_from_keyword",
                    selected.openalex_id,
                    build_query_for_author_topic(
                        selected,
                        generated_sort=options.generated_query_sort,
                        extra_filter_components=extra_filter_components,
                    ),
                )
                for selected in author_topics
            ]

        return (
            selected_keywords,
            author_topics,
            [*keyword_verifications, *author_topic_verifications],
            work_query_bundles,
            author_query_bundles,
            exact_query,
            selector_strategy,
        )


async def _prepare_topic_mode(
    input_query: str,
    *,
    options: OpenAlexPipelineOptions,
    extra_filter_components: list[str],
    query_focus: str | None = None,
    selector: CandidateSelector | None,
    verifier: CandidateVerifier | None,
    catalog_repository_factory: CatalogRepositoryFactory,
    logs: list[PipelineLogEntry],
) -> tuple[
    list[SelectedTopic],
    list[SelectedTopic],
    list[CandidateVerificationRecord],
    list[tuple[str, str, str, ExactOpenAlexQuery]],
    list[tuple[str, str, str, ExactOpenAlexQuery]],
    str,
]:
    async with catalog_repository_factory() as repo:
        topic_catalog = await repo.fetch_topic_catalog()
        candidates = build_topic_candidates(
            query_focus or input_query, topic_catalog, options.candidate_limit
        )
        _append_log(
            logs,
            stage="topic_candidates",
            message=f"Built {len(candidates)} topic candidates.",
            details={
                "query_focus": query_focus or input_query,
                "top_candidates": [
                    _catalog_candidate_preview(candidate) for candidate in candidates[:10]
                ],
            },
        )
        selections, selector_strategy = await select_candidates(
            query=query_focus or input_query,
            candidate_type="topic",
            candidates=candidates,
            options=options,
            selector=selector,
        )
        candidate_map = {candidate.topic_id: candidate for candidate in candidates}
        selection_ids = [item.candidate_id for item in selections]
        selection_reasons = {
            item.candidate_id: item.selection_reason for item in selections
        }
        selected_topics = _select_topics_from_ids(
            candidate_map, selection_ids, selection_reasons
        )
        _append_log(
            logs,
            stage="topic_selection",
            message=(
                f"Selected {len(selected_topics)} topic candidates before verification."
            ),
            details={
                "selector_strategy": selector_strategy,
                "selected_candidates": [
                    _candidate_preview(candidate) for candidate in selected_topics
                ],
            },
        )
        verified_topics, topic_verifications = await _verify_candidates(
            original_query=input_query,
            query_focus=query_focus,
            candidate_type="topic",
            candidates=selected_topics,
            options=options,
            verifier=verifier,
            logs=logs,
        )
        selected_topics = [
            candidate for candidate in verified_topics if isinstance(candidate, SelectedTopic)
        ]
        work_query_bundles = [
            (
                selected.topic_name,
                "topic",
                selected.openalex_id,
                build_query_for_topic(
                    selected,
                    base_query=None,
                    generated_sort=options.generated_query_sort,
                    extra_filter_components=extra_filter_components,
                ),
            )
            for selected in selected_topics
        ]
        author_topics = [topic.model_copy(deep=True) for topic in selected_topics]
        author_query_bundles = [
            (
                selected.topic_name,
                "topic",
                selected.openalex_id,
                build_query_for_author_topic(
                    selected,
                    generated_sort=options.generated_query_sort,
                    extra_filter_components=extra_filter_components,
                ),
            )
            for selected in author_topics
        ]
        return (
            selected_topics,
            author_topics,
            topic_verifications,
            work_query_bundles,
            author_query_bundles,
            selector_strategy,
        )


def _resolve_catalog_repository_factory(
    deps: OpenAlexDependencies | None,
) -> CatalogRepositoryFactory:
    if deps is not None and deps.catalog_repository_factory is not None:
        return deps.catalog_repository_factory
    return build_catalog_repository_factory()


def _resolve_query_validator(deps: OpenAlexDependencies | None) -> QueryValidator:
    if deps is not None and deps.query_validator is not None:
        return deps.query_validator
    return LenientQueryValidator()


def _resolve_candidate_selector(
    deps: OpenAlexDependencies | None,
) -> CandidateSelector | None:
    if deps is None:
        return None
    return deps.candidate_selector


def _resolve_candidate_verifier(
    deps: OpenAlexDependencies | None,
    options: OpenAlexPipelineOptions,
) -> CandidateVerifier | None:
    if not options.verify_candidate_relevance:
        return None
    if deps is not None and deps.candidate_verifier is not None:
        return deps.candidate_verifier
    if not settings.gemini_api_key:
        return None
    return GeminiCandidateVerifier(
        model=options.verifier_model or settings.verifier_model,
        temperature=options.verifier_temperature,
        api_key=settings.gemini_api_key,
    )


def _supports_author_target(mode: PipelineMode) -> bool:
    return mode in {
        PipelineMode.NATURAL_LANGUAGE_KEYWORDS_AND_TOPICS,
        PipelineMode.NATURAL_LANGUAGE_KEYWORDS,
        PipelineMode.NATURAL_LANGUAGE_TOPICS,
        PipelineMode.OPENALEX_QUERY_KEYWORDS,
        PipelineMode.EXACT_OPENALEX_QUERY,
    }


async def run_openalex_pipeline(
    input_query: str,
    options: OpenAlexPipelineOptions | None = None,
    deps: OpenAlexDependencies | None = None,
) -> OpenAlexRunResult:
    effective_options = options or OpenAlexPipelineOptions(
        mode=PipelineMode.NATURAL_LANGUAGE_KEYWORDS_AND_TOPICS
    )
    if effective_options.selector_model is None:
        effective_options.selector_model = settings.selector_model
    if effective_options.verifier_model is None:
        effective_options.verifier_model = settings.verifier_model

    if _should_fetch_authors(effective_options.target) and not _supports_author_target(
        effective_options.mode
    ):
        raise RuntimeError(
            f"Author retrieval is not supported for mode {effective_options.mode.value!r}."
        )

    catalog_repository_factory = _resolve_catalog_repository_factory(deps)
    query_validator = _resolve_query_validator(deps)
    candidate_selector = _resolve_candidate_selector(deps)
    candidate_verifier = _resolve_candidate_verifier(deps, effective_options)
    logs: list[PipelineLogEntry] = []
    candidate_verifications: list[CandidateVerificationRecord] = []
    _append_log(
        logs,
        stage="start",
        message="Starting OpenAlex pipeline run.",
        details={
            "input_query": input_query,
            "mode": effective_options.mode.value,
            "target": effective_options.target.value,
            "selector_strategy": effective_options.selector_strategy,
            "verify_candidate_relevance": effective_options.verify_candidate_relevance,
            "verifier": (
                type(candidate_verifier).__name__
                if candidate_verifier is not None
                else "none"
            ),
        },
    )

    await _ensure_valid_natural_language_query(
        input_query,
        mode=effective_options.mode,
        check_valid_topic=effective_options.check_valid_topic,
        validator=query_validator,
    )
    _append_log(
        logs,
        stage="query_validation",
        message="Natural-language query validation passed or was not required.",
        details={
            "mode": effective_options.mode.value,
            "check_valid_topic": effective_options.check_valid_topic,
        },
    )

    query_modifiers: list[AppliedQueryModifier] = []
    extra_filter_components: list[str] = []
    query_focus = input_query
    if effective_options.mode in {
        PipelineMode.NATURAL_LANGUAGE_KEYWORDS_AND_TOPICS,
        PipelineMode.NATURAL_LANGUAGE_KEYWORDS,
        PipelineMode.NATURAL_LANGUAGE_TOPICS,
    }:
        query_modifiers = extract_query_modifiers(input_query)
        query_focus = extract_query_topic_focus(input_query)
        extra_filter_components = [
            modifier.filter_fragment for modifier in query_modifiers
        ]
    _append_log(
        logs,
        stage="query_focus",
        message="Computed query focus and filter modifiers.",
        details={
            "query_focus": query_focus,
            "query_modifiers": [
                modifier.model_dump(mode="json") for modifier in query_modifiers
            ],
            "extra_filter_components": extra_filter_components,
        },
    )

    selected_keywords: list[SelectedKeyword] = []
    selected_topics: list[SelectedTopic] = []
    selected_author_topics: list[SelectedTopic] = []
    exact_query: ExactOpenAlexQuery | None = None
    selector_strategy_used = "none"
    work_query_bundles: list[tuple[str, str, str, ExactOpenAlexQuery]] = []
    author_query_bundles: list[tuple[str, str, str, ExactOpenAlexQuery]] = []

    if effective_options.mode == PipelineMode.EXACT_OPENALEX_QUERY:
        if effective_options.target == RetrievalTarget.WORKS_AND_AUTHORS:
            raise RuntimeError(
                "Exact query mode does not support target='works_and_authors'. "
                "Choose 'works' or 'authors'."
            )
        default_endpoint = (
            "/authors"
            if effective_options.target == RetrievalTarget.AUTHORS
            else "/works"
        )
        exact_query = parse_openalex_query_input(
            input_query,
            default_endpoint=default_endpoint,
        )
        if exact_query.endpoint != default_endpoint:
            raise RuntimeError(
                "Exact query target does not match the explicit OpenAlex endpoint. "
                f"Expected {default_endpoint!r}, got {exact_query.endpoint!r}."
            )
        _append_log(
            logs,
            stage="exact_query",
            message="Using exact OpenAlex query without candidate selection.",
            details={"query": exact_query.model_dump(mode="json")},
        )
        if effective_options.target == RetrievalTarget.AUTHORS:
            author_query_bundles = [
                ("exact_query", "exact", input_query, exact_query),
            ]
        else:
            work_query_bundles = [
                ("exact_query", "exact", input_query, exact_query),
            ]
    elif effective_options.mode == PipelineMode.NATURAL_LANGUAGE_KEYWORDS_AND_TOPICS:
        (
            selected_keywords,
            keyword_author_topics,
            keyword_verifications,
            keyword_work_query_bundles,
            keyword_author_query_bundles,
            _,
            keyword_selector_strategy,
        ) = await _prepare_keyword_mode(
            input_query,
            options=effective_options,
            extra_filter_components=extra_filter_components,
            query_focus=query_focus,
            selector=candidate_selector,
            verifier=candidate_verifier,
            catalog_repository_factory=catalog_repository_factory,
            logs=logs,
        )
        (
            selected_topics,
            topic_author_topics,
            topic_verifications,
            topic_work_query_bundles,
            topic_author_query_bundles,
            topic_selector_strategy,
        ) = await _prepare_topic_mode(
            input_query,
            options=effective_options,
            extra_filter_components=extra_filter_components,
            query_focus=query_focus,
            selector=candidate_selector,
            verifier=candidate_verifier,
            catalog_repository_factory=catalog_repository_factory,
            logs=logs,
        )
        candidate_verifications.extend(keyword_verifications)
        candidate_verifications.extend(topic_verifications)
        selected_author_topics = _merge_selected_topics(
            topic_author_topics,
            keyword_author_topics,
        )
        work_query_bundles = _merge_query_bundles(
            keyword_work_query_bundles,
            topic_work_query_bundles,
        )
        author_query_bundles = _merge_query_bundles(
            topic_author_query_bundles,
            keyword_author_query_bundles,
        )
        selector_strategy_used = (
            keyword_selector_strategy
            if keyword_selector_strategy == topic_selector_strategy
            else f"{keyword_selector_strategy}+{topic_selector_strategy}"
        )
    elif effective_options.mode in {
        PipelineMode.NATURAL_LANGUAGE_KEYWORDS,
        PipelineMode.OPENALEX_QUERY_KEYWORDS,
    }:
        (
            selected_keywords,
            selected_author_topics,
            keyword_verifications,
            work_query_bundles,
            author_query_bundles,
            exact_query,
            selector_strategy_used,
        ) = await _prepare_keyword_mode(
            input_query,
            options=effective_options,
            extra_filter_components=extra_filter_components,
            query_focus=query_focus,
            selector=candidate_selector,
            verifier=candidate_verifier,
            catalog_repository_factory=catalog_repository_factory,
            logs=logs,
        )
        candidate_verifications.extend(keyword_verifications)
    else:
        (
            selected_topics,
            selected_author_topics,
            topic_verifications,
            work_query_bundles,
            author_query_bundles,
            selector_strategy_used,
        ) = await _prepare_topic_mode(
            input_query,
            options=effective_options,
            extra_filter_components=extra_filter_components,
            query_focus=query_focus,
            selector=candidate_selector,
            verifier=candidate_verifier,
            catalog_repository_factory=catalog_repository_factory,
            logs=logs,
        )
        candidate_verifications.extend(topic_verifications)

    if not _should_fetch_works(effective_options.target):
        work_query_bundles = []
    if not _should_fetch_authors(effective_options.target):
        author_query_bundles = []
        selected_author_topics = []
    _append_log(
        logs,
        stage="query_plan",
        message="Prepared executable OpenAlex query bundles.",
        details={
            "work_queries": _query_bundle_preview(work_query_bundles),
            "author_queries": _query_bundle_preview(author_query_bundles),
        },
    )
    if not work_query_bundles and not author_query_bundles:
        raise RuntimeError("OpenAlex workflow produced no executable queries")

    semaphore = asyncio.Semaphore(max(effective_options.parallel, 1))
    async with OpenAlexApiClient(
        timeout_seconds=effective_options.request_timeout_seconds
    ) as api_client:
        work_executed = (
            await asyncio.gather(
                *[
                    _execute_query_bundle(
                        entity_type="work",
                        label=label,
                        source_kind=source_kind,
                        source_value=source_value,
                        query=query,
                        options=effective_options,
                        api_client=api_client,
                        semaphore=semaphore,
                    )
                    for label, source_kind, source_value, query in work_query_bundles
                ]
            )
            if work_query_bundles
            else []
        )
        author_executed = (
            await asyncio.gather(
                *[
                    _execute_query_bundle(
                        entity_type="author",
                        label=label,
                        source_kind=source_kind,
                        source_value=source_value,
                        query=query,
                        options=effective_options,
                        api_client=api_client,
                        semaphore=semaphore,
                    )
                    for label, source_kind, source_value, query in author_query_bundles
                ]
            )
            if author_query_bundles
            else []
        )

    papers: list[OpenAlexPaper] = []
    works_summary: RunSummary | None = None
    if work_executed:
        merged_papers, work_query_summaries = _merge_entity_results(
            work_executed,
            normalize_record=lambda record, matches: _normalize_paper(
                record,
                matches,
                max_authors_per_paper=effective_options.max_authors_per_paper,
            ),
            sort_key=lambda paper: (
                paper.matched_query_count,
                paper.cited_by_count,
                paper.publication_year or 0,
            ),
        )
        papers = merged_papers[: effective_options.top_k]
        works_summary = _build_run_summary(
            work_executed,
            merged_papers,
            work_query_summaries,
            top_k_returned=len(papers),
        )
        _append_log(
            logs,
            stage="work_execution",
            message=f"Executed {len(work_executed)} work queries.",
            details={
                "queries": [
                    {
                        "label": execution.label,
                        "source_kind": execution.source_kind,
                        "returned_count": execution.returned_count,
                    }
                    for execution, _ in work_executed
                ],
                "top_k_returned": len(papers),
            },
        )

    authors: list[OpenAlexAuthor] = []
    author_summary: RunSummary | None = None
    if author_executed:
        merged_authors, author_query_summaries = _merge_entity_results(
            author_executed,
            normalize_record=_normalize_author,
            sort_key=lambda author: (
                author.matched_query_count,
                author.cited_by_count,
                author.works_count,
            ),
        )
        authors = merged_authors[: effective_options.top_k]
        author_summary = _build_run_summary(
            author_executed,
            merged_authors,
            author_query_summaries,
            top_k_returned=len(authors),
        )
        _append_log(
            logs,
            stage="author_execution",
            message=f"Executed {len(author_executed)} author queries.",
            details={
                "queries": [
                    {
                        "label": execution.label,
                        "source_kind": execution.source_kind,
                        "returned_count": execution.returned_count,
                    }
                    for execution, _ in author_executed
                ],
                "top_k_returned": len(authors),
            },
        )

    result = OpenAlexRunResult(
        mode=effective_options.mode,
        target=effective_options.target,
        input_query=input_query,
        selector_model=(
            None
            if effective_options.mode == PipelineMode.EXACT_OPENALEX_QUERY
            else effective_options.selector_model
        ),
        selector_strategy=selector_strategy_used,
        exact_query=exact_query,
        query_modifiers=query_modifiers,
        selected_keywords=selected_keywords,
        selected_topics=selected_topics,
        selected_author_topics=selected_author_topics,
        candidate_verifications=candidate_verifications,
        logs=logs,
        executions=[execution for execution, _ in work_executed],
        summary=works_summary,
        author_executions=[execution for execution, _ in author_executed],
        author_summary=author_summary,
        papers=papers,
        authors=authors,
    )

    if effective_options.save_output:
        task_dir = create_output_dir(input_query, effective_options.output_dir)
        output_path = task_dir / effective_options.output_filename
        save_run_result(result, output_path)
        result.output_path = str(output_path)

    return result
