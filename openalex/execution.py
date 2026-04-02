from __future__ import annotations

import asyncio
from typing import Any, Callable

from .api import OpenAlexApiClient
from .schemas import (
    ExactOpenAlexQuery,
    MatchedQuery,
    OpenAlexPipelineOptions,
    QueryExecution,
    QuerySummary,
    RunSummary,
)
from .text import short_openalex_id


async def execute_query_bundle(
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


def merge_entity_results(
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


def build_run_summary(
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
