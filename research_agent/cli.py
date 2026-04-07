"""CLI entry point: python -m research_agent 'your query here'."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from research_agent.config import Settings, settings
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

    final_state = asyncio.run(
        run_research(
            args.query,
            cfg=cfg,
            max_iterations=args.max_iterations,
        )
    )

    # Extract the structured output
    output = final_state.get("structured_output") or {}
    output["_meta"] = {
        "query": args.query,
        "llm_provider": cfg.llm_provider,
        "llm_model": cfg.llm_model,
        "search_provider": cfg.search_provider,
        "iterations": final_state.get("iteration", 0),
        "total_raw_results": len(final_state.get("all_search_results", [])),
        "timestamp": datetime.now().isoformat(),
    }

    result_json = json.dumps(output, indent=2, default=str)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(result_json, encoding="utf-8")
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(result_json)

    # Also save to log dir
    log_dir = Path(cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = log_dir / f"results_{ts}.json"
    result_path.write_text(result_json, encoding="utf-8")
    print(f"Results also saved to {result_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
