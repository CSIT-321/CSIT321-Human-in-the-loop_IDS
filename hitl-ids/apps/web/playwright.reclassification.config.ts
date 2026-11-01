import base from "./playwright.assistance.config";
const python = process.env.HITL_PYTHON ?? "python";
export default { ...base, testMatch: ["human-reclassification.spec.ts", "investigation-assistance.spec.ts"],
  outputDir: "test-results/reclassification-artifacts",
  use: { ...base.use, baseURL: "http://127.0.0.1:5190" },
  webServer: [
    { ...base.webServer[0], command: `"${python}" e2e/human-reclassification-fixture.py`, url: "http://127.0.0.1:8020/api/health" },
    { ...base.webServer[1], command: base.webServer[1].command.replace("5189", "5190"), url: "http://127.0.0.1:5190", env: { HITL_API_TARGET: "http://127.0.0.1:8020" } },
  ],
};
