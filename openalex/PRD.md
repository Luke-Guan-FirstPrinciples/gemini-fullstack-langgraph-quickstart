# OpenAlex Workflow PRD

## Goal

Build a standalone OpenAlex retrieval pipeline that can:

1. Turn a natural-language research request into OpenAlex keyword-based or topic-based searches.
2. Take an OpenAlex query, expand it into relevant keyword searches.
3. Execute an exact OpenAlex works query without expansion.

The pipeline must write a JSON artifact containing top papers, overlap/uniqueness analysis, query provenance, and selected keyword/topic metadata. It should keep the core framework-agnostic so it can be integrated into LangChain, Autogen, or custom orchestrators later through thin adapters.

## In-Scope

- Async standalone workflow under `openalex`
- Config-driven selector strategy with optional external selector injection
- Candidate retrieval from:
  - `openalex.oa_physics_related_keyword_embeddings`
  - `openalex.oa_physics_related_topic_summary_embeddings`
- OpenAlex works API execution and normalized JSON output
- Result comparison across multiple keyword/topic-derived calls
- Optional use of the official OpenAlex CLI as an installed project dependency
- Standalone CLI entry point for the workflow

## Out of Scope

- Full integration into the existing report-generation workflow
- PDF downloading or fulltext ingestion
- In-database vector similarity over the embedding columns
- Support for non-`/works` endpoints in the first version

## Users

- Internal developers integrating literature search into larger systems
- Researchers exploring physics-related OpenAlex discovery flows

## Modes

### 1. `natural_language_keywords`

Input is a natural-language question.

Flow:
- Load keyword catalog from Postgres.
- Lexically pre-rank candidate keywords.
- Use an LLM selector to choose the most relevant OpenAlex keywords from the existing table.
- Execute one OpenAlex `/works` query per keyword using `keywords.id:<alias>`.
- Compare overlap and combine results.

### 2. `natural_language_topics`

Input is a natural-language question.

Flow:
- Load topic catalog from Postgres.
- Lexically pre-rank candidate topics.
- Use an LLM selector to choose the most relevant OpenAlex topics from the existing table.
- Execute one OpenAlex `/works` query per topic using `primary_topic.id:T{topic_id}`.
- Compare overlap and combine results.

### 3. `openalex_query_keywords`

Input is an OpenAlex query string, query params, JSON blob, or full API URL.

Flow:
- Parse the OpenAlex query into a structured `/works` spec.
- Extract text intent from the query when possible.
- Remove text constraints from the base query and preserve non-text filters.
- Select relevant keywords from the physics keyword catalog.
- Execute one keyword query per selected keyword using `keywords.id:<alias>` while preserving non-text filters from the base query.
- Compare overlap and combine results.

### 4. `exact_openalex_query`

Input is an OpenAlex query string, query params, JSON blob, or full API URL.

Flow:
- Parse and validate the exact query.
- Execute it directly against `/works`.
- Normalize and save the returned papers.

## Functional Requirements

- Output must be JSON and include:
  - input query
  - mode
  - selected keywords or topics
  - exact query spec when applicable
  - executed request params and request URLs
  - per-query returned counts
  - combined paper list
  - overlap counts and per-query unique/overlap summaries
- Each paper record must include at least:
  - title
  - OpenAlex ID
  - authors
  - citation count
  - publication year/date
  - DOI
  - work type
  - source/journal metadata when available
  - matched query provenance
- Config must cover:
  - selector model
  - selector strategy (`llm` or `heuristic`)
  - fallback behavior
  - candidate limit
  - selection limit
  - per-query result limit
  - final top-k size
  - concurrency
  - API base URL / key / email

## Non-Functional Requirements

- Async I/O for pipeline orchestration with optional external backends
- Clear failure messages when DB access is required but unavailable
- Safe fallback to heuristic selection if an external selector fails and fallback is enabled
- Importable workflow class and library API that are easy to wrap in tool frameworks later
- No hard dependency in the core on DLS, Autogen, or LangChain

## Ranking and Merge Rules

- Per-query retrieval uses OpenAlex works responses.
- Combined ranking sorts by:
  1. number of matched queries
  2. citation count
  3. publication year
- Papers returned by multiple query executions are marked as overlap.
- Papers returned by only one execution are marked as unique.

## Deliverables

- `openalex` package
- standalone CLI module
- PRD
- tests for parsing, candidate ranking, and merge logic
- `openalex-official` installed as a project dependency
