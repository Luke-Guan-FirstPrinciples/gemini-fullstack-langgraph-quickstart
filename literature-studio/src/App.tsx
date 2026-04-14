import { startTransition, useEffect, useState } from "react";
import type { ComponentType, MouseEvent, ReactNode } from "react";
import { ConnectedPapersPanel } from "./components/ConnectedPapersPanel";
import { FeatureFrame } from "./components/FeatureFrame";
import { OpenAlexPanel } from "./components/OpenAlexPanel";
import { ResearchAgentPanel } from "./components/ResearchAgentPanel";
import { SemanticScholarPanel } from "./components/SemanticScholarPanel";

type Theme = "dark" | "light";

interface FeatureRoute {
  path: string;
  navLabel: string;
  index: string;
  eyebrow: string;
  title: string;
  description: string;
  summary: string;
  accentClassName: string;
  Component: ComponentType;
}

const featureRoutes: FeatureRoute[] = [
  {
    path: "/connected-papers",
    navLabel: "Connected Papers",
    index: "01",
    eyebrow: "Graph explorer",
    title: "Connected Papers",
    description:
      "Query the official graph API, inspect the network visually, and keep usage-related controls beside the graph.",
    summary:
      "Interactive graph exploration, response inspection, and progressive paper drill-downs.",
    accentClassName: "accent-amber",
    Component: ConnectedPapersPanel,
  },
  {
    path: "/openalex",
    navLabel: "OpenAlex",
    index: "02",
    eyebrow: "Exact retrieval",
    title: "OpenAlex",
    description:
      "Run exact `/works` and `/authors` queries against OpenAlex with request previews and result cards tuned for each entity type.",
    summary:
      "Entity retrieval for works and authors with request visibility and clean result cards.",
    accentClassName: "accent-cyan",
    Component: OpenAlexPanel,
  },
  {
    path: "/semantic-scholar",
    navLabel: "Semantic Scholar",
    index: "03",
    eyebrow: "Recommendation proxy",
    title: "Semantic Scholar",
    description:
      "Exercise the local FastAPI recommendations proxy with manual seeds or a local JSON file, without entangling it with the other surfaces.",
    summary:
      "Recommendation testing against the local proxy without coupling it to the rest of the workspace.",
    accentClassName: "accent-rose",
    Component: SemanticScholarPanel,
  },
  {
    path: "/research-agent",
    navLabel: "Research Agent",
    index: "04",
    eyebrow: "LLM discovery pipeline",
    title: "Research Agent",
    description:
      "Run the repo's academic-search pipeline end to end from a natural-language query, inspect its generated search plan, and review OpenAlex-enriched ranked papers.",
    summary:
      "Natural-language literature discovery with parsed queries, enrichment, and weighted ranking.",
    accentClassName: "accent-lime",
    Component: ResearchAgentPanel,
  },
];

const runbook = [
  "cd literature-studio && npm install && npm run dev",
  "backend/venv/bin/uvicorn semantic_scholar.app:app --reload --port 8000",
  "backend/venv/bin/uvicorn research_agent.app:app --reload --port 8001",
  "Use TEST_TOKEN for the Connected Papers demo paper or swap in your own token",
];

const normalizePath = (value: string): string => {
  if (!value || value === "/") {
    return "/";
  }

  return value.replace(/\/+$/, "") || "/";
};

const getInitialTheme = (): Theme => {
  const stored = window.localStorage.getItem("literature-studio-theme");
  if (stored === "dark" || stored === "light") {
    return stored;
  }

  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
};

const isPlainLeftClick = (event: MouseEvent<HTMLAnchorElement>) =>
  event.button === 0 &&
  !event.altKey &&
  !event.ctrlKey &&
  !event.metaKey &&
  !event.shiftKey;

interface RouteLinkProps {
  active?: boolean;
  children: ReactNode;
  className?: string;
  navigate: (path: string) => void;
  to: string;
}

