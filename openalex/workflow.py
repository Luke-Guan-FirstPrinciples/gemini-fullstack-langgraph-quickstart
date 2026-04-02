from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from .config import settings
from .pipeline import run_openalex_pipeline
from .ports import OpenAlexDependencies
from .schemas import OpenAlexPipelineOptions, PipelineMode, RetrievalTarget

WORKFLOW_NAME = "openalex"


def _log_details(
    result: object,
    stage: str,
) -> dict[str, Any]:
    logs = getattr(result, "logs", [])
    for entry in logs:
        if entry.stage == stage:
            return entry.details
    return {}


def _verification_summary(
    result: object,
    candidate_type: str,
) -> str | None:
    records = [
        record
        for record in getattr(result, "candidate_verifications", [])
        if record.candidate_type == candidate_type
    ]
    if not records:
        return None
    kept = sum(1 for record in records if record.included)
    rejected = [record.label for record in records if not record.included]
    summary = f"{candidate_type}: kept {kept}/{len(records)}"
    if rejected:
        summary += f"; rejected: {', '.join(rejected[:5])}"
    return summary


class DeepLiteratureSearch:
    def __init__(
        self,
        topic: str,
        output_dir: str | None = None,
        output_filename: str = "results.json",
        save_files: bool = True,
        deps: OpenAlexDependencies | None = None,
    ) -> None:
        self.topic = topic
        self.output_dir = output_dir
        self.output_filename = output_filename
        self.save_files = save_files
        self.deps = deps

    async def deep_lit_search(
        self,
        *,
        max_papers: int = 20,
        per_page: int | None = None,
        parallel: int = 4,
        mode: str = PipelineMode.NATURAL_LANGUAGE_KEYWORDS_AND_TOPICS.value,
        target: str = RetrievalTarget.WORKS.value,
        check_valid_topic: bool = True,
        candidate_limit: int | None = None,
        selection_limit: int | None = None,
        max_author_topics_per_keyword: int | None = None,
        selector_model: str | None = None,
        selector_strategy: str | None = None,
        verify_candidate_relevance: bool | None = None,
        verifier_model: str | None = None,
        top_k: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        yield f"Starting OpenAlex workflow for input: {self.topic}"
        options = OpenAlexPipelineOptions(
            mode=PipelineMode(mode),
            target=RetrievalTarget(target),
            candidate_limit=candidate_limit or settings.candidate_limit,
            selection_limit=selection_limit or settings.selection_limit,
            max_results_per_query=max_papers or settings.max_results_per_query,
            per_page=per_page or settings.per_page,
            top_k=top_k or settings.top_k,
            parallel=parallel or settings.parallel,
            max_author_topics_per_keyword=(
                max_author_topics_per_keyword
                or settings.max_author_topics_per_keyword
            ),
            selector_model=selector_model or settings.selector_model,
            selector_strategy=selector_strategy or settings.selector_strategy,
            selector_temperature=settings.selector_temperature,
            fallback_to_heuristic=settings.fallback_to_heuristic,
            verify_candidate_relevance=(
                settings.verify_candidate_relevance
                if verify_candidate_relevance is None
                else verify_candidate_relevance
            ),
            verifier_model=verifier_model or settings.verifier_model,
            verifier_temperature=settings.verifier_temperature,
            fallback_to_unverified_candidates=(
                settings.fallback_to_unverified_candidates
            ),
            generated_query_sort=settings.generated_query_sort,
            request_timeout_seconds=settings.request_timeout_seconds,
            max_authors_per_paper=settings.max_authors_per_paper,
            check_valid_topic=check_valid_topic,
            save_output=self.save_files,
            output_dir=self.output_dir,
            output_filename=self.output_filename,
        )
        result = await run_openalex_pipeline(self.topic, options, deps=self.deps)
        focus_details = _log_details(result, "query_focus")
        query_focus = focus_details.get("query_focus")
        if query_focus:
            yield f"Query focus: {query_focus}"
        if result.query_modifiers:
            yield (
                "Applied modifiers: "
                + ", ".join(
                    modifier.filter_fragment for modifier in result.query_modifiers
                )
            )
        for candidate_type in ("keyword", "topic", "author_topic"):
            summary = _verification_summary(result, candidate_type)
            if summary:
                yield f"Verification {summary}"
        plan_details = _log_details(result, "query_plan")
        work_queries = len(plan_details.get("work_queries", []))
        author_queries = len(plan_details.get("author_queries", []))
        yield f"Planned queries: works={work_queries}, authors={author_queries}"
        work_queries = result.summary.total_queries_executed if result.summary else 0
        author_queries = (
            result.author_summary.total_queries_executed if result.author_summary else 0
        )
        status_bits = [f"Work queries: {work_queries}", f"Author queries: {author_queries}"]
        if result.summary is not None:
            status_bits.append(f"Top works: {result.summary.top_k_returned}")
        if result.author_summary is not None:
            status_bits.append(f"Top authors: {result.author_summary.top_k_returned}")
        yield "OpenAlex workflow complete. " + ", ".join(status_bits)
        if result.output_path:
            yield f"Results saved: {result.output_path}"
        yield json.dumps(result.model_dump(mode="json"), indent=2)
