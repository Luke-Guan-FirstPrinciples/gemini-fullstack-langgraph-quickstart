# Literature Studio

Standalone React + TypeScript landing app for the four research surfaces in this repo:

- `connected_papers/connectedpapers-py`
- `openalex`
- `semantic_scholar`
- `research_agent`

It lives outside the existing `frontend/` app and keeps each feature independent.

## What it includes

- One unified landing page
- Connected Papers graph explorer with quota and free-access checks
- OpenAlex exact-query workspace for `/works` and `/authors`
- Semantic Scholar recommendations workspace that targets the local FastAPI proxy
- Research Agent workspace that runs the LangGraph pipeline through a local FastAPI proxy

## Run

From the repo root:

```bash
cd literature-studio
npm install
npm run dev
```

In a second terminal, start the Semantic Scholar proxy if you want that feature live:

```bash
cd /Users/firstprinciplesextralaptop2/code/2026/gemini-fullstack-langgraph-quickstart
backend/venv/bin/uvicorn semantic_scholar.app:app --reload --port 8000
```

If you want the Research Agent panel live, start its proxy too:

```bash
cd /Users/firstprinciplesextralaptop2/code/2026/gemini-fullstack-langgraph-quickstart
backend/venv/bin/uvicorn research_agent.app:app --reload --port 8001
```

Then open the Vite URL, usually `http://localhost:5173`.

## Environment

Copy `.env.example` to `.env` if you want to override API base URLs or dev proxy targets.

- Connected Papers defaults to `https://rest.prod.connectedpapers.com`
- OpenAlex defaults to `https://api.openalex.org`
- Semantic Scholar defaults to `http://127.0.0.1:8000`
- Research Agent defaults to `http://127.0.0.1:8001`

The Connected Papers and OpenAlex features work through the Vite dev proxy by default. Semantic Scholar and Research Agent are set up the same way for local proxy-backed development. For a production deployment, put these routes behind your own reverse proxy or update the base URL env vars to match your deployment.
