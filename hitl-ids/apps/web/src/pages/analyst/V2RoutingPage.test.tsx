import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import type { Schemas } from "../../api/client";
import { jsonResponse, stubFetch } from "../../test/renderApp";
import { RoutingDetail, V2RoutingPage } from "./V2RoutingPage";
import { SessionProvider } from "../../session/SessionContext";

const view: Schemas["RoutingView"] = {
  work: null,
  effectiveReview: null, detectionSummary: null,
  classification: null, systemRouting: {routeClass:"ROUTINE_REVIEW",route:"tier1_review",decisionSource:"system_policy",policyVersion:"system-routing-v1",reasons:["Normal review"]}, caseRef: null, operationalAlertRef: "fe130e6f-af86-4fc6-89f2-bc76b6cad68b", title: "External NIDS alert", detectorName: "Suricata", detectorSource: "suricata",
  stateVersion: "a".repeat(64), reviewReasons: ["Critical asset requires review"], latestDecision: null,
  allowedActions: ["approve_tier2", "reject_tier2", "manual_escalate"],
  state: { operationalAlertId: 1, operationalPriority: 85, priorityBand: "P1", priorityBandScheme: "p1_p4",
    handlingRoute: "tier1_review", workflowStage: "triage", reviewRequired: true, reviewReason: "Review required",
    tier2Recommended: true, tier2RecommendationReasons: ["Unresolved by Tier 1"], decisionSource: "system_policy",
    triagePolicyVersion: "operational-triage-v1", updatedAt: "2026-10-31T00:00:00Z" },
};

