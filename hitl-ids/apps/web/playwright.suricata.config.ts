import base from "./playwright.routing.config";
const python = process.env.HITL_PYTHON ?? "python";
export default {
  ...base,
  testMatch: ["suricata-routing.spec.ts"],
  outputDir: "test-results/suricata-browser-artifacts",
  use: { ...base.use, baseURL: "http://127.0.0.1:5182" },
  webServer: [
    { ...base.webServer[0], command: `"${python}" e2e/suricata-fixture.py --port 8009`, url: "http://127.0.0.1:8009/api/health" },
    { ...base.webServer[1], command: base.webServer[1].command.replace("5175", "5182"), url: "http://127.0.0.1:5182", env: { HITL_API_TARGET: "http://127.0.0.1:8009" } },
  ],
};
