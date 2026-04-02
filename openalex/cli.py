from __future__ import annotations

import argparse
import asyncio
import sys

from .catalog import build_catalog_repository_factory
from .config import settings
from .ports import OpenAlexDependencies
from .workflow import DeepLiteratureSearch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the standalone OpenAlex workflow."
    )
    parser.add_argument("query", help="Natural-language request or OpenAlex query.")
    parser.add_argument(
        "--mode",
        choices=[
            "natural_language_keywords_and_topics",
            "natural_language_keywords",
            "natural_language_topics",
            "openalex_query_keywords",
            "exact_openalex_query",
        ],
        default="natural_language_keywords_and_topics",
        help="OpenAlex workflow mode.",
    )
    parser.add_argument(
        "--max-results-per-query",
        "--max-papers",
        dest="max_results_per_query",
        type=int,
        default=settings.max_results_per_query,
        help="Maximum total results to fetch for each executed OpenAlex query.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=settings.per_page,
        help="OpenAlex page size to use while paginating. Clamped to 200.",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="works",
        choices=["works", "authors", "works_and_authors"],
        help="Which OpenAlex entity type(s) to retrieve.",
    )
    parser.add_argument("--top-k", type=int, default=settings.top_k)
    parser.add_argument("--parallel", type=int, default=settings.parallel)
    parser.add_argument("--candidate-limit", type=int, default=settings.candidate_limit)
    parser.add_argument("--selection-limit", type=int, default=settings.selection_limit)
    parser.add_argument(
        "--max-author-topics-per-keyword",
        type=int,
        default=settings.max_author_topics_per_keyword,
        help="Maximum author-topic queries to derive from each selected keyword.",
    )
    parser.add_argument("--selector-model", type=str, default=settings.selector_model)
    parser.add_argument(
        "--verifier-model",
        type=str,
        default=settings.verifier_model,
        help="Gemini model to use for post-selection candidate verification.",
    )
    parser.add_argument(
        "--selector-strategy",
        type=str,
        default=settings.selector_strategy,
        choices=["heuristic", "external", "llm"],
        help=(
            "Selection mode. 'heuristic' is fully standalone; 'external' and 'llm' "
            "are reserved for injected selectors when using the library API."
        ),
    )
    parser.add_argument(
        "--skip-candidate-verification",
        action="store_true",
        help="Skip LLM verification of selected keyword/topic labels before query execution.",
    )
    parser.add_argument(
        "--catalog-backend",
        type=str,
        default=settings.catalog_backend,
        choices=["auto", "json", "postgres"],
        help="Catalog source for keyword/topic modes.",
    )
    parser.add_argument(
        "--catalog-path",
        type=str,
        default=settings.catalog_path,
        help="Path to a JSON catalog file used in keyword/topic modes.",
    )
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--output-filename", type=str, default=settings.output_filename)
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write the JSON artifact to disk.",
    )
    parser.add_argument(
        "--skip-query-validation",
        action="store_true",
        help="Skip natural-language query validation before planning/execution.",
    )
    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    deps = OpenAlexDependencies(
        catalog_repository_factory=build_catalog_repository_factory(
            backend=args.catalog_backend,
            catalog_path=args.catalog_path,
        )
    )

    workflow = DeepLiteratureSearch(
        topic=args.query,
        output_dir=args.output_dir,
        output_filename=args.output_filename,
        save_files=not args.no_save,
        deps=deps,
    )
    stream = workflow.deep_lit_search(
        max_papers=args.max_results_per_query,
        per_page=args.per_page,
        target=args.target,
        top_k=args.top_k,
        parallel=args.parallel,
        mode=args.mode,
        check_valid_topic=not args.skip_query_validation,
        candidate_limit=args.candidate_limit,
        selection_limit=args.selection_limit,
        max_author_topics_per_keyword=args.max_author_topics_per_keyword,
        selector_model=args.selector_model,
        selector_strategy=args.selector_strategy,
        verify_candidate_relevance=not args.skip_candidate_verification,
        verifier_model=args.verifier_model,
    )
    async for message in stream:
        print(message)
        sys.stdout.flush()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
