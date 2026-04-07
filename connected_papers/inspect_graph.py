"""
Inspect what Connected Papers' Get Graph returns.

Uses TEST_TOKEN which only works for the DEEPFRUITS paper.
Dumps raw JSON + a human-readable summary to local files.
"""
import asyncio
import json
import os
import sys

import aiohttp

DEEPFRUITS_PAPER_ID = "9397e7acd062245d37350f5c05faf56e9cfae0d6"
API_BASE = "https://rest.prod.connectedpapers.com"
TOKEN = os.environ.get("CONNECTED_PAPERS_API_KEY", "TEST_TOKEN")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


async def fetch_graph(paper_id: str) -> dict:
    """Poll the API until we get a terminal status, return the raw JSON dict."""
    url = f"{API_BASE}/papers-api/graph/0/{paper_id}"
    headers = {"X-Api-Key": TOKEN}
    terminal = {"BAD_ID", "ERROR", "NOT_IN_DB", "FRESH_GRAPH", "BAD_TOKEN",
                "BAD_REQUEST", "OUT_OF_REQUESTS"}

    async with aiohttp.ClientSession() as session:
        while True:
            async with session.get(url, headers=headers) as resp:
                print(f"  HTTP {resp.status}")
                data = await resp.json()
                status = data.get("status", "UNKNOWN")
                print(f"  status={status}  progress={data.get('progress')}")

                if status in terminal:
                    return data
                if status == "OLD_GRAPH":
                    return data

                await asyncio.sleep(1.5)


def summarize(data: dict) -> str:
    """Build a human-readable summary of the graph response."""
    lines = []
    graph = data.get("graph_json")
    if graph is None:
        return f"No graph_json in response. Status: {data.get('status')}"

    lines.append(f"status: {data['status']}")
    lines.append(f"remaining_requests: {data.get('remaining_requests')}")
    lines.append(f"start_id: {graph['start_id']}")

    nodes = graph.get("nodes", {})
    edges = graph.get("edges", [])
    common_refs = graph.get("common_references", [])
    common_cits = graph.get("common_citations", [])
    common_auths = graph.get("common_authors", [])
    path_lengths = graph.get("path_lengths", {})

    lines.append(f"\nnodes: {len(nodes)}")
    lines.append(f"edges: {len(edges)}")
    lines.append(f"common_references (prior works): {len(common_refs)}")
    lines.append(f"common_citations (derivative works): {len(common_cits)}")
    lines.append(f"common_authors: {len(common_auths)}")
    lines.append(f"path_lengths entries: {len(path_lengths)}")

    # --- Sample nodes ---
    lines.append("\n=== SAMPLE NODES (first 3) ===")
    for pid, paper in list(nodes.items())[:3]:
        lines.append(f"\n  id: {pid}")
        lines.append(f"  title: {paper.get('title')}")
        lines.append(f"  year: {paper.get('year')}")
        authors = paper.get("authors", [])
        lines.append(f"  authors: {[a.get('name') for a in authors[:3]]}{'...' if len(authors) > 3 else ''}")
        lines.append(f"  path_length: {paper.get('path_length')}")
        lines.append(f"  path: {paper.get('path')}")
        lines.append(f"  pos: {paper.get('pos')}")
        lines.append(f"  fieldsOfStudy: {paper.get('fieldsOfStudy')}")
        abstract = paper.get("abstract") or ""
        lines.append(f"  abstract: {abstract[:150]}...")
        lines.append(f"  ALL KEYS: {sorted(paper.keys())}")

    # --- Edges ---
    lines.append("\n=== EDGES (similarity connections) ===")
    lines.append("  Format: [paper_id_1, paper_id_2, similarity_weight]")
    weights = [e[2] for e in edges if len(e) >= 3]
    if weights:
        lines.append(f"  Weight range: {min(weights):.6f} — {max(weights):.6f}")
        lines.append(f"  Weight mean:  {sum(weights)/len(weights):.6f}")
    for e in edges[:5]:
        lines.append(f"  {e}")
    lines.append(f"  ... ({max(0, len(edges) - 5)} more)")

    # --- Path lengths ---
    lines.append("\n=== PATH LENGTHS (distance from seed) ===")
    sorted_pl = sorted(path_lengths.items(), key=lambda x: x[1])
    for pid, pl in sorted_pl[:5]:
        title = nodes.get(pid, {}).get("title", "?")
        lines.append(f"  {pl:.4f}  {title[:80]}")
    lines.append(f"  ... ({max(0, len(sorted_pl) - 5)} more)")

    # --- Common references ---
    lines.append("\n=== COMMON REFERENCES (prior works) — first 3 ===")
    for ref in common_refs[:3]:
        lines.append(f"  {ref.get('year')}: {ref.get('title')}")
        lines.append(f"    edges_count={ref.get('edges_count')}")
        lines.append(f"    local_citations={ref.get('local_citations', [])[:5]}")
        lines.append(f"    ALL KEYS: {sorted(ref.keys())}")

    # --- Common citations ---
    lines.append("\n=== COMMON CITATIONS (derivative works) — first 3 ===")
    for cit in common_cits[:3]:
        lines.append(f"  {cit.get('year')}: {cit.get('title')}")
        lines.append(f"    edges_count={cit.get('edges_count')}")
        lines.append(f"    local_references={cit.get('local_references', [])[:5]}")
        lines.append(f"    ALL KEYS: {sorted(cit.keys())}")

    # --- Common authors ---
    lines.append("\n=== COMMON AUTHORS — first 3 ===")
    for auth in common_auths[:3]:
        lines.append(f"  {auth.get('name')} (id={auth.get('id')})")
        lines.append(f"    mentions: {auth.get('mentions', [])[:3]}...")
        lines.append(f"    ALL KEYS: {sorted(auth.keys())}")

    # --- Full schema of one node ---
    lines.append("\n=== FULL SCHEMA: one Paper node ===")
    sample = list(nodes.values())[0]
    for k in sorted(sample.keys()):
        v = sample[k]
        lines.append(f"  {k}: {type(v).__name__} = {repr(v)[:120]}")

    return "\n".join(lines)


async def main():
    print(f"Fetching graph for {DEEPFRUITS_PAPER_ID}...\n")
    data = await fetch_graph(DEEPFRUITS_PAPER_ID)

    # Write raw JSON
    raw_path = os.path.join(OUT_DIR, "graph_raw.json")
    with open(raw_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nRaw JSON → {raw_path}  ({os.path.getsize(raw_path)} bytes)")

    # Write summary
    summary = summarize(data)
    summary_path = os.path.join(OUT_DIR, "graph_summary.txt")
    with open(summary_path, "w") as f:
        f.write(summary)
    print(f"Summary  → {summary_path}")
    print(f"\n{summary}")


if __name__ == "__main__":
    asyncio.run(main())
