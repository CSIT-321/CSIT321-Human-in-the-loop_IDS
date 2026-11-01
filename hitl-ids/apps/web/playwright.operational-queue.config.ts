import base from "./playwright.routing.config";
const python = process.env.HITL_PYTHON ?? "python";
export default {
  ...base,
  testMatch: ["operational-queue.spec.ts"],
  outputDir: "test-results/operational-queue-browser-artifacts",
  use: { ...base.use, baseURL: "http://127.0.0.1:5183" },
  webServer: [
    { ...base.webServer[0], command: `"${python}" e2e/operational-queue-fixture.py --port 8010`, url: "http://127.0.0.1:8010/api/health" },
    { ...base.webServer[1], command: base.webServer[1].command.replace("5175", "5183"), url: "http://127.0.0.1:5183", env: { HITL_API_TARGET: "http://127.0.0.1:8010" } },
  ],
};
