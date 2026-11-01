import base from "./playwright.pre-freeze.config";
const python = process.env.HITL_PYTHON ?? "python";
export default { ...base, testMatch: ["f2-boundary.spec.ts"],
  outputDir: "test-results/f2-boundary-artifacts",
  use: { ...base.use, baseURL: "http://127.0.0.1:5186" },
  webServer: [
    { ...base.webServer[0], command: `"${python}" e2e/f2-boundary-fixture.py`, url: "http://127.0.0.1:8016/api/health" },
    { ...base.webServer[1], command: base.webServer[1].command.replace("5187", "5186"), url: "http://127.0.0.1:5186", env: { HITL_API_TARGET: "http://127.0.0.1:8016" } },
  ],
};
