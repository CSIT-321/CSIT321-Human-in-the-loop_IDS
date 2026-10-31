import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import type { Schemas } from "../../api/client";
import { jsonResponse, stubFetch } from "../../test/renderApp";
import { RoutingDetail, V2RoutingPage } from "./V2RoutingPage";
import { SessionProvider } from "../../session/SessionContext";

const view: Schemas["RoutingView"] = {
  operationalAlertRef: "fe130e6f-af86-4fc6-89f2-bc76b6cad68b", title: "External NIDS alert", detectorName: "Suricata",
  stateVersion: "a".repeat(64), reviewReasons: ["Critical asset requires review"], latestDecision: null,
  allowedActions: ["approve_tier2", "reject_tier2", "manual_escalate"],
  state: { operationalAlertId: 1, operationalPriority: 85, priorityBand: "P1", priorityBandScheme: "p1_p4",
    handlingRoute: "tier1_review", workflowStage: "triage", reviewRequired: true, reviewReason: "Review required",
    tier2Recommended: true, tier2RecommendationReasons: ["Unresolved by Tier 1"], decisionSource: "system_policy",
    triagePolicyVersion: "operational-triage-v1", updatedAt: "2026-10-31T00:00:00Z" },
};

describe("V2 routing", () => {
  it("distinguishes recommendation from route and requires a reason", async () => {
    render(<RoutingDetail initial={view} refresh={vi.fn()} />);
    expect(screen.getByText("tier1 review")).toBeInTheDocument();
    expect(screen.getByText("YES")).toBeInTheDocument();
    expect(screen.getByText("Unresolved by Tier 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve Tier 2" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Decision reason"), "Needs deeper investigation");
    expect(screen.getByRole("button", { name: "Approve Tier 2" })).toBeEnabled();
  });

  it("evaluator has no mutation controls", () => {
    render(<RoutingDetail initial={{ ...view, allowedActions: [] }} refresh={vi.fn()} />);
    expect(screen.queryByLabelText("Decision reason")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve Tier 2" })).not.toBeInTheDocument();
  });

  it("retains idempotency identity on transport failure and refreshes explicitly", async () => {
    const bodies: unknown[] = [];
    stubFetch(async request => { bodies.push(await request.json()); throw new Error("Connection lost"); });
    const refresh = vi.fn();
    render(<RoutingDetail initial={view} refresh={refresh} />);
    await userEvent.type(screen.getByLabelText("Decision reason"), "Reviewed");
    await userEvent.click(screen.getByRole("button", { name: "Approve Tier 2" }));
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Approve Tier 2" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Approve Tier 2" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("State changed");
    expect(screen.getByText("tier1 review")).toBeInTheDocument();
  });

  it("renders empty and API failure states", async () => {
    stubFetch(() => jsonResponse({ items: [], page: { total: 0, limit: 50, offset: 0, returned: 0 } }));
    const result = render(<MemoryRouter><V2RoutingPage /></MemoryRouter>);
    expect(await screen.findByText("No materialized V2 alerts.")).toBeInTheDocument();
    result.unmount();
    stubFetch(() => jsonResponse({ error: { code: "OFFLINE", message: "Database unavailable" } }, 503));
    render(<MemoryRouter><V2RoutingPage /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable");
  });

  it("does not invent priority before policy application", () => {
    render(<RoutingDetail initial={{ ...view, state: { ...view.state, operationalPriority: null, priorityBand: null } }} refresh={vi.fn()} />);
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
