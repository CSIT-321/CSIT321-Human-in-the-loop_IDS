import base from "./playwright.config";
import path from "node:path";
import os from "node:os";
const python = process.env.HITL_PYTHON ?? "python";
const db = path.join(os.homedir(), "AppData", "Local", "Temp", "hitl-review", "p2w-flow.db");
// Legacy flow lane only (CICIDS2018 features). Labelled for removal in the walkthrough.
// Not part of the gate: it writes the packet-to-workstation screenshots.
export default {
  ...base,
  testDir: path.resolve("e2e"),
  testMatch: ["p2w-flow.spec.ts"],
  timeout: 300_000,
  outputDir: path.resolve("test-results/p2w-flow-artifacts"),
  use: { ...base.use, baseURL: "http://127.0.0.1:5195" },
  webServer: [
    { command: `"${python}" e2e/p2w_fixture.py "${db}" 8045`,
      url: "http://127.0.0.1:8045/api/health", timeout: 180000, reuseExistingServer: false },
    { command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5195 --strictPort`,
      url: "http://127.0.0.1:5195", timeout: 60000, reuseExistingServer: false,
      env: { HITL_API_TARGET: "http://127.0.0.1:8045" } },
  ],
};
