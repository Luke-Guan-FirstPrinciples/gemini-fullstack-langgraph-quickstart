# Semantic Scholar Test Backend

Small standalone FastAPI app for testing the Semantic Scholar recommendations API with local JSON seed files.

## Run

From the repo root:

```bash
backend/venv/bin/uvicorn semantic_scholar.app:app --reload --port 8000
```

The app reads `S2_API_KEY` from:

- repo root `.env`
- `backend/.env`
- current process environment

## Endpoints

### 1. Mirror the official endpoint

`POST /recommendations/v1/papers`

Query params:

- `fields`
- `limit`

Body:

```json
{
  "positivePaperIds": ["paper-id-1", "paper-id-2"],
  "negativePaperIds": ["paper-id-3"]
}
```

### 2. Read from a local JSON file

`POST /recommendations/v1/papers/from-file`

Query params:

- `fields`
- `limit`

Body:

```json
{
  "jsonFilePath": "semantic_scholar/seed_papers.json"
}
```

Supported local JSON shapes:

```json
{
  "positivePaperIds": ["id-1"],
  "negativePaperIds": ["id-2"]
}
```

```json
{
  "positive": [{"paperId": "id-1"}],
  "negative": [{"id": "id-2"}]
}
```

## Postman

Import `semantic_scholar/semantic_scholar.postman_collection.json`.
