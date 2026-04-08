# Research Agent

LLM-driven academic literature search pipeline for this repo.

It takes a natural-language query, generates targeted search queries, structures the results, enriches papers with OpenAlex metadata, reranks them, and optionally loops for gap-filling.

## Workflow

Current graph:

```text
parse_query -> execute_search -> structure_results -> enrich_results -> rerank_results -> assess_coverage
                   ^                                                                  |
                   +---------------------- optional sub-query loop -------------------+
```

### 1. `parse_query`

- Input: natural-language research query
- Output: intent, fields, key terms, and 4-6 targeted search queries with `site:` operators

### 2. `execute_search`

- Runs all current search queries in parallel
- Uses the configured search provider: `google_cse`, `openai`, `tavily`, or `jina`

### 3. `structure_results`

- Uses the LLM to turn raw search hits into:
- papers
- authors
- labs
- fields
- keywords
- suggested follow-up queries

### 4. `enrich_results`

- Looks up each paper title in OpenAlex
- Adds:
- authors
- citation count
- FWCI
- DOI
- publication year
- OpenAlex match metadata

### 5. `rerank_results`

- Computes a semantic relevance score for each paper
- Combines weighted signals:
- semantic relevance
- citation count
- FWCI
- Produces `ranked_output`

### 6. `assess_coverage`

- Checks whether the current result set covers the query adequately
- If not, generates sub-queries and loops back to `execute_search`
- Loop count is bounded by `max_iterations`

## Outputs

Each run writes:

- `logs/research_agent/run_<timestamp>.log`
- `logs/research_agent/results_<timestamp>.json`
- `logs/research_agent/ranked_results_<timestamp>.json`

`results_*.json` is the enriched structured output.

`ranked_results_*.json` is the ranked paper list with:

- `ranking.rank`
- `ranking.score`
- `ranking.normalized_signals.semantic_relevance`
- `ranking.normalized_signals.citation_count`
- `ranking.normalized_signals.fwci`

## Setup

Install dependencies in the Python environment you plan to run:

```bash
pip install -r research_agent/requirements.txt
```

Minimum env vars depend on the provider combination you use.

Common ones:

```bash
OPENAI_API_KEY=...
GEMINI_API_KEY=...
GOOGLE_CSE_API_KEY=...
GOOGLE_CSE_ID=...
OPENALEX_EMAIL=you@example.com
```

Useful model env vars:

```bash
LLM_PROVIDER=gemini
LLM_MODEL=
GEMINI_LLM_MODEL=gemini-2.5-flash
OPENAI_LLM_MODEL=gpt-5.4-mini
ANTHROPIC_LLM_MODEL=claude-3-5-sonnet-latest
OPENAI_SEARCH_MODEL=gpt-5.4-mini
```

Notes:

- `LLM_MODEL` is a generic override. If unset, the code chooses a provider-specific default model.
- OpenAlex enrichment works without an API key, but setting `OPENALEX_EMAIL` is recommended.

## Common Commands

Run from the repo root unless noted otherwise.

### CLI

Default run:

```bash
python -m research_agent "quantum error correction"
```

OpenAI LLM + OpenAI search:

```bash
python -m research_agent "quantum error correction" \
  --llm-provider openai \
  --search-provider openai
```

Gemini LLM + Google CSE search:

```bash
python -m research_agent "recent surface code thresholds" \
  --llm-provider gemini \
  --search-provider google_cse
```

Set ranking weights explicitly:

```bash
python -m research_agent "biased-noise quantum error correction" \
  --semantic-weight 0.7 \
  --citation-weight 0.2 \
  --fwci-weight 0.1
```

Write outputs to custom files:

```bash
python -m research_agent "neutral atom fault tolerance" \
  --output out/research_agent/results.json \
  --ranked-output out/research_agent/ranked.json
```

Increase loop depth:

```bash
python -m research_agent "machine learning for quantum error correction" \
  --max-iterations 3
```

Override the chat model directly:

```bash
python -m research_agent "quantum error correction" \
  --llm-provider openai \
  --llm-model gpt-5.4-mini
```

### Local API

Start the FastAPI wrapper:

```bash
uvicorn research_agent.app:app --reload --port 8001
```

Health check:

```bash
curl http://127.0.0.1:8001/
```

Run the pipeline through the API:

```bash
curl -X POST http://127.0.0.1:8001/run \
  -H "Content-Type: application/json" \
  -d '{
    "query": "quantum error correction",
    "llmProvider": "openai",
    "searchProvider": "openai",
    "semanticWeight": 0.6,
    "citationWeight": 0.25,
    "fwciWeight": 0.15
  }'
```

### Literature Studio UI

Start the `research_agent` API:

```bash
uvicorn research_agent.app:app --reload --port 8001
```

In another terminal:

```bash
cd literature-studio
npm install
npm run dev
```

Then open the Vite URL and use the `Research Agent` panel.

The UI defaults to `Ranked result` and can be toggled to `Raw result`.

## Troubleshooting

### Provider/model mismatch

If you switch providers at runtime, do not keep a provider-specific model from another backend.

Good:

```bash
python -m research_agent "quantum error correction" \
  --llm-provider openai \
  --search-provider openai
```

Also good:

```bash
python -m research_agent "quantum error correction" \
  --llm-provider openai \
  --llm-model gpt-5.4-mini
```

### Structured-output errors with OpenAI

The pipeline uses OpenAI function calling for structured outputs. If you still see schema-related failures, check:

- `langchain-openai` version in your environment
- `openai` package version in your environment
- whether the active Python environment matches the one where you installed `research_agent/requirements.txt`

### Search provider failures

Check the relevant credentials:

- `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_ID`
- `OPENAI_API_KEY`
- `TAVILY_API_KEY`
- `JINA_API_KEY`

### OpenAlex enrichment missing

If many papers return `status: "not_found"` in `openalex`, that usually means:

- title extraction from search results was noisy
- the search result was not actually a paper page
- the OpenAlex title match threshold was too strict

Tune:

- `RESEARCH_OPENALEX_TITLE_SEARCH_LIMIT`
- `RESEARCH_OPENALEX_MIN_TITLE_SIMILARITY`

## Key Files

- `research_agent/graph.py`: graph topology and node logic
- `research_agent/cli.py`: CLI entry point
- `research_agent/app.py`: FastAPI wrapper used by the UI
- `research_agent/config.py`: env-driven settings
- `research_agent/enrichment.py`: OpenAlex enrichment
- `research_agent/ranking.py`: weighted reranking
- `research_agent/prompts.py`: prompt templates
