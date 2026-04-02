from __future__ import annotations

import re
from difflib import SequenceMatcher

from .schemas import (
    AppliedQueryModifier,
    KeywordCandidate,
    TopicCandidate,
)
from .text import normalize_alias, normalize_text, tokenize

YEAR_RANGE_PATTERN = re.compile(
    r"\b(?:published\s+)?(?P<relation>after|since|from)\s+(?P<year>20\d{2})\b",
    flags=re.IGNORECASE,
)
CITATION_COMPARISON_PATTERN = re.compile(
    r"\b(?:citation count|citations?|cited(?:\s+by)?\s+count)\s*"
    r"(?P<operator>>=|<=|>|<|=)\s*(?P<count>\d+)\b",
    flags=re.IGNORECASE,
)
CITATION_WORD_COMPARISON_PATTERN = re.compile(
    r"\b(?:citation count|citations?|cited(?:\s+by)?\s+count)\s+"
    r"(?P<operator>greater than|more than|less than|under|over|at least)\s+"
    r"(?P<count>\d+)\b",
    flags=re.IGNORECASE,
)
TOPIC_FOCUS_CLEANUP_PATTERNS = (
    r"\b(?:get|find|show me|give me|retrieve)\b",
    r"\btop\s+\d+\s+(?:papers?|works?|articles?|studies?)\b",
    r"\btop\s+\d+\b",
    r"\b(?:papers?|works?|articles?|studies?)\b",
    r"\brelated\b",
    r"\b(?:has to be|must be|should be)\b",
    r"\b(?:ranked|sorted)\s+by\b[^,.;]*",
)


def _score_phrase_match(query_norm: str, candidate_norm: str) -> float:
    if not query_norm or not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 125.0
    if candidate_norm in query_norm:
        return 60.0
    if query_norm in candidate_norm:
        return 45.0
    return 0.0


def _score_token_overlap(tokens: list[str], text: str, *, full_weight: float) -> float:
    normalized = normalize_text(text)
    candidate_tokens = normalized.split()
    score = 0.0
    for token in tokens:
        if f" {token} " in f" {normalized} ":
            score += full_weight
        elif token in normalized:
            score += full_weight / 2.0
        else:
            best_ratio = max(
                (
                    SequenceMatcher(None, token, candidate).ratio()
                    for candidate in candidate_tokens
                ),
                default=0.0,
            )
            if best_ratio >= 0.82:
                score += full_weight * 0.45
    return score


def extract_query_modifiers(query: str) -> list[AppliedQueryModifier]:
    lowered = normalize_text(query)
    modifiers: list[AppliedQueryModifier] = []

    if "recent" in lowered.split():
        modifiers.append(
            AppliedQueryModifier(
                source_phrase="recent",
                filter_fragment="from_publication_date:2020-01-01",
                reason="Interpret recency language as papers published on or after January 1, 2020.",
            )
        )

    if "important" in lowered.split():
        modifiers.append(
            AppliedQueryModifier(
                source_phrase="important",
                filter_fragment="fwci:>5",
                reason="Interpret importance language as Field-weighted Citation Impact greater than 5.",
            )
        )

    for match in YEAR_RANGE_PATTERN.finditer(query):
        relation = match.group("relation").lower()
        year = int(match.group("year"))
        start_year = year + 1 if relation == "after" else year
        modifiers.append(
            AppliedQueryModifier(
                source_phrase=match.group(0),
                filter_fragment=f"from_publication_date:{start_year:04d}-01-01",
                reason=(
                    "Interpret publication-year language as a lower bound on "
                    "publication date."
                ),
            )
        )

    for match in CITATION_COMPARISON_PATTERN.finditer(query):
        operator = match.group("operator")
        count = int(match.group("count"))
        modifiers.append(
            AppliedQueryModifier(
                source_phrase=match.group(0),
                filter_fragment=_citation_filter_fragment(operator, count),
                reason="Interpret citation-count language as an OpenAlex cited_by_count filter.",
            )
        )

    for match in CITATION_WORD_COMPARISON_PATTERN.finditer(query):
        operator = match.group("operator").lower()
        count = int(match.group("count"))
        modifiers.append(
            AppliedQueryModifier(
                source_phrase=match.group(0),
                filter_fragment=_citation_filter_fragment(operator, count),
                reason="Interpret citation-count language as an OpenAlex cited_by_count filter.",
            )
        )

    return modifiers


