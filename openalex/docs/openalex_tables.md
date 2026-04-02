# OpenAlex Table Documentation

This document describes the six `oa_` tables created by this repo in the Postgres schema `openalex`.

## Overview

The tables fall into three groups:

| Group | Tables | Purpose |
| --- | --- | --- |
| Base topic tables | `oa_all_fields`, `oa_physics_related_fields_only` | Store raw topic-mapping rows from the source CSVs |
| Keyword tables | `oa_all_field_keywords`, `oa_physics_related_keywords` | Store deduplicated keyword vocabularies derived from the base tables |
| Embedding tables | `oa_physics_related_keyword_embeddings`, `oa_physics_related_topic_summary_embeddings` | Store vectorized text features for retrieval and similarity workflows |

## Data Lineage

### 1. Full OpenAlex topic mapping

Source:

- `OpenAlex_topic_mapping_table - final_topic_field_subfield_table.csv`

Outputs:

- `openalex.oa_all_fields`
- `openalex.oa_all_field_keywords`

### 2. Physics-only topic mapping

Source:

- `OpenAlex_topic_mapping_table_public - Copy of all physics.csv`

Outputs:

- `openalex.oa_physics_related_fields_only`
- `openalex.oa_physics_related_keywords`
- `openalex.oa_physics_related_keyword_embeddings`
- `openalex.oa_physics_related_topic_summary_embeddings`

## Table Dictionary

### `openalex.oa_all_fields`

Full OpenAlex topic mapping table loaded directly from the complete CSV snapshot.

Row count in current load: `4516`

| Column | Type | Notes |
| --- | --- | --- |
| `topic_id` | `BIGINT` | Primary key |
| `topic_name` | `TEXT` | OpenAlex topic label |
| `subfield_id` | `INTEGER` | OpenAlex subfield identifier |
| `subfield_name` | `TEXT` | OpenAlex subfield label |
| `field_id` | `INTEGER` | OpenAlex field identifier |
| `field_name` | `TEXT` | OpenAlex field label |
| `domain_id` | `INTEGER` | OpenAlex domain identifier |
| `domain_name` | `TEXT` | OpenAlex domain label |
| `keywords` | `TEXT` | Semicolon-delimited keyword list from the source CSV |
| `summary` | `TEXT` | Topic summary text |
| `wikipedia_url` | `TEXT` | Topic reference URL when available |

Indexes:

- Primary key on `topic_id`
- Secondary index on `field_id`

### `openalex.oa_physics_related_fields_only`

Physics-focused subset of the topic mapping table loaded directly from the filtered CSV snapshot.

Row count in current load: `112`

| Column | Type | Notes |
| --- | --- | --- |
| `topic_id` | `BIGINT` | Primary key |
| `topic_name` | `TEXT` | OpenAlex topic label |
| `subfield_id` | `INTEGER` | OpenAlex subfield identifier |
| `subfield_name` | `TEXT` | OpenAlex subfield label |
| `field_id` | `INTEGER` | OpenAlex field identifier |
| `field_name` | `TEXT` | OpenAlex field label |
| `domain_id` | `INTEGER` | OpenAlex domain identifier |
| `domain_name` | `TEXT` | OpenAlex domain label |
| `keywords` | `TEXT` | Semicolon-delimited keyword list from the source CSV |
| `summary` | `TEXT` | Topic summary text |
| `wikipedia_url` | `TEXT` | Topic reference URL when available |

Indexes:

- Primary key on `topic_id`
- Secondary index on `field_id`

### `openalex.oa_all_field_keywords`

Deduplicated keyword vocabulary extracted from `openalex.oa_all_fields`.

Row count in current load: `27855`

Derivation rules:

- Split the `keywords` string on `;`
- Trim whitespace
- Deduplicate repeated keywords within a single topic row before counting
- Aggregate counts across all topics

| Column | Type | Notes |
| --- | --- | --- |
| `keyword_id` | `BIGSERIAL` | Primary key |
| `keyword` | `TEXT` | Unique keyword text |
| `topic_count` | `INTEGER` | Number of topics containing the keyword |

Indexes:

- Primary key on `keyword_id`
- Unique constraint on `keyword`
- Secondary index on `keyword`

### `openalex.oa_physics_related_keywords`

Deduplicated keyword vocabulary extracted from `openalex.oa_physics_related_fields_only`.

Row count in current load: `1036`

Derivation rules are the same as `oa_all_field_keywords`, but applied only to the physics-only dataset.

