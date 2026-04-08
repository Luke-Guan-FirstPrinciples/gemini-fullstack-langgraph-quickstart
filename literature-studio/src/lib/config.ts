const readEnv = (value: string | undefined, fallback: string) =>
  value && value.trim().length > 0 ? value : fallback;

export const connectedPapersBaseUrl = readEnv(
  import.meta.env.VITE_CONNECTED_PAPERS_BASE_URL,
  "/api/connected-papers",
);

export const openAlexBaseUrl = readEnv(
  import.meta.env.VITE_OPENALEX_BASE_URL,
  "/api/openalex",
);

export const semanticScholarBaseUrl = readEnv(
  import.meta.env.VITE_SEMANTIC_SCHOLAR_BASE_URL,
  "/api/semantic-scholar",
);

export const researchAgentBaseUrl = readEnv(
  import.meta.env.VITE_RESEARCH_AGENT_BASE_URL,
  "/api/research-agent",
);

export const deepFruitsPaperId =
  "9397e7acd062245d37350f5c05faf56e9cfae0d6";

export const semanticScholarSeedFile = "semantic_scholar/seed_papers.json";

export const semanticScholarSeedPositive = [
  "02138d6d094d1e7511c157f0b1a3dd4e5b20ebee",
  "018f58247a20ec6b3256fd3119f57980a6f37748",
];

export const semanticScholarSeedNegative = [
  "0045ad0c1e14a4d1f4b011c92eb36b8df63d65bc",
];
