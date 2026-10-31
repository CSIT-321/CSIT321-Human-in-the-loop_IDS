import base from "./playwright.config";
import path from "node:path";
const python = process.env.HITL_PYTHON ?? "python";
export default {
  ...base,
  testDir: path.resolve("e2e"),
  testMatch: ["routing-workflow.spec.ts", "detector-foundation.spec.ts", "external-admission.spec.ts", "tier2-case.spec.ts", "response-approval.spec.ts"],
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
