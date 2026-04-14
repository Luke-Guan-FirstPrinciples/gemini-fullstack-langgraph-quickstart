import { useEffect } from "react";
import { createPortal } from "react-dom";
import {
  formatCompactNumber,
  formatDate,
  shortId,
  truncateText,
} from "../lib/format";
import type {
  ConnectedPapersGraph,
  ConnectedPapersNode,
  ConnectedPapersSidePaper,
} from "../lib/types";

export type ConnectedPaperRelationKind = "closest" | "prior" | "derivative";

type InspectablePaper = ConnectedPapersNode | ConnectedPapersSidePaper;

interface ConnectedPaperModalProps {
  graph: ConnectedPapersGraph;
  kind: ConnectedPaperRelationKind;
  onClose: () => void;
  onFocusNode: (nodeId: string) => void;
  paper: InspectablePaper | null;
}

const joinAuthorNames = (
  authors: Array<{ name: string }> | undefined,
  limit = 6,
): string => {
  if (!authors || authors.length === 0) {
    return "Unknown authors";
  }

  return authors
    .slice(0, limit)
    .map((author) => author.name)
    .join(", ");
};

const relationCopy = {
  closest: {
    eyebrow: "Closest paper",
    title: "Similarity match",
    evidenceLabel: "Path evidence",
  },
  prior: {
    eyebrow: "Prior work",
    title: "Shared reference",
    evidenceLabel: "Cited by graph papers",
  },
  derivative: {
    eyebrow: "Derivative work",
    title: "Shared citation",
    evidenceLabel: "References graph papers",
  },
} satisfies Record<
  ConnectedPaperRelationKind,
  { eyebrow: string; title: string; evidenceLabel: string }
>;

const getVenueCopy = (paper: InspectablePaper): string =>
  [paper.journalName, paper.venue].filter(Boolean).join(" / ") ||
  "Venue unavailable";

const getRelatedGraphIds = (
  kind: ConnectedPaperRelationKind,
  paper: InspectablePaper,
): string[] => {
  if (kind === "prior") {
    return paper.local_citations ?? [];
  }

  if (kind === "derivative") {
    return paper.local_references ?? [];
  }

  if ("path" in paper && Array.isArray(paper.path)) {
    return paper.path;
  }

  return [paper.id];
};

const getEvidenceCopy = (
  kind: ConnectedPaperRelationKind,
  paper: InspectablePaper,
): string => {
  if (kind === "closest" && "path_length" in paper) {
    return `Path length ${paper.path_length.toFixed(2)} from the seed paper.`;
  }

  if (kind === "prior") {
    return `${paper.local_citations?.length ?? 0} graph papers cite this work.`;
  }

  return `${paper.local_references?.length ?? 0} graph papers reference this work.`;
};

