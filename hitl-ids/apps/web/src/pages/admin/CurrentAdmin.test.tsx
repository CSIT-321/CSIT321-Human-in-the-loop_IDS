import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ROLE_META } from "../../session/roles";
import { jsonResponse, renderApp, stubFetch } from "../../test/renderApp";

const admin = { username: "admin", displayName: "System Administrator", role: "system_admin" as const, token: "admin-token" };
const analyst = { username: "g.ang", displayName: "Glenn Ang", role: "security_analyst" as const, token: "analyst-token" };
const evaluator = { username: "evaluator", displayName: "Evaluator", role: "evaluator" as const, token: "eval-token" };
const overview = {
  detectorSource: "Suricata", activeWorkspaceId: "v3-1-replay", activeWorkspaceName: "V3.1 Demo Replay",
  workspaceReady: true, databaseReady: true, workspaceAlertCount: 200,
  operational: { totalAlerts: 200, criticalAlerts: 0, tier1Review: 190, tier2Cases: 10,
    expertReview: 10, reviewRequired: 200, noImmediateReview: 4, openTier2Cases: 10,
    activeAlerts: 191, completedWork: 5, escalatedWork: 4, availableWork: 185, inReviewWork: 2 },
  memory: { total: 7, active: 3, conflictReview: 1 },
  classificationPolicyVersion: "suricata-classification-v3", routingPolicyVersion: "system-routing-v1",
  memoryPolicyVersion: "triage-memory-v1", selectiveReviewPolicyVersion: "selective-review-v1",
};
const governance = {
  automaticLearningEnabled: true, responseExecution: "disabled",
  classification: { version: "suricata-classification-v3", conflictPolicy: "unknown_needs_expert" },
  routing: { version: "system-routing-v1", rules: ["unknown_classification_requires_expert"] },
  memory: { version: "triage-memory-v1", exactRequiredFields: ["detectorSource", "sourceIp"],
    narrowRequiredFields: ["detectorSource", "detectionCategory"], minimumSupport: 3,
    minimumAgreementRatio: 0.67, maximumConflicts: 0, defaultValidityDays: 30 },
  autoLearning: { version: "safe-memory-auto-activation-v1", eligibleOutcomes: ["expected_activity", "false_positive"],
    evidenceScope: "exact", activationScope: "exact", slidingRenewal: false, postExpiryReactivation: false },
  selectiveReview: { version: "selective-review-v1", minimumSupport: 3, falsePositiveMinimumSupport: 5,
    minimumAgreementRatio: 0.67, contextMaximumAgeHours: 24, campaignAlertThreshold: 5, auditSamplePercent: 10 },
  analystWork: { version: "analyst-work-claim-v1", claimArbitrationWindowMs: 750 },
};

function setup() {
  return stubFetch(request => {
    const path = new URL(request.url).pathname;
    if (path === "/api/admin/overview") return jsonResponse(overview);
    if (path === "/api/admin/governance") return jsonResponse(governance);
    if (path === "/api/admin/users") return jsonResponse({ items: [
      { username: "admin", displayName: "System Administrator", role: "system_admin", status: "active", lastLogin: "2026-11-03T00:00:00Z" },
      { username: "g.ang", displayName: "Glenn Ang", role: "security_analyst", status: "active", lastLogin: null },
    ] });
    return jsonResponse({ error: { code: "NOT_FOUND", message: path } }, 404);
  });
}

