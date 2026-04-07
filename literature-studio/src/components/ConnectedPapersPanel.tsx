import { startTransition, useState } from "react";
import { connectedPapersBaseUrl, deepFruitsPaperId } from "../lib/config";
import { requestJson } from "../lib/api";
import {
  formatCompactNumber,
  formatDate,
  formatNumber,
  shortId,
  truncateText,
} from "../lib/format";
import type {
  ConnectedPapersFreeAccessResponse,
  ConnectedPapersGraphResponse,
  ConnectedPapersNode,
  ConnectedPapersRemainingUsesResponse,
  ConnectedPapersSidePaper,
} from "../lib/types";
import { ConnectedGraph } from "./ConnectedGraph";

const DEFAULT_TOKEN = "TEST_TOKEN";

const joinAuthorNames = (
  papers: Array<{ name: string }> | undefined,
  limit = 4,
): string => {
  if (!papers || papers.length === 0) {
    return "Unknown authors";
  }

  return papers
    .slice(0, limit)
    .map((author) => author.name)
    .join(", ");
};

const sortByEdgeStrength = (papers: ConnectedPapersSidePaper[]) =>
  [...papers].sort(
    (left, right) => (right.edges_count ?? 0) - (left.edges_count ?? 0),
  );

const sortByDistance = (nodes: ConnectedPapersNode[], startId: string) =>
  [...nodes]
    .filter((node) => node.id !== startId)
    .sort((left, right) => left.path_length - right.path_length);

