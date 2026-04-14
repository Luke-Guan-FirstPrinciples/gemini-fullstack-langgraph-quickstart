import { startTransition, useDeferredValue, useState } from "react";
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
  ConnectedPapersGraphResponse,
  ConnectedPapersNode,
  ConnectedPapersRemainingUsesResponse,
  ConnectedPapersSidePaper,
  ConnectedPapersFreeAccessResponse,
} from "../lib/types";
import { ConnectedGraph } from "./ConnectedGraph";
import {
  ConnectedPaperModal,
  type ConnectedPaperRelationKind,
} from "./ConnectedPaperModal";

const DEFAULT_TOKEN = "TEST_TOKEN";

type InspectablePaper = ConnectedPapersNode | ConnectedPapersSidePaper;

interface ActivePaperDialog {
  kind: ConnectedPaperRelationKind;
  paper: InspectablePaper;
}

const joinAuthorNames = (
  authors: Array<{ name: string }> | undefined,
  limit = 4,
): string => {
  if (!authors || authors.length === 0) {
    return "Unknown authors";
  }

  return authors
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

const getVenueCopy = (paper: InspectablePaper) =>
  [paper.journalName, paper.venue].filter(Boolean).join(" / ") ||
  "Venue unavailable";

const matchesNodeQuery = (node: ConnectedPapersNode, query: string): boolean => {
  const haystacks = [
    node.title,
    node.journalName,
    node.venue,
    ...(node.authors ?? []).map((author) => author.name),
  ];

  return haystacks.some((entry) => entry?.toLowerCase().includes(query));
};

const getHighlightedNodeIds = (
  activePaper: ActivePaperDialog | null,
  selectedNode: ConnectedPapersNode | null,
): string[] => {
  if (activePaper) {
    if (activePaper.kind === "prior") {
      return Array.from(new Set(activePaper.paper.local_citations ?? []));
    }

    if (activePaper.kind === "derivative") {
      return Array.from(new Set(activePaper.paper.local_references ?? []));
    }

    if ("path" in activePaper.paper && activePaper.paper.path?.length) {
      return Array.from(new Set(activePaper.paper.path));
    }

    return [activePaper.paper.id];
  }

  if (selectedNode?.path?.length) {
    return Array.from(new Set(selectedNode.path));
  }

  return selectedNode ? [selectedNode.id] : [];
};

const collectFieldStats = (nodes: ConnectedPapersNode[]) =>
  Array.from(
    nodes.reduce((accumulator, node) => {
      node.fieldsOfStudy?.forEach((field) => {
        accumulator.set(field, (accumulator.get(field) ?? 0) + 1);
      });
      return accumulator;
    }, new Map<string, number>()),
  )
    .sort((left, right) => right[1] - left[1])
    .slice(0, 6);

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
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [graphQuery, setGraphQuery] = useState("");
  const [activePaper, setActivePaper] = useState<ActivePaperDialog | null>(null);

  const deferredGraphQuery = useDeferredValue(graphQuery);
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
  const selectedNode = graph
    ? graph.nodes[selectedNodeId ?? graph.start_id] ?? startPaper
    : null;
  const normalizedQuery = deferredGraphQuery.trim().toLowerCase();
  const graphMatches = graph
    ? sortByDistance(nodes, graph.start_id)
        .filter((node) => matchesNodeQuery(node, normalizedQuery))
        .slice(0, 6)
    : [];
  const highlightedNodeIds = getHighlightedNodeIds(activePaper, selectedNode);
  const fieldStats = collectFieldStats(nodes);
  const commonAuthors = graph?.common_authors ?? [];
  const openAccessCount = nodes.filter((node) => node.isOpenAccess).length;
  const pdfCount = nodes.filter((node) =>
    node.pdfUrls?.some((entry) => entry.trim().length > 0),
  ).length;
  const rawResponse = graphResponse ? JSON.stringify(graphResponse, null, 2) : null;
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
        setSelectedNodeId(response.graph_json?.start_id ?? null);
        setGraphQuery("");
        setActivePaper(null);
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

  const openPaperDialog = (
    kind: ConnectedPaperRelationKind,
    paper: InspectablePaper,
  ) => {
    setActivePaper({ kind, paper });

    if (graph?.nodes[paper.id]) {
      setSelectedNodeId(paper.id);
    }
  };

  const statusCopy = graphResponse?.status ?? "idle";
  const responseIdeas = graph
    ? [
        {
          title: "Author bridge explorer",
          body: `Use common_authors (${commonAuthors.length}) to find researchers tying separate graph neighborhoods together.`,
        },
        {
          title: "Citation lineage workspace",
          body: `Track upstream references and downstream derivatives using local citation/reference membership instead of flat paper lists.`,
        },
        {
          title: "Open-access reading queue",
          body: `${formatNumber(openAccessCount)} of ${formatNumber(nodes.length)} graph nodes are open access and ${formatNumber(pdfCount)} expose a PDF URL.`,
        },
        {
          title: "Drift and frontier alerts",
          body: `path_lengths and graph parameters make it possible to detect boundary papers, new subclusters, and retrieval drift over time.`,
        },
      ]
    : [];

  return (
    <>
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
                  <span>{getVenueCopy(startPaper)}</span>
                  <span>{startPaper.year ?? "Year unavailable"}</span>
                  <span>
                    {formatCompactNumber(startPaper.citations_length)} citations
                  </span>
                  <span>
                    {formatCompactNumber(startPaper.references_length)} references
                  </span>
                  <span>Created {formatDate(graph.creation_time)}</span>
                </div>
              </section>

              <ConnectedGraph
                graph={graph}
                highlightedNodeIds={highlightedNodeIds}
                onSelectNode={setSelectedNodeId}
                selectedNodeId={selectedNode?.id ?? graph.start_id}
              />

              <section className="result-card list-card">
                <div className="graph-tools-header">
                  <div>
                    <p className="mini-label">Graph controls</p>
                    <h3>Search, pin, and walk the graph</h3>
                  </div>
                  <button
                    className="button ghost"
                    onClick={() => {
                      setSelectedNodeId(graph.start_id);
                      setActivePaper(null);
                    }}
                    type="button"
                  >
                    Reset focus
                  </button>
                </div>

                <div className="input-grid compact">
                  <label className="field">
                    <span>Find a node by title, venue, or author</span>
                    <input
                      value={graphQuery}
                      onChange={(event) => setGraphQuery(event.target.value)}
                      placeholder="Search inside this graph"
                    />
                  </label>
                  <div className="graph-query-helper">
                    <span>Current focus</span>
                    <strong>{selectedNode ? shortId(selectedNode.id) : "n/a"}</strong>
                  </div>
                </div>

                {normalizedQuery ? (
                  graphMatches.length > 0 ? (
                    <div className="chip-row">
                      {graphMatches.map((node) => (
                        <button
                          key={node.id}
                          className="chip-button"
                          onClick={() => setSelectedNodeId(node.id)}
                          type="button"
                        >
                          {trimToChip(node.title)}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="muted-copy">No nodes match that query.</p>
                  )
                ) : (
                  <p className="muted-copy">
                    Search is local to the fetched graph. Node clicks and modal actions
                    reuse the same pinned state.
                  </p>
                )}

                {selectedNode ? (
                  <div className="selected-paper-card">
                    <div>
                      <p className="mini-label">Pinned node</p>
                      <h3>{selectedNode.title}</h3>
                      <p className="muted-copy">
                        {truncateText(selectedNode.abstract ?? selectedNode.tldr, 260)}
                      </p>
                    </div>
                    <div className="inline-details">
                      <span>{selectedNode.year ?? "n/a"}</span>
                      <span>{joinAuthorNames(selectedNode.authors, 4)}</span>
                      <span>Path length {selectedNode.path_length.toFixed(2)}</span>
                      <span>{formatCompactNumber(selectedNode.citations_length)} citations</span>
                    </div>
                    {selectedNode.path?.length ? (
                      <div className="chip-row">
                        {selectedNode.path.map((nodeId) => (
                          <button
                            key={nodeId}
                            className="chip-button"
                            onClick={() => setSelectedNodeId(nodeId)}
                            type="button"
                          >
                            {trimToChip(graph.nodes[nodeId]?.title ?? shortId(nodeId))}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </section>

              <div className="card-grid three-up">
                <article className="result-card">
                  <p className="mini-label">Closest papers</p>
                  <h3>Nearest nodes in the graph</h3>
                  <ul className="result-list">
                    {closestNodes.map((node) => (
                      <li key={node.id}>
                        <button
                          className="paper-list-button"
                          onClick={() => openPaperDialog("closest", node)}
                          type="button"
                        >
                          <strong>{node.title}</strong>
                          <span>
                            {node.year ?? "n/a"} · {joinAuthorNames(node.authors, 3)}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <p className="muted-copy result-card-note">
                    Open a node to inspect its graph path and raw node payload.
                  </p>
                </article>

                <article className="result-card">
                  <p className="mini-label">Prior works</p>
                  <h3>Shared references</h3>
                  <ul className="result-list">
                    {priorWorks.map((paper) => (
                      <li key={paper.id}>
                        <button
                          className="paper-list-button"
                          onClick={() => openPaperDialog("prior", paper)}
                          type="button"
                        >
                          <strong>{paper.title}</strong>
                          <span>
                            {paper.year ?? "n/a"} · {paper.edges_count ?? 0} links
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <p className="muted-copy result-card-note">
                    Modal details show which graph papers cite each shared reference.
                  </p>
                </article>

                <article className="result-card">
                  <p className="mini-label">Derivative works</p>
                  <h3>Shared citations</h3>
                  <ul className="result-list">
                    {derivativeWorks.map((paper) => (
                      <li key={paper.id}>
                        <button
                          className="paper-list-button"
                          onClick={() => openPaperDialog("derivative", paper)}
                          type="button"
                        >
                          <strong>{paper.title}</strong>
                          <span>
                            {paper.year ?? "n/a"} · {paper.edges_count ?? 0} links
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <p className="muted-copy result-card-note">
                    Modal details show which graph papers each derivative paper builds on.
                  </p>
                </article>
              </div>

              <div className="card-grid">
                <article className="result-card list-card">
                  <p className="mini-label">Response inspector</p>
                  <h3>Inspect the live Connected Papers payload</h3>
                  <div className="stat-grid">
                    <article className="stat-card">
                      <span>Top-level keys</span>
                      <strong>
                        {graphResponse ? Object.keys(graphResponse).join(", ") : "n/a"}
                      </strong>
                    </article>
                    <article className="stat-card">
                      <span>Graph keys</span>
                      <strong>{Object.keys(graph).slice(0, 6).join(", ")}</strong>
                    </article>
                    <article className="stat-card">
                      <span>Common authors</span>
                      <strong>{formatNumber(commonAuthors.length)}</strong>
                    </article>
                    <article className="stat-card">
                      <span>Path-length entries</span>
                      <strong>{formatNumber(Object.keys(graph.path_lengths ?? {}).length)}</strong>
                    </article>
                  </div>
                  <div className="inline-tags">
                    {fieldStats.map(([field, count]) => (
                      <span key={field} className="tag">
                        {field} · {count}
                      </span>
                    ))}
                  </div>
                  <div className="id-list">
                    {commonAuthors.slice(0, 4).map((author) => (
                      <code key={author.id}>
                        {author.name}: {author.mentions.length} mentions
                      </code>
                    ))}
                  </div>
                  <details className="disclosure-card disclosure-inline">
                    <summary>Show raw API response</summary>
                    <div className="disclosure-body">
                      <pre className="json-block">{rawResponse}</pre>
                    </div>
                  </details>
                </article>

                <article className="result-card list-card">
                  <p className="mini-label">Possible products</p>
                  <h3>What this response can power beyond the current UI</h3>
                  <ul className="result-list">
                    {responseIdeas.map((idea) => (
                      <li key={idea.title}>
                        <strong>{idea.title}</strong>
                        <span>{idea.body}</span>
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

      {graph ? (
        <ConnectedPaperModal
          graph={graph}
          kind={activePaper?.kind ?? "closest"}
          onClose={() => setActivePaper(null)}
          onFocusNode={setSelectedNodeId}
          paper={activePaper?.paper ?? null}
        />
      ) : null}
    </>
  );
}

function trimToChip(value: string) {
  return value.length <= 28 ? value : `${value.slice(0, 27).trimEnd()}...`;
}
