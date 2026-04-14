import type { ResearchAgentPaper, ResearchAgentRunResponse } from "./types";

interface BuildMockResearchAgentResponseOptions {
  citationWeight: number;
  fwciWeight: number;
  maxIterations: number;
  query: string;
  resultsPerQuery: number;
  semanticWeight: number;
}

interface MockPaperSeed {
  abstract: string;
  authors: string[];
  baseSemantic: number;
  citationCount: number;
  doi: string;
  fwci: number;
  keyFinding: string;
  landingPageUrl: string;
  openalexId: string;
  source: string;
  title: string;
  url: string;
  year: number;
}

export const DEFAULT_MOCK_RESEARCH_QUERY =
  "Recent quantum error correction papers adapted to biased noise";

const STOP_WORDS = new Set([
  "about",
  "adapted",
  "and",
  "benchmark",
  "benchmarking",
  "for",
  "from",
  "in",
  "into",
  "last",
  "methods",
  "of",
  "on",
  "papers",
  "recent",
  "the",
  "to",
  "with",
  "years",
]);

const MOCK_PAPER_SEEDS: MockPaperSeed[] = [
  {
    title: "Bias-Aware Surface Codes for Fast Logical Memory in Superconducting Qubits",
    authors: ["Maya Chen", "Daniel Ruiz", "Priya Narayan"],
    source: "Quantum Science and Technology",
    year: 2025,
    abstract:
      "This study evaluates decoder and circuit choices for surface-code memories under strongly biased dephasing noise, emphasizing hardware-realistic idle errors and short-cycle stabilizer extraction.",
    keyFinding:
      "Tailoring syndrome extraction to the dominant error channel improved logical memory lifetimes without increasing the physical qubit footprint.",
    doi: "10.48550/arXiv.2502.10231",
    url: "https://arxiv.org/abs/2502.10231",
    landingPageUrl: "https://openalex.org/W4400102310",
    openalexId: "https://openalex.org/W4400102310",
    citationCount: 186,
    fwci: 3.1,
    baseSemantic: 0.96,
  },
  {
    title: "Adaptive Decoders for Biased Noise with Lightweight Neural Priors",
    authors: ["Irene Volkov", "Marcus Lee", "Jules Perrin"],
    source: "Physical Review Applied",
    year: 2024,
    abstract:
      "We combine analytical decoder structure with compact learned priors to improve performance on biased-noise workloads while retaining latency suitable for control-stack deployment.",
    keyFinding:
      "A small neural prior closed most of the gap to heavyweight learned decoders while preserving the predictability of classical matching pipelines.",
    doi: "10.1103/PhysRevApplied.22.041002",
    url: "https://journals.aps.org/prapplied/abstract/10.1103/PhysRevApplied.22.041002",
    landingPageUrl: "https://openalex.org/W4400102311",
    openalexId: "https://openalex.org/W4400102311",
    citationCount: 142,
    fwci: 2.7,
    baseSemantic: 0.91,
  },
  {
    title: "Fault-Tolerant Neutral-Atom Architectures with Erasure-Dominant Noise",
    authors: ["Noah Patel", "Sofia Hartmann", "Luca Bianchi"],
    source: "Nature Physics",
    year: 2025,
    abstract:
      "Neutral-atom arrays increasingly operate in error regimes where erasures and leakage dominate over symmetric Pauli channels, motivating architecture-specific fault-tolerance benchmarks.",
    keyFinding:
      "Explicit erasure handling shifted the best-performing code-distance schedule and made neutral-atom benchmarks more comparable across hardware generations.",
    doi: "10.1038/s41567-025-03141-8",
    url: "https://www.nature.com/articles/s41567-025-03141-8",
    landingPageUrl: "https://openalex.org/W4400102312",
    openalexId: "https://openalex.org/W4400102312",
    citationCount: 128,
    fwci: 3.6,
    baseSemantic: 0.82,
  },
  {
    title: "Benchmarking Cat-Code Memories Under Realistic Biased Photon Loss",
    authors: ["Elena Rossi", "Tom Becker", "Amir Qureshi"],
    source: "PRX Quantum",
    year: 2024,
    abstract:
      "Cat-code memories promise strong protection when noise is highly asymmetric, but realistic calibration drift and finite-latency feedback complicate benchmarking and cross-platform comparisons.",
    keyFinding:
      "Loss-aware feedback scheduling preserved cat-code advantages across wider calibration drift than static pulse schedules.",
    doi: "10.1103/PRXQuantum.5.030112",
    url: "https://journals.aps.org/prxquantum/abstract/10.1103/PRXQuantum.5.030112",
    landingPageUrl: "https://openalex.org/W4400102313",
    openalexId: "https://openalex.org/W4400102313",
    citationCount: 97,
    fwci: 2.3,
    baseSemantic: 0.77,
  },
  {
    title: "Data-Efficient Reinforcement Learning for Quantum Error-Correction Scheduling",
    authors: ["Keisha Morgan", "Tobias Lindholm", "Arjun Rao"],
    source: "Machine Learning: Science and Technology",
    year: 2023,
    abstract:
      "The paper studies reinforcement-learning agents for adaptive scheduling of syndrome collection, reset, and decoding under constrained hardware budgets and sparse experimental data.",
    keyFinding:
      "Careful offline warm starts reduced sample requirements enough to make policy adaptation feasible on limited experimental traces.",
    doi: "10.1088/2632-2153/adf103",
    url: "https://iopscience.iop.org/article/10.1088/2632-2153/adf103",
    landingPageUrl: "https://openalex.org/W4400102314",
    openalexId: "https://openalex.org/W4400102314",
    citationCount: 84,
    fwci: 1.9,
    baseSemantic: 0.7,
  },
  {
    title: "Cross-Platform Evaluation of Biased-Noise Decoders on Open Hardware Traces",
    authors: ["Lena Hoffman", "Victor Kim", "Sara El-Amin"],
    source: "npj Quantum Information",
    year: 2025,
    abstract:
      "Open hardware traces enable more faithful comparisons of decoders and code families, especially when bias and leakage patterns differ across superconducting, photonic, and neutral-atom platforms.",
    keyFinding:
      "Shared evaluation traces changed the ranking of several decoders that previously looked dominant under synthetic noise assumptions.",
    doi: "10.1038/s41534-025-01087-4",
    url: "https://www.nature.com/articles/s41534-025-01087-4",
    landingPageUrl: "https://openalex.org/W4400102315",
    openalexId: "https://openalex.org/W4400102315",
    citationCount: 63,
    fwci: 2.1,
    baseSemantic: 0.74,
  },
];

