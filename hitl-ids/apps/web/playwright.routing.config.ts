import base from "./playwright.config";
import path from "node:path";
const python = process.env.HITL_PYTHON ?? "python";
export default {
  ...base,
  testDir: path.resolve("e2e"),
  // Base for operational-queue/pre-freeze/real-suricata/suricata. Its own old specs were retired to
  // e2e/historical/ (2026-11-09, see analysis/phase-f/RETIRED-SPECS.md); it now runs the role surfaces.
  testMatch: ["role-surfaces.spec.ts"],
  outputDir: path.resolve("test-results/routing-browser-artifacts"),
  use: { ...base.use, baseURL: "http://127.0.0.1:5175" },
  webServer: [
    { command: `"${python}" ../../scripts/serve_routing_rehearsal.py --port 8002`,
      url: "http://127.0.0.1:8002/api/health", timeout: 60000, reuseExistingServer: false },
    { command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5175 --strictPort`,
      url: "http://127.0.0.1:5175", timeout: 60000, reuseExistingServer: false,
      env: { HITL_API_TARGET: "http://127.0.0.1:8002" } },
  ],
};
