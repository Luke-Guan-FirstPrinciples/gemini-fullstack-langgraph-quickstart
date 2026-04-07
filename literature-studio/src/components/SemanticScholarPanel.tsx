import { startTransition, useState } from "react";
import { requestJson } from "../lib/api";
import {
  semanticScholarBaseUrl,
  semanticScholarSeedFile,
  semanticScholarSeedNegative,
  semanticScholarSeedPositive,
} from "../lib/config";
import {
  formatCompactNumber,
  formatNumber,
  splitLines,
  truncateText,
} from "../lib/format";
import type { SemanticScholarRecommendationsResponse } from "../lib/types";

export function SemanticScholarPanel() {
  const [positiveInput, setPositiveInput] = useState(
    semanticScholarSeedPositive.join("\n"),
  );
  const [negativeInput, setNegativeInput] = useState(
    semanticScholarSeedNegative.join("\n"),
  );
  const [fields, setFields] = useState(
    "title,url,citationCount,authors,year,venue,abstract",
  );
  const [limit, setLimit] = useState(8);
  const [jsonFilePath, setJsonFilePath] = useState(semanticScholarSeedFile);
  const [loadingMode, setLoadingMode] = useState<"ids" | "file" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] =
    useState<SemanticScholarRecommendationsResponse | null>(null);

  const buildQuery = () => {
    const params = new URLSearchParams();
    if (fields.trim()) {
      params.set("fields", fields.trim());
    }
    params.set("limit", String(limit));
    return params.toString();
  };

  const queryString = buildQuery();

  const handleRecommendFromIds = async () => {
    setLoadingMode("ids");
    setError(null);

    try {
      const payload = await requestJson<SemanticScholarRecommendationsResponse>(
        `${semanticScholarBaseUrl}/recommendations/v1/papers?${queryString}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            positivePaperIds: splitLines(positiveInput),
            negativePaperIds: splitLines(negativeInput),
          }),
        },
      );

      startTransition(() => {
        setResponse(payload);
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to fetch Semantic Scholar recommendations.",
      );
    } finally {
      setLoadingMode(null);
    }
  };

  const handleRecommendFromFile = async () => {
    setLoadingMode("file");
    setError(null);

    try {
      const payload = await requestJson<SemanticScholarRecommendationsResponse>(
        `${semanticScholarBaseUrl}/recommendations/v1/papers/from-file?${queryString}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            jsonFilePath,
          }),
        },
      );

      startTransition(() => {
        setResponse(payload);
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to load the Semantic Scholar recommendation seed file.",
      );
    } finally {
      setLoadingMode(null);
    }
  };

  return (
    <div className="workspace-grid">
      <div className="control-panel">
        <div className="input-grid">
          <label className="field">
            <span>Positive paper IDs</span>
            <textarea
              value={positiveInput}
              onChange={(event) => setPositiveInput(event.target.value)}
              rows={5}
              placeholder="One paper ID per line"
            />
          </label>

          <label className="field">
            <span>Negative paper IDs</span>
            <textarea
              value={negativeInput}
              onChange={(event) => setNegativeInput(event.target.value)}
              rows={5}
              placeholder="Optional negative paper IDs"
            />
          </label>
        </div>

        <div className="input-grid compact">
          <label className="field">
            <span>Fields</span>
            <input
              value={fields}
              onChange={(event) => setFields(event.target.value)}
              placeholder="title,url,citationCount,authors"
            />
          </label>

          <label className="field narrow">
            <span>Limit</span>
            <input
              type="number"
              min={1}
              max={20}
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value) || 1)}
            />
          </label>
        </div>

        <label className="field">
          <span>Seed JSON path</span>
          <input
            value={jsonFilePath}
            onChange={(event) => setJsonFilePath(event.target.value)}
            placeholder="semantic_scholar/seed_papers.json"
          />
        </label>

        <div className="action-row">
          <button
            className="button primary"
            type="button"
            onClick={handleRecommendFromIds}
            disabled={loadingMode !== null}
          >
            {loadingMode === "ids" ? "Loading..." : "Recommend from IDs"}
          </button>
          <button
            className="button secondary"
            type="button"
            onClick={handleRecommendFromFile}
            disabled={loadingMode !== null}
          >
            {loadingMode === "file" ? "Loading..." : "Recommend from file"}
          </button>
        </div>

        <p className="panel-note">
          This panel targets the local FastAPI proxy in `semantic_scholar/app.py`.
          Start it on port `8000` for live results.
        </p>

        <div className="mono-card">
          <span>Proxy request</span>
          <code>
            POST {semanticScholarBaseUrl}/recommendations/v1/papers?{queryString}
          </code>
        </div>

        <div className="stat-grid">
          <article className="stat-card">
            <span>Positive seeds</span>
            <strong>{formatNumber(splitLines(positiveInput).length)}</strong>
          </article>
          <article className="stat-card">
            <span>Negative seeds</span>
            <strong>{formatNumber(splitLines(negativeInput).length)}</strong>
          </article>
          <article className="stat-card">
            <span>Returned</span>
            <strong>{formatNumber(response?.recommendedPapers.length)}</strong>
          </article>
          <article className="stat-card">
            <span>Mode</span>
            <strong>Local proxy</strong>
          </article>
        </div>

        {error ? <p className="status-message error">{error}</p> : null}
      </div>

      <div className="result-stack">
        {response?.recommendedPapers.length ? (
          <div className="card-grid">
            {response.recommendedPapers.map((paper) => (
              <article key={paper.paperId} className="result-card">
                <p className="mini-label">{paper.paperId}</p>
                <h3>
                  {paper.url ? (
                    <a href={paper.url} target="_blank" rel="noreferrer">
                      {paper.title}
                    </a>
                  ) : (
                    paper.title
                  )}
                </h3>
                <p>{truncateText(paper.abstract, 210)}</p>
                <div className="inline-tags">
                  <span className="tag">{paper.year ?? "Year n/a"}</span>
                  <span className="tag">
                    {formatCompactNumber(paper.citationCount)} citations
                  </span>
                  <span className="tag">{paper.venue ?? "Venue unknown"}</span>
                  <span className="tag">
                    {truncateText(
                      paper.authors?.map((author) => author.name).join(", "),
                      80,
                    )}
                  </span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <section className="empty-state">
            <p className="mini-label">Recommendation sandbox</p>
            <h3>Run the local Semantic Scholar proxy to fill this panel</h3>
            <p>
              You can seed recommendations with manual paper IDs or by pointing at
              `semantic_scholar/seed_papers.json`.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
