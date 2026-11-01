import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { OperationalEvidence } from "../../features/alert/OperationalEvidence";
import { jsonResponse, renderApp, stubFetch } from "../../test/renderApp";

const session = { username: "g.ang", displayName: "Analyst", role: "security_analyst" as const, token: "test" };
const ref = "fe130e6f-af86-4fc6-89f2-bc76b6cad68b";
const other = "fe130e6f-af86-4fc6-89f2-bc76b6cad68c";
const view = { operationalAlertRef: ref, title: "SYNTHETIC Suricata detection", detectorSource: "suricata", detectorName: "Suricata",
  stateVersion: "a".repeat(64), reviewReasons: ["Human review required"], latestDecision: null, caseRef: null, allowedActions: ["manual_escalate"],
  state: { operationalPriority: 85, priorityBand: "P1", reviewRequired: true, handlingRoute: "tier1_review", workflowStage: "triage", tier2Recommended: false, tier2RecommendationReasons: [] } };
const empty = { items: [], page: { total: 0, offset: 0, limit: 50, returned: 0 } };
const review = { disposition: "must_review", policyEvaluation: { contextProvenance: { fields: [{ status: "trusted" }] } } };
function evidence(source = "suricata") {
  return { detectorEvidence: { detectorSource: source, detectorName: source === "suricata" ? "Suricata" : "XGBoost", detectorVersion: "synthetic-v1",
    detectionTitle: "Synthetic detector evidence", detectionCategory: "Test scan", sourceIp: "192.0.2.1", destinationIp: "192.0.2.2", protocol: "TCP",
    occurredAt: "2026-10-31T00:00:00Z", detectorSeverity: 2, confidence: source === "suricata" ? null : 0.91, provenance: {},
    structuredEvidence: source === "suricata" ? { signatureId: 123, action: "allowed" } : { mlPredictedClass: "PortScan", signatureRules: [{ name: "Historical scan rule" }],
      treeShap: { topSupportingFeatures: [{ featureName: "Flow Duration", featureValue: 10, shapContribution: 0.42 }] } } } } as unknown as Schemas["OperationalAlertV2"];
}
function reads(request: Request) {
  const url = new URL(request.url);
  if (url.pathname === "/api/v2/alerts") return jsonResponse({ ...empty, items: [view, { ...view, operationalAlertRef: other, title: "Second alert" }], page: { ...empty.page, total: 51 } });
  if (url.pathname.endsWith("/triage-state")) return jsonResponse({ ...view, operationalAlertRef: url.pathname.includes(other) ? other : ref });
  if (url.pathname.endsWith("/evidence")) return jsonResponse(evidence());
  if (url.pathname.endsWith("/selective-review")) return jsonResponse(review);
  if (url.pathname.endsWith("/matches")) return jsonResponse(empty);
  return jsonResponse({ error: { code: "UNEXPECTED", message: url.pathname } }, 500);
}

