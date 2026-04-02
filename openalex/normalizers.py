from __future__ import annotations

from typing import Any

from .schemas import (
    AuthorInstitution,
    AuthorSummaryStats,
    AuthorTopic,
    MatchedQuery,
    OpenAlexAuthor,
    OpenAlexPaper,
    PaperAuthor,
    PaperLocation,
)
from .text import short_openalex_id


def normalize_paper(
    work: dict[str, Any],
    matches: list[MatchedQuery],
    *,
    max_authors_per_paper: int,
) -> OpenAlexPaper:
    authorships = work.get("authorships", [])
    authors: list[PaperAuthor] = []
    if isinstance(authorships, list):
        for authorship in authorships[:max_authors_per_paper]:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author")
            if not isinstance(author, dict):
                continue
            authors.append(
                PaperAuthor(
                    name=str(author.get("display_name", "Unknown Author")),
                    openalex_id=short_openalex_id(author.get("id")),
                )
            )

    primary_location_data = work.get("primary_location")
    primary_location: PaperLocation | None = None
    if isinstance(primary_location_data, dict):
        source = primary_location_data.get("source")
        primary_location = PaperLocation(
            source_display_name=source.get("display_name")
            if isinstance(source, dict)
            else None,
            source_openalex_id=short_openalex_id(source.get("id"))
            if isinstance(source, dict)
            else None,
            landing_page_url=primary_location_data.get("landing_page_url"),
            pdf_url=primary_location_data.get("pdf_url"),
            is_oa=primary_location_data.get("is_oa"),
        )

    topics_data = work.get("topics", [])
    topics: list[str] = []
    if isinstance(topics_data, list):
        for topic in topics_data[:5]:
            if isinstance(topic, dict):
                display_name = topic.get("display_name")
                if isinstance(display_name, str) and display_name:
                    topics.append(display_name)

    matched_queries = sorted(matches, key=lambda item: item.label.lower())
    return OpenAlexPaper(
        openalex_id=short_openalex_id(work.get("id")) or "unknown",
        title=str(work.get("display_name", "Untitled")),
        cited_by_count=int(work.get("cited_by_count", 0) or 0),
        publication_year=(
            int(work["publication_year"]) if work.get("publication_year") else None
        ),
        publication_date=(
            str(work["publication_date"]) if work.get("publication_date") else None
        ),
        doi=work.get("doi"),
        work_type=work.get("type"),
        primary_location=primary_location,
        authors=authors,
        topics=topics,
        matched_queries=matched_queries,
        matched_query_count=len(matched_queries),
        overlap_type="overlap" if len(matched_queries) > 1 else "unique",
    )


def normalize_author(
    author: dict[str, Any],
    matches: list[MatchedQuery],
) -> OpenAlexAuthor:
    summary_stats_data = author.get("summary_stats")
    summary_stats: AuthorSummaryStats | None = None
    if isinstance(summary_stats_data, dict):
        summary_stats = AuthorSummaryStats(
            two_year_mean_citedness=(
                float(summary_stats_data["2yr_mean_citedness"])
                if summary_stats_data.get("2yr_mean_citedness") is not None
                else None
            ),
            h_index=(
                int(summary_stats_data["h_index"])
                if summary_stats_data.get("h_index") is not None
                else None
            ),
            i10_index=(
                int(summary_stats_data["i10_index"])
                if summary_stats_data.get("i10_index") is not None
                else None
            ),
        )

    institutions: list[AuthorInstitution] = []
    last_known_institutions = author.get("last_known_institutions", [])
    if isinstance(last_known_institutions, list):
        for institution in last_known_institutions[:3]:
            if not isinstance(institution, dict):
                continue
            institutions.append(
                AuthorInstitution(
                    display_name=str(
                        institution.get("display_name", "Unknown Institution")
                    ),
                    openalex_id=short_openalex_id(institution.get("id")),
                    country_code=(
                        str(institution["country_code"])
                        if institution.get("country_code") is not None
                        else None
                    ),
                    institution_type=(
                        str(institution["type"])
                        if institution.get("type") is not None
                        else None
                    ),
                )
            )

    topics: list[AuthorTopic] = []
    topics_data = author.get("topics", [])
    if isinstance(topics_data, list):
        for topic in topics_data[:5]:
            if not isinstance(topic, dict):
                continue
            display_name = topic.get("display_name")
            topic_id = short_openalex_id(topic.get("id"))
            if not isinstance(display_name, str) or not topic_id:
                continue
            topics.append(
                AuthorTopic(
                    openalex_id=topic_id,
                    display_name=display_name,
                    count=(
                        int(topic["count"]) if topic.get("count") is not None else None
                    ),
                )
            )

    matched_queries = sorted(matches, key=lambda item: item.label.lower())
    return OpenAlexAuthor(
        openalex_id=short_openalex_id(author.get("id")) or "unknown",
        display_name=str(author.get("display_name", "Unknown Author")),
        orcid=(
            str(author["orcid"]) if author.get("orcid") is not None else None
        ),
        works_count=int(author.get("works_count", 0) or 0),
        cited_by_count=int(author.get("cited_by_count", 0) or 0),
        summary_stats=summary_stats,
        last_known_institutions=institutions,
        topics=topics,
        matched_queries=matched_queries,
        matched_query_count=len(matched_queries),
        overlap_type="overlap" if len(matched_queries) > 1 else "unique",
    )