function RouteLink({
  active = false,
  children,
  className,
  navigate,
  to,
}: RouteLinkProps) {
  const classes = ["route-link", active ? "active" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <a
      aria-current={active ? "page" : undefined}
      className={classes}
      href={to}
      onClick={(event) => {
        if (!isPlainLeftClick(event)) {
          return;
        }

        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}

export default function App() {
  const [pathname, setPathname] = useState(() =>
    normalizePath(window.location.pathname),
  );
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    const onPopState = () => {
      setPathname(normalizePath(window.location.pathname));
    };

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("literature-studio-theme", theme);
  }, [theme]);

  const activeRoute = featureRoutes.find((route) => route.path === pathname) ?? null;

  const navigate = (path: string) => {
    const nextPath = normalizePath(path);

    if (nextPath === pathname) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }

    window.history.pushState({}, "", nextPath);
    window.scrollTo({ top: 0, left: 0 });

    startTransition(() => {
      setPathname(nextPath);
    });
  };

  return (
    <div className="app-shell">
      <header className="shell-header">
        <div className="shell-bar">
          <RouteLink className="brand-lockup" navigate={navigate} to="/">
            <span className="brand">Literature Studio</span>
            <span className="brand-meta">Routed literature workspaces</span>
          </RouteLink>

          <nav className="nav-links" aria-label="Primary">
            <RouteLink
              active={pathname === "/"}
              navigate={navigate}
              to="/"
            >
              Home
            </RouteLink>
            {featureRoutes.map((route) => (
              <RouteLink
                key={route.path}
                active={pathname === route.path}
                navigate={navigate}
                to={route.path}
              >
                {route.navLabel}
              </RouteLink>
            ))}
          </nav>

          <button
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            className="button ghost theme-toggle"
            onClick={() =>
              setTheme((currentTheme) =>
                currentTheme === "dark" ? "light" : "dark",
              )
            }
            type="button"
          >
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </header>

      <main className="shell-main">
        {pathname === "/" ? (
          <HomePage navigate={navigate} />
        ) : activeRoute ? (
          <FeaturePage navigate={navigate} route={activeRoute} />
        ) : (
          <NotFoundPage navigate={navigate} />
        )}
      </main>
    </div>
  );
}

function HomePage({ navigate }: { navigate: (path: string) => void }) {
  return (
    <div className="page-stack">
      <section className="hero">
        <div className="hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">Progressive research UI</p>
            <h1>One front end, four routes, less cognitive spillover.</h1>
            <p className="hero-text">
              Each tool now lives on its own route instead of sharing a single
              scrolled page. The shell keeps a fixed glass header, a persistent
              light or dark theme, and a home view that lets you enter the right
              workspace directly.
            </p>

            <div className="cta-row">
              <RouteLink
                className="button primary"
                navigate={navigate}
                to="/connected-papers"
              >
                Open Connected Papers
              </RouteLink>
              <RouteLink
                className="button secondary"
                navigate={navigate}
                to="/research-agent"
              >
                Open Research Agent
              </RouteLink>
            </div>
          </div>

          <aside className="hero-panel">
            <p className="mini-label">Workspace map</p>
            <h2>Choose a route, then stay in that task.</h2>
            <div className="route-card-stack">
              {featureRoutes.map((route) => (
                <RouteLink
                  key={route.path}
                  className={`feature-route-card ${route.accentClassName}`}
                  navigate={navigate}
                  to={route.path}
                >
                  <span className="feature-index">{route.index}</span>
                  <strong>{route.title}</strong>
                  <span>{route.summary}</span>
                </RouteLink>
              ))}
            </div>
          </aside>
        </div>
      </section>

      <section className="overview-grid">
        {featureRoutes.map((route) => (
          <RouteLink
            key={route.path}
            className="overview-card"
            navigate={navigate}
            to={route.path}
          >
            <p className="mini-label">{route.eyebrow}</p>
            <h3>{route.title}</h3>
            <p>{route.summary}</p>
          </RouteLink>
        ))}
      </section>

      <section className="runbook">
        <div>
          <p className="eyebrow">Runbook</p>
          <h2>Local setup</h2>
          <p>
            The app remains standalone. Start it separately from the existing
            `frontend/` folder and route into the workspace you need.
          </p>
        </div>
        <div className="runbook-list">
          {runbook.map((step) => (
            <code key={step}>{step}</code>
          ))}
        </div>
      </section>
    </div>
  );
}

function FeaturePage({
  navigate,
  route,
}: {
  navigate: (path: string) => void;
  route: FeatureRoute;
}) {
  const Panel = route.Component;

  return (
    <div className="page-stack">
      <section className="page-banner">
        <div className="page-banner-copy">
          <p className="feature-index">{route.index}</p>
          <p className="feature-eyebrow">{route.eyebrow}</p>
          <h1 className="page-title">{route.title}</h1>
          <p className="hero-text">{route.description}</p>
        </div>
        <div className="page-banner-actions">
          <RouteLink className="button ghost" navigate={navigate} to="/">
            All workspaces
          </RouteLink>
          <RouteLink className="button secondary" navigate={navigate} to={route.path}>
            Stay on this route
          </RouteLink>
        </div>
      </section>

      <FeatureFrame
        accentClassName={route.accentClassName}
        description={route.description}
        eyebrow={route.eyebrow}
        id={route.path.slice(1)}
        index={route.index}
        title={route.title}
      >
        <Panel />
      </FeatureFrame>
    </div>
  );
}

function NotFoundPage({ navigate }: { navigate: (path: string) => void }) {
  return (
    <section className="empty-state not-found-state">
      <p className="mini-label">Unknown route</p>
      <h3>That workspace does not exist.</h3>
      <p>
        Use the fixed header to switch routes or jump back to the overview.
      </p>
      <div className="cta-row">
        <RouteLink className="button primary" navigate={navigate} to="/">
          Return home
        </RouteLink>
      </div>
    </section>
  );
}