const clamp = (value: number, min: number, max: number): number =>
  Math.min(Math.max(value, min), max);

const normalizeWeights = (weights: {
  citation: number;
  fwci: number;
  semantic: number;
}) => {
  const safeWeights = {
    semantic: Math.max(weights.semantic, 0),
    citation: Math.max(weights.citation, 0),
    fwci: Math.max(weights.fwci, 0),
  };
  const total = safeWeights.semantic + safeWeights.citation + safeWeights.fwci;

  if (total <= 0) {
    return { semantic: 1, citation: 0, fwci: 0 };
  }

  return {
    semantic: safeWeights.semantic / total,
    citation: safeWeights.citation / total,
    fwci: safeWeights.fwci / total,
  };
};

const toDisplayToken = (value: string): string =>
  value.length <= 3
    ? value.toUpperCase()
    : `${value.charAt(0).toUpperCase()}${value.slice(1)}`;

const extractQueryTokens = (query: string): string[] =>
  query
    .toLowerCase()
    .match(/[a-z0-9-]+/g)
    ?.filter((token) => token.length > 2 && !STOP_WORDS.has(token)) ?? [];

const buildDateConstraint = (query: string): string | null => {
  const yearsMatch = query.match(/last\s+(\d+)\s+years?/i);
  if (yearsMatch) {
    return `Last ${yearsMatch[1]} years`;
  }

  if (/recent/i.test(query)) {
    return "Recent literature";
  }

  const yearMatch = query.match(/\b(20\d{2})\b/);
  return yearMatch?.[1] ?? null;
};

