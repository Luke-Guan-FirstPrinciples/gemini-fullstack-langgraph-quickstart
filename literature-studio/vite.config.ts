import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api/connected-papers": {
          target:
            env.VITE_CONNECTED_PAPERS_PROXY_TARGET ??
            "https://rest.prod.connectedpapers.com",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/connected-papers/, ""),
          secure: true,
        },
        "/api/openalex": {
          target:
            env.VITE_OPENALEX_PROXY_TARGET ?? "https://api.openalex.org",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/openalex/, ""),
          secure: true,
        },
        "/api/semantic-scholar": {
          target:
            env.VITE_SEMANTIC_SCHOLAR_PROXY_TARGET ?? "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/semantic-scholar/, ""),
          secure: false,
        },
      },
    },
  };
});
