from __future__ import annotations

import datetime
import json
from pathlib import Path

from .schemas import OpenAlexRunResult
from .text import slugify


def create_output_dir(query: str, output_dir: str | None = None) -> Path:
    slug = slugify(query) or "openalex"
    slug = slug[:50]
    if output_dir:
        base_dir = Path(output_dir)
    else:
        from .config import settings

        base_dir = Path(settings.output_root) if settings.output_root else Path.cwd() / "out"
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    task_dir = base_dir / f"{timestamp}_openalex_{slug}"
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def build_run_artifact_paths(file_path: Path) -> tuple[Path, Path]:
    logs_path = file_path.with_name(f"{file_path.stem}.logs.json")
    llm_calls_path = file_path.with_name(f"{file_path.stem}.llm_calls.json")
    return logs_path, llm_calls_path


def save_run_result(result: OpenAlexRunResult, file_path: Path) -> None:
    logs_path, llm_calls_path = build_run_artifact_paths(file_path)
    with open(file_path, "w", encoding="utf-8") as handle:
        json.dump(
            result.model_dump(
                mode="json",
                exclude={"logs", "llm_calls"},
            ),
            handle,
            indent=2,
            ensure_ascii=False,
        )

    with open(logs_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "workflow_name": result.workflow_name,
                "input_query": result.input_query,
                "logs": result.model_dump(mode="json")["logs"],
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )

    with open(llm_calls_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "workflow_name": result.workflow_name,
                "input_query": result.input_query,
                "summary": (
                    result.llm_usage_summary.model_dump(mode="json")
                    if result.llm_usage_summary is not None
                    else None
                ),
                "calls": [call.model_dump(mode="json") for call in result.llm_calls],
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )
