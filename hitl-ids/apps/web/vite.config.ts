/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Read without @types/node: the config runs under Node, but the app's tsconfig types the browser.
const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {};

// The dev server proxies /api to uvicorn, so the browser sees one origin. The API's CORS list
// (apps/api/main.py DEV_ORIGINS) still names :5173 for anyone who points the client at :8000.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    // HITL_API_TARGET lets the end-to-end run point at a disposable API on another port, so a rehearsal
    // never writes verdicts into data/demo.db.
    proxy: { "/api": env.HITL_API_TARGET ?? "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // Unit and component tests only; the Playwright narrative in e2e/ runs under `npm run e2e`.
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
