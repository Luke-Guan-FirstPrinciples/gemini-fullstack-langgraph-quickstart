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
