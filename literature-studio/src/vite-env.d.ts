/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CONNECTED_PAPERS_BASE_URL?: string;
  readonly VITE_OPENALEX_BASE_URL?: string;
  readonly VITE_SEMANTIC_SCHOLAR_BASE_URL?: string;
  readonly VITE_CONNECTED_PAPERS_PROXY_TARGET?: string;
  readonly VITE_OPENALEX_PROXY_TARGET?: string;
  readonly VITE_SEMANTIC_SCHOLAR_PROXY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
