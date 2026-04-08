"""CLI entry point: python -m research_agent 'your query here'."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from research_agent.config import Settings
from research_agent.graph import run_research


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research_agent",
        description="LLM-powered academic literature search via LangGraph",
    )
    p.add_argument("query", help="Natural language research query")
    p.add_argument(
        "--llm-provider",
        choices=["gemini", "openai", "anthropic"],
        default=None,
        help="LLM provider (default: from RESEARCH_LLM_PROVIDER or 'gemini')",
    )
    p.add_argument("--llm-model", default=None, help="Model name override")
    p.add_argument(
        "--search-provider",
        choices=["google_cse", "tavily", "jina", "openai"],
        default=None,
        help="Search provider (default: from SEARCH_PROVIDER or 'google_cse')",
    )
    p.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Max search→assess loop iterations (default: 2)",
    )
    p.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output JSON file path (default: stdout + logs/research_agent/)",
    )
    p.add_argument(
        "--ranked-output",
        default=None,
        help="Optional output path for ranked-results JSON (default: derived sibling/log file)",
    )
    p.add_argument(
        "--semantic-weight",
        type=float,
        default=None,
        help="Weight for semantic relevance in paper reranking",
    )
    p.add_argument(
        "--citation-weight",
        type=float,
        default=None,
        help="Weight for citation count in paper reranking",
    )
    p.add_argument(
        "--fwci-weight",
        type=float,
        default=None,
        help="Weight for FWCI in paper reranking",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    # Build a Settings override from CLI args
    cfg = Settings()
    if args.llm_provider:
        cfg.llm_provider = args.llm_provider
    if args.llm_model:
        cfg.llm_model = args.llm_model
    if args.search_provider:
        cfg.search_provider = args.search_provider
    if args.semantic_weight is not None:
        cfg.semantic_relevance_weight = args.semantic_weight
    if args.citation_weight is not None:
        cfg.citation_count_weight = args.citation_weight
    if args.fwci_weight is not None:
        cfg.fwci_weight = args.fwci_weight

    final_state = asyncio.run(
        run_research(
            args.query,
            cfg=cfg,
            max_iterations=args.max_iterations,
        )
    )

    # Extract the structured output
    output = final_state.get("structured_output") or {}
    ranked_output = final_state.get("ranked_output") or {}
    output["_meta"] = {
        "query": args.query,
        "llm_provider": cfg.llm_provider,
        "llm_model": cfg.llm_model,
        "search_provider": cfg.search_provider,
        "ranking_weights": cfg.ranking_weights(),
        "iterations": final_state.get("iteration", 0),
        "total_raw_results": len(final_state.get("all_search_results", [])),
        "timestamp": datetime.now().isoformat(),
    }
    if ranked_output:
        ranked_output["_meta"] = {
            "query": args.query,
            "llm_provider": cfg.llm_provider,
            "llm_model": cfg.rerank_model_name(),
            "search_provider": cfg.search_provider,
            "ranking_weights": cfg.ranking_weights(),
            "iterations": final_state.get("iteration", 0),
            "total_raw_results": len(final_state.get("all_search_results", [])),
            "timestamp": datetime.now().isoformat(),
        }

    result_json = json.dumps(output, indent=2, default=str)
    ranked_json = json.dumps(ranked_output, indent=2, default=str)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result_json, encoding="utf-8")
        ranked_path = Path(args.ranked_output) if args.ranked_output else output_path.with_name(
            f"{output_path.stem}_ranked{output_path.suffix or '.json'}"
        )
        ranked_path.parent.mkdir(parents=True, exist_ok=True)
        ranked_path.write_text(ranked_json, encoding="utf-8")
        print(f"Results written to {args.output}", file=sys.stderr)
        print(f"Ranked results written to {ranked_path}", file=sys.stderr)
    else:
        print(result_json)

    # Also save to log dir
    log_dir = Path(cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = log_dir / f"results_{ts}.json"
    ranked_path = log_dir / f"ranked_results_{ts}.json"
    result_path.write_text(result_json, encoding="utf-8")
    ranked_path.write_text(ranked_json, encoding="utf-8")
    print(f"Results also saved to {result_path}", file=sys.stderr)
    print(f"Ranked results also saved to {ranked_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
