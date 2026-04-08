#!/usr/bin/env python3
"""Quick smoke test: one Google Custom Search query to verify API key + CSE ID."""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"


def get_env(name: str, *fallbacks: str) -> str:
    val = os.getenv(name)
    if val:
        return val
    if ENV_FILE.is_file():
        env = dotenv_values(ENV_FILE)
        for key in (name, *fallbacks):
            if env.get(key):
                return env[key]
    sys.exit(f"ERROR: {name} not found in environment or {ENV_FILE}")


def main():
    api_key = get_env("GOOGLE_CSE_API_KEY", "GOOGLE_API_KEY")
    cse_id = get_env("GOOGLE_CSE_ID")

    print(f"API key: {api_key[:8]}...{api_key[-4:]}")
    print(f"CSE ID:  {cse_id}")

    import httpx

    params = {
        "key": api_key,
        "cx": cse_id,
        "q": "machine learning",
        "num": 1,
    }

    try:
        resp = httpx.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        body = e.response.text[:300]
        if e.response.status_code == 403:
            sys.exit(f"FAIL: 403 Forbidden — API key invalid or CSE not enabled.\n{body}")
        if e.response.status_code == 400:
            sys.exit(f"FAIL: 400 Bad Request — likely invalid CSE ID.\n{body}")
        sys.exit(f"FAIL: HTTP {e.response.status_code}\n{body}")
    except httpx.ConnectError as e:
        sys.exit(f"FAIL: Network error — {e}")

    data = resp.json()
    items = data.get("items", [])
    if not items:
        sys.exit("FAIL: Search returned no results (unexpected).")

    item = items[0]
    print(f"\nSUCCESS — API key and CSE ID are valid.")
    print(f"  Title:   {item.get('title')}")
    print(f"  Link:    {item.get('link')}")
    print(f"  Snippet: {item.get('snippet', '')[:120]}...")


if __name__ == "__main__":
    main()