export function ConnectedPapersPanel() {
  const [paperId, setPaperId] = useState(deepFruitsPaperId);
  const [token, setToken] = useState(DEFAULT_TOKEN);
  const [freshOnly, setFreshOnly] = useState(false);
  const [loadingAction, setLoadingAction] = useState<
    "graph" | "quota" | "free" | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const [graphResponse, setGraphResponse] =
    useState<ConnectedPapersGraphResponse | null>(null);
  const [remainingUses, setRemainingUses] = useState<number | null>(null);
  const [freeAccessPapers, setFreeAccessPapers] = useState<string[]>([]);

  const graph = graphResponse?.graph_json ?? null;
  const nodes = graph ? Object.values(graph.nodes) : [];
  const startPaper = graph ? graph.nodes[graph.start_id] : null;
  const closestNodes = graph ? sortByDistance(nodes, graph.start_id).slice(0, 5) : [];
  const priorWorks = graph
    ? sortByEdgeStrength(graph.common_references).slice(0, 5)
    : [];
  const derivativeWorks = graph
    ? sortByEdgeStrength(graph.common_citations).slice(0, 5)
    : [];

  const requestHeaders = token.trim()
    ? { "X-Api-Key": token.trim() }
    : undefined;

  const loadDemoSeed = () => {
    setPaperId(deepFruitsPaperId);
    setToken(DEFAULT_TOKEN);
    setFreshOnly(false);
  };

  const handleFetchGraph = async () => {
    setLoadingAction("graph");
    setError(null);

    try {
      const response = await requestJson<ConnectedPapersGraphResponse>(
        `${connectedPapersBaseUrl}/papers-api/graph/${freshOnly ? 1 : 0}/${paperId.trim()}`,
        {
          headers: requestHeaders,
        },
      );

      startTransition(() => {
        setGraphResponse(response);
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to fetch the Connected Papers graph.",
      );
    } finally {
      setLoadingAction(null);
    }
  };

  const handleFetchQuota = async () => {
    setLoadingAction("quota");
    setError(null);

    try {
      const response = await requestJson<ConnectedPapersRemainingUsesResponse>(
        `${connectedPapersBaseUrl}/papers-api/remaining-usages`,
        {
          headers: requestHeaders,
        },
      );

      startTransition(() => {
        setRemainingUses(response.remaining_uses);
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to fetch the remaining Connected Papers quota.",
      );
    } finally {
      setLoadingAction(null);
    }
  };

  const handleFetchFreeAccess = async () => {
    setLoadingAction("free");
    setError(null);

    try {
      const response = await requestJson<ConnectedPapersFreeAccessResponse>(
        `${connectedPapersBaseUrl}/papers-api/free-access-papers`,
        {
          headers: requestHeaders,
        },
      );

      startTransition(() => {
        setFreeAccessPapers(response.papers);
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to fetch Connected Papers free-access papers.",
      );
    } finally {
      setLoadingAction(null);
    }
  };

  const statusCopy = graphResponse?.status ?? "idle";

  return (
    <div className="workspace-grid">
      <div className="control-panel">
        <div className="input-grid">
          <label className="field">
            <span>Semantic Scholar paper ID</span>
            <input
              value={paperId}
              onChange={(event) => setPaperId(event.target.value)}
              placeholder="Enter a paper SHA ID"
            />
          </label>

          <label className="field">
            <span>Connected Papers access token</span>
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="TEST_TOKEN or your API key"
            />
          </label>
        </div>

        <label className="toggle-row">
          <input
            type="checkbox"
            checked={freshOnly}
            onChange={(event) => setFreshOnly(event.target.checked)}
          />
          <span>Force a fresh graph rebuild instead of using a cached graph.</span>
        </label>

        <div className="action-row">
          <button
            className="button primary"
            type="button"
            onClick={handleFetchGraph}
            disabled={loadingAction !== null}
          >
            {loadingAction === "graph" ? "Loading graph..." : "Fetch graph"}
          </button>
          <button
            className="button secondary"
            type="button"
            onClick={handleFetchQuota}
            disabled={loadingAction !== null}
          >
            {loadingAction === "quota" ? "Checking..." : "Check quota"}
          </button>
          <button
            className="button secondary"
            type="button"
            onClick={handleFetchFreeAccess}
            disabled={loadingAction !== null}
          >
            {loadingAction === "free" ? "Loading..." : "Free re-access"}
          </button>
          <button
            className="button ghost"
            type="button"
            onClick={loadDemoSeed}
            disabled={loadingAction !== null}
          >
            Load demo seed
          </button>
        </div>

        <p className="panel-note">
          `TEST_TOKEN` only works against the public DeepFruits demo paper. Use a
          real access token for arbitrary paper IDs.
        </p>

        <div className="stat-grid">
          <article className="stat-card">
            <span>Status</span>
            <strong>{statusCopy}</strong>
          </article>
          <article className="stat-card">
            <span>Nodes</span>
            <strong>{graph ? formatNumber(nodes.length) : "n/a"}</strong>
          </article>
          <article className="stat-card">
            <span>Edges</span>
            <strong>{graph ? formatNumber(graph.edges.length) : "n/a"}</strong>
          </article>
          <article className="stat-card">
            <span>Remaining uses</span>
            <strong>{remainingUses === null ? "n/a" : formatNumber(remainingUses)}</strong>
          </article>
        </div>

        <div className="mono-card">
          <span>Free-access papers</span>
          <code>
            {freeAccessPapers.length > 0
              ? freeAccessPapers.map((entry) => shortId(entry)).join(", ")
              : "Run free re-access to inspect the current allowance."}
          </code>
        </div>

        {error ? <p className="status-message error">{error}</p> : null}
      </div>

      <div className="result-stack">
        {graph && startPaper ? (
          <>
            <section className="spotlight-card">
              <div className="spotlight-copy">
                <p className="mini-label">Start paper</p>
                <h3>{startPaper.title}</h3>
                <p>{truncateText(startPaper.abstract ?? startPaper.tldr, 320)}</p>
              </div>

              <div className="inline-details">
                <span>{joinAuthorNames(startPaper.authors, 5)}</span>
                <span>
                  {[startPaper.journalName, startPaper.venue]
                    .filter(Boolean)
                    .join(" / ") || "Venue unavailable"}
                </span>
                <span>{startPaper.year ?? "Year unavailable"}</span>
                <span>
                  {formatCompactNumber(startPaper.citations_length)} citations
                </span>
                <span>
                  {formatCompactNumber(startPaper.references_length)} references
                </span>
                <span>
                  Created {formatDate(graph.creation_time)}
                </span>
              </div>
            </section>

            <ConnectedGraph graph={graph} />

            <div className="card-grid three-up">
              <article className="result-card">
                <p className="mini-label">Closest papers</p>
                <h3>Nearest nodes in the graph</h3>
                <ul className="result-list">
                  {closestNodes.map((node) => (
                    <li key={node.id}>
                      <strong>{node.title}</strong>
                      <span>
                        {node.year ?? "n/a"} · {joinAuthorNames(node.authors, 3)}
                      </span>
                    </li>
                  ))}
                </ul>
              </article>

              <article className="result-card">
                <p className="mini-label">Prior works</p>
                <h3>Shared references</h3>
                <ul className="result-list">
                  {priorWorks.map((paper) => (
                    <li key={paper.id}>
                      <strong>{paper.title}</strong>
                      <span>
                        {paper.year ?? "n/a"} · {paper.edges_count ?? 0} links
                      </span>
                    </li>
                  ))}
                </ul>
              </article>

              <article className="result-card">
                <p className="mini-label">Derivative works</p>
                <h3>Shared citations</h3>
                <ul className="result-list">
                  {derivativeWorks.map((paper) => (
                    <li key={paper.id}>
                      <strong>{paper.title}</strong>
                      <span>
                        {paper.year ?? "n/a"} · {paper.edges_count ?? 0} links
                      </span>
                    </li>
                  ))}
                </ul>
              </article>
            </div>
          </>
        ) : (
          <section className="empty-state">
            <p className="mini-label">Ready</p>
            <h3>Fetch a graph to light up this workspace</h3>
            <p>
              Start with the DeepFruits demo paper or provide your own Connected
              Papers token and Semantic Scholar SHA ID.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
