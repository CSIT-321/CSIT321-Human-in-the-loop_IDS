import base from "./playwright.config";
import path from "node:path";
const python = process.env.HITL_PYTHON ?? "python";
// SOC flow on the routed demo data (a temp copy of data/demo.db). The fixture copies and routes ~45 s.
export default {
  ...base,
  testDir: path.resolve("e2e"),
  testMatch: ["soc-flow.spec.ts"],
  outputDir: path.resolve("test-results/soc-flow-artifacts"),
  use: { ...base.use, baseURL: "http://127.0.0.1:5190" },
  webServer: [
    { command: `"${python}" e2e/soc-flow-fixture.py`,
      url: "http://127.0.0.1:8040/api/health", timeout: 180000, reuseExistingServer: false },
    { command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5190 --strictPort`,
      url: "http://127.0.0.1:5190", timeout: 60000, reuseExistingServer: false,
      env: { HITL_API_TARGET: "http://127.0.0.1:8040" } },
  ],
};
