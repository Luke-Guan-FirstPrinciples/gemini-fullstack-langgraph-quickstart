from __future__ import annotations

import asyncio
import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from research_agent.config import Settings
from research_agent.deduplication import (
    dedupe_papers,
    dedupe_search_results,
    dedupe_structured_papers,
)
from research_agent.enrichment import (
    OpenAlexEnricher,
    SemanticScholarEnricher,
    _build_enrichment,
    _build_semantic_scholar_enrichment,
)
from research_agent.graph import run_research, structure_results
from research_agent.models import (
    Lab,
    Paper,
    PaperOpenAlexEnrichment,
    PaperSemanticScholarEnrichment,
    StructuredPaper,
    StructuredResearchOutput,
)
from research_agent.ranking import rerank_papers
from research_agent.search.factory import create_search_provider


class _FakeResponse:
    def __init__(
        self,
        payload: dict,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.request = httpx.Request("GET", "https://example.test/")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}",
                request=self.request,
                response=self,  # type: ignore[arg-type]
            )

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

    def test_yaml_overrides_are_applied_when_env_unset(self) -> None:
        import research_agent.config as cfg_mod

        overrides = {
            "semantic_relevance_weight": 0.45,
            "citation_count_weight": 0.55,
            "max_iterations": 4,
            "preferred_sources": ["example.org"],
        }
        env_without_weights = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "RESEARCH_WEIGHT_SEMANTIC_RELEVANCE",
                "RESEARCH_WEIGHT_CITATION_COUNT",
                "RESEARCH_MAX_ITERATIONS",
            }
        }
        with patch.dict("os.environ", env_without_weights, clear=True), patch.dict(
            cfg_mod._YAML_OVERRIDES, overrides, clear=True
        ):
            cfg = Settings()

        self.assertAlmostEqual(cfg.semantic_relevance_weight, 0.45)
        self.assertAlmostEqual(cfg.citation_count_weight, 0.55)
        self.assertEqual(cfg.max_iterations, 4)
        self.assertEqual(cfg.preferred_sources, ["example.org"])

    def test_env_variable_overrides_yaml(self) -> None:
        import research_agent.config as cfg_mod

        overrides = {"semantic_relevance_weight": 0.2}
        with patch.dict(
            "os.environ",
            {"RESEARCH_WEIGHT_SEMANTIC_RELEVANCE": "0.9"},
            clear=True,
        ), patch.dict(cfg_mod._YAML_OVERRIDES, overrides, clear=True):
            cfg = Settings()

        self.assertAlmostEqual(cfg.semantic_relevance_weight, 0.9)

    def test_yaml_coercion_handles_string_values(self) -> None:
        import research_agent.config as cfg_mod

        overrides = {
            "semantic_relevance_weight": "0.7",
            "semantic_scholar_use_api_key": "true",
            "preferred_sources": "arxiv.org, nature.com",
        }
        env_without_keys = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "RESEARCH_WEIGHT_SEMANTIC_RELEVANCE",
                "RESEARCH_SEMANTIC_SCHOLAR_USE_API_KEY",
            }
        }
        with patch.dict("os.environ", env_without_keys, clear=True), patch.dict(
            cfg_mod._YAML_OVERRIDES, overrides, clear=True
        ):
            cfg = Settings()

        self.assertAlmostEqual(cfg.semantic_relevance_weight, 0.7)
        self.assertTrue(cfg.semantic_scholar_use_api_key)
        self.assertEqual(cfg.preferred_sources, ["arxiv.org", "nature.com"])


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

    def test_build_semantic_scholar_enrichment_parses_paper(self) -> None:
        paper_data = {
            "paperId": "649def34f8be52c8b66281af98ae884c09aef38b",
            "corpusId": 19170988,
            "title": "Construction of the Literature Graph in Semantic Scholar",
            "matchScore": 174.22,
            "year": 2018,
            "citationCount": 365,
            "influentialCitationCount": 90,
            "venue": "NAACL",
            "publicationVenue": {
                "id": "venue-123",
                "name": "North American Chapter of the Association for Computational Linguistics",
                "type": "conference",
                "alternate_names": ["NAACL", "NAACL-HLT"],
                "url": "https://aclanthology.org/venues/naacl/",
            },
            "authors": [
                {"authorId": "1", "name": "Alice Example"},
                {"authorId": "2", "name": "Bob Example"},
            ],
            "url": "https://www.semanticscholar.org/paper/649def34f8be52c8b66281af98ae884c09aef38b",
            "externalIds": {"DOI": "10.18653/v1/n18-3011"},
        }

        enrichment = _build_semantic_scholar_enrichment(
            paper_data,
            title_similarity=0.97,
        )

        self.assertEqual(enrichment.status, "matched")
        self.assertEqual(enrichment.paper_id, "649def34f8be52c8b66281af98ae884c09aef38b")
        self.assertEqual(enrichment.corpus_id, 19170988)
        self.assertEqual(enrichment.citation_count, 365)
        self.assertEqual(enrichment.influential_citation_count, 90)
        self.assertEqual(
            enrichment.publication_venue_name,
            "North American Chapter of the Association for Computational Linguistics",
        )
        self.assertEqual(enrichment.authors, ["Alice Example", "Bob Example"])
        self.assertEqual(enrichment.doi, "10.18653/v1/n18-3011")

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

    async def test_semantic_scholar_fetch_prefers_doi_lookup_before_title_search(self) -> None:
        cfg = Settings()
        enricher = SemanticScholarEnricher(cfg)
        client = AsyncMock()
        client.get = AsyncMock(
            return_value=_FakeResponse(
                {
                    "paperId": "paper-123",
                    "title": "Canonical Semantic Scholar Title",
                    "citationCount": 77,
                    "venue": "Nature",
                    "publicationVenue": {"name": "Nature"},
                    "externalIds": {"DOI": "10.1234/example"},
                }
            )
        )

        enrichment = await enricher._fetch_enrichment(
            client,
            title="Slightly Different Title",
            doi="10.1234/example",
        )

        self.assertEqual(enrichment.status, "matched")
        self.assertEqual(enrichment.paper_id, "paper-123")
        self.assertEqual(enrichment.citation_count, 77)
        self.assertEqual(client.get.await_count, 1)
        self.assertIn("paper/DOI:10.1234%2Fexample", client.get.await_args.args[0])

    async def test_semantic_scholar_does_not_send_api_key_by_default(self) -> None:
        cfg = Settings()
        cfg.semantic_scholar_api_key = "should-not-be-sent"
        cfg.semantic_scholar_use_api_key = False
        cfg.semantic_scholar_requests_per_second = 0.0
        enricher = SemanticScholarEnricher(cfg)
        client = AsyncMock()
        client.get = AsyncMock(
            return_value=_FakeResponse(
                {
                    "paperId": "paper-123",
                    "title": "Example",
                    "externalIds": {"DOI": "10.1/x"},
                }
            )
        )

        await enricher._fetch_by_identifier(client, "DOI:10.1/x")

        call = client.get.await_args
        self.assertEqual(call.kwargs.get("headers"), {})

    async def test_semantic_scholar_sends_api_key_when_explicitly_enabled(self) -> None:
        cfg = Settings()
        cfg.semantic_scholar_api_key = "secret-key"
        cfg.semantic_scholar_use_api_key = True
        cfg.semantic_scholar_requests_per_second = 0.0
        enricher = SemanticScholarEnricher(cfg)
        client = AsyncMock()
        client.get = AsyncMock(
            return_value=_FakeResponse(
                {"paperId": "paper-123", "title": "Example", "externalIds": {}}
            )
        )

        await enricher._fetch_by_identifier(client, "DOI:10.1/x")

        call = client.get.await_args
        self.assertEqual(call.kwargs.get("headers"), {"x-api-key": "secret-key"})

    async def test_semantic_scholar_retries_after_429_and_returns_payload(self) -> None:
        cfg = Settings()
        cfg.semantic_scholar_requests_per_second = 0.0
        cfg.semantic_scholar_max_retries = 3
        cfg.semantic_scholar_initial_backoff_seconds = 0.01
        cfg.semantic_scholar_max_backoff_seconds = 0.05
        enricher = SemanticScholarEnricher(cfg)
        client = AsyncMock()
        client.get = AsyncMock(
            side_effect=[
                _FakeResponse(
                    {"message": "too many"},
                    status_code=429,
                    headers={"Retry-After": "0"},
                ),
                _FakeResponse(
                    {"paperId": "paper-123", "title": "Example", "externalIds": {}}
                ),
            ]
        )

        enrichment = await enricher._fetch_by_identifier(client, "DOI:10.1/x")

        self.assertEqual(enrichment.status, "matched")
        self.assertEqual(enrichment.paper_id, "paper-123")
        self.assertEqual(client.get.await_count, 2)

    async def test_semantic_scholar_gives_up_after_max_retries_on_429(self) -> None:
        cfg = Settings()
        cfg.semantic_scholar_requests_per_second = 0.0
        cfg.semantic_scholar_max_retries = 1
        cfg.semantic_scholar_initial_backoff_seconds = 0.01
        cfg.semantic_scholar_max_backoff_seconds = 0.05
        enricher = SemanticScholarEnricher(cfg)
        client = AsyncMock()
        client.get = AsyncMock(
            return_value=_FakeResponse(
                {"message": "too many"},
                status_code=429,
                headers={"Retry-After": "0"},
            )
        )

        enrichment = await enricher._fetch_by_identifier(client, "DOI:10.1/x")

        self.assertEqual(enrichment.status, "error")
        self.assertEqual(client.get.await_count, 2)

    async def test_semantic_scholar_rate_limiter_serializes_requests(self) -> None:
        cfg = Settings()
        cfg.semantic_scholar_requests_per_second = 20.0
        cfg.semantic_scholar_max_retries = 0
        enricher = SemanticScholarEnricher(cfg)

        async def _slow_get(*args, **kwargs):
            return _FakeResponse(
                {"paperId": "paper-123", "title": "Example", "externalIds": {}}
            )

        client = AsyncMock()
        client.get = AsyncMock(side_effect=_slow_get)

        start = time.monotonic()
        await asyncio.gather(
            enricher._fetch_by_identifier(client, "DOI:10.1/x"),
            enricher._fetch_by_identifier(client, "DOI:10.1/y"),
            enricher._fetch_by_identifier(client, "DOI:10.1/z"),
        )
        elapsed = time.monotonic() - start

        self.assertGreaterEqual(elapsed, 2 * (1.0 / 20.0) * 0.9)


