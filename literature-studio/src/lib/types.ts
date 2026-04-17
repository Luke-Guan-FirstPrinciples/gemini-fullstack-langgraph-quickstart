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

export type ConnectedPapersExternalIds = Record<
  string,
  string | number | null | undefined
>;

export interface ConnectedPapersPaperBase {
  id: string;
  title: string;
  paperId: string;
  paper_id?: string;
  corpusid?: number;
  year?: number | null;
  venue?: string | null;
  journalName?: string | null;
  journalVolume?: string | null;
  journalPages?: string | null;
  url?: string | null;
  abstract?: string | null;
  tldr?: string | null;
  doi?: string | null;
  pmid?: string | null;
  magId?: string | null;
  arxivId?: string | null;
  publicationDate?: string | null;
  publicationTypes?: string[] | null;
  authors: ConnectedPapersAuthor[];
  citations_length?: number;
  references_length?: number;
  total_citations?: number;
  edges_count?: number;
  fieldsOfStudy?: string[] | null;
  pdfUrls?: string[] | null;
  externalIds?: ConnectedPapersExternalIds;
  isOpenAccess?: boolean;
  number_of_authors?: number;
  pi_name?: string | null;
  local_citations?: string[];
  local_references?: string[];
}

export interface ConnectedPapersNode extends ConnectedPapersPaperBase {
  path_length: number;
  pos: [number, number];
  path?: string[];
  ref_with_start?: number;
  cit_with_start?: number;
}

export interface ConnectedPapersSidePaper extends ConnectedPapersPaperBase {}

export interface ConnectedPapersCommonAuthor {
  id: string;
  name: string;
  mentions: string[];
  mention_indexes?: number[];
  url?: string | null;
}

export interface ConnectedPapersGraphParameters {
  paper_id?: string;
  total_nodes?: number;
  num_commons?: number;
  max_load?: number;
  num_neighbors?: number;
  spring_iterations?: number;
  params_version?: number;
}

export interface ConnectedPapersGraph {
  nodes: Record<string, ConnectedPapersNode>;
  edges: Array<[string, string, number]>;
  common_references: ConnectedPapersSidePaper[];
  common_citations: ConnectedPapersSidePaper[];
  common_authors: ConnectedPapersCommonAuthor[];
  start_id: string;
  creation_time?: string;
  current_corpus_date?: string;
  parameters?: ConnectedPapersGraphParameters | null;
  path_lengths?: Record<string, number>;
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

export interface ResearchAgentPaperSemanticScholarPublicationVenue {
  venue_id?: string | null;
  name?: string | null;
  type?: string | null;
  alternate_names?: string[];
  url?: string | null;
}

export interface ResearchAgentPaperSemanticScholar {
  status: "matched" | "not_found" | "error";
  paper_id?: string | null;
  corpus_id?: number | null;
  matched_title?: string | null;
  title_similarity?: number | null;
  match_score?: number | null;
  citation_count?: number | null;
  influential_citation_count?: number | null;
  venue?: string | null;
  publication_venue?: ResearchAgentPaperSemanticScholarPublicationVenue | null;
  publication_venue_name?: string | null;
  authors?: string[];
  doi?: string | null;
  publication_year?: number | null;
  url?: string | null;
  error?: string | null;
}

export interface ResearchAgentPaperRanking {
  rank?: number | null;
  score?: number;
  normalized_signals?: Record<string, number>;
  explanation?: string;
  explanation_chips?: string[];
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
  semantic_scholar?: ResearchAgentPaperSemanticScholar | null;
  ranking?: ResearchAgentPaperRanking | null;
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