describe("unified operational workstation", () => {
  it("loads a deep-linked alert outside the current page without replacing server order", async () => {
    stubFetch(request => new URL(request.url).pathname === "/api/v2/alerts" ? jsonResponse(empty) : reads(request));
    renderApp("/analyst/operations?alertRef=" + ref, { session });
    expect(await screen.findByRole("heading", { name: view.title })).toBeVisible();
    expect(screen.getByRole("list", { name: "Operational alerts" })).toBeEmptyDOMElement();
    await userEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    expect(await screen.findByRole("heading", { name: "Suricata Rule Evidence" })).toBeVisible();
  });

  it("handles an empty queue and exposes a retry on queue failure", async () => {
    stubFetch(() => jsonResponse(empty));
    const mounted = renderApp("/analyst/operations", { session });
    expect(await screen.findByText("No operational alerts match this view.")).toBeVisible();
    mounted.unmount();
    stubFetch(() => jsonResponse({ error: { code: "OFFLINE", message: "Queue unavailable" } }, 503));
    renderApp("/analyst/operations", { session });
    expect(await screen.findByRole("alert")).toHaveTextContent("Queue unavailable");
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });

  it.each(["/analyst/operations", "/analyst/v2-triage"])("uses one operational workspace at %s, source APIs and tabbed evidence", async route => {
    const requests = stubFetch(reads);
    const { router } = renderApp(route + "?alertRef=" + ref, { session });
    expect(await screen.findByRole("heading", { name: "Analyst Workstation" })).toBeVisible();
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    await waitFor(() => expect(within(queue).getAllByRole("button")).toHaveLength(2));
    expect(within(queue).getAllByRole("button")[0]).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("Trusted fields: 1 / 1")).toBeVisible();
    expect(screen.getByRole("complementary", { name: "Context and assistance" })).toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    expect(await screen.findByRole("heading", { name: "Suricata Rule Evidence" })).toBeVisible();
    expect(screen.queryByText(/TreeSHAP|Historical Signature Evidence|Model Evidence/)).toBeNull();
    await userEvent.keyboard("j");
    expect(router.state.location.search).toContain(other);
    await userEvent.click(screen.getByRole("button", { name: "Next alerts" }));
    await waitFor(() => expect(requests.some(req => req.url.includes("offset=50"))).toBe(true));
    expect(requests.every(req => req.method === "GET" && !new URL(req.url).pathname.startsWith("/api/alerts"))).toBe(true);
  });

  it("preserves decision drafts across tabs and performs a single compound escalation without leaving", async () => {
    const caseRef = "00000000-0000-4000-8000-000000000123";
    const bodies: unknown[] = [];
    const requests = stubFetch(async req => {
      if (req.method === "POST") { bodies.push(await req.json()); return jsonResponse({ view: { ...view, caseRef, allowedActions: [], stateVersion: "b".repeat(64), state: { ...view.state, handlingRoute: "tier2_case", workflowStage: "investigation" } }, case: { caseRef } }); }
      return reads(req);
    });
    const { router } = renderApp("/analyst/operations?alertRef=" + ref, { session });
    await userEvent.type(await screen.findByLabelText("Decision reason"), "SYNTHETIC reviewed evidence");
    await userEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));
    expect(screen.getByLabelText("Decision reason")).toHaveValue("SYNTHETIC reviewed evidence");
    await userEvent.click(screen.getByRole("button", { name: "Escalate to Tier 2" }));
    expect(await screen.findByRole("heading", { name: "Escalated to Tier 2" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Tier 2 Case" })).toHaveAttribute("href", "/analyst/tier2-cases/" + caseRef);
    expect(screen.queryByText(/Tier 2 Candidate/)).toBeNull();
    expect(screen.queryByLabelText("Case title")).toBeNull();
    expect(bodies).toEqual([expect.objectContaining({ action: "manual_escalate", reason: "SYNTHETIC reviewed evidence", expectedStateVersion: view.stateVersion })]);
    expect(requests.filter(req => req.method === "POST").map(req => new URL(req.url).pathname)).toEqual([`/api/v2/alerts/${ref}/tier2/escalate-case`]);
    await userEvent.click(screen.getByRole("button", { name: "Continue Reviewing" }));
    expect(router.state.location.pathname).toBe("/analyst/operations");
    await userEvent.click(within(screen.getByRole("list", { name: "Operational alerts" })).getAllByRole("button")[1]!);
    expect(router.state.location.search).toContain(other);
  });
});

describe("canonical detector presentation", () => {
  it("shows supplied XGBoost model and attributions", () => {
    render(<OperationalEvidence alert={evidence("xgboost")} />);
    expect(screen.getByRole("heading", { name: "Model Evidence" })).toBeVisible();
    expect(screen.getByRole("region", { name: "TreeSHAP evidence" })).toBeVisible();
    expect(screen.getByText("Flow Duration")).toBeVisible();
    expect(screen.getByText("0.42")).toBeVisible();
    expect(screen.queryByText("Historical Signature Evidence")).toBeNull();
  });
  it("labels canonical legacy evidence as historical without feedback controls", () => {
    render(<OperationalEvidence alert={evidence("current_flow")} />);
    expect(screen.getByText("Legacy Flow Detector")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Historical Signature Evidence" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Historical XGBoost Evidence" })).toBeVisible();
    expect(screen.queryByText("Escalation Recommended")).toBeNull();
  });
});