class DeduplicationTests(unittest.TestCase):
    def test_dedupe_search_results_filters_existing_and_in_batch_duplicates(self) -> None:
        existing_results = [
            {
                "title": "Quantum Error Correction with Widgets",
                "url": "https://example.org/paper",
                "snippet": "existing",
                "source": "example",
            }
        ]
        new_results = [
            {
                "title": "Quantum Error Correction with Widgets",
                "url": "https://example.org/paper?utm_source=newsletter#section",
                "snippet": "duplicate url with tracking params",
                "source": "example",
            },
            {
                "title": "Fault-tolerant widgets for quantum memory",
                "url": "https://example.org/another-paper",
                "snippet": "unique",
                "source": "example",
            },
            {
                "title": "Fault-tolerant widgets for quantum memory",
                "url": "",
                "snippet": "duplicate title in the same batch",
                "source": "example",
            },
        ]

        deduped = dedupe_search_results(existing_results, new_results)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["url"], "https://example.org/another-paper")

    def test_dedupe_papers_merges_duplicate_records_and_keeps_enrichment(self) -> None:
        left = Paper(
            title="Quantum Error Correction with Widgets",
            authors=["Alice Example"],
            source="arxiv",
            url="https://arxiv.org/abs/1234.5678",
            openalex=PaperOpenAlexEnrichment(
                status="matched",
                openalex_id="https://openalex.org/W123",
                doi="10.1234/example",
                publication_year=2024,
                authors=["Alice Example", "Bob Example"],
                source_display_name="Nature Physics",
            ),
        )
        right = Paper(
            title="Quantum error correction with widgets",
            authors=["Alice Example", "Bob Example"],
            url="https://publisher.example/paper",
            abstract="Longer abstract from a second discovery path.",
            key_finding="Shows widgets improve logical error suppression.",
            semantic_scholar=PaperSemanticScholarEnrichment(
                status="matched",
                paper_id="paper-123",
                doi="10.1234/example",
                citation_count=77,
                publication_year=2024,
                authors=["Alice Example", "Bob Example"],
            ),
        )

        deduped = dedupe_papers([left, right])

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].doi, "10.1234/example")
        self.assertEqual(deduped[0].year, 2024)
        self.assertEqual(deduped[0].openalex.openalex_id, "https://openalex.org/W123")
        self.assertEqual(deduped[0].semantic_scholar.paper_id, "paper-123")
        self.assertEqual(
            deduped[0].authors,
            ["Alice Example", "Bob Example"],
        )
        self.assertEqual(
            deduped[0].key_finding,
            "Shows widgets improve logical error suppression.",
        )
        self.assertEqual(
            deduped[0].abstract,
            "Longer abstract from a second discovery path.",
        )