| Column | Type | Notes |
| --- | --- | --- |
| `keyword_id` | `BIGSERIAL` | Primary key |
| `keyword` | `TEXT` | Unique keyword text |
| `topic_count` | `INTEGER` | Number of physics topics containing the keyword |

Indexes:

- Primary key on `keyword_id`
- Unique constraint on `keyword`
- Secondary index on `keyword`

### `openalex.oa_physics_related_keyword_embeddings`

Embedding table for physics keyword search, matching, and semantic retrieval.

Row count in current load: `1036`

Source rows:

- One row per keyword in `openalex.oa_physics_related_keywords`

| Column | Type | Notes |
| --- | --- | --- |
| `keyword_id` | `BIGINT` | Primary key, foreign key to `oa_physics_related_keywords.keyword_id` |
| `keyword` | `TEXT` | Original keyword text |
| `alias` | `TEXT` | Lowercase slug form of the keyword |
| `gemma300_embedding` | `DOUBLE PRECISION[]` | Embedding from `google/embeddinggemma-300M` |
| `scibert_embedding` | `DOUBLE PRECISION[]` | Embedding from `allenai/scibert_scivocab_uncased` |
| `created_at` | `TIMESTAMPTZ` | Insert timestamp |

Alias rules:

- Convert to lowercase
- Replace one or more non-alphanumeric characters with `-`
- Trim leading and trailing hyphens

Example:

```text
Quantum Error Correction -> quantum-error-correction
```

Important note:

- `alias` is indexed but not unique
- Some visually different keywords can normalize to the same alias, such as capitalization or punctuation variants

Indexes:

- Primary key on `keyword_id`
- Secondary index on `alias`

### `openalex.oa_physics_related_topic_summary_embeddings`

Embedding table for semantic retrieval over physics topics and their summaries.

Row count in current load: `112`

Source rows:

- One row per topic in `openalex.oa_physics_related_fields_only`

| Column | Type | Notes |
| --- | --- | --- |
| `topic_id` | `BIGINT` | Primary key, foreign key to `oa_physics_related_fields_only.topic_id` |
| `topic_name` | `TEXT` | Original topic name |
| `summary` | `TEXT` | Original topic summary |
| `topic_name_gemma300_embedding` | `DOUBLE PRECISION[]` | Gemma embedding of `topic_name` |
| `topic_name_scibert_embedding` | `DOUBLE PRECISION[]` | SciBERT embedding of `topic_name` |
| `summary_gemma300_embedding` | `DOUBLE PRECISION[]` | Gemma embedding of `summary` |
| `summary_scibert_embedding` | `DOUBLE PRECISION[]` | SciBERT embedding of `summary` |
| `created_at` | `TIMESTAMPTZ` | Insert timestamp |

## Embedding Model Notes

The pipeline currently uses:

- `google/embeddinggemma-300M`
- `allenai/scibert_scivocab_uncased`

Implementation details:

- Gemma embeddings are produced through `sentence-transformers`
- SciBERT embeddings use mean pooling over token embeddings from the final hidden state
- Both embedding outputs are stored as Postgres arrays of doubles

This is suitable for export and reuse, but if a downstream project needs in-database vector similarity, a future migration to `pgvector` would be cleaner.

## Example Queries

### Inspect the physics topic table

```sql
select topic_id, topic_name, field_name, subfield_name
from openalex.oa_physics_related_fields_only
order by topic_name;
```

### Get the most frequent physics keywords

```sql
select keyword, topic_count
from openalex.oa_physics_related_keywords
order by topic_count desc, keyword asc
limit 25;
```

### Find a keyword by alias

```sql
select keyword_id, keyword, alias
from openalex.oa_physics_related_keyword_embeddings
where alias = 'quantum-error-correction';
```

### Join keyword embeddings back to keyword frequency

```sql
select k.keyword, k.topic_count, e.alias
from openalex.oa_physics_related_keywords k
join openalex.oa_physics_related_keyword_embeddings e
  on e.keyword_id = k.keyword_id
order by k.topic_count desc, k.keyword asc;
```

### Inspect topic-level embeddings

```sql
select topic_id, topic_name, left(summary, 160) as summary_preview
from openalex.oa_physics_related_topic_summary_embeddings
order by topic_name;
```

## Operational Notes

- The build is rerunnable and destructive for the six managed `oa_` tables
- Each run drops and recreates these tables before loading data
- The pipeline expects `.env` to contain `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`
- All tables live in the Postgres schema `openalex`
