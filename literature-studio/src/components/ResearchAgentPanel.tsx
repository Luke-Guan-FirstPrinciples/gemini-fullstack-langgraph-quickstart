import { startTransition, useEffect, useRef, useState } from "react";
import { requestJson } from "../lib/api";
import { researchAgentBaseUrl } from "../lib/config";
import {
  formatCompactNumber,
  formatDate,
  formatDecimal,
  formatNumber,
  truncateText,
} from "../lib/format";
import {
  buildMockResearchAgentResponse,
  DEFAULT_MOCK_RESEARCH_QUERY,
} from "../lib/mockResearchAgent";
import type {
  ResearchAgentPaper,
  ResearchAgentRunResponse,
} from "../lib/types";

type DataMode = "live" | "mock";

const RESEARCH_AGENT_MODE_STORAGE_KEY = "literature-studio-research-agent-mode";
const DEFAULT_QUERY = DEFAULT_MOCK_RESEARCH_QUERY;
const DEFAULT_MAX_ITERATIONS = 2;
const DEFAULT_RESULTS_PER_QUERY = 10;
const DEFAULT_SEMANTIC_WEIGHT = 0.6;
const DEFAULT_CITATION_WEIGHT = 0.25;
const DEFAULT_FWCI_WEIGHT = 0.15;

const QUERY_PRESETS = [
  "Recent quantum error correction papers adapted to biased noise",
  "Recent benchmark papers on fault-tolerant neutral-atom quantum computing",
  "Machine learning methods for quantum error correction in the last 3 years",
];

const providerOptions = [
  { label: "Default from env", value: "" },
  { label: "Gemini", value: "gemini" },
  { label: "OpenAI", value: "openai" },
  { label: "Anthropic", value: "anthropic" },
];

const searchProviderOptions = [
  { label: "Default from env", value: "" },
  { label: "Google CSE", value: "google_cse" },
  { label: "OpenAI search", value: "openai" },
  { label: "Tavily", value: "tavily" },
  { label: "Jina", value: "jina" },
];

const buildRequestBody = (params: {
  query: string;
  llmProvider: string;
  llmModel: string;
  searchProvider: string;
  maxIterations: number;
  resultsPerQuery: number;
  semanticWeight: number;
  citationWeight: number;
  fwciWeight: number;
}) => {
  const body: Record<string, unknown> = {
    query: params.query.trim(),
    maxIterations: params.maxIterations,
    resultsPerQuery: params.resultsPerQuery,
    semanticWeight: params.semanticWeight,
    citationWeight: params.citationWeight,
    fwciWeight: params.fwciWeight,
  };

  if (params.llmProvider) {
    body.llmProvider = params.llmProvider;
  }
  if (params.llmModel.trim()) {
    body.llmModel = params.llmModel.trim();
  }
  if (params.searchProvider) {
    body.searchProvider = params.searchProvider;
  }

  return body;
};

const getInitialDataMode = (): DataMode => {
  const stored = window.localStorage.getItem(RESEARCH_AGENT_MODE_STORAGE_KEY);
  return stored === "mock" ? "mock" : "live";
};

const buildPaperDestination = (paper: ResearchAgentPaper): string | null =>
  paper.openalex?.landing_page_url ?? paper.url ?? paper.openalex?.openalex_id ?? null;

const buildPaperSummary = (paper: ResearchAgentPaper): string => {
  const summary = paper.key_finding?.trim() || paper.abstract?.trim();
  if (summary) {
    return truncateText(summary, 220);
  }

  if (paper.authors.length) {
    return truncateText(`Authors: ${paper.authors.join(", ")}`, 220);
  }

  return "No summary provided.";
};

