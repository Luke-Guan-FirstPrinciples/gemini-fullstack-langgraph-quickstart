from __future__ import annotations

import re

STOPWORDS = {
    "about",
    "advances",
    "analysis",
    "and",
    "development",
    "developments",
    "for",
    "from",
    "important",
    "into",
    "latest",
    "literature",
    "methods",
    "papers",
    "physics",
    "recent",
    "research",
    "review",
    "state",
    "studies",
    "study",
    "survey",
    "techniques",
    "the",
    "their",
    "using",
    "with",
}


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def normalize_alias(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def slugify(text: str) -> str:
    return normalize_alias(text)


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOPWORDS]


def short_openalex_id(value: str | None) -> str | None:
    if not value:
        return None
    if "/" not in value:
        return value
    return value.rsplit("/", 1)[-1]


def openalex_topic_id(topic_id: int) -> str:
    return f"T{topic_id}"


def openalex_keyword_id(alias: str) -> str:
    normalized = normalize_alias(alias)
    if not normalized:
        raise ValueError("OpenAlex keyword alias cannot be empty")
    return normalized
