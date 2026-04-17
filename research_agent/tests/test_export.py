from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.config import Settings
from research_agent.export import build_local_result_payload, save_local_results


def _make_final_state() -> dict:
    return {
        "parsed_query": {
            "intent": "recent quantum error correction",
            "fields": [
                "Surface Codes",
                "Fault-Tolerant Quantum Computing",
            ],
            "search_queries": [
                "surface codes for quantum error correction",
                "fault-tolerant quantum computing with error correction",
            ],
        },
        "search_queries": [],
        "all_search_results": [
            {"title": "x", "url": "https://example.test/x", "snippet": "", "source": ""},
            {"title": "y", "url": "https://example.test/y", "snippet": "", "source": ""},
        ],
        "iteration": 2,
        "structured_output": {
            "papers": [
                {
                    "title": "Surface Code Breakthrough",
                    "authors": ["Alice", "Bob"],
                    "source": "arxiv",
                    "url": "https://arxiv.org/abs/2307.13100v2",
                    "year": 2023,
                    "abstract": "We demonstrate a surface code experiment.",
                    "doi": "10.1234/example",
                    "openalex": {
                        "status": "matched",
                        "openalex_id": "https://openalex.org/W123",
                        "citation_count": 42,
                        "fwci": 3.7,
                        "source_display_name": "Nature Physics",
                    },
                    "semantic_scholar": {
                        "status": "matched",
                        "paper_id": "paper-1",
                        "citation_count": 77,
                        "publication_venue_name": "Nature",
                        "venue": "Nature",
                    },
                },
                {
                    "title": "Decoding Improvements",
                    "authors": [],
                    "source": "",
                    "url": "https://example.test/paper",
                    "year": None,
                    "abstract": "",
                },
            ],
            "labs": [],
            "fields": ["quantum"],
            "keywords": ["qec"],
            "sub_queries": [],
        },
        "ranked_output": {
            "query": "quantum error correction",
            "weights": {"semantic_relevance": 0.6, "citation_count": 0.4},
            "papers": [
                {
                    "title": "Surface Code Breakthrough",
                    "authors": ["Alice", "Bob"],
                    "source": "arxiv",
                    "url": "https://arxiv.org/abs/2307.13100v2",
                    "year": 2023,
                    "abstract": "We demonstrate a surface code experiment.",
                    "openalex": {
                        "openalex_id": "https://openalex.org/W123",
                        "citation_count": 42,
                        "fwci": 3.7,
                        "source_display_name": "Nature Physics",
                    },
                    "semantic_scholar": {
                        "citation_count": 77,
                        "publication_venue_name": "Nature",
                    },
                },
            ],
        },
    }


class BuildLocalResultPayloadTests(unittest.TestCase):
    def test_payload_matches_sample_schema(self) -> None:
        cfg = Settings()
        state = _make_final_state()

        payload = build_local_result_payload(
            "Recent advancements in quantum error correction",
            state,
            cfg,
            elapsed_seconds=12.5,
        )

        expected_top_keys = {
            "workflow_name",
            "status",
            "topic",
            "sub_topics",
            "arxiv_categories",
            "arxiv_search_queries",
            "papers_by_topic",
            "sorted_papers",
            "paper_summaries",
            "paper_critic_summaries",
            "web_queries",
            "web_sources",
            "web_summaries",
            "final_summaries",
            "final_composition",
            "elapsed",
        }
        self.assertTrue(expected_top_keys.issubset(payload.keys()))
        self.assertEqual(payload["workflow_name"], "research")
        self.assertEqual(payload["topic"], "Recent advancements in quantum error correction")
        self.assertEqual(
            payload["sub_topics"],
            ["Surface Codes", "Fault-Tolerant Quantum Computing"],
        )
        self.assertEqual(
            payload["arxiv_search_queries"],
            [
                "surface codes for quantum error correction",
                "fault-tolerant quantum computing with error correction",
            ],
        )
        self.assertEqual(payload["elapsed"], 12.5)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["paper_summaries"], [])
        self.assertEqual(payload["web_queries"], {})
        self.assertIsNone(payload["final_composition"])

    def test_paper_record_uses_sample_keys(self) -> None:
        cfg = Settings()
        state = _make_final_state()

        payload = build_local_result_payload("quantum error correction", state, cfg)

        topic_key = "quantum error correction"
        self.assertIn(topic_key, payload["papers_by_topic"])
        papers = payload["papers_by_topic"][topic_key]
        self.assertEqual(len(papers), 2)

        first = papers[0]
        self.assertEqual(
            set(first.keys()),
            {
                "id",
                "title",
                "authors",
                "published",
                "summary",
                "pdf_url",
                "full_content",
                "cite_key",
                "source",
                "openalex_id",
                "cited_by_count_from_openalex",
                "cited_by_count_from_semantic_scholar",
                "publication_venue",
                "fwci",
                "openalex_author_ids",
            },
        )
        self.assertEqual(first["id"], "2307.13100v2")
        self.assertEqual(first["source"], "arxiv")
        self.assertEqual(first["pdf_url"], "https://arxiv.org/pdf/2307.13100.pdf")
        self.assertEqual(first["published"], "2023-01-01")
        self.assertEqual(first["summary"], "We demonstrate a surface code experiment.")
        self.assertEqual(first["cite_key"], "ref1")
        self.assertEqual(first["openalex_id"], "https://openalex.org/W123")
        self.assertEqual(first["cited_by_count_from_openalex"], 42)
        self.assertEqual(first["cited_by_count_from_semantic_scholar"], 77)
        self.assertEqual(first["publication_venue"], "Nature")
        self.assertEqual(first["fwci"], 3.7)

        second = papers[1]
        self.assertEqual(second["id"], "https://example.test/paper")
        self.assertEqual(second["pdf_url"], "https://example.test/paper")
        self.assertEqual(second["published"], "")
        self.assertIsNone(second["cited_by_count_from_openalex"])
        self.assertIsNone(second["publication_venue"])

    def test_sorted_papers_come_from_ranked_output(self) -> None:
        cfg = Settings()
        state = _make_final_state()

        payload = build_local_result_payload("quantum error correction", state, cfg)

        sorted_papers = payload["sorted_papers"]["quantum error correction"]
        self.assertEqual(len(sorted_papers), 1)
        self.assertEqual(sorted_papers[0]["title"], "Surface Code Breakthrough")
        self.assertEqual(sorted_papers[0]["cite_key"], "ref1")

    def test_status_falls_back_when_no_ranked_papers(self) -> None:
        cfg = Settings()
        state = _make_final_state()
        state["ranked_output"] = {"papers": []}

        payload = build_local_result_payload("q", state, cfg)

        self.assertEqual(payload["status"], "stopped_after_structuring")

    def test_status_when_no_papers_at_all(self) -> None:
        cfg = Settings()
        state = {
            "parsed_query": {"fields": [], "search_queries": []},
            "structured_output": {"papers": []},
            "ranked_output": {"papers": []},
            "all_search_results": [],
            "iteration": 1,
        }

        payload = build_local_result_payload("q", state, cfg)

        self.assertEqual(payload["status"], "stopped_without_results")


class SaveLocalResultsTests(unittest.TestCase):
    def test_save_writes_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"hello": "world"}

            path = save_local_results(payload, output_dir=tmp)

            self.assertTrue(path.exists())
            self.assertEqual(path.parent, Path(tmp))
            self.assertTrue(path.name.startswith("research_"))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)


if __name__ == "__main__":
    unittest.main()
