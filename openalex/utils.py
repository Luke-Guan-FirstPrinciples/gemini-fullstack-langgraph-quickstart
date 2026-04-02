"""Backward-compatible re-exports. New code should import from the specific modules."""

from __future__ import annotations

from .output import build_run_artifact_paths, create_output_dir, save_run_result
from .query_builder import (
    append_filter,
    build_query_for_author_topic,
    build_query_for_keyword,
    build_query_for_topic,
    extract_query_intent,
    extract_topic_ids,
    filter_components_for_authors,
    parse_openalex_query_input,
    split_filter_components,
    strip_text_constraints,
)
from .scoring import (
    build_keyword_candidates,
    build_topic_candidates,
    extract_query_modifiers,
    extract_query_topic_focus,
)
from .text import (
    normalize_alias,
    normalize_text,
    openalex_keyword_id,
    openalex_topic_id,
    short_openalex_id,
    slugify,
    tokenize,
)

__all__ = [
    "append_filter",
    "build_keyword_candidates",
    "build_query_for_author_topic",
    "build_query_for_keyword",
    "build_query_for_topic",
    "build_run_artifact_paths",
    "build_topic_candidates",
    "create_output_dir",
    "extract_query_intent",
    "extract_query_modifiers",
    "extract_query_topic_focus",
    "extract_topic_ids",
    "filter_components_for_authors",
    "normalize_alias",
    "normalize_text",
    "openalex_keyword_id",
    "openalex_topic_id",
    "parse_openalex_query_input",
    "save_run_result",
    "short_openalex_id",
    "slugify",
    "split_filter_components",
    "strip_text_constraints",
    "tokenize",
]