const buildFields = (query: string): string[] => {
  const fields = ["Quantum information"];

  if (/error correction|decoder|surface code|fault[- ]tolerant/i.test(query)) {
    fields.push("Quantum error correction");
  }
  if (/neutral[- ]atom/i.test(query)) {
    fields.push("Neutral-atom systems");
  }
  if (/machine learning|neural|reinforcement/i.test(query)) {
    fields.push("Machine learning");
  }
  if (/bias|biased|dephasing|erasure|photon loss/i.test(query)) {
    fields.push("Noise-aware benchmarking");
  }

  return Array.from(new Set(fields)).slice(0, 4);
};

const buildKeywords = (query: string): string[] => {
  const tokens = extractQueryTokens(query);
  const keywords = [
    ...tokens.slice(0, 6).map(toDisplayToken),
    "OpenAlex enrichment",
    "Weighted ranking",
  ];

  return Array.from(new Set(keywords)).slice(0, 8);
};

const buildSearchQueries = (query: string): string[] => [
  query,
  `"${query}" decoder benchmark`,
  `${query} OpenAlex citation impact`,
  `${query} site:arxiv.org`,
];

const computeSemanticRelevance = (
  queryTokens: string[],
  paper: MockPaperSeed,
): number => {
  if (!queryTokens.length) {
    return paper.baseSemantic;
  }

  const haystack = [
    paper.title,
    paper.abstract,
    paper.keyFinding,
    paper.source,
    paper.authors.join(" "),
  ]
    .join(" ")
    .toLowerCase();

  const matchedTokens = queryTokens.filter((token) => haystack.includes(token)).length;
  const overlap = matchedTokens / queryTokens.length;

  return clamp(paper.baseSemantic * 0.72 + overlap * 0.28, 0.52, 0.99);
};

const buildStructuredPaper = (paper: MockPaperSeed): ResearchAgentPaper => ({
  title: paper.title,
  authors: paper.authors,
  source: paper.source,
  url: paper.url,
  year: paper.year,
  abstract: paper.abstract,
  doi: paper.doi,
  key_finding: paper.keyFinding,
  openalex: {
    status: "matched",
    openalex_id: paper.openalexId,
    matched_title: paper.title,
    title_similarity: 0.99,
    search_relevance_score: 0.94,
    citation_count: paper.citationCount,
    fwci: paper.fwci,
    citation_normalized_percentile: clamp(0.74 + paper.fwci / 6, 0, 1),
    is_in_top_1_percent: paper.fwci >= 3.2,
    is_in_top_10_percent: paper.fwci >= 1.8,
    authors: paper.authors,
    doi: paper.doi,
    publication_year: paper.year,
    source_display_name: paper.source,
    landing_page_url: paper.landingPageUrl,
    error: null,
  },
});

