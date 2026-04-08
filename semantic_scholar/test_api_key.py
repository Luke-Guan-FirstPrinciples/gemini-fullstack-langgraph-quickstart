#!/usr/bin/env python3
"""Quick smoke test: search for one paper to verify S2_API_KEY is valid."""

import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent
S2_ENV_FILES = (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env")

def get_api_key() -> str:
    key = os.getenv("S2_API_KEY")
    if key:
        return key
    for env_path in S2_ENV_FILES:
        if env_path.is_file():
            val = dotenv_values(env_path).get("S2_API_KEY")
            if val:
                return val
    sys.exit("ERROR: S2_API_KEY not found in environment or .env files.")

def main():
    api_key = get_api_key()
    print(f"Using API key: {api_key[:8]}...{api_key[-4:]}")

    # Search for a well-known paper (Attention Is All You Need)
    params = urlencode({
        "query": "Attention Is All You Need",
        "limit": "1",
        "fields": "title,year,authors",
    })
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{params}"

    req = Request(url, headers={"x-api-key": api_key})

    try:
        with urlopen(req, timeout=15) as resp:
            import json
            data = json.loads(resp.read())
    except HTTPError as e:
        if e.code == 403:
            sys.exit("FAIL: 403 Forbidden — API key is invalid or expired.")
        sys.exit(f"FAIL: HTTP {e.code} — {e.reason}")
    except URLError as e:
        sys.exit(f"FAIL: Network error — {e.reason}")

    papers = data.get("data", [])
    if not papers:
        sys.exit("FAIL: Search returned no results (unexpected).")

    p = papers[0]
    authors = ", ".join(a["name"] for a in p.get("authors", [])[:3])
    print(f"\nSUCCESS — API key is valid.")
    print(f"  Title:   {p['title']}")
    print(f"  Year:    {p.get('year')}")
    print(f"  Authors: {authors}...")

if __name__ == "__main__":
    main()
