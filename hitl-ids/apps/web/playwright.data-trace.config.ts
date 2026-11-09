import base from "./playwright.config";
import path from "node:path";
const python = process.env.HITL_PYTHON ?? "python";
// Data-flow trace on the routed demo data (a temp copy of data/demo.db). Not part of the gate: it writes the
// decision-tree evidence (trace.json + screenshots) to TRACE_OUT.
export default {
  ...base,
  testDir: path.resolve("e2e"),
  testMatch: ["data-trace.spec.ts"],
  timeout: 600_000,
  outputDir: path.resolve("test-results/data-trace-artifacts"),
  use: { ...base.use, baseURL: "http://127.0.0.1:5191" },
  webServer: [
    { command: `"${python}" e2e/data-trace-fixture.py`,
      url: "http://127.0.0.1:8041/api/health", timeout: 180000, reuseExistingServer: false },
    { command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5191 --strictPort`,
      url: "http://127.0.0.1:5191", timeout: 60000, reuseExistingServer: false,
      env: { HITL_API_TARGET: "http://127.0.0.1:8041" } },
  ],
};
