import base from "./playwright.pre-freeze.config";
const python = process.env.HITL_PYTHON ?? "python";
export default { ...base, testMatch: ["investigation-assistance.spec.ts"],
  outputDir: "test-results/assistance-artifacts",
  use: { ...base.use, baseURL: "http://127.0.0.1:5189" },
  webServer: [
    { ...base.webServer[0], command: `"${python}" e2e/pre-freeze-fixture.py --port 8019`, url: "http://127.0.0.1:8019/api/health" },
    { ...base.webServer[1], command: base.webServer[1].command.replace("5187", "5189"), url: "http://127.0.0.1:5189", env: { HITL_API_TARGET: "http://127.0.0.1:8019" } },
  ],
};
