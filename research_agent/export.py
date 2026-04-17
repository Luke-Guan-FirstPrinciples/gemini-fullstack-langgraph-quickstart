"""Persist research-agent runs as local JSON files.

The export schema intentionally mirrors the upstream "literature study" sample
JSON layout so downstream tooling can consume results from either source.

Top-level shape::

    {
      "workflow_name": "research",
      "status": "...",
      "topic": "...",
      "sub_topics": [...],
      "arxiv_categories": [...],
      "arxiv_search_queries": [...],
      "papers_by_topic": {"<topic>": [<paper>, ...]},
      "sorted_papers": {"<topic>": [<paper>, ...]},
      "paper_summaries": [],
      "paper_critic_summaries": [],
      "web_queries": {},
      "web_sources": {},
      "web_summaries": [],
      "final_summaries": [],
      "final_composition": null,
      "elapsed": 0.0
    }

The per-paper record uses the keys from the sample: ``id``, ``title``,
``authors``, ``published``, ``summary``, ``pdf_url``, ``full_content``,
``cite_key``, ``source``, ``openalex_id``, ``cited_by_count_from_openalex``,
``cited_by_count_from_semantic_scholar``, ``publication_venue``, ``fwci``,
``openalex_author_ids``.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from research_agent.config import Settings

logger = logging.getLogger("research_agent.export")

_ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(?P<id>\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+/\d{7})",
    re.IGNORECASE,
)
_ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$|^[a-z\-]+/\d{7}$", re.IGNORECASE)


def build_local_result_payload(
    query: str,
    final_state: dict[str, Any],
    cfg: Settings,
    *,
    elapsed_seconds: float | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Convert a LangGraph final state into a sample.json-compatible payload."""
    parsed_query = final_state.get("parsed_query") or {}
    structured_output = final_state.get("structured_output") or {}
    ranked_output = final_state.get("ranked_output") or {}

    structured_papers = list(structured_output.get("papers") or [])
    ranked_papers = list(ranked_output.get("papers") or [])

    topic = query.strip() or "research"
    topic_key = _topic_key(topic)

    sub_topics = _coerce_str_list(parsed_query.get("fields")) or _coerce_str_list(
        structured_output.get("fields")
    )
    arxiv_search_queries = _coerce_str_list(parsed_query.get("search_queries"))

    papers_by_topic = {
        topic_key: [_paper_to_sample(paper, idx) for idx, paper in enumerate(structured_papers)]
    }
    sorted_papers = {
        topic_key: [_paper_to_sample(paper, idx) for idx, paper in enumerate(ranked_papers)]
    }

    resolved_status = status or _infer_status(structured_output, ranked_output)

    return {
        "workflow_name": "research",
        "status": resolved_status,
        "topic": topic,
        "sub_topics": sub_topics,
        "arxiv_categories": [],
        "arxiv_search_queries": arxiv_search_queries,
        "papers_by_topic": papers_by_topic,
        "sorted_papers": sorted_papers,
        "paper_summaries": [],
        "paper_critic_summaries": [],
        "web_queries": {},
        "web_sources": {},
        "web_summaries": [],
        "final_summaries": [],
        "final_composition": None,
        "elapsed": float(elapsed_seconds) if elapsed_seconds is not None else 0.0,
        "_meta": _build_meta(query, cfg, final_state),
    }


def save_local_results(
    payload: dict[str, Any],
    *,
    output_dir: str | Path,
    timestamp: datetime | None = None,
    filename: str | None = None,
) -> Path:
    """Write ``payload`` as JSON to ``output_dir`` and return the path."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    ts = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    name = filename or f"research_{ts}.json"
    path = directory / name
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("Saved local research result to %s", path)
    return path


# ---------------------------------------------------------------------------
# Paper mapping helpers
# ---------------------------------------------------------------------------


def _paper_to_sample(paper: Any, index: int) -> dict[str, Any]:
    data = _as_dict(paper)
    openalex = _as_dict(data.get("openalex"))
    semantic_scholar = _as_dict(data.get("semantic_scholar"))

    title = _coerce_str(data.get("title")) or ""
    url = _coerce_str(data.get("url")) or ""
    doi = _coerce_str(data.get("doi")) or _coerce_str(openalex.get("doi")) or _coerce_str(
        semantic_scholar.get("doi")
    )

    arxiv_id = _extract_arxiv_id(url) or _extract_arxiv_id(data.get("source"))
    paper_id = arxiv_id or doi or url or f"paper-{index + 1}"

    source = _coerce_str(data.get("source")) or ("arxiv" if arxiv_id else "")

    pdf_url = url
    if arxiv_id:
        clean_id = arxiv_id.split("v")[0] if re.match(r"^\d{4}\.", arxiv_id) else arxiv_id
        pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"

    published = _published_date(data.get("year"))

    publication_venue = (
        _coerce_str(semantic_scholar.get("publication_venue_name"))
        or _coerce_str(semantic_scholar.get("venue"))
        or _coerce_str(openalex.get("source_display_name"))
    )

    return {
        "id": paper_id,
        "title": title,
        "authors": _coerce_str_list(data.get("authors")),
        "published": published,
        "summary": _coerce_str(data.get("abstract")) or "",
        "pdf_url": pdf_url,
        "full_content": "",
        "cite_key": f"ref{index + 1}",
        "source": source,
        "openalex_id": _coerce_str(openalex.get("openalex_id")),
        "cited_by_count_from_openalex": _coerce_int(openalex.get("citation_count")),
        "cited_by_count_from_semantic_scholar": _coerce_int(
            semantic_scholar.get("citation_count")
        ),
        "publication_venue": publication_venue,
        "fwci": _coerce_float(openalex.get("fwci")),
        "openalex_author_ids": [],
    }


def _extract_arxiv_id(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    match = _ARXIV_URL_RE.search(text)
    if match:
        return match.group("id")
    if _ARXIV_ID_RE.match(text):
        return text
    return None


def _published_date(year: Any) -> str:
    year_int = _coerce_int(year)
    if year_int is None:
        return ""
    return f"{year_int:04d}-01-01"


def _topic_key(topic: str) -> str:
    normalized = " ".join(topic.strip().split())
    return normalized.lower()


def _infer_status(structured_output: dict[str, Any], ranked_output: dict[str, Any]) -> str:
    if ranked_output.get("papers"):
        return "completed"
    if structured_output.get("papers"):
        return "stopped_after_structuring"
    return "stopped_without_results"


def _build_meta(
    query: str,
    cfg: Settings,
    final_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "query": query,
        "llm_provider": cfg.llm_provider,
        "llm_model": cfg.resolved_llm_model(),
        "search_provider": cfg.search_provider,
        "ranking_weights": cfg.ranking_weights(),
        "iterations": final_state.get("iteration", 0),
        "total_raw_results": len(final_state.get("all_search_results", []) or []),
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Coercion utilities
# ---------------------------------------------------------------------------


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
        except Exception:
            return {}
        if isinstance(dumped, dict):
            return dumped
    return {}


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _coerce_str(item)
        if text:
            result.append(text)
    return result


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
