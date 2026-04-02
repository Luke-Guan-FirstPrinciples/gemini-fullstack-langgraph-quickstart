# OpenAlex Workflow

Standalone OpenAlex retrieval workflow for `/works` and `/authors`, with a small, framework-agnostic core.

## Design

The package is now structured around a library-first core:

- Core pipeline: query parsing, ranking, merge logic, OpenAlex HTTP execution
- Optional catalog backends: JSON or Postgres
- Injectable integration points: selector, validator, catalog repository
- Thin CLI wrapper for human use

The core no longer imports DLS, Autogen, LangChain, `aiohttp`, or `rich`.

## Modes

- `natural_language_keywords_and_topics`
- `natural_language_keywords`
- `natural_language_topics`
- `openalex_query_keywords`
- `exact_openalex_query`

## Standalone Usage

Exact query mode has the fewest dependencies and does not require a catalog:

```bash
python3 -m openalex.cli \
  "filter=primary_topic.id:T11994&sort=cited_by_count:desc" \
  --mode exact_openalex_query
```

Exact author query mode:

```bash
python3 -m openalex.cli \
  "filter=topics.id:T10622&sort=cited_by_count:desc" \
  --mode exact_openalex_query \
  --target authors
```

Default natural-language combined mode with a JSON catalog:

```bash
python3 -m openalex.cli \
  "recent advances in quantum error correction" \
  --target works_and_authors \
  --catalog-backend json \
  --catalog-path ./catalogs/openalex_physics_catalog.json
```

Note: this repo does not currently ship `./catalogs/openalex_physics_catalog.json`.
Provide your own catalog file in the documented format below, or use Postgres mode instead.

Natural-language modes can still use Postgres:

```bash
python3 -m openalex.cli \
  "topological photonics" \
  --mode natural_language_topics \
  --catalog-backend postgres
```

Postgres mode requires `asyncpg` to be installed in the Python environment.

Results are written to `./out/<timestamp>_openalex_<slug>/results.json` by default.

## Catalog JSON Format

For fully portable keyword/topic execution, provide a JSON catalog with this shape:

```json
{
  "keywords": [
    {
      "keyword_id": 1,
      "keyword": "Quantum Error Correction",
      "alias": "quantum-error-correction",
      "topic_count": 12
    }
  ],
  "topics": [
    {
      "topic_id": 11994,
      "topic_name": "Quantum Error Correction",
      "summary": "Protecting quantum information against decoherence.",
      "field_name": "Physics",
      "subfield_name": "Quantum Physics",
      "keywords": "quantum codes;fault tolerance"
    }
  ]
}
```

## Library Usage

Heuristic-only, dependency-light execution:

```python
import asyncio

from openalex import OpenAlexPipelineOptions, run_openalex_pipeline


async def main() -> None:
    result = await run_openalex_pipeline(
        "filter=primary_topic.id:T11994&sort=cited_by_count:desc",
        OpenAlexPipelineOptions(mode="exact_openalex_query"),
    )
    print(result.summary.top_k_returned)


asyncio.run(main())
```

Injected dependencies for later framework integration:

```python
from openalex import OpenAlexDependencies, OpenAlexPipelineOptions, run_openalex_pipeline


deps = OpenAlexDependencies(
    candidate_selector=my_selector,
    candidate_verifier=my_verifier,
    query_validator=my_validator,
    catalog_repository_factory=my_catalog_repo_factory,
)

result = await run_openalex_pipeline(
    "quantum error mitigation",
    OpenAlexPipelineOptions(
        mode="natural_language_keywords_and_topics",
        selector_strategy="external",
    ),
    deps=deps,
)
```

## Integration Guidance

Use the core pipeline as the stable boundary and wrap it in whatever agent framework you need later.

- LangChain: build a tool around `run_openalex_pipeline(...)`
- Autogen: expose `run_openalex_pipeline(...)` as an async callable tool
- Custom app: inject your own selector, validator, and catalog repository through `OpenAlexDependencies`

Keep framework-specific code outside the core package.

## Notes

- `--target` controls which OpenAlex entity type is retrieved:
  - `works`
  - `authors`
  - `works_and_authors`
- `--selector-strategy heuristic` is the fully standalone path.
- `--selector-strategy external` and `llm` are supported by the library API only when you inject a selector.
- Selected keywords/topics are verified before query execution by default when Gemini is configured.
- Use `--skip-candidate-verification` to keep the pre-verification behavior.
- Natural-language modes validate the query by default; use `--skip-query-validation` to bypass that.
- Built-in modifier mapping currently applies:
  - `recent -> from_publication_date:2020-01-01`
  - `important -> fwci:>5`
  - explicit lower bounds such as `published after 2024`
  - citation thresholds such as `citation count > 10`
- Keyword-mode execution uses `keywords.id:<alias>` filters from the catalog.
- Topic-mode execution uses `primary_topic.id:T<topic_id>`.
- Combined mode executes both the keyword-selected and topic-selected query sets.
- Author retrieval is topic-backed:
  - topic mode queries `/authors` with `topics.id:T<topic_id>`
  - keyword mode derives the closest topics from the topic catalog, then queries `/authors`