export function buildMockResearchAgentResponse(
  options: BuildMockResearchAgentResponseOptions,
): ResearchAgentRunResponse {
  const query =
    options.query.trim().length >= 3
      ? options.query.trim()
      : DEFAULT_MOCK_RESEARCH_QUERY;
  const weights = normalizeWeights({
    semantic: options.semanticWeight,
    citation: options.citationWeight,
    fwci: options.fwciWeight,
  });
  const queryTokens = extractQueryTokens(query);
  const structuredPapers = MOCK_PAPER_SEEDS.map(buildStructuredPaper);
  const maxCitations = Math.max(...MOCK_PAPER_SEEDS.map((paper) => paper.citationCount));
  const maxFwci = Math.max(...MOCK_PAPER_SEEDS.map((paper) => paper.fwci));

  const rankedPapers = structuredPapers
    .map((paper, index) => {
      const seed = MOCK_PAPER_SEEDS[index];
      const semanticRelevance = computeSemanticRelevance(queryTokens, seed);
      const citationSignal = seed.citationCount / maxCitations;
      const fwciSignal = seed.fwci / maxFwci;
      const score =
        weights.semantic * semanticRelevance +
        weights.citation * citationSignal +
        weights.fwci * fwciSignal;

      return {
        ...paper,
        ranking: {
          rank: null,
          score: Number(score.toFixed(4)),
          normalized_signals: {
            semantic_relevance: Number(semanticRelevance.toFixed(4)),
            citation_count: Number(citationSignal.toFixed(4)),
            fwci: Number(fwciSignal.toFixed(4)),
          },
        },
      };
    })
    .sort((left, right) => (right.ranking?.score ?? 0) - (left.ranking?.score ?? 0))
    .map((paper, index) => ({
      ...paper,
      ranking: {
        ...paper.ranking,
        rank: index + 1,
      },
    }));

  const mockAuthorPool = Array.from(
    new Set(
      rankedPapers
        .slice(0, 4)
        .flatMap((paper) => paper.authors),
    ),
  ).slice(0, 6);

  const returnedPaperCount = clamp(options.resultsPerQuery, 1, MOCK_PAPER_SEEDS.length);
  const iterations = clamp(options.maxIterations, 0, 6);
  const timestamp = new Date().toISOString();
  const meta = {
    query,
    llm_provider: "mock",
    llm_model: "frontend-fixture-v1",
    search_provider: "mock",
    ranking_weights: {
      semantic_relevance: Number(weights.semantic.toFixed(3)),
      citation_count: Number(weights.citation.toFixed(3)),
      fwci: Number(weights.fwci.toFixed(3)),
    },
    iterations,
    total_raw_results: returnedPaperCount * (iterations + 1),
    timestamp,
  };

  return {
    parsed_query: {
      intent: "Review recent literature with ranking-ready metadata",
      fields: buildFields(query),
      key_terms: buildKeywords(query),
      date_constraint: buildDateConstraint(query),
      search_queries: buildSearchQueries(query),
    },
    structured_output: {
      papers: structuredPapers.slice(0, returnedPaperCount),
      authors: mockAuthorPool.map((name) => ({
        name,
        affiliations: [
          "Caltech Institute for Quantum Information",
          "Center for Adaptive Quantum Systems",
        ],
        research_areas: ["Quantum error correction", "Noise-aware decoding"],
      })),
      labs: [
        {
          name: "Caltech Surface Code Lab",
          institution: "Caltech",
          url: "https://www.caltech.edu",
          key_researchers: ["Maya Chen", "Priya Narayan"],
          focus_areas: ["Biased-noise decoding", "Logical memory benchmarks"],
        },
        {
          name: "Neutral Atom Fault Tolerance Group",
          institution: "Harvard and QuEra",
          url: "https://www.quera.com",
          key_researchers: ["Noah Patel", "Sofia Hartmann"],
          focus_areas: ["Neutral-atom architectures", "Erasure-dominant noise"],
        },
        {
          name: "Adaptive QEC Systems Lab",
          institution: "ETH Zurich",
          url: "https://ethz.ch",
          key_researchers: ["Irene Volkov", "Tobias Lindholm"],
          focus_areas: ["ML-assisted decoding", "Control-stack integration"],
        },
      ],
      fields: buildFields(query),
      keywords: buildKeywords(query),
      sub_queries: [
        "Compare biased-noise decoders against standard MWPM baselines",
        "Separate hardware-specific benchmarks from synthetic noise studies",
        "Track papers with both OpenAlex impact signals and reproducible evaluation traces",
      ],
      _meta: meta,
    },
    ranked_output: {
      query,
      weights: meta.ranking_weights,
      normalization: {
        semantic_relevance: "query-token overlap blended with fixture prior",
        citation_count: "max-normalized within mock paper set",
        fwci: "max-normalized within mock paper set",
      },
      papers: rankedPapers.slice(0, returnedPaperCount),
      _meta: meta,
    },
    meta,
  };
}
