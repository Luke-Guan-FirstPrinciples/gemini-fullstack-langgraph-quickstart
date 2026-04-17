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
type FeedbackVote = "helpful" | "unhelpful" | null;

interface PaperFeedbackEntry {
  note: string;
  updatedAt: string | null;
  vote: FeedbackVote;
}

function FeedbackThumbUpIcon() {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      height="18"
      viewBox="0 0 24 24"
      width="18"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M9.5 10.25V19H6.75A1.75 1.75 0 0 1 5 17.25v-5.5C5 10.78 5.78 10 6.75 10h2.75Zm0 0 3.28-5.45A1.5 1.5 0 0 1 15.5 5.57v2.2c0 .43-.08.86-.24 1.26l-.4.97h2.63c1.26 0 2.16 1.22 1.79 2.42l-1.52 4.93A2.5 2.5 0 0 1 15.37 19H9.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function FeedbackThumbDownIcon() {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      height="18"
      viewBox="0 0 24 24"
      width="18"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M14.5 13.75V5h2.75A1.75 1.75 0 0 1 19 6.75v5.5c0 .97-.78 1.75-1.75 1.75H14.5Zm0 0-3.28 5.45a1.5 1.5 0 0 1-2.72-.77v-2.2c0-.43.08-.86.24-1.26l.4-.97H6.51c-1.26 0-2.16-1.22-1.79-2.42l1.52-4.93A2.5 2.5 0 0 1 8.63 5H14.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function FeedbackNoteIcon() {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      height="18"
      viewBox="0 0 24 24"
      width="18"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M7.75 5h8.5A2.75 2.75 0 0 1 19 7.75v8.5A2.75 2.75 0 0 1 16.25 19h-8.5A2.75 2.75 0 0 1 5 16.25v-8.5A2.75 2.75 0 0 1 7.75 5Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M9 10h6M9 14h4.25"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

const RESEARCH_AGENT_MODE_STORAGE_KEY = "literature-studio-research-agent-mode";
const RESEARCH_AGENT_FEEDBACK_STORAGE_KEY =
  "literature-studio-research-agent-feedback";
const RESEARCH_AGENT_RESPONSE_CACHE_STORAGE_KEY =
  "literature-studio-research-agent-response-cache";
const DEFAULT_QUERY = DEFAULT_MOCK_RESEARCH_QUERY;
const DEFAULT_MAX_ITERATIONS = 2;
const DEFAULT_RESULTS_PER_QUERY = 10;
const DEFAULT_SEMANTIC_WEIGHT = 0.6;
const DEFAULT_CITATION_WEIGHT = 0.25;
const RESULTS_PAGE_SIZE = 10;
const EMPTY_FEEDBACK: PaperFeedbackEntry = {
  vote: null,
  note: "",
  updatedAt: null,
};

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
}) => {
  const body: Record<string, unknown> = {
    query: params.query.trim(),
    maxIterations: params.maxIterations,
    resultsPerQuery: params.resultsPerQuery,
    semanticWeight: params.semanticWeight,
    citationWeight: params.citationWeight,
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

const getStoredFeedback = (): Record<string, PaperFeedbackEntry> => {
  const stored = window.localStorage.getItem(RESEARCH_AGENT_FEEDBACK_STORAGE_KEY);
  if (!stored) {
    return {};
  }

  try {
    const parsed = JSON.parse(stored) as Record<string, Partial<PaperFeedbackEntry>>;

    return Object.fromEntries(
      Object.entries(parsed).map(([key, value]) => [
        key,
        {
          vote:
            value.vote === "helpful" || value.vote === "unhelpful"
              ? value.vote
              : null,
          note: typeof value.note === "string" ? value.note : "",
          updatedAt:
            typeof value.updatedAt === "string" ? value.updatedAt : null,
        },
      ]),
    );
  } catch {
    return {};
  }
};

const getStoredResearchAgentResponse = (): ResearchAgentRunResponse | null => {
  const stored = window.localStorage.getItem(
    RESEARCH_AGENT_RESPONSE_CACHE_STORAGE_KEY,
  );
  if (!stored) {
    return null;
  }

  try {
    const parsed = JSON.parse(stored) as Partial<ResearchAgentRunResponse>;
    if (
      parsed &&
      typeof parsed === "object" &&
      parsed.structured_output &&
      parsed.ranked_output &&
      parsed.meta
    ) {
      return parsed as ResearchAgentRunResponse;
    }
  } catch {
    return null;
  }

  return null;
};

const buildPaperFeedbackKey = (paper: ResearchAgentPaper): string =>
  (
    paper.semantic_scholar?.paper_id ??
    paper.openalex?.openalex_id ??
    paper.doi ??
    paper.url ??
    `${paper.title}:${paper.year ?? "unknown"}`
  )
    .trim()
    .toLowerCase();

const buildPaperDestination = (paper: ResearchAgentPaper): string | null =>
  paper.openalex?.landing_page_url ??
  paper.semantic_scholar?.url ??
  paper.url ??
  paper.openalex?.openalex_id ??
  null;

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

const buildOpenAlexStatusLabel = (paper: ResearchAgentPaper): string => {
  if (paper.openalex?.status === "matched") {
    return "OpenAlex matched";
  }

  if (paper.openalex?.status === "error") {
    return "OpenAlex error";
  }

  return "OpenAlex missing";
};

const buildSemanticScholarStatusLabel = (paper: ResearchAgentPaper): string => {
  if (paper.semantic_scholar?.status === "matched") {
    return "Semantic Scholar matched";
  }

  if (paper.semantic_scholar?.status === "error") {
    return "Semantic Scholar error";
  }

  return "Semantic Scholar missing";
};

export function ResearchAgentPanel() {
  const initialCachedResponse = getStoredResearchAgentResponse();
  const [dataMode, setDataMode] = useState<DataMode>(getInitialDataMode);
  const [controlMode, setControlMode] = useState<"simple" | "advanced">(
    "simple",
  );
  const [resultView, setResultView] = useState<"ranked" | "raw">(
    "ranked",
  );
  const [query, setQuery] = useState(
    () => initialCachedResponse?.meta.query ?? DEFAULT_QUERY,
  );
  const [llmProvider, setLlmProvider] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [searchProvider, setSearchProvider] = useState("");
  const [maxIterations, setMaxIterations] = useState(DEFAULT_MAX_ITERATIONS);
  const [resultsPerQuery, setResultsPerQuery] = useState(DEFAULT_RESULTS_PER_QUERY);
  const [resultsPage, setResultsPage] = useState(0);
  const [expandedFeedbackByPaper, setExpandedFeedbackByPaper] = useState<
    Record<string, boolean>
  >({});
  const [semanticWeight, setSemanticWeight] = useState(DEFAULT_SEMANTIC_WEIGHT);
  const [citationWeight, setCitationWeight] = useState(DEFAULT_CITATION_WEIGHT);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedbackByPaper, setFeedbackByPaper] = useState<
    Record<string, PaperFeedbackEntry>
  >(getStoredFeedback);
  const [response, setResponse] = useState<ResearchAgentRunResponse | null>(
    () =>
      initialCachedResponse ??
      (getInitialDataMode() === "mock"
        ? buildMockResearchAgentResponse({
            query: DEFAULT_QUERY,
            maxIterations: DEFAULT_MAX_ITERATIONS,
            resultsPerQuery: DEFAULT_RESULTS_PER_QUERY,
            semanticWeight: DEFAULT_SEMANTIC_WEIGHT,
            citationWeight: DEFAULT_CITATION_WEIGHT,
          })
        : null),
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
  });

  const loadMockResponse = () => {
    const cachedResponse = getStoredResearchAgentResponse();
    if (cachedResponse && query.trim() === cachedResponse.meta.query.trim()) {
      setLoading(false);
      setError(null);
      startTransition(() => {
        setResponse(cachedResponse);
      });
      return;
    }

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
        }),
      );
    });
  };

  useEffect(() => {
    window.localStorage.setItem(RESEARCH_AGENT_MODE_STORAGE_KEY, dataMode);
  }, [dataMode]);

  useEffect(() => {
    window.localStorage.setItem(
      RESEARCH_AGENT_FEEDBACK_STORAGE_KEY,
      JSON.stringify(feedbackByPaper),
    );
  }, [feedbackByPaper]);

  useEffect(() => {
    setResultsPage(0);
  }, [response, resultView]);

  useEffect(() => {
    setExpandedFeedbackByPaper({});
  }, [response, resultView]);

  const handleDataModeChange = (nextMode: DataMode) => {
    setDataMode(nextMode);
    const cachedResponse = getStoredResearchAgentResponse();

    if (nextMode === "mock") {
      const lastLiveResponse =
        response && response.meta.llm_provider !== "mock"
          ? response
          : cachedResponse;
      if (lastLiveResponse) {
        if (lastLiveResponse.meta.query !== query) {
          setQuery(lastLiveResponse.meta.query);
        }
        startTransition(() => {
          setResponse(lastLiveResponse);
        });
        return;
      }
      loadMockResponse();
      return;
    }

    if (nextMode === "live" && !response && cachedResponse) {
      if (cachedResponse.meta.query !== query) {
        setQuery(cachedResponse.meta.query);
      }
      startTransition(() => {
        setResponse(cachedResponse);
      });
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

      window.localStorage.setItem(
        RESEARCH_AGENT_RESPONSE_CACHE_STORAGE_KEY,
        JSON.stringify(payload),
      );

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

  const updatePaperFeedback = (
    paper: ResearchAgentPaper,
    update: Partial<PaperFeedbackEntry>,
  ) => {
    const feedbackKey = buildPaperFeedbackKey(paper);

    setFeedbackByPaper((currentFeedback) => {
      const previousEntry = currentFeedback[feedbackKey] ?? EMPTY_FEEDBACK;
      const nextEntry: PaperFeedbackEntry = {
        ...previousEntry,
        ...update,
        updatedAt: new Date().toISOString(),
      };

      if (!nextEntry.vote && !nextEntry.note.trim()) {
        const { [feedbackKey]: _removed, ...remainingFeedback } = currentFeedback;
        return remainingFeedback;
      }

      return {
        ...currentFeedback,
        [feedbackKey]: nextEntry,
      };
    });
  };

  const togglePaperVote = (paper: ResearchAgentPaper, vote: Exclude<FeedbackVote, null>) => {
    const feedbackKey = buildPaperFeedbackKey(paper);
    const currentVote = feedbackByPaper[feedbackKey]?.vote ?? null;

    updatePaperFeedback(paper, {
      vote: currentVote === vote ? null : vote,
    });
  };

  const toggleFeedbackNote = (paper: ResearchAgentPaper) => {
    const feedbackKey = buildPaperFeedbackKey(paper);

    setExpandedFeedbackByPaper((currentState) => ({
      ...currentState,
      [feedbackKey]: !currentState[feedbackKey],
    }));
  };

  const rankedPapers = response?.ranked_output.papers ?? [];
  const structured = response?.structured_output;
  const rawPapers = structured?.papers ?? [];
  const visiblePapers = resultView === "raw" ? rawPapers : rankedPapers;
  const totalPages = Math.max(1, Math.ceil(visiblePapers.length / RESULTS_PAGE_SIZE));
  const currentPage = Math.min(resultsPage, totalPages - 1);
  const pageStartIndex = currentPage * RESULTS_PAGE_SIZE;
  const paginatedPapers = visiblePapers.slice(
    pageStartIndex,
    pageStartIndex + RESULTS_PAGE_SIZE,
  );
  const weightTotal = semanticWeight + citationWeight;

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
            ? "Mock mode uses the last cached live result when available, otherwise it falls back to the in-browser fixture."
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
            {response?.meta.llm_provider && response.meta.llm_provider !== "mock"
              ? "Mock mode is active. Showing the last cached live result."
              : "Mock mode is active. Results are synthesized locally and load immediately."}
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

            {resultView === "ranked" ? (
              <div className="paper-table-header" aria-hidden="true">
                <span>Rank</span>
                <span>Paper</span>
                <span>Signals</span>
                <span>Feedback</span>
              </div>
            ) : null}

            <div className="paper-row-list">
              {paginatedPapers.map((paper, index) => {
                const destination = buildPaperDestination(paper);
                const semanticRelevance =
                  paper.ranking?.normalized_signals?.semantic_relevance ?? 0;
                const feedbackKey = buildPaperFeedbackKey(paper);
                const feedback = feedbackByPaper[feedbackKey] ?? EMPTY_FEEDBACK;
                const feedbackTimestamp = feedback.updatedAt
                  ? formatDate(feedback.updatedAt)
                  : null;
                const isFeedbackExpanded =
                  expandedFeedbackByPaper[feedbackKey] ?? false;
                const explanationChips = paper.ranking?.explanation_chips ?? [];
                const paperNumber = pageStartIndex + index + 1;
                const paperSource = paper.source || "Web/LLM venue unknown";
                const paperPublicationVenue =
                  paper.semantic_scholar?.publication_venue_name ||
                  paper.semantic_scholar?.venue ||
                  "Publication venue unknown";
                const openAlexStatus = buildOpenAlexStatusLabel(paper);
                const semanticScholarStatus = buildSemanticScholarStatusLabel(paper);
                const paperRowClassName = [
                  "result-card",
                  "paper-row-card",
                  resultView === "ranked"
                    ? "paper-row-card-ranked"
                    : "paper-row-card-raw",
                ]
                  .filter(Boolean)
                  .join(" ");

                return (
                  <article
                    key={`${paper.title}-${paper.ranking?.rank ?? index}`}
                    className={paperRowClassName}
                  >
                    <div className="paper-row-rank">
                      <p className="mini-label">
                        {resultView === "ranked" ? "Rank" : "Paper"}
                      </p>
                      <strong>
                        {resultView === "ranked"
                          ? `#${paper.ranking?.rank ?? "n/a"}`
                          : paperNumber}
                      </strong>
                      <span>
                        {resultView === "ranked"
                          ? `Score ${formatDecimal(paper.ranking?.score, 3)}`
                          : `Raw result ${paperNumber}`}
                      </span>
                    </div>

                    <div className="paper-row-main">
                      <div className="paper-row-title-block">
                        <h3>
                          {destination ? (
                            <a href={destination} target="_blank" rel="noreferrer">
                              {paper.title}
                            </a>
                          ) : (
                            paper.title
                          )}
                        </h3>
                        <p className="paper-row-summary">{buildPaperSummary(paper)}</p>
                      </div>

                      <div className="paper-row-supporting">
                        <div className="inline-tags paper-row-tags">
                          <span className="tag">{paper.year ?? "Year n/a"}</span>
                          <span className="tag">{`Web/LLM: ${paperSource}`}</span>
                          <span className="tag">{`Venue: ${paperPublicationVenue}`}</span>
                        </div>

                        <p className="muted-copy paper-row-authors">
                          {truncateText(paper.authors.join(", "), 180)}
                        </p>
                      </div>

                      {resultView === "ranked" && explanationChips.length ? (
                        <div className="inline-tags explanation-row">
                          {explanationChips.map((chip) => (
                            <span key={chip} className="tag explanation-chip">
                              {chip}
                            </span>
                          ))}
                        </div>
                      ) : null}

                      {resultView === "ranked" ? (
                        <div className="score-meter paper-row-score-meter">
                          <div
                            className="score-fill"
                            style={{
                              width: `${Math.max(0, Math.min(semanticRelevance * 100, 100))}%`,
                            }}
                          />
                        </div>
                      ) : null}
                    </div>

                    <div className="paper-row-metrics">
                      <div className="paper-metric">
                        <span>Citations</span>
                        <strong>
                          {formatCompactNumber(paper.semantic_scholar?.citation_count)}
                        </strong>
                      </div>
                      <div className="paper-metric">
                        <span>S2 status</span>
                        <strong>{semanticScholarStatus.replace("Semantic Scholar ", "")}</strong>
                      </div>
                      {resultView === "ranked" ? (
                        <div className="paper-metric">
                          <span>Relevance</span>
                          <strong>{formatDecimal(semanticRelevance, 2)}</strong>
                        </div>
                      ) : null}
                      <div className="paper-metric">
                        <span>OpenAlex</span>
                        <strong>{openAlexStatus.replace("OpenAlex ", "")}</strong>
                      </div>
                    </div>

                    <div className="paper-row-feedback">
                      <div className="feedback-panel">
                        <div
                          className="feedback-actions"
                          role="group"
                          aria-label={`Feedback for ${paper.title}`}
                        >
                          <button
                            className={[
                              "feedback-button",
                              feedback.vote === "helpful"
                                ? "active helpful"
                                : "",
                            ]
                              .filter(Boolean)
                              .join(" ")}
                            type="button"
                            aria-label="Mark result as helpful"
                            aria-pressed={feedback.vote === "helpful"}
                            onClick={() => togglePaperVote(paper, "helpful")}
                            title="Helpful"
                          >
                            <FeedbackThumbUpIcon />
                          </button>
                          <button
                            className={[
                              "feedback-button",
                              feedback.vote === "unhelpful"
                                ? "active unhelpful"
                                : "",
                            ]
                              .filter(Boolean)
                              .join(" ")}
                            type="button"
                            aria-label="Mark result as unhelpful"
                            aria-pressed={feedback.vote === "unhelpful"}
                            onClick={() => togglePaperVote(paper, "unhelpful")}
                            title="Unhelpful"
                          >
                            <FeedbackThumbDownIcon />
                          </button>
                          <button
                            className={[
                              "feedback-button",
                              isFeedbackExpanded || feedback.note.trim()
                                ? "active note"
                                : "",
                            ]
                              .filter(Boolean)
                              .join(" ")}
                            type="button"
                            aria-label="Add text feedback"
                            aria-expanded={isFeedbackExpanded}
                            onClick={() => toggleFeedbackNote(paper)}
                            title={feedback.note.trim() ? "Edit note" : "Add note"}
                          >
                            <FeedbackNoteIcon />
                          </button>
                        </div>

                        {feedbackTimestamp ? (
                          <p className="paper-feedback-timestamp">{feedbackTimestamp}</p>
                        ) : null}

                        {isFeedbackExpanded ? (
                          <label
                            className="field feedback-field"
                            title={feedbackTimestamp ? `Saved ${feedbackTimestamp}` : "Local only"}
                          >
                            <div className="feedback-input-shell">
                              <span
                                className={`feedback-input-icon${feedback.note.trim() ? " active" : ""}`}
                              >
                                <FeedbackNoteIcon />
                              </span>
                              <textarea
                                aria-label={`Text feedback for ${paper.title}`}
                                className="feedback-note-input"
                                rows={3}
                                value={feedback.note}
                                onChange={(event) =>
                                  updatePaperFeedback(paper, {
                                    note: event.target.value,
                                  })
                                }
                              />
                            </div>
                          </label>
                        ) : null}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>

            {visiblePapers.length > RESULTS_PAGE_SIZE ? (
              <div className="pagination-row">
                <span className="pagination-status">
                  {pageStartIndex + 1}-{Math.min(pageStartIndex + RESULTS_PAGE_SIZE, visiblePapers.length)} of{" "}
                  {visiblePapers.length}
                </span>
                <div className="pagination-actions">
                  <button
                    className="button ghost"
                    type="button"
                    onClick={() =>
                      setResultsPage((current) => Math.max(current - 1, 0))
                    }
                    disabled={currentPage === 0}
                  >
                    Previous
                  </button>
                  <button
                    className="button secondary"
                    type="button"
                    onClick={() =>
                      setResultsPage((current) =>
                        Math.min(current + 1, totalPages - 1),
                      )
                    }
                    disabled={currentPage >= totalPages - 1}
                  >
                    Next page
                  </button>
                </div>
              </div>
            ) : null}
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
