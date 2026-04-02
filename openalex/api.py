from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .config import settings
from .schemas import ExactOpenAlexQuery


@dataclass
class OpenAlexFetchResult:
    results: list[dict[str, Any]]
    total_count: int | None
    request_urls: list[str]


class OpenAlexApiClient:
    def __init__(self, *, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds

    async def __aenter__(self) -> "OpenAlexApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def fetch_results(
        self,
        query: ExactOpenAlexQuery,
        *,
        limit: int,
        per_page: int,
    ) -> OpenAlexFetchResult:
        results: list[dict[str, Any]] = []
        request_urls: list[str] = []
        total_count: int | None = None
        remaining = max(limit, 1)
        effective_per_page = _clamp_per_page(per_page)
        next_cursor: str | None = query.cursor
        next_page = query.page if query.page is not None else 1
        use_cursor = query.cursor is not None or query.page is None

        while remaining > 0:
            page_size = min(remaining, effective_per_page)
            cursor_override = next_cursor if use_cursor else None
            if use_cursor and next_cursor is None:
                cursor_override = "*"
            params = query.to_query_params(
                per_page_override=page_size,
                cursor_override=cursor_override,
            )
            if not use_cursor:
                params["page"] = str(next_page)
            if settings.openalex_api_key:
                params["api_key"] = settings.openalex_api_key
            if settings.openalex_email:
                params["mailto"] = settings.openalex_email

            url = f"{settings.openalex_base_url.rstrip('/')}{query.endpoint}"
            body, final_url = await asyncio.to_thread(
                _fetch_json,
                url=url,
                params=params,
                timeout_seconds=self._timeout_seconds,
            )
            request_urls.append(_sanitize_url(final_url))

            meta = body.get("meta", {})
            if total_count is None:
                raw_total = meta.get("count")
                total_count = int(raw_total) if isinstance(raw_total, int) else None

            batch = body.get("results", [])
            if not isinstance(batch, list) or not batch:
                break
            for item in batch:
                if isinstance(item, dict):
                    results.append(item)
            remaining = limit - len(results)
            if remaining <= 0:
                break
            if use_cursor:
                next_cursor_raw = meta.get("next_cursor")
                next_cursor = (
                    next_cursor_raw if isinstance(next_cursor_raw, str) else None
                )
                if next_cursor is None:
                    break
                continue

            if len(batch) < page_size:
                break
            next_page += 1

        return OpenAlexFetchResult(
            results=results[:limit],
            total_count=total_count,
            request_urls=request_urls,
        )


def _fetch_json(
    *,
    url: str,
    params: dict[str, str],
    timeout_seconds: float,
) -> tuple[dict[str, Any], str]:
    full_url = f"{url}?{urlencode(params, doseq=True)}"
    request = Request(
        full_url,
        headers={"User-Agent": "openalex-workflow/0.1"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None) or response.getcode()
            body = _decode_json_response(response.read())
            if status >= 400:
                raise RuntimeError(f"OpenAlex API error {status}: {body}")
            return body, response.geturl()
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            body = payload
        raise RuntimeError(f"OpenAlex API error {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAlex API request failed: {exc.reason}") from exc


def _decode_json_response(payload: bytes) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="replace")
    body = json.loads(text)
    if not isinstance(body, dict):
        raise RuntimeError(f"Unexpected OpenAlex response payload: {body!r}")
    return body


def _sanitize_url(url: str) -> str:
    parsed = urlsplit(url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    sanitized_pairs = []
    for key, value in query_pairs:
        if key in {"api_key", "mailto"}:
            sanitized_pairs.append((key, "[REDACTED]"))
        else:
            sanitized_pairs.append((key, value))

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(sanitized_pairs, doseq=True),
            parsed.fragment,
        )
    )


def _clamp_per_page(value: int) -> int:
    return max(1, min(value, 200))
