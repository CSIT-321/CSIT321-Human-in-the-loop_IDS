import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ROLE_META } from "../../session/roles";
import { jsonResponse, renderApp, stubFetch } from "../../test/renderApp";

const admin = { username: "admin", displayName: "LIOW CHEE KUANG", role: "system_admin" as const, token: "admin-token" };
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
const auditEvents = [
  { eventRef: "work-1", timestamp: "2026-11-03T02:01:12Z", actorType: "human", actorId: 1,
    actorName: "Alice", decisionSource: "analyst", eventCategory: "WORK", eventType: "CLAIM_INTENT",
    action: "Review requested", objectType: "alert", objectRef: "alert-630b68", alertRef: "alert-630b68",
    caseRef: null, lessonRef: null, workspace: "v3-1-replay", summary: "Alice requested review of alert-630b68.",
    result: null, sourceSubsystem: "analyst_work_events", detail: { policyVersion: "analyst-work-claim-v1" } },
  { eventRef: "memory-1", timestamp: "2026-11-03T02:03:08Z", actorType: "system", actorId: null,
    actorName: null, decisionSource: "system_policy", eventCategory: "MEMORY", eventType: "V2_TRIAGE_MEMORY_AUTO_ACTIVATED",
    action: "Lesson auto-activated", objectType: "lesson", objectRef: "lesson-31a9cd", alertRef: "alert-630b68",
    caseRef: null, lessonRef: "lesson-31a9cd", workspace: "v3-1-replay", summary: "Lesson auto-activated.",
    result: "active", sourceSubsystem: "triage_memory_audit", detail: { supportCount: 3 } },
  { eventRef: "response-1", timestamp: "2026-11-03T02:10:42Z", actorType: "human", actorId: 1,
    actorName: "Alice", decisionSource: "analyst", eventCategory: "RESPONSE", eventType: "V2_RESPONSE_APPROVED",
    action: "Response approved", objectType: "recommendation", objectRef: "recommendation-1", alertRef: "alert-630b68",
    caseRef: "case-91dbe2", lessonRef: null, workspace: "v3-1-replay", summary: "Alice approved recommendation.",
    result: "Approved — Not Executed", sourceSubsystem: "response_decisions", detail: { reason: "Reviewed" } },
];

function setup() {
  return stubFetch(request => {
    const path = new URL(request.url).pathname;
    if (path === "/api/admin/overview") return jsonResponse(overview);
    if (path === "/api/admin/governance") return jsonResponse(governance);
    if (path === "/api/admin/users") return jsonResponse({ items: [
      { username: "admin", displayName: "LIOW CHEE KUANG", role: "system_admin", status: "active", lastLogin: "2026-11-03T00:00:00Z" },
      { username: "g.ang", displayName: "Glenn Ang", role: "security_analyst", status: "active", lastLogin: null },
      { username: "evaluator", displayName: "Evaluator", role: "evaluator", status: "active", lastLogin: null },
    ] });
    if (path === "/api/admin/audit/current") {
      const query = new URL(request.url).searchParams;
      const items = auditEvents.filter(event => (!query.get("category") || event.eventCategory === query.get("category")) &&
        (!query.get("decisionSource") || event.decisionSource === query.get("decisionSource")) &&
        (!query.get("objectType") || event.objectType === query.get("objectType")) &&
        (!query.get("search") || [event.alertRef, event.caseRef, event.lessonRef].some(ref => ref?.includes(query.get("search")!))) &&
        (!query.get("actor") || event.actorName?.includes(query.get("actor")!)));
      return jsonResponse({ items, total: items.length, limit: 25, offset: 0, activeWorkspace: "v3-1-replay" });
    }
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
    expect(screen.getByText("Database availability")).toBeVisible();
    expect(screen.getByText("Workspace availability")).toBeVisible();
    expect(screen.getAllByText("Available").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("Workspace readiness")).toBeNull();
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
    expect(screen.getByRole("cell", { name: "LIOW CHEE KUANG" })).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "Not available" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "System Administrator" })).toBeVisible();
    expect(screen.getByText(/Tier 2 \/ Senior Analyst investigation/)).toBeVisible();
    expect(screen.getByText(/Final V3.1 Evaluation, and Current HITL Audit/)).toBeVisible();
    expect(screen.queryByText("Evaluator")).toBeNull();
    expect(screen.queryByText(/password reset|permission matrix/i)).toBeNull();
  });

  it("separates current audit, frozen evaluation, and historical feedback", async () => {
    setup();
    renderApp("/admin/evaluation", { session: admin });
    expect(await screen.findByRole("heading", { level: 1, name: "Evaluation & Audit" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Final V3.1 Evaluation" })).toHaveAttribute("href", "/admin/evaluation/final-v3-1");
    expect(screen.getByRole("link", { name: "Open Current HITL Audit" })).toHaveAttribute("href", "/admin/evaluation/audit");
    expect(screen.getByRole("link", { name: "Open Historical Audit" })).toHaveAttribute("href", "/admin/audit");
    expect(screen.getByText(/separate from this evaluation/)).toBeVisible();
  });

  it("renders one current timeline with attribution, references, filters and non-execution", async () => {
    const seen = setup();
    renderApp("/admin/evaluation/audit", { session: admin });
    expect(await screen.findByRole("heading", { level: 1, name: "Current HITL Audit" })).toBeVisible();
    expect(screen.getAllByTestId("audit-event")).toHaveLength(3);
    expect(within(screen.getAllByTestId("audit-event")[1]!).getAllByText("System Policy")[0]).toBeVisible();
    expect(screen.getAllByText("Alice")).toHaveLength(2);
    expect(screen.getByText("Approved — Not Executed")).toBeVisible();
    fireEvent.click(screen.getAllByText("Event details")[1]!);
    expect(screen.getAllByText("lesson-31a9cd").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByRole("combobox", { name: "Category" }), { target: { value: "MEMORY" } });
    await waitFor(() => expect(screen.getAllByTestId("audit-event")).toHaveLength(1));
    expect(screen.getByText("Lesson auto-activated")).toBeVisible();
    expect(seen.some(request => new URL(request.url).searchParams.get("category") === "MEMORY")).toBe(true);
    fireEvent.change(screen.getByRole("combobox", { name: "Category" }), { target: { value: "" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Decision source" }), { target: { value: "system_policy" } });
    await waitFor(() => expect(screen.getAllByTestId("audit-event")).toHaveLength(1));
    fireEvent.change(screen.getByRole("combobox", { name: "Decision source" }), { target: { value: "" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Reference search" }), { target: { value: "case-91dbe2" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply text filters" }));
    await waitFor(() => expect(screen.getAllByTestId("audit-event")).toHaveLength(1));
    expect(screen.getByText("Approved — Not Executed")).toBeVisible();
  });

  it("keeps Current HITL Audit unavailable to Analyst and Evaluator routes", async () => {
    setup();
    const mounted = renderApp("/admin/evaluation/audit", { session: analyst });
    await waitFor(() => expect(mounted.router.state.location.pathname).not.toBe("/admin/evaluation/audit"));
    mounted.unmount();
    const other = renderApp("/admin/evaluation/audit", { session: evaluator });
    await waitFor(() => expect(other.router.state.location.pathname).not.toBe("/admin/evaluation/audit"));
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