def _citation_filter_fragment(operator: str, count: int) -> str:
    operator_map = {
        ">": f"cited_by_count:>{count}",
        ">=": f"cited_by_count:{count}-",
        "=": f"cited_by_count:{count}",
        "<": f"cited_by_count:<{count}",
        "<=": f"cited_by_count:<{count + 1}",
        "greater than": f"cited_by_count:>{count}",
        "more than": f"cited_by_count:>{count}",
        "over": f"cited_by_count:>{count}",
        "less than": f"cited_by_count:<{count}",
        "under": f"cited_by_count:<{count}",
        "at least": f"cited_by_count:{count}-",
    }
    try:
        return operator_map[operator]
    except KeyError as exc:
        raise ValueError(f"Unsupported citation-count operator: {operator}") from exc


def extract_query_topic_focus(query: str) -> str:
    focused_query = query
    for modifier in extract_query_modifiers(query):
        if modifier.source_phrase:
            focused_query = re.sub(
                re.escape(modifier.source_phrase),
                " ",
                focused_query,
                flags=re.IGNORECASE,
            )
    for pattern in TOPIC_FOCUS_CLEANUP_PATTERNS:
        focused_query = re.sub(pattern, " ", focused_query, flags=re.IGNORECASE)
    focused_query = re.sub(r"\b(?:and|or)\b", " ", focused_query, flags=re.IGNORECASE)
    focused_query = re.sub(r"[^A-Za-z0-9]+", " ", focused_query)
    focused_query = re.sub(r"\s+", " ", focused_query).strip()
    return focused_query or query.strip()


def build_keyword_candidates(
    query: str,
    catalog: list[KeywordCandidate],
    limit: int,
) -> list[KeywordCandidate]:
    query_norm = normalize_text(query)
    query_alias = normalize_alias(query)
    query_tokens = tokenize(query)
    ranked: list[KeywordCandidate] = []

    for item in catalog:
        candidate_tokens = tokenize(item.keyword)
        matching_tokens = sum(1 for token in query_tokens if token in candidate_tokens)
        score = _score_phrase_match(query_norm, normalize_text(item.keyword))
        if query_alias and query_alias == item.alias:
            score += 55.0
        score += _score_token_overlap(query_tokens, item.keyword, full_weight=12.0)
        score += _score_token_overlap(
            query_tokens, item.alias.replace("-", " "), full_weight=8.0
        )
        score += matching_tokens * 8.0
        score += max(len(candidate_tokens) - 1, 0) * 6.0
        if len(candidate_tokens) == 1 and len(query_tokens) > 1:
            score -= 35.0
        if matching_tokens <= 1 and len(query_tokens) >= 3:
            score -= 12.0
        score += min(item.topic_count, 10)
        if score > 0:
            ranked.append(item.model_copy(update={"lexical_score": score}))

    if not ranked:
        fallback = sorted(catalog, key=lambda item: item.topic_count, reverse=True)
        return [
            item.model_copy(update={"lexical_score": float(item.topic_count)})
            for item in fallback[:limit]
        ]

    ranked.sort(
        key=lambda item: (item.lexical_score, item.topic_count, item.keyword.lower()),
        reverse=True,
    )
    return ranked[:limit]


def build_topic_candidates(
    query: str,
    catalog: list[TopicCandidate],
    limit: int,
) -> list[TopicCandidate]:
    query_norm = normalize_text(query)
    query_tokens = tokenize(query)
    ranked: list[TopicCandidate] = []

    for item in catalog:
        topic_name = item.topic_name
        summary = item.summary or ""
        keywords = item.keywords or ""
        score = _score_phrase_match(query_norm, normalize_text(topic_name))
        score += _score_token_overlap(query_tokens, topic_name, full_weight=16.0)
        score += _score_token_overlap(query_tokens, keywords, full_weight=7.0)
        score += _score_token_overlap(query_tokens, summary, full_weight=4.0)
        score += _score_token_overlap(
            query_tokens, item.subfield_name or "", full_weight=4.0
        )
        score += _score_token_overlap(
            query_tokens, item.field_name or "", full_weight=3.0
        )
        if score > 0:
            ranked.append(item.model_copy(update={"lexical_score": score}))

    if not ranked:
        fallback = sorted(catalog, key=lambda item: item.topic_name.lower())
        return [
            item.model_copy(update={"lexical_score": 0.0}) for item in fallback[:limit]
        ]

    ranked.sort(
        key=lambda item: (item.lexical_score, item.topic_name.lower()),
        reverse=True,
    )
    return ranked[:limit]
