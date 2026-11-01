import base from "./playwright.refinement.config";

// Separate ports keep an analyst's existing refinement preview undisturbed.
export default {
  ...base,
  testMatch: [...base.testMatch, "direct-escalation.spec.ts"],
  outputDir: "test-results/direct-browser-artifacts",
  use: { ...base.use, baseURL: "http://127.0.0.1:5180" },
  webServer: [
    { ...base.webServer[0], command: base.webServer[0].command.replace("refinement-fixture.py", "direct-fixture.py").replace("8002", "8007"), url: "http://127.0.0.1:8007/api/health" },
    { ...base.webServer[1], command: base.webServer[1].command.replace("5175", "5180"), url: "http://127.0.0.1:5180",
      env: { HITL_API_TARGET: "http://127.0.0.1:8007" } },
  ],
};