export function ResearchAgentPanel() {
  const [dataMode, setDataMode] = useState<DataMode>(getInitialDataMode);
  const [controlMode, setControlMode] = useState<"simple" | "advanced">(
    "simple",
  );
  const [resultView, setResultView] = useState<"ranked" | "raw">("ranked");
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [llmProvider, setLlmProvider] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [searchProvider, setSearchProvider] = useState("");
  const [maxIterations, setMaxIterations] = useState(DEFAULT_MAX_ITERATIONS);
  const [resultsPerQuery, setResultsPerQuery] = useState(DEFAULT_RESULTS_PER_QUERY);
  const [semanticWeight, setSemanticWeight] = useState(DEFAULT_SEMANTIC_WEIGHT);
  const [citationWeight, setCitationWeight] = useState(DEFAULT_CITATION_WEIGHT);
  const [fwciWeight, setFwciWeight] = useState(DEFAULT_FWCI_WEIGHT);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<ResearchAgentRunResponse | null>(() =>
    getInitialDataMode() === "mock"
      ? buildMockResearchAgentResponse({
          query: DEFAULT_QUERY,
          maxIterations: DEFAULT_MAX_ITERATIONS,
          resultsPerQuery: DEFAULT_RESULTS_PER_QUERY,
          semanticWeight: DEFAULT_SEMANTIC_WEIGHT,
          citationWeight: DEFAULT_CITATION_WEIGHT,
          fwciWeight: DEFAULT_FWCI_WEIGHT,
        })
      : null,
  );
  const requestSequence = useRef(0);

  const requestBody = buildRequestBody({
    query,
    llmProvider,
    llmModel,
    searchProvider,
    maxIterations,
    resultsPerQuery,
    semanticWeight,
    citationWeight,
    fwciWeight,
  });

  const loadMockResponse = () => {
    const nextQuery = query.trim().length >= 3 ? query : DEFAULT_QUERY;

    if (nextQuery !== query) {
      setQuery(nextQuery);
    }

    requestSequence.current += 1;
    setLoading(false);
    setError(null);

    startTransition(() => {
      setResponse(
        buildMockResearchAgentResponse({
          query: nextQuery,
          maxIterations,
          resultsPerQuery,
          semanticWeight,
          citationWeight,
          fwciWeight,
        }),
      );
    });
  };

  useEffect(() => {
    window.localStorage.setItem(RESEARCH_AGENT_MODE_STORAGE_KEY, dataMode);
  }, [dataMode]);

  const handleDataModeChange = (nextMode: DataMode) => {
    setDataMode(nextMode);
    if (nextMode === "mock") {
      loadMockResponse();
    }
  };

  const handleSubmit = async () => {
    if (dataMode === "mock") {
      loadMockResponse();
      return;
    }

    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    setLoading(true);
    setError(null);

    try {
      const payload = await requestJson<ResearchAgentRunResponse>(
        `${researchAgentBaseUrl}/run`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(requestBody),
        },
      );

      if (requestSequence.current !== requestId) {
        return;
      }

      startTransition(() => {
        setResponse(payload);
      });
    } catch (caughtError) {
      if (requestSequence.current !== requestId) {
        return;
      }

      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to run the research agent.",
      );
    } finally {
      if (requestSequence.current === requestId) {
        setLoading(false);
      }
    }
  };

  const rankedPapers = response?.ranked_output.papers ?? [];
  const structured = response?.structured_output;
  const rawPapers = structured?.papers ?? [];
  const visiblePapers = resultView === "ranked" ? rankedPapers : rawPapers;
  const topPaper = rankedPapers[0];
  const weightTotal = semanticWeight + citationWeight + fwciWeight;

  return (
    <div className="workspace-grid">
      <div className="control-panel">
        <div className="panel-mode-row">
          <div>
            <p className="mini-label">Control surface</p>
            <h3>{controlMode === "simple" ? "Default mode" : "Advanced mode"}</h3>
          </div>
          <div
            className="segmented-control"
            role="tablist"
            aria-label="Research agent control mode"
          >
            <button
              className={controlMode === "simple" ? "active" : undefined}
              onClick={() => setControlMode("simple")}
              type="button"
            >
              Default
            </button>
            <button
              className={controlMode === "advanced" ? "active" : undefined}
              onClick={() => setControlMode("advanced")}
              type="button"
            >
              Advanced
            </button>
          </div>
        </div>

        <div className="panel-mode-row">
          <div>
            <p className="mini-label">Data source</p>
            <h3>{dataMode === "mock" ? "Mock mode" : "Live proxy"}</h3>
          </div>
          <div
            className="segmented-control"
            role="tablist"
            aria-label="Research agent data source"
          >
            <button
              className={dataMode === "live" ? "active" : undefined}
              onClick={() => handleDataModeChange("live")}
              type="button"
            >
              Live API
            </button>
            <button
              className={dataMode === "mock" ? "active" : undefined}
              onClick={() => handleDataModeChange("mock")}
              type="button"
            >
              Mock mode
            </button>
          </div>
        </div>

        <label className="field">
          <span>Research query</span>
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            rows={5}
            placeholder="Recent quantum error correction papers adapted to biased noise"
          />
        </label>

        {controlMode === "advanced" ? (
          <>
            <details className="disclosure-card" open>
              <summary>Model and search providers</summary>
              <div className="disclosure-body">
                <div className="input-grid compact">
                  <label className="field">
                    <span>LLM provider</span>
                    <select
                      value={llmProvider}
                      onChange={(event) => setLlmProvider(event.target.value)}
                    >
                      {providerOptions.map((option) => (
                        <option key={option.label} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="field">
                    <span>Search provider</span>
                    <select
                      value={searchProvider}
                      onChange={(event) => setSearchProvider(event.target.value)}
                    >
                      {searchProviderOptions.map((option) => (
                        <option key={option.label} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="field">
                  <span>Model override</span>
                  <input
                    value={llmModel}
                    onChange={(event) => setLlmModel(event.target.value)}
                    placeholder="Leave blank for env default"
                  />
                </label>
              </div>
            </details>

            <details className="disclosure-card">
              <summary>Retrieval and ranking controls</summary>
              <div className="disclosure-body">
                <div className="input-grid compact">
                  <label className="field narrow">
                    <span>Max iterations</span>
                    <input
                      type="number"
                      min={0}
                      max={6}
                      value={maxIterations}
                      onChange={(event) =>
                        setMaxIterations(Number(event.target.value) || 0)
                      }
                    />
                  </label>

                  <label className="field narrow">
                    <span>Results / query</span>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={resultsPerQuery}
                      onChange={(event) =>
                        setResultsPerQuery(Number(event.target.value) || 1)
                      }
                    />
                  </label>
                </div>

                <div className="weight-grid">
                  <label className="field narrow">
                    <span>Semantic weight</span>
                    <input
                      type="number"
                      min={0}
                      step={0.05}
                      value={semanticWeight}
                      onChange={(event) =>
                        setSemanticWeight(Number(event.target.value) || 0)
                      }
                    />
                  </label>

                  <label className="field narrow">
                    <span>Citation weight</span>
                    <input
                      type="number"
                      min={0}
                      step={0.05}
                      value={citationWeight}
                      onChange={(event) =>
                        setCitationWeight(Number(event.target.value) || 0)
                      }
                    />
                  </label>

                  <label className="field narrow">
                    <span>FWCI weight</span>
                    <input
                      type="number"
                      min={0}
                      step={0.05}
                      value={fwciWeight}
                      onChange={(event) =>
                        setFwciWeight(Number(event.target.value) || 0)
                      }
                    />
                  </label>
                </div>
              </div>
            </details>

            <details className="disclosure-card">
              <summary>Starter prompts</summary>
              <div className="disclosure-body">
                <div className="chip-row">
                  {QUERY_PRESETS.map((preset) => (
                    <button
                      key={preset}
                      className="chip-button"
                      type="button"
                      onClick={() => setQuery(preset)}
                    >
                      {truncateText(preset, 42)}
                    </button>
                  ))}
                </div>
              </div>
            </details>
          </>
        ) : null}

        <div className="action-row">
          <button
            className="button primary"
            type="button"
            onClick={handleSubmit}
            disabled={loading || (dataMode === "live" && query.trim().length < 3)}
          >
            {loading
              ? "Running research..."
              : dataMode === "mock"
                ? "Refresh mock data"
                : "Run research agent"}
          </button>
        </div>

        <p className="panel-note">
          {dataMode === "mock"
            ? "Mock mode bypasses the network and instantly loads a realistic in-browser fixture so front-end work can continue without the research agent backend."
            : controlMode === "simple"
              ? "Default mode only asks for the query. Switch to advanced mode for provider, retrieval, and ranking controls."
              : "This panel targets the local FastAPI proxy in `research_agent/app.py`. Start it on port `8001` and it will return both enriched structured output and weighted ranked results."}
        </p>

        {controlMode === "advanced" ? (
          <details className="disclosure-card">
            <summary>
              {dataMode === "mock" ? "Mock fixture preview" : "Proxy request preview"}
            </summary>
            <div className="disclosure-body">
              <div className="mono-card">
                <span>{dataMode === "mock" ? "Mock source" : "Proxy request"}</span>
                <code>
                  {dataMode === "mock"
                    ? "In-browser fixture response generated locally"
                    : `POST ${researchAgentBaseUrl}/run`}
                </code>
                <code>
                  {JSON.stringify(
                    dataMode === "mock"
                      ? {
                          mode: "mock",
                          query: requestBody.query,
                          resultsPerQuery,
                          maxIterations,
                          weights: {
                            semanticWeight,
                            citationWeight,
                            fwciWeight,
                          },
                        }
                      : requestBody,
                    null,
                    2,
                  )}
                </code>
              </div>
            </div>
          </details>
        ) : null}

        <div className="stat-grid">
          <article className="stat-card">
            <span>Iterations</span>
            <strong>{formatNumber(response?.meta.iterations ?? maxIterations)}</strong>
          </article>
          <article className="stat-card">
            <span>Raw results</span>
            <strong>{formatNumber(response?.meta.total_raw_results)}</strong>
          </article>
          <article className="stat-card">
            <span>Ranked papers</span>
            <strong>{formatNumber(rankedPapers.length)}</strong>
          </article>
          <article className="stat-card">
            <span>Weight total</span>
            <strong>{formatDecimal(weightTotal, 2)}</strong>
          </article>
        </div>

        {dataMode === "mock" ? (
          <p className="status-message info">
            Mock mode is active. Results are synthesized locally and load
            immediately.
          </p>
        ) : error ? (
          <p className="status-message error">{error}</p>
        ) : null}
      </div>

      <div className="result-stack">
        {rankedPapers.length ? (
          <>
            <div
              className="segmented-control"
              role="tablist"
              aria-label="Research agent result view"
            >
              <button
                className={resultView === "ranked" ? "active" : undefined}
                type="button"
                onClick={() => setResultView("ranked")}
              >
                Ranked result
              </button>
              <button
                className={resultView === "raw" ? "active" : undefined}
                type="button"
                onClick={() => setResultView("raw")}
              >
                Raw result
              </button>
            </div>

            <div className="summary-grid">
              <article className="result-card list-card">
                <p className="mini-label">Parsed query</p>
                <h3>{response?.parsed_query?.intent || "Query decomposition"}</h3>
                <div className="inline-tags">
                  {(response?.parsed_query?.fields ?? []).map((field) => (
                    <span key={field} className="tag">
                      {field}
                    </span>
                  ))}
                  {(response?.parsed_query?.key_terms ?? []).slice(0, 6).map((term) => (
                    <span key={term} className="tag">
                      {term}
                    </span>
                  ))}
                </div>
                <ul className="result-list">
                  {(response?.parsed_query?.search_queries ?? []).map((searchQuery) => (
                    <li key={searchQuery}>
                      <strong>{searchQuery}</strong>
                    </li>
                  ))}
                </ul>
              </article>

              <article className="result-card list-card">
                <p className="mini-label">Coverage and metadata</p>
                <h3>
                  {structured?.fields.length
                    ? structured.fields.join(" / ")
                    : "Structured overview"}
                </h3>
                <div className="inline-tags">
                  {(structured?.keywords ?? []).slice(0, 8).map((keyword) => (
                    <span key={keyword} className="tag">
                      {keyword}
                    </span>
                  ))}
                </div>
                <ul className="result-list">
                  <li>
                    <strong>Follow-up queries</strong>
                    <span>
                      {(structured?.sub_queries ?? []).length
                        ? structured?.sub_queries?.join(" | ")
                        : "No follow-up queries were suggested."}
                    </span>
                  </li>
                  <li>
                    <strong>Notable authors</strong>
                    <span>
                      {(structured?.authors ?? [])
                        .slice(0, 5)
                        .map((author) => author.name)
                        .join(", ") || "No author aggregation returned."}
                    </span>
                  </li>
                  <li>
                    <strong>Labs</strong>
                    <span>
                      {(structured?.labs ?? [])
                        .slice(0, 4)
                        .map((lab) => lab.name)
                        .join(", ") || "No lab aggregation returned."}
                    </span>
                  </li>
                  <li>
                    <strong>Last run</strong>
                    <span>{formatDate(response?.meta.timestamp)}</span>
                  </li>
                </ul>
              </article>
            </div>

            {resultView === "ranked" && topPaper ? (
              <article className="spotlight-card">
                <div className="spotlight-copy">
                  <p className="mini-label">Top ranked paper</p>
                  <h3>{topPaper.title}</h3>
                  <p>{buildPaperSummary(topPaper)}</p>
                </div>
                <div className="inline-details">
                  <span>Rank #{topPaper.ranking?.rank ?? "n/a"}</span>
                  <span>Score {formatDecimal(topPaper.ranking?.score, 3)}</span>
                  <span>
                    {formatCompactNumber(topPaper.openalex?.citation_count)} citations
                  </span>
                  <span>FWCI {formatDecimal(topPaper.openalex?.fwci, 2)}</span>
                  <span>{topPaper.openalex?.source_display_name ?? topPaper.source ?? "Source unknown"}</span>
                </div>
              </article>
            ) : null}

            <div className="card-grid">
              {visiblePapers.slice(0, 8).map((paper, index) => {
                const destination = buildPaperDestination(paper);
                const semanticRelevance =
                  paper.ranking?.normalized_signals?.semantic_relevance ?? 0;

                return (
                  <article
                    key={`${paper.title}-${paper.ranking?.rank ?? index}`}
                    className="result-card"
                  >
                    <p className="mini-label">
                      {resultView === "ranked"
                        ? `#${paper.ranking?.rank ?? "n/a"} · score ${formatDecimal(paper.ranking?.score, 3)}`
                        : `Raw paper ${index + 1}`}
                    </p>
                    <h3>
                      {destination ? (
                        <a href={destination} target="_blank" rel="noreferrer">
                          {paper.title}
                        </a>
                      ) : (
                        paper.title
                      )}
                    </h3>
                    <p>{buildPaperSummary(paper)}</p>

                    {resultView === "ranked" ? (
                      <div className="score-meter">
                        <div
                          className="score-fill"
                          style={{
                            width: `${Math.max(0, Math.min(semanticRelevance * 100, 100))}%`,
                          }}
                        />
                      </div>
                    ) : null}

                    <div className="inline-tags">
                      <span className="tag">{paper.year ?? "Year n/a"}</span>
                      <span className="tag">
                        {formatCompactNumber(paper.openalex?.citation_count)} citations
                      </span>
                      <span className="tag">
                        FWCI {formatDecimal(paper.openalex?.fwci, 2)}
                      </span>
                      {resultView === "ranked" ? (
                        <span className="tag">
                          Relevance {formatDecimal(semanticRelevance, 2)}
                        </span>
                      ) : null}
                      <span className="tag">
                        {paper.openalex?.status === "matched"
                          ? "OpenAlex matched"
                          : paper.openalex?.status === "error"
                            ? "OpenAlex error"
                            : "OpenAlex missing"}
                      </span>
                    </div>

                    <p className="muted-copy">
                      {truncateText(paper.authors.join(", "), 140)}
                    </p>
                  </article>
                );
              })}
            </div>
          </>
        ) : (
          <section className="empty-state">
            <p className="mini-label">LLM pipeline workspace</p>
            <h3>Run the research agent to populate the ranked literature view</h3>
            <p>
              This surface takes a natural-language query, decomposes it into search
              queries, enriches papers with OpenAlex metadata, and returns a weighted
              ranking you can inspect directly.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
