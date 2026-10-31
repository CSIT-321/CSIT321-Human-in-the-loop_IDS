import base from "./playwright.routing.config";

const python = process.env.HITL_PYTHON ?? "python";
export default {
  ...base,
  testMatch: ["analyst-refinement.spec.ts", "routing-workflow.spec.ts", "external-admission.spec.ts",
    "tier2-case.spec.ts", "response-approval.spec.ts", "triage-memory.spec.ts", "selective-review.spec.ts"],
  webServer: [
    { ...base.webServer[0], command: `"${python}" e2e/refinement-fixture.py --port 8002` },
    base.webServer[1],
  ],
};
