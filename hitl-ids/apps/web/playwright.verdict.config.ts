import base from "./playwright.pre-freeze.config";
export default { ...base, testMatch:["analyst-verdict.spec.ts"], outputDir:"test-results/verdict-browser-artifacts" };