class RankingTests(unittest.IsolatedAsyncioTestCase):
    async def test_rerank_combines_semantic_and_bibliometric_signals(self) -> None:
        cfg = Settings()
        cfg.semantic_relevance_weight = 0.3
        cfg.citation_count_weight = 0.7

        papers = [
            Paper(
                title="Paper A",
                semantic_scholar=PaperSemanticScholarEnrichment(
                    status="matched",
                    citation_count=10,
                ),
            ),
            Paper(
                title="Paper B",
                semantic_scholar=PaperSemanticScholarEnrichment(
                    status="matched",
                    citation_count=1000,
                ),
            ),
            Paper(
                title="Paper C",
                year=2025,
                semantic_scholar=PaperSemanticScholarEnrichment(
                    status="matched",
                    citation_count=50,
                ),
            ),
        ]

        with patch(
            "research_agent.ranking._score_semantic_relevance",
            new=AsyncMock(return_value=[0.9, 0.5, 0.7]),
        ):
            ranked = await rerank_papers("quantum error correction", papers, cfg)

        self.assertEqual([paper.title for paper in ranked.papers], ["Paper B", "Paper C", "Paper A"])
        self.assertEqual([paper.ranking.rank for paper in ranked.papers], [1, 2, 3])
        self.assertEqual(ranked.weights["semantic_relevance"], 0.3)
        self.assertEqual(ranked.weights["citation_count"], 0.7)
        self.assertGreater(ranked.papers[0].ranking.score, ranked.papers[1].ranking.score)
        self.assertIn("Strong citation record", ranked.papers[0].ranking.explanation_chips)
        self.assertTrue(ranked.papers[0].ranking.explanation)
        self.assertIn("Recent work", ranked.papers[1].ranking.explanation_chips)

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


