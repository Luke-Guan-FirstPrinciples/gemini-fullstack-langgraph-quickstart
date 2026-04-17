from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from research_agent.config import Settings
from research_agent.deduplication import dedupe_papers, dedupe_search_results
from research_agent.enrichment import (
    OpenAlexEnricher,
    SemanticScholarEnricher,
    WebSearchCitationsEnricher,
    _build_enrichment,
    _build_semantic_scholar_enrichment,
    _extract_citation_count,
)
from research_agent.graph import run_research
from research_agent.models import (
    Paper,
    PaperOpenAlexEnrichment,
    PaperSemanticScholarEnrichment,
    SearchResult,
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


class WebSearchCitationsEnricherTests(unittest.IsolatedAsyncioTestCase):
    def test_extract_citation_count_handles_common_patterns(self) -> None:
        self.assertEqual(_extract_citation_count("Cited by 123 — Nature"), 123)
        self.assertEqual(_extract_citation_count("1,245 citations reported"), 1245)
        self.assertEqual(_extract_citation_count("Citations: 42"), 42)
        self.assertIsNone(_extract_citation_count("No numbers here"))
        self.assertIsNone(_extract_citation_count(None))

    async def test_enrich_papers_extracts_count_from_best_snippet(self) -> None:
        cfg = Settings()
        cfg.web_search_citations_enabled = True
        cfg.web_search_citations_parallelism = 1
        cfg.web_search_citations_max_papers = 5

        class _FakeProvider:
            async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
                return [
                    SearchResult(
                        title="Scholarly article",
                        url="https://scholar.example/article",
                        snippet="Quantum widgets — Cited by 42 — 2024",
                        source="scholar.example",
                    ),
                    SearchResult(
                        title="Blog post",
                        url="https://blog.example",
                        snippet="Read our thoughts on quantum widgets.",
                        source="blog.example",
                    ),
                ]

        enricher = WebSearchCitationsEnricher(cfg, _FakeProvider())  # type: ignore[arg-type]
        paper = Paper(title="Quantum Widgets for Everyone", authors=["Alice"])

        [enriched] = await enricher.enrich_papers([paper])

        self.assertIsNotNone(enriched.web_search)
        self.assertEqual(enriched.web_search.status, "matched")
        self.assertEqual(enriched.web_search.citation_count, 42)
        self.assertEqual(enriched.web_search.source_url, "https://scholar.example/article")

    async def test_enrich_papers_respects_disabled_flag(self) -> None:
        cfg = Settings()
        cfg.web_search_citations_enabled = False

        class _UnusedProvider:
            async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
                raise AssertionError("provider should not be called when disabled")

        enricher = WebSearchCitationsEnricher(cfg, _UnusedProvider())  # type: ignore[arg-type]
        papers = [Paper(title="Paper A", authors=[]), Paper(title="Paper B", authors=[])]

        enriched = await enricher.enrich_papers(papers)

        self.assertEqual(len(enriched), 2)
        for paper in enriched:
            self.assertIsNotNone(paper.web_search)
            self.assertEqual(paper.web_search.status, "skipped")

    async def test_enrich_papers_marks_papers_without_citation_as_not_found(self) -> None:
        cfg = Settings()
        cfg.web_search_citations_enabled = True
        cfg.web_search_citations_parallelism = 1

        class _EmptyProvider:
            async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
                return [
                    SearchResult(
                        title="Unrelated",
                        url="https://example.org",
                        snippet="Nothing about citations here.",
                        source="example.org",
                    )
                ]

        enricher = WebSearchCitationsEnricher(cfg, _EmptyProvider())  # type: ignore[arg-type]
        [enriched] = await enricher.enrich_papers(
            [Paper(title="Quantum Widgets", authors=[])]
        )
        self.assertEqual(enriched.web_search.status, "not_found")
        self.assertIsNone(enriched.web_search.citation_count)


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


if __name__ == "__main__":
    unittest.main()
