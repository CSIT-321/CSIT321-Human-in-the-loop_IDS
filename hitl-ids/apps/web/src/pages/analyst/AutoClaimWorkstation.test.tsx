import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Schemas } from "../../api/client";
import { jsonResponse, renderApp, stubFetch } from "../../test/renderApp";

const analyst = { username: "g.ang", displayName: "Glenn Ang", role: "security_analyst" as const, token: "analyst-token" };
const first = "fe130e6f-af86-4fc6-89f2-bc76b6cad68b";
const second = "fe130e6f-af86-4fc6-89f2-bc76b6cad68c";
const third = "fe130e6f-af86-4fc6-89f2-bc76b6cad68d";
const work: Schemas["WorkView"] = { status: "available", revision: 0, canClaim: true, canMutate: false, isOwner: false,
  explanation: "Available for Review. Selecting this alert starts your review.", claimedAt: null, finishedAt: null,
  finishedByActorId: null, finishedByName: null, ownerActorId: null, ownerName: null, roundRef: null,
  verdictRef: null, verdictOutcome: null };
const base = { systemRouting: { routeClass: "ROUTINE_REVIEW", route: "tier1_review", decisionSource: "system_policy",
  policyVersion: "system-routing-v1", reasons: ["Normal review"] }, operationalAlertRef: first,
  title: "First available alert", detectorSource: "suricata", detectorName: "Suricata",
  stateVersion: "a".repeat(64), reviewReasons: ["Human review required"], latestDecision: null,
  caseRef: null, allowedActions: [], work,
  state: { decisionSource: "system_policy", operationalPriority: 85, priorityBand: "P1", reviewRequired: true,
    handlingRoute: "tier1_review", workflowStage: "triage", tier2Recommended: false,
    tier2RecommendationReasons: [] } };
const summary = { totalAlerts: 2, criticalAlerts: 0, tier1Review: 2, tier2Cases: 0, expertReview: 0,
  reviewRequired: 2, noImmediateReview: 0, openTier2Cases: 0, activeAlerts: 2,
  completedWork: 0, escalatedWork: 0 };

function workspaceResponse(body: unknown, status = 200, workspace = "operational") {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json",
    "X-Operational-Workspace": workspace } });
}

type Scenario = { claimed?: string; conflict?: boolean; uncertain?: boolean; workWorkspace?: string;
  overrideRoute?: string; noImmediate?: boolean;
  overrideWork?: Partial<typeof work>; posts: { path: string; body: unknown; workspace: string | null }[];
  stream?: ReadableStream<Uint8Array>; arrived?: boolean; holdNextQueue?: boolean;
  releaseQueue?: () => void; streamFactory?: () => ReadableStream<Uint8Array> };

function setup(scenario: Scenario) {
  return stubFetch(async request => {
    const path = new URL(request.url).pathname;
    if (path === "/api/v2/alerts/stream" && (scenario.stream || scenario.streamFactory)) return new Response(scenario.streamFactory?.() ?? scenario.stream, {
      headers: { "Content-Type": "text/event-stream", "X-Operational-Workspace": "operational" },
    });
    if (path === "/api/workspace/current") return jsonResponse({ id: "operational", name: "Operational" });
    if (path === "/api/v2/alerts/summary") return jsonResponse(scenario.arrived
      ? { ...summary, totalAlerts: 3, activeAlerts: 3, tier1Review: 3 } : summary);
    const currentWork = (ref: string) => scenario.claimed === ref
      ? { ...work, status: "in_review", revision: 1, canClaim: false, canMutate: true,
        isOwner: true, ownerName: "Glenn Ang", ownerActorId: 1, explanation: "In Review — You" }
      : { ...work, ...scenario.overrideWork };
    const record = (ref: string) => ({ ...base, operationalAlertRef: ref,
      title: ref === first ? "First available alert" : ref === second ? "Second available alert" : "Newly arrived alert", work: currentWork(ref),
      state: { ...base.state, handlingRoute: scenario.overrideRoute ?? base.state.handlingRoute,
        priorityBand: ref === third ? "P3" : base.state.priorityBand },
      effectiveReview: scenario.noImmediate ? { disposition: "no_immediate_review", reviewRequired: false } : undefined,
      allowedActions: scenario.claimed === ref ? ["manual_escalate"] : [] });
    if (path === "/api/v2/alerts" && request.method === "GET") {
      if (scenario.arrived && scenario.holdNextQueue) {
        scenario.holdNextQueue = false;
        await new Promise<void>(resolve => { scenario.releaseQueue = resolve; });
      }
      const critical = new URL(request.url).searchParams.get("priorityBand") === "P1";
      const items = scenario.arrived && !critical ? [record(third), record(first), record(second)] : [record(first), record(second)];
      return workspaceResponse({ items, page: { total: items.length, limit: 50, offset: 0, returned: items.length } });
    }
    if (path.endsWith("/triage-state")) return jsonResponse(record(path.includes(second) ? second : first));
    if (path.endsWith("/verdict") && request.method === "GET") return jsonResponse({
      latest: null, canRecord: Boolean(scenario.overrideWork?.isOwner), revision: 0,
      sourceStateVersion: base.stateVersion,
    });
    if (path.endsWith("/work") && request.method === "GET")
      return workspaceResponse(currentWork(path.includes(second) ? second : first), 200,
        scenario.workWorkspace ?? "operational");
    if (path.endsWith("/work/claim") && request.method === "POST") {
      const body = await request.json();
      scenario.posts.push({ path, body, workspace: request.headers.get("X-Operational-Workspace") });
      if (scenario.conflict) return jsonResponse({ error: { code: "CLAIM_CONTENTION", message: "Contention" } }, 409);
      if (scenario.uncertain) { scenario.uncertain = false;
        return jsonResponse({ error: { code: "UNAVAILABLE", message: "Connection uncertain" } }, 503); }
      scenario.claimed = path.includes(second) ? second : first;
      return jsonResponse({ outcome: "claimed", work: currentWork(scenario.claimed) });
    }
    return jsonResponse({ error: { code: "NOT_FOUND", message: path } }, 404);
  });
}