describe("V2 routing", () => {
  it.each(["manual_escalate"] as const)("%s creates a case in one request and stays on the alert", async action => {
    const bodies: unknown[] = [];
    const caseRef = "00000000-0000-4000-8000-000000000123";
    const completed = { ...view, caseRef, allowedActions: [], state: { ...view.state,
      handlingRoute: "tier2_case", workflowStage: "investigation" } };
    const seen = stubFetch(async request => {
      bodies.push(await request.json());
      return jsonResponse({ view: completed, case: { caseRef }, audit: { id: 9 } });
    });
    render(<MemoryRouter><RoutingDetail initial={view} refresh={vi.fn()} /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText("Decision reason"), "Needs deeper investigation");
    await userEvent.click(screen.getByRole("button", { name: "Escalate to Tier 2" }));
    expect(await screen.findByRole("heading", { name: "Escalated to Tier 2" })).toBeVisible();
    expect(screen.getByText("Tier 2 Case created successfully.")).toBeVisible();
    expect(screen.getByText("Case: " + caseRef)).toBeVisible();
    expect(screen.queryByText(/Tier 2 Candidate|assessment/i)).toBeNull();
    expect(screen.queryByLabelText("Case title")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Create Tier 2 Case$/ })).toBeNull();
    expect(screen.getByRole("link", { name: "Open Tier 2 Case" })).toHaveAttribute("href", "/analyst/tier2-cases/" + caseRef);
    expect(screen.getByRole("heading", { name: "External NIDS alert" })).toBeVisible();
    expect(seen).toHaveLength(1);
    expect(new URL(seen[0]!.url).pathname).toBe("/api/v2/alerts/" + view.operationalAlertRef + "/tier2/escalate-case");
    expect(bodies[0]).toMatchObject({ action, expectedStateVersion: view.stateVersion, reason: "Needs deeper investigation" });
    expect(bodies[0]).not.toHaveProperty("title");
    await userEvent.click(screen.getByRole("button", { name: "Continue Reviewing" }));
    expect(screen.queryByRole("status", { name: "Tier 2 escalation result" })).toBeNull();
    expect(screen.getByRole("heading", { name: "External NIDS alert" })).toBeVisible();
    expect(seen).toHaveLength(1);
  });

  it("shows the candidate reasons and states that context is read once, at routing (B5 scope)", () => {
    stubFetch(() => { throw new Error("No writes expected"); });
    render(<MemoryRouter><RoutingDetail initial={view} refresh={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("region", { name: "Tier 2 candidate reasons" })).toHaveTextContent("Unresolved by Tier 1");
    expect(screen.getByText(/Context is read once, when the alert is routed\. A fact recorded later does not change this recommendation\./)).toBeTruthy();
  });

  it("shows no candidate section when nothing recommends Tier 2", () => {
    stubFetch(() => { throw new Error("No writes expected"); });
    render(<MemoryRouter><RoutingDetail initial={{ ...view, state: { ...view.state, tier2Recommended: false,
      tier2RecommendationReasons: [] } }} refresh={vi.fn()} /></MemoryRouter>);
    expect(screen.queryByRole("region", { name: "Tier 2 candidate reasons" })).toBeNull();
  });

  it("keeps historical candidate state read-only without recovery or admission controls", () => {
    const seen = stubFetch(() => { throw new Error("No writes expected"); });
    render(<RoutingDetail initial={{...view, systemRouting:null, state:{...view.state, handlingRoute:"tier2_candidate",workflowStage:"assessment"}}} refresh={vi.fn()} />);
    expect(screen.queryByRole("button", {name:/Complete Earlier|Approve Tier 2|Create.*Case|Admit|Escalate/})).toBeNull();
    expect(screen.queryByLabelText("Decision reason")).toBeNull();
    expect(seen).toHaveLength(0);
  });
  it.each([
    ["approve_tier2", "Historical Tier 2 candidate approval"],
    ["reject_tier2", "Historical Tier 2 candidate rejection"],
  ] as const)("labels %s as historical compatibility", (action, label) => {
    render(<RoutingDetail initial={{ ...view, systemRouting: null, allowedActions: [], latestDecision: {
      action, decisionSource: "analyst", actorId: 1, reason: "Legacy record", createdAt: "2026-10-31T00:00:00Z",
      beforeState: { ...view.state, handlingRoute: "tier2_candidate" }, afterState: view.state,
    } as Schemas["RoutingView"]["latestDecision"] }} refresh={vi.fn()} />);
    expect(screen.getByText(new RegExp(label))).toBeVisible();
    expect(screen.getByText(/Historical routing record/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Approve Tier 2|Keep in Tier 1/ })).toBeNull();
  });
  it("shows system routing and requires a reason", async () => {
    render(<RoutingDetail initial={view} refresh={vi.fn()} />);
    expect(screen.getByRole("heading", {name:"System Routing"})).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Escalate to Tier 2" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Decision reason"), "Needs deeper investigation");
    expect(screen.getByRole("button", { name: "Escalate to Tier 2" })).toBeEnabled();
  });

  it("evaluator has no mutation controls", () => {
    render(<RoutingDetail initial={{ ...view, allowedActions: [] }} refresh={vi.fn()} />);
    expect(screen.queryByLabelText("Decision reason")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Escalate to Tier 2" })).not.toBeInTheDocument();
  });

  it("retains idempotency identity on transport failure and refreshes explicitly", async () => {
    const bodies: unknown[] = [];
    stubFetch(async request => { bodies.push(await request.json()); throw new Error("Connection lost"); });
    const refresh = vi.fn();
    render(<RoutingDetail initial={view} refresh={refresh} />);
    await userEvent.type(screen.getByLabelText("Decision reason"), "Reviewed");
    await userEvent.click(screen.getByRole("button", { name: "Escalate to Tier 2" }));
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Escalate to Tier 2" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual(bodies[0]);
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh state" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Refresh state" }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("shows a stale conflict without optimistically changing route", async () => {
    stubFetch(() => jsonResponse({ error: { code: "ROUTING_CONFLICT", message: "State changed; refresh" } }, 409));
    render(<RoutingDetail initial={view} refresh={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Decision reason"), "Reviewed");
    await userEvent.click(screen.getByRole("button", { name: "Escalate to Tier 2" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("State changed");
    expect(screen.getByRole("heading", {name:"System Routing"})).toBeInTheDocument();
  });

  it("renders empty and API failure states", async () => {
    stubFetch(() => jsonResponse({ items: [], page: { total: 0, limit: 50, offset: 0, returned: 0 } }));
    const result = render(<SessionProvider><MemoryRouter><V2RoutingPage /></MemoryRouter></SessionProvider>);
    expect(await screen.findByText("No operational alerts.")).toBeInTheDocument();
    result.unmount();
    stubFetch(() => jsonResponse({ error: { code: "OFFLINE", message: "Database unavailable" } }, 503));
    render(<SessionProvider><MemoryRouter><V2RoutingPage /></MemoryRouter></SessionProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable");
  });

  it("does not invent priority before policy application", () => {
    render(<RoutingDetail initial={{ ...view, systemRouting:null, state: { ...view.state, operationalPriority: null, priorityBand: null } }} refresh={vi.fn()} />);
    expect(screen.getAllByText("Not assigned")).toHaveLength(2);
  });

  it("loads a linked alert directly even outside the first queue page", async () => {
    const seen = stubFetch(request => request.url.includes("/selective-review") ? jsonResponse({error:{code:"OFFLINE",message:"Review service unavailable"}},503) : jsonResponse(request.url.includes("/matches") ? {items:[],page:{total:0}} : view));
    render(<SessionProvider><MemoryRouter initialEntries={["/analyst/v2-triage?alertRef=" + view.operationalAlertRef]}>
      <V2RoutingPage />
    </MemoryRouter></SessionProvider>);
    expect(await screen.findByText("External NIDS alert")).toBeInTheDocument();
    expect(seen[0]?.url).toContain("/" + view.operationalAlertRef + "/triage-state");
  });
});
