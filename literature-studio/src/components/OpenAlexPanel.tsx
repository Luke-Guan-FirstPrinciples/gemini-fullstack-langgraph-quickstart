import { startTransition, useState } from "react";
import { requestJson } from "../lib/api";
import { openAlexBaseUrl } from "../lib/config";
import {
  formatCompactNumber,
  formatNumber,
  shortId,
  truncateText,
} from "../lib/format";
import type {
  OpenAlexAuthor,
  OpenAlexResponse,
  OpenAlexWork,
} from "../lib/types";

type OpenAlexEndpoint = "works" | "authors";

const WORK_PRESET = "search=quantum error correction";
const AUTHOR_PRESET = "filter=topics.id:T10622&sort=cited_by_count:desc";

const buildRequestUrl = (
  endpoint: OpenAlexEndpoint,
  queryText: string,
  limit: number,
) => {
  const normalized = queryText.trim().replace(/^\?/, "");
  const params = new URLSearchParams(normalized);

  if (!params.has("per-page") && !params.has("per_page")) {
    params.set("per-page", String(limit));
  }

  if (!params.has("page") && !params.has("cursor")) {
    params.set("page", "1");
  }

  return `${openAlexBaseUrl}/${endpoint}?${params.toString()}`;
};

const getWorkAuthors = (work: OpenAlexWork): string =>
  work.authorships?.length
    ? work.authorships
        .slice(0, 4)
        .map((entry) => entry.author?.display_name ?? "Unknown author")
        .join(", ")
    : "Unknown authors";

export function OpenAlexPanel() {
  const [endpoint, setEndpoint] = useState<OpenAlexEndpoint>("works");
  const [queryText, setQueryText] = useState(WORK_PRESET);
  const [limit, setLimit] = useState(8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<
    OpenAlexResponse<OpenAlexWork | OpenAlexAuthor> | null
  >(null);

  const requestUrl = buildRequestUrl(endpoint, queryText, limit);

  const applyPreset = (nextEndpoint: OpenAlexEndpoint, nextQueryText: string) => {
    setEndpoint(nextEndpoint);
    setQueryText(nextQueryText);
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);

    try {
      const payload = await requestJson<
        OpenAlexResponse<OpenAlexWork | OpenAlexAuthor>
      >(requestUrl);

      startTransition(() => {
        setResponse(payload);
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to query the OpenAlex API.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="workspace-grid">
      <div className="control-panel">
        <div className="segmented-control" role="tablist" aria-label="OpenAlex target">
          <button
            className={endpoint === "works" ? "active" : undefined}
            type="button"
            onClick={() => setEndpoint("works")}
          >
            Works
          </button>
          <button
            className={endpoint === "authors" ? "active" : undefined}
            type="button"
            onClick={() => setEndpoint("authors")}
          >
            Authors
          </button>
        </div>

        <label className="field">
          <span>Exact OpenAlex query</span>
          <textarea
            value={queryText}
            onChange={(event) => setQueryText(event.target.value)}
            rows={5}
            placeholder="search=quantum error correction"
          />
        </label>

        <label className="field narrow">
          <span>Result count</span>
          <input
            type="number"
            min={1}
            max={20}
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value) || 1)}
          />
        </label>

        <div className="chip-row">
          <button
            className="chip-button"
            type="button"
            onClick={() => applyPreset("works", WORK_PRESET)}
          >
            Works preset
          </button>
          <button
            className="chip-button"
            type="button"
            onClick={() =>
              applyPreset(
                "works",
                "filter=primary_topic.id:T11994&sort=cited_by_count:desc",
              )
            }
          >
            Topic ranking
          </button>
          <button
            className="chip-button"
            type="button"
            onClick={() => applyPreset("authors", AUTHOR_PRESET)}
          >
            Author preset
          </button>
        </div>

        <div className="action-row">
          <button
            className="button primary"
            type="button"
            onClick={handleSubmit}
            disabled={loading}
          >
            {loading ? "Running query..." : "Run OpenAlex query"}
          </button>
        </div>

        <div className="mono-card">
          <span>Request preview</span>
          <code>{requestUrl}</code>
        </div>

        {error ? <p className="status-message error">{error}</p> : null}

        <div className="stat-grid">
          <article className="stat-card">
            <span>Total matches</span>
            <strong>{formatNumber(response?.meta?.count)}</strong>
          </article>
          <article className="stat-card">
            <span>Response time</span>
            <strong>
              {response?.meta?.db_response_time_ms
                ? `${formatNumber(response.meta.db_response_time_ms)} ms`
                : "n/a"}
            </strong>
          </article>
          <article className="stat-card">
            <span>Returned</span>
            <strong>{formatNumber(response?.results.length)}</strong>
          </article>
          <article className="stat-card">
            <span>Mode</span>
            <strong>Exact query</strong>
          </article>
        </div>
      </div>

      <div className="result-stack">
        {response?.results.length ? (
          <div className="card-grid">
            {endpoint === "works"
              ? (response.results as OpenAlexWork[]).map((work) => {
                  const destination =
                    work.primary_location?.landing_page_url ?? work.id;

                  return (
                    <article key={work.id} className="result-card">
                      <p className="mini-label">
                        {work.type ?? "work"} · {shortId(work.id, 10, 7)}
                      </p>
                      <h3>
                        <a href={destination} target="_blank" rel="noreferrer">
                          {work.display_name ?? work.title ?? "Untitled work"}
                        </a>
                      </h3>
                      <p>{truncateText(getWorkAuthors(work), 120)}</p>
                      <div className="inline-tags">
                        <span className="tag">
                          {work.publication_year ?? "Year n/a"}
                        </span>
                        <span className="tag">
                          {formatCompactNumber(work.cited_by_count)} citations
                        </span>
                        <span className="tag">
                          {work.primary_location?.source?.display_name ??
                            "Source unknown"}
                        </span>
                        <span className="tag">
                          {work.open_access?.is_oa ? "Open access" : "Closed"}
                        </span>
                      </div>
                    </article>
                  );
                })
              : (response.results as OpenAlexAuthor[]).map((author) => (
                  <article key={author.id} className="result-card">
                    <p className="mini-label">{shortId(author.id, 10, 7)}</p>
                    <h3>
                      <a href={author.id} target="_blank" rel="noreferrer">
                        {author.display_name ?? "Unnamed author"}
                      </a>
                    </h3>
                    <p>
                      {truncateText(
                        author.last_known_institutions
                          ?.map((institution) =>
                            [institution.display_name, institution.country_code]
                              .filter(Boolean)
                              .join(" "),
                          )
                          .join(" / "),
                        150,
                      )}
                    </p>
                    <div className="inline-tags">
                      <span className="tag">
                        {formatCompactNumber(author.works_count)} works
                      </span>
                      <span className="tag">
                        {formatCompactNumber(author.cited_by_count)} citations
                      </span>
                      <span className="tag">
                        h-index {formatNumber(author.summary_stats?.h_index)}
                      </span>
                      <span className="tag">
                        ORCID {author.orcid ? "linked" : "n/a"}
                      </span>
                    </div>
                  </article>
                ))}
          </div>
        ) : (
          <section className="empty-state">
            <p className="mini-label">Query workspace</p>
            <h3>Exact OpenAlex retrieval for works and authors</h3>
            <p>
              This surface maps to the repo&apos;s exact-query path and runs directly
              against the OpenAlex API through the local proxy.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
