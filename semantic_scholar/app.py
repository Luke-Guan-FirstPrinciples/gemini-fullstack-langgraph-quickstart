import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

SEMANTIC_SCHOLAR_RECOMMENDATIONS_URL = (
    "https://api.semanticscholar.org/recommendations/v1/papers"
)
APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
S2_ENV_FILES = (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env")

app = FastAPI(title="Semantic Scholar Test Backend", version="0.1.0")


class PaperRecommendationsRequest(BaseModel):
    """Mirror the Semantic Scholar recommendations request body."""

    model_config = ConfigDict(populate_by_name=True)

    positive_paper_ids: list[str] = Field(
        default_factory=list,
        alias="positivePaperIds",
    )
    negative_paper_ids: list[str] = Field(
        default_factory=list,
        alias="negativePaperIds",
    )

    @model_validator(mode="after")
    def validate_seed_papers(self) -> "PaperRecommendationsRequest":
        """Require at least one input paper ID."""
        if not self.positive_paper_ids and not self.negative_paper_ids:
            raise ValueError(
                "Provide at least one paper ID in positivePaperIds or negativePaperIds."
            )
        return self


class PaperRecommendationsFromFileRequest(BaseModel):
    """Request body for loading seed papers from a local JSON file."""

    model_config = ConfigDict(populate_by_name=True)

    json_file_path: str = Field(alias="jsonFilePath")


def resolve_s2_api_key() -> str:
    """Return the Semantic Scholar API key from env or known .env files."""
    env_value = os.getenv("S2_API_KEY")
    if env_value:
        return env_value

    for env_path in S2_ENV_FILES:
        if not env_path.is_file():
            continue
        env_values = dotenv_values(env_path)
        value = env_values.get("S2_API_KEY")
        if isinstance(value, str) and value:
            return value

    raise HTTPException(
        status_code=500,
        detail="S2_API_KEY was not found in the environment, .env, or backend/.env.",
    )


def resolve_local_json_path(json_file_path: str) -> Path:
    """Resolve a JSON path relative to the repo root or app directory."""
    path = Path(json_file_path).expanduser()
    if path.is_absolute():
        return path.resolve()

    repo_path = (REPO_ROOT / path).resolve()
    if repo_path.exists():
        return repo_path

    app_path = (APP_DIR / path).resolve()
    if app_path.exists():
        return app_path

    return repo_path


def extract_paper_ids(raw_value: Any, label: str) -> list[str]:
    """Normalize supported JSON shapes into a flat paper ID list."""
    if raw_value is None:
        return []

    if isinstance(raw_value, str):
        return [raw_value]

    if not isinstance(raw_value, list):
        raise HTTPException(
            status_code=422,
            detail=f"{label} must be a string or a list of strings/objects.",
        )

    paper_ids: list[str] = []
    for item in raw_value:
        if isinstance(item, str) and item:
            paper_ids.append(item)
            continue

        if isinstance(item, dict):
            for key in ("paperId", "paper_id", "id"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    paper_ids.append(value)
                    break
            else:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"{label} contains an object without a supported paper ID key. "
                        "Expected paperId, paper_id, or id."
                    ),
                )
            continue

        raise HTTPException(
            status_code=422,
            detail=f"{label} contains an unsupported item type.",
        )

    return paper_ids


def load_recommendations_request_from_json(
    json_file_path: str,
) -> PaperRecommendationsRequest:
    """Load recommendation seed papers from a local JSON file."""
    path = resolve_local_json_path(json_file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"JSON file not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON in {path}: {exc.msg}",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=422,
            detail="The JSON file must contain an object at the top level.",
        )

    if "positivePaperIds" in payload or "negativePaperIds" in payload:
        return PaperRecommendationsRequest.model_validate(payload)

    positive_candidates = (
        payload.get("positive"),
        payload.get("positivePapers"),
        payload.get("positive_papers"),
        payload.get("positive_paper_ids"),
    )
    negative_candidates = (
        payload.get("negative"),
        payload.get("negativePapers"),
        payload.get("negative_papers"),
        payload.get("negative_paper_ids"),
    )

    positive = next((value for value in positive_candidates if value is not None), None)
    negative = next((value for value in negative_candidates if value is not None), None)

    return PaperRecommendationsRequest(
        positivePaperIds=extract_paper_ids(positive, "positive papers"),
        negativePaperIds=extract_paper_ids(negative, "negative papers"),
    )


def parse_upstream_error(error: HTTPError) -> dict[str, Any]:
    """Return the upstream error payload if it is JSON."""
    body = error.read().decode("utf-8", errors="replace").strip()
    if not body:
        return {"error": error.reason}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"error": body}

    if isinstance(payload, dict):
        return payload
    return {"error": body}


def fetch_paper_recommendations(
    payload: PaperRecommendationsRequest,
    *,
    fields: str | None,
    limit: int,
) -> JSONResponse | dict[str, Any]:
    """Proxy a request to Semantic Scholar's recommendations endpoint."""
    params = {"limit": str(limit)}
    if fields:
        params["fields"] = fields

    request = Request(
        url=f"{SEMANTIC_SCHOLAR_RECOMMENDATIONS_URL}?{urlencode(params)}",
        data=json.dumps(payload.model_dump(by_alias=True)).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": resolve_s2_api_key(),
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        return JSONResponse(status_code=exc.code, content=parse_upstream_error(exc))
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        return JSONResponse(
            status_code=502,
            content={"error": f"Failed to reach Semantic Scholar: {reason}"},
        )


@app.get("/")
def healthcheck() -> dict[str, str]:
    """Return a simple health payload."""
    return {"status": "ok"}


@app.post("/recommendations/v1/papers", response_model=None)
def recommendations_from_body(
    payload: PaperRecommendationsRequest,
    fields: str | None = Query(
        default=None,
        description=(
            "Comma-separated fields to request from Semantic Scholar. "
            "If omitted, only paperId and title are returned."
        ),
    ),
    limit: int = Query(default=100, ge=1, le=500),
) -> Any:
    """Mirror Semantic Scholar's POST /recommendations/v1/papers endpoint."""
    return fetch_paper_recommendations(payload, fields=fields, limit=limit)


@app.post("/recommendations/v1/papers/from-file", response_model=None)
def recommendations_from_file(
    payload: PaperRecommendationsFromFileRequest,
    fields: str | None = Query(
        default=None,
        description=(
            "Comma-separated fields to request from Semantic Scholar. "
            "If omitted, only paperId and title are returned."
        ),
    ),
    limit: int = Query(default=100, ge=1, le=500),
) -> Any:
    """Load seed papers from a local JSON file and forward the request upstream."""
    request_payload = load_recommendations_request_from_json(payload.json_file_path)
    return fetch_paper_recommendations(request_payload, fields=fields, limit=limit)
