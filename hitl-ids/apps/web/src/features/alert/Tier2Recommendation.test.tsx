import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import type { Schemas } from "../../api/client";
import { jsonResponse, stubFetch } from "../../test/renderApp";
import { Tier2RecommendationPanel } from "./Tier2Recommendation";

type View = Schemas["RoutingView"];
const REF = "107a0cf6-a827-4593-98c0-d340d154933d";
const REASON = "E3: score 100 and Botnet has attack severity 9. A Tier 1 analyst confirms before escalation. (5 of 5 members; first shown.)";

function view(overrides: Partial<View> = {}): View {
  return {
    work: null, effectiveReview: null, detectionSummary: null, classification: null, caseRef: null, groupMemberCount: null,
    systemRouting: { routeClass: "ROUTINE_REVIEW", route: "tier1_review", decisionSource: "system_policy", policyVersion: "flow-routing-v1", reasons: ["Normal review"] },
    operationalAlertRef: REF, title: "XGBoost: Botnet", detectorName: "Legacy Flow Detector", detectorSource: "legacy_flow",
    stateVersion: "a".repeat(64), reviewReasons: ["Review"], latestDecision: null,
    allowedActions: ["approve_tier2", "reject_tier2", "manual_escalate"], tier2RecommendationOpen: true,
    state: { operationalAlertId: 1, operationalPriority: 100, priorityBand: "P1", priorityBandScheme: "p1_p4",
      handlingRoute: "tier1_review", workflowStage: "triage", reviewRequired: true, reviewReason: "Review",
      tier2Recommended: true, tier2RecommendationReasons: [REASON], decisionSource: "system_policy",
      triagePolicyVersion: "operational-triage-v1", updatedAt: "2026-11-08T00:00:00Z" },
    ...overrides,
  };
}

function show(v: View, onChanged = vi.fn()) {
  render(<MemoryRouter><Tier2RecommendationPanel view={v} onChanged={onChanged} /></MemoryRouter>);
  return onChanged;
}

const panel = () => screen.getByRole("region", { name: "Why Tier 2 is recommended" });

afterEach(() => vi.unstubAllGlobals());

describe("Why Tier 2 panel (C3)", () => {
  it("shows the reasons, the reason box and the 3 buttons while the recommendation is open", () => {
    stubFetch(() => { throw new Error("no request expected"); });
    show(view());
    expect(panel()).toHaveTextContent(REASON);
    expect(within(panel()).getByLabelText(/Reason/)).toBeVisible();
    expect(within(panel()).getByRole("button", { name: "Escalate to Tier 2" })).toBeDisabled();   // no reason yet
    expect(within(panel()).getByRole("button", { name: "Keep in Tier 1" })).toBeDisabled();
    expect(within(panel()).getByRole("button", { name: /Record verdict/ })).toBeEnabled();
  });

  it("is not shown when no recommendation is open", () => {
    stubFetch(() => { throw new Error("no request expected"); });
    show(view({ tier2RecommendationOpen: false, allowedActions: ["manual_escalate"] }));
    expect(screen.queryByRole("region", { name: "Why Tier 2 is recommended" })).toBeNull();
  });

  it("disables both decisions when the server offers neither (not the owner)", async () => {
    stubFetch(() => { throw new Error("no request expected"); });
    show(view({ allowedActions: [] }));
    await userEvent.type(within(panel()).getByLabelText(/Reason/), "Time constraints");
    expect(within(panel()).getByRole("button", { name: "Escalate to Tier 2" })).toBeDisabled();
    expect(within(panel()).getByRole("button", { name: "Keep in Tier 1" })).toBeDisabled();
    expect(panel()).toHaveTextContent("Start review to decide.");
  });

  it("Keep in Tier 1 sends the reject with the reason and hands back the new view", async () => {
    const after = view({ tier2RecommendationOpen: false, allowedActions: ["manual_escalate"] });
    const bodies: unknown[] = [];
    const seen = stubFetch(async request => { bodies.push(await request.json()); return jsonResponse({ view: after, audit: { id: 3 }, replayed: false }); });
    const onChanged = show(view());
    await userEvent.type(within(panel()).getByLabelText(/Reason/), "  Time constraints  ");
    await userEvent.click(within(panel()).getByRole("button", { name: "Keep in Tier 1" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(after));
    expect(new URL(seen[0]!.url).pathname).toBe(`/api/v2/alerts/${REF}/tier2/reject`);
    expect(bodies[0]).toMatchObject({ reason: "Time constraints", expectedStateVersion: "a".repeat(64) });
    expect(seen).toHaveLength(1);
  });

  it("Escalate to Tier 2 uses the atomic escalate-case with approve_tier2 and passes on the case", async () => {
    const caseRef = "00000000-0000-4000-8000-000000000123";
    const after = view({ tier2RecommendationOpen: false, allowedActions: [], state: { ...view().state, handlingRoute: "tier2_case", workflowStage: "investigation" } });
    const bodies: unknown[] = [];
    const seen = stubFetch(async request => { bodies.push(await request.json()); return jsonResponse({ view: after, case: { caseRef }, audit: { id: 4 }, replayed: false }); });
    const onChanged = show(view());
    await userEvent.type(within(panel()).getByLabelText(/Reason/), "Same campaign as the 14 Feb group.");
    await userEvent.click(within(panel()).getByRole("button", { name: "Escalate to Tier 2" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith({ ...after, caseRef }));
    expect(new URL(seen[0]!.url).pathname).toBe(`/api/v2/alerts/${REF}/tier2/escalate-case`);
    expect(bodies[0]).toMatchObject({ action: "approve_tier2", reason: "Same campaign as the 14 Feb group." });
  });

  it("keeps the reason and the request id after a failure, so a retry is the same request", async () => {
    const bodies: { requestId: string }[] = [];
    let calls = 0;
    stubFetch(async request => {
      bodies.push(await request.json());
      calls += 1;
      return calls === 1 ? jsonResponse({ error: { code: "ROUTING_CONFLICT", message: "V2 state changed" } }, 409)
        : jsonResponse({ view: view({ tier2RecommendationOpen: false }), audit: { id: 5 }, replayed: true });
    });
    show(view());
    await userEvent.type(within(panel()).getByLabelText(/Reason/), "Time constraints");
    await userEvent.click(within(panel()).getByRole("button", { name: "Keep in Tier 1" }));
    expect(await within(panel()).findByRole("alert")).toHaveTextContent("V2 state changed");
    expect(within(panel()).getByLabelText(/Reason/)).toHaveValue("Time constraints");
    await userEvent.click(within(panel()).getByRole("button", { name: "Keep in Tier 1" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]!.requestId).toBe(bodies[0]!.requestId);
  });

  it("Record verdict moves to the existing verdict form and sends nothing", async () => {
    const seen = stubFetch(() => { throw new Error("no request expected"); });
    const target = document.createElement("select");
    target.id = "analyst-verdict-outcome";
    target.scrollIntoView = vi.fn();
    document.body.appendChild(target);
    show(view());
    await userEvent.click(within(panel()).getByRole("button", { name: /Record verdict/ }));
    expect(target.scrollIntoView).toHaveBeenCalled();
    expect(document.activeElement).toBe(target);
    expect(seen).toHaveLength(0);
    target.remove();
  });
});