const claims = (seen: Request[]) => seen.filter(request => request.method === "POST" &&
  new URL(request.url).pathname.endsWith("/work/claim"));

describe("intentional queue selection auto-claim", () => {
  it("silently reconciles a persisted arrival while preserving the selected alert, tab, draft and ownership", async () => {
    let streamController!: ReadableStreamDefaultController<Uint8Array>;
    const cancelled = vi.fn();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) { streamController = controller; }, cancel: cancelled,
    });
    const scenario: Scenario = { posts: [], stream, overrideWork: { status: "in_review",
      canClaim: false, canMutate: true, isOwner: true, ownerName: "Glenn Ang" } };
    const seen = setup(scenario);
    const mounted = renderApp("/analyst/operations", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    expect(await within(queue).findAllByRole("button")).toHaveLength(2);
    await waitFor(() => expect(screen.getByText("Arrival updates connected")).toBeVisible());
    await userEvent.click(screen.getByRole("tab", { name: "Analyst Verdict" }));
    await userEvent.type(await screen.findByLabelText("Verdict reason"), "Keep this draft");
    expect(screen.getByRole("tab", { name: "Analyst Verdict" })).toHaveAttribute("aria-selected", "true");
    scenario.arrived = true;
    scenario.holdNextQueue = true;
    const beforeReads = seen.filter(request => new URL(request.url).pathname === "/api/v2/alerts").length;
    const payload = { eventId: "operational:3", workspaceId: "operational", operationalAlertRef: third, timestamp: "now" };
    act(() => streamController.enqueue(new TextEncoder().encode(`id: operational:3\nevent: alert_arrived\ndata: ${JSON.stringify(payload)}\n\n`)));
    await waitFor(() => expect(seen.filter(request => new URL(request.url).pathname === "/api/v2/alerts").length).toBeGreaterThan(beforeReads));
    expect(within(queue).getAllByRole("button")).toHaveLength(2);
    expect(screen.queryByText("Loading operational alerts…")).toBeNull();
    expect(screen.getByText("First available alert", { selector: "h2" })).toBeVisible();
    expect(screen.getByLabelText("Verdict reason")).toHaveValue("Keep this draft");
    act(() => scenario.releaseQueue?.());
    expect(await within(queue).findByRole("button", { name: /Newly arrived alert/ })).toBeVisible();
    expect(screen.getByText("First available alert", { selector: "h2" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Analyst Verdict" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Verdict reason")).toHaveValue("Keep this draft");
    expect(claims(seen)).toHaveLength(0);
    await userEvent.click(within(queue).getByRole("button", { name: /Newly arrived alert/ }));
    // Already owned rows stay Viewer/Owner projections; selection does not issue another claim.
    expect(claims(seen)).toHaveLength(0);
    mounted.unmount();
    await waitFor(() => expect(cancelled).toHaveBeenCalled());
  });

  it("does not claim an arriving Available alert until the analyst clicks it", async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const scenario: Scenario = { posts: [], stream: new ReadableStream({ start(value) { controller = value; } }) };
    const seen = setup(scenario);
    renderApp("/analyst/operations", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    await waitFor(() => expect(screen.getByText("Arrival updates connected")).toBeVisible());
    scenario.arrived = true;
    act(() => controller.enqueue(new TextEncoder().encode(`event: alert_arrived\ndata: ${JSON.stringify({
      eventId: "operational:3", workspaceId: "operational", operationalAlertRef: third, timestamp: "now",
    })}\n\n`)));
    await within(queue).findByRole("button", { name: /Newly arrived alert/ });
    expect(claims(seen)).toHaveLength(0);
    await userEvent.click(within(queue).getByRole("button", { name: /Newly arrived alert/ }));
    await waitFor(() => expect(claims(seen)).toHaveLength(1));
  });

  it("keeps a Critical filter while a routine arrival updates the KPI count", async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const scenario: Scenario = { posts: [], stream: new ReadableStream({ start(value) { controller = value; } }) };
    const seen = setup(scenario);
    renderApp("/analyst/operations?view=critical", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    await waitFor(() => expect(screen.getByText("Arrival updates connected")).toBeVisible());
    expect(screen.getByRole("tab", { name: /^Critical / })).toHaveAttribute("aria-selected", "true");
    scenario.arrived = true;
    act(() => controller.enqueue(new TextEncoder().encode(`event: alert_arrived\ndata: ${JSON.stringify({
      eventId: "operational:3", workspaceId: "operational", operationalAlertRef: third, timestamp: "now",
    })}\n\n`)));
    await waitFor(() => expect(screen.getByRole("button", { name: /^Total Alerts 3$/ })).toBeVisible());
    expect(within(queue).getAllByRole("button")).toHaveLength(2);
    expect(within(queue).queryByRole("button", { name: /Newly arrived alert/ })).toBeNull();
    expect(screen.getByRole("tab", { name: /^Critical / })).toHaveAttribute("aria-selected", "true");
    expect(claims(seen)).toHaveLength(0);
  });

  it("reconnects a dropped stream and reconciles again without duplicate queue rows", async () => {
    const streams: ReadableStream<Uint8Array>[] = [];
    const scenario: Scenario = { posts: [], streamFactory: () => {
      const stream = new ReadableStream<Uint8Array>({
        start(controller) { if (streams.length === 0) controller.close(); },
      });
      streams.push(stream);
      return stream;
    } };
    const seen = setup(scenario);
    renderApp("/analyst/operations", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    await waitFor(() => expect(seen.filter(request => new URL(request.url).pathname === "/api/v2/alerts/stream").length).toBeGreaterThanOrEqual(2), { timeout: 4000 });
    scenario.arrived = true;
    await waitFor(() => expect(screen.getByRole("button", { name: /^Total Alerts 3$/ })).toBeVisible());
    expect(within(queue).getAllByRole("button", { name: /Newly arrived alert/ })).toHaveLength(1);
    expect(claims(seen)).toHaveLength(0);
  });

  it("keeps default display and refresh read-only, then claims the explicitly selected Available row once", async () => {
    const scenario: Scenario = { posts: [] };
    const timers = vi.spyOn(window, "setInterval");
    const seen = setup(scenario);
    renderApp("/analyst/operations", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    expect(await within(queue).findAllByRole("button")).toHaveLength(2);
    expect(screen.getByRole("region", { name: "Human work status" })).toHaveTextContent("Available for Review");
    expect(claims(seen)).toHaveLength(0);
    const readsBefore = seen.filter(request => new URL(request.url).pathname === "/api/v2/alerts").length;
    act(() => { for (const [callback, delay] of timers.mock.calls) if (delay === 15000 && typeof callback === "function") callback(); });
    await waitFor(() => expect(seen.filter(request => new URL(request.url).pathname === "/api/v2/alerts").length).toBeGreaterThan(readsBefore));
    expect(claims(seen)).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Refresh operational queue" }));
    await waitFor(() => expect(within(queue).getAllByRole("button")).toHaveLength(2));
    expect(claims(seen)).toHaveLength(0);
    await userEvent.click(within(queue).getByRole("button", { name: /Second available alert/ }));
    await waitFor(() => expect(scenario.posts).toHaveLength(1));
    expect(scenario.posts[0]).toMatchObject({ body: { requestId: expect.any(String), expectedRevision: 0 },
      workspace: "operational" });
    expect(await screen.findByText("Glenn Ang (You)")).toBeVisible();
    expect(screen.getByText("Owner", { exact: true })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Start Review" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Refresh operational queue" }));
    expect(claims(seen)).toHaveLength(1);
  });

  it("keeps direct alert URLs and queue filters read-only", async () => {
    const scenario: Scenario = { posts: [] };
    const seen = setup(scenario);
    renderApp(`/analyst/operations?alertRef=${second}`, { session: analyst });
    expect(await screen.findByText("Second available alert", { selector: "h2" })).toBeVisible();
    expect(claims(seen)).toHaveLength(0);
    await userEvent.click(screen.getByRole("tab", { name: /^Tier 1 / }));
    expect(claims(seen)).toHaveLength(0);
  });

  it("clears a simultaneous-claim conflict and never retries without another selection", async () => {
    const scenario: Scenario = { posts: [], conflict: true };
    const seen = setup(scenario);
    renderApp("/analyst/operations", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    await userEvent.click(await within(queue).findByRole("button", { name: /Second available alert/ }));
    expect(await screen.findByRole("alert", { name: "" })).toHaveTextContent("Claim Conflict");
    expect(screen.getByRole("region", { name: "Operational alert workspace" })).toHaveTextContent("Select an operational alert.");
    expect(claims(seen)).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Refresh operational queue" }));
    expect(claims(seen)).toHaveLength(1);
  });

  it("reuses an uncertain request ID when the analyst selects the same row again", async () => {
    const scenario: Scenario = { posts: [], uncertain: true };
    setup(scenario);
    renderApp("/analyst/operations", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    await userEvent.click(await within(queue).findByRole("button", { name: /Second available alert/ }));
    expect(await screen.findByText(/Could not confirm review ownership/)).toBeVisible();
    await userEvent.click(within(queue).getByRole("button", { name: /Second available alert/ }));
    await waitFor(() => expect(scenario.posts).toHaveLength(2));
    expect(scenario.posts[0]!.body).toEqual(scenario.posts[1]!.body);
  });

  it("opens an already owned alert as Viewer without another claim", async () => {
    const scenario: Scenario = { posts: [], overrideWork: { status: "in_review", canClaim: false,
      canMutate: false, isOwner: false, ownerName: "Alice", explanation: "Reviewed by Alice" } };
    const seen = setup(scenario);
    renderApp("/analyst/operations", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    await userEvent.click(await within(queue).findByRole("button", { name: /Second available alert/ }));
    expect(await screen.findByText("Viewer", { exact: true })).toBeVisible();
    expect(screen.getByText("Alice", { exact: true })).toBeVisible();
    expect(claims(seen)).toHaveLength(0);
    expect(screen.queryByLabelText("Verdict reason")).toBeNull();
    expect(screen.queryByLabelText("Decision reason", { exact: true })).toBeNull();
  });

  it.each([
    { label: "No Immediate Review", status: "available", explanation: "Require Human Review first", canClaim: true, noImmediate: true, overrideRoute: "tier1_review" },
    { label: "Automatic Tier 2 / Unknown", status: "available", explanation: "Expert review", canClaim: true, noImmediate: false, overrideRoute: "tier2_case" },
    { label: "Completed", status: "completed", explanation: "Historical work", canClaim: false, noImmediate: false, overrideRoute: "tier1_review" },
    { label: "Escalated", status: "escalated", explanation: "Tier 2 history", canClaim: false, noImmediate: false, overrideRoute: "tier2_case" },
  ])("keeps $label selection read-only", async ({ status, explanation, canClaim, noImmediate, overrideRoute }) => {
    const scenario: Scenario = { posts: [], overrideWork: { status: status as Schemas["WorkView"]["status"],
      canClaim, explanation }, noImmediate, overrideRoute };
    const seen = setup(scenario);
    renderApp("/analyst/operations", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    await userEvent.click(await within(queue).findByRole("button", { name: /Second available alert/ }));
    expect(claims(seen)).toHaveLength(0);
  });

  it("rejects a workspace switch between queue and work read before POST", async () => {
    const scenario: Scenario = { posts: [], workWorkspace: "v3-1-replay" };
    const seen = setup(scenario);
    renderApp("/analyst/operations", { session: analyst });
    const queue = await screen.findByRole("list", { name: "Operational alerts" });
    await userEvent.click(await within(queue).findByRole("button", { name: /Second available alert/ }));
    expect(await screen.findByText(/active workspace changed/i)).toBeVisible();
    expect(claims(seen)).toHaveLength(0);
  });
});
