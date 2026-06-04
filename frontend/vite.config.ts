import http from "node:http";
import { defineConfig } from "vite-plus";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Match Flask default from `python wsgi.py` (app.run). Override if needed:
//   set BOWLYZER_DEV_API=http://127.0.0.1:PORT && npm run dev
const BACKEND = process.env.BOWLYZER_DEV_API ?? "http://127.0.0.1:5000";

/** League cold-cache builds can take 15–30s; default proxy timeouts abort → Vite logs ECONNRESET. */
const DEV_PROXY_TIMEOUT_MS = 120_000;
const devProxyAgent = new http.Agent({ keepAlive: true });

function devApiProxy() {
  return {
    target: BACKEND,
    changeOrigin: true,
    agent: devProxyAgent,
    proxyTimeout: DEV_PROXY_TIMEOUT_MS,
    timeout: DEV_PROXY_TIMEOUT_MS,
  };
}

const DEV_API_PROXY_PATHS = [
  "/league",
  "/get_latest_events",
  "/player",
  "/team",
  "/tournament",
  "/switch-database",
  "/get-data-sources-info",
  "/home",
  "/set-season",
] as const;

export default defineConfig({
  lint: { options: { typeAware: true, typeCheck: true } },
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(DEV_API_PROXY_PATHS.map((path) => [path, devApiProxy()])),
  },
});