const renderModal = ({
  graph,
  kind,
  onClose,
  onFocusNode,
  paper,
}: ConnectedPaperModalProps) => {
  if (!paper) {
    return null;
  }

  const copy = relationCopy[kind];
  const fieldsOfStudy = paper.fieldsOfStudy ?? [];
  const externalIds = Object.entries(paper.externalIds ?? {}).filter(
    ([, value]) => value !== null && value !== undefined && `${value}`.length > 0,
  );
  const pdfLink = paper.pdfUrls?.find((entry) => entry.trim().length > 0) ?? null;
  const relatedGraphIds = getRelatedGraphIds(kind, paper);
  const inGraph = Boolean(graph.nodes[paper.id]);

  return (
    <div className="modal-scrim" onClick={onClose}>
      <section
        aria-labelledby="connected-paper-modal-title"
        aria-modal="true"
        className="modal-card"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="modal-header">
          <div>
            <p className="mini-label">{copy.eyebrow}</p>
            <h3 id="connected-paper-modal-title">{paper.title}</h3>
            <p className="muted-copy">{truncateText(paper.abstract ?? paper.tldr, 220)}</p>
          </div>
          <button
            aria-label="Close paper details"
            className="button ghost modal-close"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>

        <div className="inline-details">
          <span>{paper.year ?? "Year unavailable"}</span>
          <span>{joinAuthorNames(paper.authors, 5)}</span>
          <span>{getVenueCopy(paper)}</span>
          <span>{formatCompactNumber(paper.citations_length)} citations</span>
          <span>{formatCompactNumber(paper.references_length)} references</span>
          {paper.edges_count !== undefined ? <span>{paper.edges_count} graph links</span> : null}
          {paper.isOpenAccess !== undefined ? (
            <span>{paper.isOpenAccess ? "Open access" : "Closed access"}</span>
          ) : null}
        </div>

        <div className="modal-actions">
          {inGraph ? (
            <button
              className="button primary"
              onClick={() => onFocusNode(paper.id)}
              type="button"
            >
              Focus in graph
            </button>
          ) : null}
          {paper.url ? (
            <a className="button secondary" href={paper.url} rel="noreferrer" target="_blank">
              Semantic Scholar
            </a>
          ) : null}
          {pdfLink ? (
            <a className="button secondary" href={pdfLink} rel="noreferrer" target="_blank">
              Open PDF
            </a>
          ) : null}
        </div>

        <div className="modal-section-stack">
          <details className="disclosure-card" open>
            <summary>Summary</summary>
            <div className="disclosure-body">
              <p>{paper.abstract ?? paper.tldr ?? "No summary provided."}</p>
              <div className="inline-tags">
                {fieldsOfStudy.length > 0 ? (
                  fieldsOfStudy.map((field) => <span key={field} className="tag">{field}</span>)
                ) : (
                  <span className="tag">No fields of study</span>
                )}
              </div>
            </div>
          </details>

          <details className="disclosure-card">
            <summary>{copy.evidenceLabel}</summary>
            <div className="disclosure-body">
              <p>{getEvidenceCopy(kind, paper)}</p>
              {kind === "closest" && "path" in paper && paper.path?.length ? (
                <div className="chip-row">
                  {paper.path.map((nodeId) => (
                    <button
                      key={nodeId}
                      className="chip-button"
                      onClick={() => onFocusNode(nodeId)}
                      type="button"
                    >
                      {graph.nodes[nodeId]?.title ?? shortId(nodeId)}
                    </button>
                  ))}
                </div>
              ) : null}
              {kind !== "closest" && relatedGraphIds.length > 0 ? (
                <div className="chip-row">
                  {relatedGraphIds.map((nodeId) => (
                    <button
                      key={nodeId}
                      className="chip-button"
                      onClick={() => onFocusNode(nodeId)}
                      type="button"
                    >
                      {graph.nodes[nodeId]?.title ?? shortId(nodeId)}
                    </button>
                  ))}
                </div>
              ) : null}
              {paper.total_citations !== undefined ? (
                <p className="muted-copy">
                  Total citations: {formatCompactNumber(paper.total_citations)}
                </p>
              ) : null}
            </div>
          </details>

          <details className="disclosure-card">
            <summary>Metadata</summary>
            <div className="disclosure-body">
              <div className="metadata-grid">
                <div>
                  <span>Publication date</span>
                  <strong>{formatDate(paper.publicationDate)}</strong>
                </div>
                <div>
                  <span>Lead author</span>
                  <strong>{paper.pi_name ?? "Unavailable"}</strong>
                </div>
                <div>
                  <span>Corpus ID</span>
                  <strong>{paper.corpusid ?? "n/a"}</strong>
                </div>
                <div>
                  <span>Paper ID</span>
                  <strong>{shortId(paper.paperId)}</strong>
                </div>
              </div>
              {externalIds.length > 0 ? (
                <div className="id-list">
                  {externalIds.slice(0, 8).map(([key, value]) => (
                    <code key={key}>
                      {key}: {String(value)}
                    </code>
                  ))}
                </div>
              ) : null}
            </div>
          </details>

          <details className="disclosure-card">
            <summary>Raw JSON</summary>
            <div className="disclosure-body">
              <pre className="json-block">{JSON.stringify(paper, null, 2)}</pre>
            </div>
          </details>
        </div>
      </section>
    </div>
  );
};

export function ConnectedPaperModal(props: ConnectedPaperModalProps) {
  useEffect(() => {
    if (!props.paper) {
      return undefined;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        props.onClose();
      }
    };

    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [props.paper, props.onClose]);

  if (!props.paper) {
    return null;
  }

  return createPortal(renderModal(props), document.body);
}