class DedupeStructuredPapersTests(unittest.TestCase):
    def test_merges_duplicates_on_doi_and_url(self) -> None:
        papers = [
            StructuredPaper(
                title="Quantum error correction below the surface code threshold",
                url="https://www.nature.com/articles/s41586-024-08449-y",
                doi="10.1038/s41586-024-08449-y",
                year=2024,
                authors=["Google Quantum AI"],
                abstract="short",
            ),
            # Duplicate by DOI (different URL).
            StructuredPaper(
                title="Quantum error correction below the surface code threshold",
                url="https://doi.org/10.1038/s41586-024-08449-y",
                doi="10.1038/s41586-024-08449-y",
                year=2024,
                abstract="a much longer and more informative abstract",
            ),
            # Duplicate by arXiv ID (abs vs pdf).
            StructuredPaper(
                title="Fusion Blossom: Fast MWPM Decoders for QEC",
                url="https://arxiv.org/abs/2305.08307",
                year=2023,
            ),
            StructuredPaper(
                title="Fusion Blossom: Fast MWPM Decoders for QEC",
                url="https://arxiv.org/pdf/2305.08307v2.pdf",
                year=2023,
            ),
            # Genuinely distinct paper.
            StructuredPaper(
                title="Bounds on Autonomous Quantum Error Correction",
                url="https://arxiv.org/abs/2308.16233",
                year=2023,
            ),
        ]

        deduped = dedupe_structured_papers(papers)

        self.assertEqual(len(deduped), 3)
        titles = {p.title for p in deduped}
        self.assertIn("Quantum error correction below the surface code threshold", titles)
        self.assertIn("Fusion Blossom: Fast MWPM Decoders for QEC", titles)
        self.assertIn("Bounds on Autonomous Quantum Error Correction", titles)

        qec_entry = next(
            p for p in deduped if p.doi == "10.1038/s41586-024-08449-y"
        )
        self.assertIn("informative", qec_entry.abstract)
        self.assertIn("Google Quantum AI", qec_entry.authors)

    def test_does_not_merge_different_papers_by_same_authors(self) -> None:
        papers = [
            StructuredPaper(
                title="Paper A about surface codes",
                url="https://arxiv.org/abs/2401.00001",
                authors=["Same Author"],
                year=2024,
            ),
            StructuredPaper(
                title="Paper B about color codes",
                url="https://arxiv.org/abs/2401.00002",
                authors=["Same Author"],
                year=2024,
            ),
        ]

        deduped = dedupe_structured_papers(papers)

        self.assertEqual(len(deduped), 2)


