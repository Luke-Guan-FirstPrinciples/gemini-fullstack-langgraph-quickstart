# Changelog

## 2026-04-16

### Research Agent

- Switched paper citation ranking and display to Semantic Scholar citation counts while keeping OpenAlex as an enrichment backend.
- Added separate venue fields:
  - `paper.source` remains the web/LLM-discovered source string.
  - `paper.semantic_scholar.publication_venue_name` now carries the publication venue resolved from Semantic Scholar.
- Removed FWCI from ranking inputs, normalization metadata, UI controls, and ranking explanations.
- Made Semantic Scholar API-key usage configurable and opt-in via `RESEARCH_SEMANTIC_SCHOLAR_USE_API_KEY`; unauthenticated calls remain supported.
- Removed the separate author-ranking/enrichment pipeline and its API/UI surface.
- Added deduplication in two places:
  - raw search results are deduplicated across queries and loop iterations before being appended to `all_search_results`
  - enriched paper records are merged by DOI, OpenAlex ID, Semantic Scholar ID, and canonicalized title/year fallbacks before reranking

### UI

- Removed the `Top ranked paper` spotlight section from the Research Agent panel.
- Removed the `Top authors` tab and author-summary UI.
- Updated paper cards to show Semantic Scholar citations and publication venue alongside the web/LLM source label.
- Updated mock Research Agent responses to match the current backend contract.

### Docs And Verification

- Updated Research Agent docs and architecture notes to reflect Semantic Scholar ranking, author removal, and deduplication behavior.
- Verified `python3 -m compileall research_agent`.
- Verified `npm run build` in `literature-studio`.
- Full Python unit execution is still blocked in the current shell when project dependencies such as `pydantic` are missing.
