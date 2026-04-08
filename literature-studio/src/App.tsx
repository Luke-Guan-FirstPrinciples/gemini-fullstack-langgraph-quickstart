import { ConnectedPapersPanel } from "./components/ConnectedPapersPanel";
import { FeatureFrame } from "./components/FeatureFrame";
import { OpenAlexPanel } from "./components/OpenAlexPanel";
import { ResearchAgentPanel } from "./components/ResearchAgentPanel";
import { SemanticScholarPanel } from "./components/SemanticScholarPanel";

const overviewCards = [
  {
    title: "Connected Papers",
    body: "Similarity graph exploration, quota checks, and free re-access all stay local to this panel.",
  },
  {
    title: "OpenAlex",
    body: "Exact-query retrieval for works and authors maps cleanly onto the standalone OpenAlex workflow in this repo.",
  },
  {
    title: "Semantic Scholar",
    body: "Recommendations run through the local FastAPI proxy so you can test seed-paper combinations without coupling it to the other features.",
  },
  {
    title: "Research Agent",
    body: "Natural-language literature discovery now runs as a local proxy-backed panel with query decomposition, OpenAlex enrichment, and weighted reranking.",
  },
];

const runbook = [
  "cd literature-studio && npm install && npm run dev",
  "backend/venv/bin/uvicorn semantic_scholar.app:app --reload --port 8000",
  "backend/venv/bin/uvicorn research_agent.app:app --reload --port 8001",
  "Use TEST_TOKEN for the Connected Papers demo paper or swap in your own token",
];

export default function App() {
  return (
    <div className="app-shell">
      <header className="hero">
        <nav className="topbar">
          <a className="brand" href="#top">
            Literature Studio
          </a>
          <div className="nav-links">
            <a href="#features">Features</a>
            <a href="#connected-papers">Connected Papers</a>
            <a href="#openalex">OpenAlex</a>
            <a href="#semantic-scholar">Semantic Scholar</a>
            <a href="#research-agent">Research Agent</a>
          </div>
        </nav>

        <div className="hero-grid" id="top">
          <div className="hero-copy">
            <p className="eyebrow">Unified landing page</p>
            <h1>One research front end, four independent literature engines.</h1>
            <p className="hero-text">
              This app sits outside the existing `frontend/` project and gives each
              repo surface its own workspace: graph exploration for Connected Papers,
              exact retrieval for OpenAlex, recommendation testing for Semantic
              Scholar, and a full LLM-driven research pipeline with enrichment and
              reranking.
            </p>

            <div className="cta-row">
              <a className="button primary" href="#features">
                Explore the page
              </a>
              <a className="button secondary" href="#runbook">
                Run locally
              </a>
            </div>
          </div>

          <aside className="hero-panel">
            <p className="mini-label">Design intent</p>
            <h2>Separate features by behavior, not by tabs.</h2>
            <ul className="hero-list">
              <li>Each section owns its own state, network flow, and empty state.</li>
              <li>No feature depends on data from another panel.</li>
              <li>The page behaves like a landing experience and a live sandbox.</li>
            </ul>
          </aside>
        </div>
      </header>

      <main className="main-content">
        <section id="features" className="overview-grid">
          {overviewCards.map((card) => (
            <article key={card.title} className="overview-card">
              <p className="mini-label">{card.title}</p>
              <h3>{card.title}</h3>
              <p>{card.body}</p>
            </article>
          ))}
        </section>

        <FeatureFrame
          id="connected-papers"
          index="01"
          eyebrow="Graph explorer"
          title="Connected Papers"
          description="Query the official graph API, inspect the network visually, and keep usage-related controls beside the graph."
          accentClassName="accent-amber"
        >
          <ConnectedPapersPanel />
        </FeatureFrame>

        <FeatureFrame
          id="openalex"
          index="02"
          eyebrow="Exact retrieval"
          title="OpenAlex"
          description="Run exact `/works` and `/authors` queries against OpenAlex with request previews and result cards tuned for each entity type."
          accentClassName="accent-cyan"
        >
          <OpenAlexPanel />
        </FeatureFrame>

        <FeatureFrame
          id="semantic-scholar"
          index="03"
          eyebrow="Recommendation proxy"
          title="Semantic Scholar"
          description="Exercise the local FastAPI recommendations proxy with manual seeds or a local JSON file, without entangling it with the other surfaces."
          accentClassName="accent-rose"
        >
          <SemanticScholarPanel />
        </FeatureFrame>

        <FeatureFrame
          id="research-agent"
          index="04"
          eyebrow="LLM discovery pipeline"
          title="Research Agent"
          description="Run the repo's academic-search pipeline end to end from a natural-language query, inspect its generated search plan, and review OpenAlex-enriched ranked papers."
          accentClassName="accent-lime"
        >
          <ResearchAgentPanel />
        </FeatureFrame>

        <section id="runbook" className="runbook">
          <div>
            <p className="eyebrow">Runbook</p>
            <h2>Local setup</h2>
            <p>
              The app is intentionally standalone. Start it separately from the
              existing `frontend/` folder.
            </p>
          </div>
          <div className="runbook-list">
            {runbook.map((step) => (
              <code key={step}>{step}</code>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
