export type ConnectedPapersStatus =
  | "BAD_ID"
  | "ERROR"
  | "NOT_IN_DB"
  | "OLD_GRAPH"
  | "FRESH_GRAPH"
  | "IN_PROGRESS"
  | "QUEUED"
  | "BAD_TOKEN"
  | "BAD_REQUEST"
  | "OUT_OF_REQUESTS"
  | "OVERLOADED"
  | string;

export interface ConnectedPapersAuthor {
  ids: Array<string | null>;
  name: string;
}

export interface ConnectedPapersNode {
  id: string;
  title: string;
  paperId: string;
  year?: number | null;
  venue?: string | null;
  journalName?: string | null;
  url?: string | null;
  abstract?: string | null;
  tldr?: string | null;
  path_length: number;
  pos: [number, number];
  authors: ConnectedPapersAuthor[];
  citations_length?: number;
  references_length?: number;
  fieldsOfStudy?: string[] | null;
}

export interface ConnectedPapersSidePaper {
  id: string;
  title: string;
  year?: number | null;
  venue?: string | null;
  journalName?: string | null;
  url?: string | null;
  edges_count?: number;
  authors: ConnectedPapersAuthor[];
}

export interface ConnectedPapersGraph {
  nodes: Record<string, ConnectedPapersNode>;
  edges: Array<[string, string, number]>;
  common_references: ConnectedPapersSidePaper[];
  common_citations: ConnectedPapersSidePaper[];
  start_id: string;
  creation_time?: string;
  current_corpus_date?: string;
}

export interface ConnectedPapersGraphResponse {
  status: ConnectedPapersStatus;
  graph_json?: ConnectedPapersGraph | null;
  progress?: number | null;
  remaining_requests?: number | null;
}

export interface ConnectedPapersRemainingUsesResponse {
  status: string;
  remaining_uses: number;
}

export interface ConnectedPapersFreeAccessResponse {
  status: string;
  papers: string[];
}

export interface OpenAlexMeta {
  count?: number;
  db_response_time_ms?: number;
  page?: number;
  per_page?: number;
  cost_usd?: number;
}

export interface OpenAlexAuthorLite {
  display_name?: string | null;
}

export interface OpenAlexAuthorship {
  author?: OpenAlexAuthorLite | null;
}

export interface OpenAlexSource {
  display_name?: string | null;
}

export interface OpenAlexPrimaryLocation {
  landing_page_url?: string | null;
  source?: OpenAlexSource | null;
  is_oa?: boolean;
}

export interface OpenAlexOpenAccess {
  is_oa?: boolean;
  oa_status?: string | null;
  oa_url?: string | null;
}

export interface OpenAlexWork {
  id: string;
  title?: string | null;
  display_name?: string | null;
  publication_year?: number | null;
  cited_by_count?: number;
  type?: string | null;
  primary_location?: OpenAlexPrimaryLocation | null;
  open_access?: OpenAlexOpenAccess | null;
  authorships?: OpenAlexAuthorship[];
}

export interface OpenAlexInstitutionLite {
  display_name?: string | null;
  country_code?: string | null;
}

export interface OpenAlexSummaryStats {
  h_index?: number;
  i10_index?: number;
  two_year_mean_citedness?: number | null;
}

export interface OpenAlexAuthor {
  id: string;
  display_name?: string | null;
  works_count?: number;
  cited_by_count?: number;
  orcid?: string | null;
  summary_stats?: OpenAlexSummaryStats | null;
  last_known_institutions?: OpenAlexInstitutionLite[];
}

export interface OpenAlexResponse<T> {
  meta?: OpenAlexMeta;
  results: T[];
}

export interface SemanticScholarAuthor {
  authorId?: string;
  name: string;
  url?: string;
}

export interface SemanticScholarPaper {
  paperId: string;
  title: string;
  url?: string;
  abstract?: string;
  venue?: string;
  year?: number;
  citationCount?: number;
  authors?: SemanticScholarAuthor[];
}

export interface SemanticScholarRecommendationsResponse {
  recommendedPapers: SemanticScholarPaper[];
}

export interface ResearchAgentMeta {
  query: string;
  llm_provider: string;
  llm_model: string;
  search_provider: string;
  ranking_weights: Record<string, number>;
  iterations: number;
  total_raw_results: number;
  timestamp: string;
}

export interface ResearchAgentParsedQuery {
  intent?: string;
  fields?: string[];
  key_terms?: string[];
  date_constraint?: string | null;
  search_queries?: string[];
}

export interface ResearchAgentPaperOpenAlex {
  status: "matched" | "not_found" | "error";
  openalex_id?: string | null;
  matched_title?: string | null;
  title_similarity?: number | null;
  search_relevance_score?: number | null;
  citation_count?: number | null;
  fwci?: number | null;
  citation_normalized_percentile?: number | null;
  is_in_top_1_percent?: boolean | null;
  is_in_top_10_percent?: boolean | null;
  authors?: string[];
  doi?: string | null;
  publication_year?: number | null;
  source_display_name?: string | null;
  landing_page_url?: string | null;
  error?: string | null;
}

export interface ResearchAgentPaperRanking {
  rank?: number | null;
  score?: number;
  normalized_signals?: Record<string, number>;
}

export interface ResearchAgentPaper {
  title: string;
  authors: string[];
  source?: string;
  url?: string;
  year?: number | null;
  abstract?: string;
  doi?: string | null;
  key_finding?: string;
  openalex?: ResearchAgentPaperOpenAlex | null;
  ranking?: ResearchAgentPaperRanking | null;
}

export interface ResearchAgentAuthor {
  name: string;
  affiliations?: string[];
  research_areas?: string[];
}

export interface ResearchAgentLab {
  name: string;
  institution?: string;
  url?: string | null;
  key_researchers?: string[];
  focus_areas?: string[];
}

export interface ResearchAgentStructuredOutput {
  papers: ResearchAgentPaper[];
  authors: ResearchAgentAuthor[];
  labs: ResearchAgentLab[];
  fields: string[];
  keywords: string[];
  sub_queries: string[];
  _meta?: ResearchAgentMeta;
}

export interface ResearchAgentRankedResults {
  query: string;
  weights: Record<string, number>;
  normalization: Record<string, string>;
  papers: ResearchAgentPaper[];
  _meta?: ResearchAgentMeta;
}

export interface ResearchAgentRunResponse {
  parsed_query?: ResearchAgentParsedQuery | null;
  structured_output: ResearchAgentStructuredOutput;
  ranked_output: ResearchAgentRankedResults;
  meta: ResearchAgentMeta;
}
