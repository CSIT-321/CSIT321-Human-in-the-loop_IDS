import base from "./playwright.direct.config";

export default {
  ...base,
  testMatch: ["unified-workstation.spec.ts", "response-approval.spec.ts", "routing-workflow.spec.ts",
    "direct-escalation.spec.ts", "external-admission.spec.ts", "tier2-case.spec.ts",
    "triage-memory.spec.ts", "selective-review.spec.ts", "analyst-refinement.spec.ts", "detector-foundation.spec.ts"],
  outputDir: "test-results/unified-browser-artifacts",
  use: { ...base.use, baseURL: "http://127.0.0.1:5181" },
  webServer: [
    { ...base.webServer[0], command: base.webServer[0].command.replace("direct-fixture.py", "unified-fixture.py").replace("8007", "8008"), url: "http://127.0.0.1:8008/api/health" },
    { ...base.webServer[1], command: base.webServer[1].command.replace("5180", "5181"), url: "http://127.0.0.1:5181", env: { HITL_API_TARGET: "http://127.0.0.1:8008" } },
  ],
};