describe("current Admin surface", () => {
  it("has exactly five primary links and lands on Overview", async () => {
    setup();
    const { router } = renderApp("/admin", { session: admin });
    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/overview"));
    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getAllByRole("link").map(link => link.textContent?.trim())).toEqual([
      "Overview", "Operational Workspace", "HITL Governance", "Users & Access", "Evaluation & Audit",
    ]);
    expect(ROLE_META.security_analyst.nav.map(item => item.label)).toEqual([
      "Analyst Workstation", "Tier 2 Cases", "Triage Memory", "Selective Review", "Incoming Alerts",
    ]);
  });

  it("shows active current operational counts and policy versions without historical dashboard calls", async () => {
    const seen = setup();
    renderApp("/admin/overview", { session: admin });
    expect(await screen.findByText("V3.1 Demo Replay")).toBeVisible();
    expect(screen.getByText("Available Work")).toBeVisible();
    expect(screen.getByText("185")).toBeVisible();
    expect(screen.getByText("In Review")).toBeVisible();
    expect(screen.getByText("Conflict Review lessons")).toBeVisible();
    expect(screen.getByText("suricata-classification-v3")).toBeVisible();
    expect(screen.getByText("Suricata")).toBeVisible();
    expect(seen.some(request => new URL(request.url).pathname.startsWith("/api/dashboard/"))).toBe(false);
    expect(seen.some(request => new URL(request.url).pathname === "/api/detection/run")).toBe(false);
  });

  it("keeps the old Status route clearly historical and outside the primary nav", async () => {
    setup();
    renderApp("/admin/status", { session: admin });
    expect(await screen.findByRole("heading", { level: 1, name: "System Status" })).toBeVisible();
    expect(screen.getByRole("note")).toHaveTextContent("Historical research view");
    expect(within(screen.getByRole("navigation", { name: "Main" })).queryByRole("link", { name: "System Status" })).toBeNull();
  });

  it("shows current policy sources, safety rules, claim semantics and disabled response execution", async () => {
    setup();
    renderApp("/admin/governance", { session: admin });
    expect(await screen.findByRole("heading", { level: 1, name: "HITL Governance" })).toBeVisible();
    for (const version of ["suricata-classification-v3", "system-routing-v1", "triage-memory-v1",
      "safe-memory-auto-activation-v1", "selective-review-v1", "analyst-work-claim-v1"])
      expect(screen.getByText(version)).toBeVisible();
    expect(screen.getByText(/Unknown \/ Needs Expert → automatic Tier 2 Expert Review → formal Tier 2 Case/)).toBeVisible();
    expect(screen.getByText(/Reusable guidance requires the policy thresholds/)).toBeVisible();
    expect(screen.getByText(/Active Memory alone does not suppress review/)).toBeVisible();
    expect(screen.getByText(/One distinct claimant becomes Owner; more than one causes Conflict with no owner/)).toBeVisible();
    expect(screen.getByText("750 ms")).toBeVisible();
    expect(screen.getByText("Approved — Not Executed")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Start Review" })).toBeNull();
  });

  it("loads minimal users and role explanations", async () => {
    setup();
    renderApp("/admin/users", { session: admin });
    expect(await screen.findByRole("heading", { level: 1, name: "Users & Access" })).toBeVisible();
    expect(screen.getByText("Glenn Ang")).toBeVisible();
    expect(screen.getByText("Last login: Not available")).toBeVisible();
    expect(screen.getByText("Read-only evaluation and assessment access.")).toBeVisible();
    expect(screen.queryByText(/password reset|permission matrix/i)).toBeNull();
  });

  it("links to the reused Final V3.1 route and labels retained audit coverage", async () => {
    setup();
    renderApp("/admin/evaluation", { session: admin });
    expect(await screen.findByRole("heading", { level: 1, name: "Evaluation & Audit" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Final V3.1 Evaluation" })).toHaveAttribute("href", "/admin/evaluation/final-v3-1");
    expect(screen.getByRole("link", { name: "Open Audit Trail" })).toHaveAttribute("href", "/admin/audit");
    expect(screen.getByText(/not yet a unified audit projection/)).toBeVisible();
  });

  it("preserves the Evaluator and Analyst primary navigation", async () => {
    setup();
    const mounted = renderApp("/evaluator/scenarios", { session: evaluator });
    expect(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Final V3.1 Evaluation" })).toBeVisible();
    expect(within(screen.getByRole("navigation", { name: "Main" })).queryByRole("link", { name: "Users & Access" })).toBeNull();
    mounted.unmount();
    renderApp("/analyst/operations", { session: analyst });
    expect(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Analyst Workstation" })).toBeVisible();
  });
});