class StructureResultsBatchingTests(unittest.IsolatedAsyncioTestCase):
    async def test_structure_results_batches_hits_and_merges_papers(self) -> None:
        cfg = Settings()
        cfg.structure_batch_size = 4
        cfg.structure_parallelism = 3

        search_results = [
            {
                "title": f"Paper about QEC number {i}",
                "url": f"https://arxiv.org/abs/2401.{i:05d}",
                "snippet": f"snippet for paper {i}",
            }
            for i in range(10)
        ]

        state: dict[str, object] = {
            "query": "quantum error correction",
            "all_search_results": search_results,
        }

        def _build_batch_output(
            batch_hits: list[dict[str, object]], batch_index: int
        ) -> StructuredResearchOutput:
            return StructuredResearchOutput(
                papers=[
                    StructuredPaper(
                        title=hit["title"],
                        url=hit["url"],
                        year=2024,
                        abstract=hit["snippet"],
                    )
                    for hit in batch_hits
                ],
                labs=[Lab(name=f"Lab {batch_index}")],
                fields=["Quantum Computing"],
                keywords=[f"kw_{batch_index}", "quantum"],
                sub_queries=[f"sub query {batch_index}"],
            )

        call_log: list[int] = []

        import re

        async def fake_ainvoke(messages: list[object]) -> StructuredResearchOutput:
            human_content = messages[-1].content
            match = re.search(r"batch (\d+) of (\d+)", human_content)
            assert match is not None
            batch_index = int(match.group(1)) - 1
            match_range = re.search(
                r"hits (\d+)[–-](\d+) of (\d+) total", human_content
            )
            assert match_range is not None
            start = int(match_range.group(1)) - 1
            end = int(match_range.group(2))
            batch_hits = search_results[start:end]
            call_log.append(batch_index)
            await asyncio.sleep(0)
            return _build_batch_output(batch_hits, batch_index)

        fake_structured_llm = MagicMock()
        fake_structured_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)

        with patch(
            "research_agent.graph._get_settings", return_value=cfg
        ), patch("research_agent.graph.create_llm"), patch(
            "research_agent.graph.with_structured_output",
            return_value=fake_structured_llm,
        ):
            result = await structure_results(state, config=None)  # type: ignore[arg-type]

        self.assertEqual(
            fake_structured_llm.ainvoke.await_count,
            3,
            "10 hits with batch size 4 should produce 3 structuring calls",
        )

        papers = result["structured_output"]["papers"]
        self.assertEqual(
            len(papers),
            10,
            "Every distinct hit should survive into the merged output",
        )

        titles = [p["title"] for p in papers]
        for i in range(10):
            self.assertIn(f"Paper about QEC number {i}", titles)

        self.assertEqual(len(result["structured_output"]["labs"]), 3)
        self.assertEqual(
            result["structured_output"]["fields"],
            ["Quantum Computing"],
        )
        self.assertIn("quantum", result["structured_output"]["keywords"])


if __name__ == "__main__":
    unittest.main()
