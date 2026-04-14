from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from research_agent.author_pipeline import _build_author_enrichment, build_ranked_authors
from research_agent.config import Settings
from research_agent.enrichment import OpenAlexEnricher, _build_enrichment
from research_agent.graph import run_research
from research_agent.models import (
    Author,
    AuthorOpenAlexEnrichment,
    Paper,
    PaperOpenAlexEnrichment,
    PaperRanking,
    ResearchOutput,
)
from research_agent.ranking import rerank_papers
from research_agent.search.factory import create_search_provider


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class SettingsTests(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "SEARCH_PROVIDER": "google_cse",
            "GOOGLE_API_KEY": "test-google-api-key",
            "GOOGLE_SEARCH_ENGINE_ID": "legacy-search-engine-id",
        },
        clear=True,
    )
    def test_google_cse_accepts_legacy_search_engine_env_name(self) -> None:
        cfg = Settings()

        provider = create_search_provider(cfg)

        self.assertEqual(cfg.google_cse_id, "legacy-search-engine-id")
        self.assertEqual(type(provider).__name__, "GoogleCSEProvider")


class EnrichmentTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_fetch_enrichment_prefers_doi_lookup_before_title_search(self) -> None:
        cfg = Settings()
        enricher = OpenAlexEnricher(cfg)
        client = AsyncMock()
        client.get = AsyncMock(return_value=_FakeResponse({
            "results": [
                {
                    "id": "https://openalex.org/W999",
                    "display_name": "Canonical OpenAlex Title",
                    "doi": "https://doi.org/10.1234/example",
                    "cited_by_count": 10,
                }
            ]
        }))

        enrichment = await enricher._fetch_enrichment(
            client,
            title="Slightly Different Title",
            doi="10.1234/example",
        )

        self.assertEqual(enrichment.status, "matched")
        self.assertEqual(enrichment.openalex_id, "https://openalex.org/W999")
        self.assertEqual(client.get.await_count, 1)
        self.assertIn("filter", client.get.await_args.kwargs["params"])

    async def test_fetch_enrichment_falls_back_to_title_when_doi_lookup_misses(self) -> None:
        cfg = Settings()
        enricher = OpenAlexEnricher(cfg)
        client = AsyncMock()
        client.get = AsyncMock(side_effect=[
            _FakeResponse({"results": []}),
            _FakeResponse({"results": []}),
            _FakeResponse({
                "results": [
                    {
                        "id": "https://openalex.org/W1000",
                        "display_name": "Quantum Error Correction with Widgets",
                        "doi": "https://doi.org/10.1234/example",
                        "cited_by_count": 12,
                    }
                ]
            }),
        ])

        enrichment = await enricher._fetch_enrichment(
            client,
            title="Quantum Error Correction with Widgets",
            doi="10.1234/example",
        )

        self.assertEqual(enrichment.status, "matched")
        self.assertEqual(enrichment.openalex_id, "https://openalex.org/W1000")
        params_list = [call.kwargs["params"] for call in client.get.await_args_list]
        self.assertIn("filter", params_list[0])
        self.assertIn("search", params_list[-1])

    def test_build_author_enrichment_parses_openalex_author(self) -> None:
        author = {
            "id": "https://openalex.org/A123",
            "display_name": "Alice Quantum",
            "relevance_score": 0.88,
            "cited_by_count": 4321,
            "works_count": 210,
            "orcid": "https://orcid.org/0000-0002-1825-0097",
            "ids": {
                "google_scholar": "https://scholar.google.com/citations?user=alice123",
                "twitter": "https://x.com/alice_quantum",
                "semantic_scholar": "https://www.semanticscholar.org/author/12345",
            },
            "last_known_institutions": [
                {"display_name": "Quantum Lab", "country_code": "US"},
                {"display_name": "Caltech", "country_code": "US"},
            ],
            "topics": [
                {"display_name": "Quantum Error Correction"},
                {"display_name": "Fault Tolerance"},
            ],
        }

        enrichment = _build_author_enrichment(
            author,
            candidate_name="Alice Quantum",
            name_similarity=0.97,
        )

        self.assertEqual(enrichment.status, "matched")
        self.assertEqual(enrichment.openalex_id, "https://openalex.org/A123")
        self.assertEqual(enrichment.citation_count, 4321)
        self.assertEqual(enrichment.orcid, "0000-0002-1825-0097")
        self.assertEqual(
            enrichment.google_scholar_url,
            "https://scholar.google.com/citations?user=alice123",
        )
        self.assertEqual(enrichment.social_media_url, "https://x.com/alice_quantum")
        self.assertEqual(enrichment.semantic_scholar_id, "12345")
        self.assertEqual(
            enrichment.affiliations,
            ["Quantum Lab US", "Caltech US"],
        )
        self.assertEqual(
            enrichment.topics,
            ["Quantum Error Correction", "Fault Tolerance"],
        )


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
                openalex=PaperOpenAlexEnrichment(
                    status="matched",
                    citation_count=1000,
                    fwci=2.0,
                    is_in_top_1_percent=True,
                ),
            ),
            Paper(
                title="Paper C",
                year=2025,
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
        self.assertIn("Highly cited (top 1%)", ranked.papers[0].ranking.explanation_chips)
        self.assertTrue(ranked.papers[0].ranking.explanation)
        self.assertIn("High field-weighted impact", ranked.papers[1].ranking.explanation_chips)

    async def test_build_ranked_authors_combines_query_match_support_and_citations(self) -> None:
        cfg = Settings()
        ranked_papers = [
            Paper(
                title="Paper A",
                authors=["Alice Quantum"],
                ranking=PaperRanking(rank=1, score=0.93),
            ),
            Paper(
                title="Paper B",
                authors=["Alice Quantum", "Bob Materials"],
                ranking=PaperRanking(rank=2, score=0.71),
            ),
        ]
        output = ResearchOutput(
            papers=ranked_papers,
            authors=[
                Author(
                    name="Alice Quantum",
                    research_areas=["Quantum error correction"],
                ),
                Author(
                    name="Bob Materials",
                    research_areas=["Condensed matter"],
                ),
            ],
        )
        enriched_authors = [
            Author(
                name="Alice Quantum",
                matched_paper_count=2,
                matched_paper_titles=["Paper A", "Paper B"],
                research_areas=["Quantum error correction"],
                openalex=AuthorOpenAlexEnrichment(
                    status="matched",
                    openalex_id="https://openalex.org/A1",
                    citation_count=800,
                    topics=["Quantum error correction", "Fault tolerance"],
                ),
            ),
            Author(
                name="Bob Materials",
                matched_paper_count=1,
                matched_paper_titles=["Paper B"],
                research_areas=["Condensed matter"],
                openalex=AuthorOpenAlexEnrichment(
                    status="matched",
                    openalex_id="https://openalex.org/A2",
                    citation_count=6000,
                    topics=["Condensed matter physics"],
                ),
            ),
        ]

        with patch(
            "research_agent.author_pipeline._enrich_authors",
            new=AsyncMock(return_value=enriched_authors),
        ):
            authors, weights, normalization = await build_ranked_authors(
                "recent quantum error correction papers adapted to biased noise",
                output,
                ranked_papers,
                cfg,
            )

        self.assertEqual([author.name for author in authors], ["Alice Quantum", "Bob Materials"])
        self.assertEqual([author.ranking.rank for author in authors], [1, 2])
        self.assertEqual(weights["query_topic_overlap"], 0.4)
        self.assertEqual(weights["paper_support"], 0.35)
        self.assertEqual(weights["citation_count"], 0.25)
        self.assertIn("paper_support", normalization)
        self.assertGreater(authors[0].ranking.score, authors[1].ranking.score)
        self.assertGreater(
            authors[0].ranking.normalized_signals["query_topic_overlap"],
            authors[1].ranking.normalized_signals["query_topic_overlap"],
        )
        self.assertIn(
            "Supported by top-ranked papers",
            authors[0].ranking.explanation_chips,
        )


class GraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_research_preserves_explicit_zero_max_iterations(self) -> None:
        cfg = Settings()
        cfg.max_iterations = 2

        graph = AsyncMock()
        graph.ainvoke.return_value = {"all_search_results": []}

        with patch("research_agent.graph.build_graph", return_value=graph), patch(
            "research_agent.graph.setup_logging"
        ):
            await run_research("quantum error correction", cfg=cfg, max_iterations=0)

        initial_state = graph.ainvoke.await_args.args[0]
        self.assertEqual(initial_state["max_iterations"], 0)


if __name__ == "__main__":
    unittest.main()
