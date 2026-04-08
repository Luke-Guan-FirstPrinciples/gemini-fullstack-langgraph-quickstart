from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from research_agent.config import Settings
from research_agent.enrichment import _build_enrichment
from research_agent.models import Paper, PaperOpenAlexEnrichment
from research_agent.ranking import rerank_papers


class EnrichmentTests(unittest.TestCase):
    def test_build_enrichment_parses_openalex_work(self) -> None:
        work = {
            "id": "https://openalex.org/W123",
            "display_name": "Quantum Error Correction with Widgets",
            "relevance_score": 0.91,
            "cited_by_count": 321,
            "fwci": 3.7,
            "doi": "https://doi.org/10.1234/example",
            "publication_year": 2024,
            "authorships": [
                {"author": {"display_name": "Alice Example"}},
                {"author": {"display_name": "Bob Example"}},
            ],
            "primary_location": {
                "landing_page_url": "https://example.org/paper",
                "source": {"display_name": "Nature Physics"},
            },
            "citation_normalized_percentile": {
                "value": 0.98,
                "is_in_top_1_percent": True,
                "is_in_top_10_percent": True,
            },
        }

        enrichment = _build_enrichment(work, title_similarity=0.96)

        self.assertEqual(enrichment.status, "matched")
        self.assertEqual(enrichment.openalex_id, "https://openalex.org/W123")
        self.assertEqual(enrichment.authors, ["Alice Example", "Bob Example"])
        self.assertEqual(enrichment.citation_count, 321)
        self.assertEqual(enrichment.fwci, 3.7)
        self.assertEqual(enrichment.doi, "10.1234/example")
        self.assertEqual(enrichment.source_display_name, "Nature Physics")
        self.assertTrue(enrichment.is_in_top_1_percent)


class RankingTests(unittest.IsolatedAsyncioTestCase):
    async def test_rerank_combines_semantic_and_bibliometric_signals(self) -> None:
        cfg = Settings()
        cfg.semantic_relevance_weight = 0.2
        cfg.citation_count_weight = 0.6
        cfg.fwci_weight = 0.2

        papers = [
            Paper(
                title="Paper A",
                openalex=PaperOpenAlexEnrichment(status="matched", citation_count=10, fwci=1.0),
            ),
            Paper(
                title="Paper B",
                openalex=PaperOpenAlexEnrichment(status="matched", citation_count=1000, fwci=2.0),
            ),
            Paper(
                title="Paper C",
                openalex=PaperOpenAlexEnrichment(status="matched", citation_count=50, fwci=10.0),
            ),
        ]

        with patch(
            "research_agent.ranking._score_semantic_relevance",
            new=AsyncMock(return_value=[0.9, 0.5, 0.7]),
        ):
            ranked = await rerank_papers("quantum error correction", papers, cfg)

        self.assertEqual([paper.title for paper in ranked.papers], ["Paper B", "Paper C", "Paper A"])
        self.assertEqual([paper.ranking.rank for paper in ranked.papers], [1, 2, 3])
        self.assertEqual(ranked.weights["semantic_relevance"], 0.2)
        self.assertEqual(ranked.weights["citation_count"], 0.6)
        self.assertEqual(ranked.weights["fwci"], 0.2)
        self.assertGreater(ranked.papers[0].ranking.score, ranked.papers[1].ranking.score)


if __name__ == "__main__":
    unittest.main()
