import base from "./playwright.routing.config";
const python = process.env.HITL_PYTHON ?? "python";
export default {
  ...base,
  testMatch: ["pre-freeze.spec.ts"],
  outputDir: "test-results/pre-freeze-browser-artifacts",
  use: { ...base.use, baseURL: "http://127.0.0.1:5187" },
  webServer: [
    { ...base.webServer[0], command: `"${python}" e2e/pre-freeze-fixture.py --port 8014`, url: "http://127.0.0.1:8014/api/health" },
    { ...base.webServer[1], command: base.webServer[1].command.replace("5175", "5187"), url: "http://127.0.0.1:5187", env: { HITL_API_TARGET: "http://127.0.0.1:8014" } },
  ],
};
