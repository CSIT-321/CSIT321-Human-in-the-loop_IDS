import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, renderApp, stubFetch } from "./renderApp";

const ADMIN = { username: "admin", displayName: "Administrator", role: "system_admin" as const, token: "admin-token" };
const ANALYST = { username: "g.ang", displayName: "Analyst", role: "security_analyst" as const, token: "analyst-token" };
const EVALUATOR = { username: "evaluator", displayName: "Evaluator", role: "evaluator" as const, token: "evaluator-token" };

function workspaceState(active: "operational" | "v3-1-replay", prepared: boolean) {
  return {
    activeWorkspaceId: active, activeWorkspaceName: active === "operational" ? "Operational" : "V3.1 Demo Replay",
    actions: [], detection: { flowChainEnabled: true }, workspaces: [
      { id: "operational", name: "Operational", active: active === "operational", ready: true,
        alertCount: 13, rawRecords: null, stagedAlerts: null, lastPreparedAt: null, workloadSha256: null },
      { id: "v3-1-replay", name: "V3.1 Demo Replay", active: active === "v3-1-replay", ready: prepared,
        alertCount: prepared ? 200 : null, rawRecords: prepared ? 200 : null, stagedAlerts: prepared ? 200 : null,
        lastPreparedAt: prepared ? "2026-11-03T01:00:00Z" : null, workloadSha256: prepared ? "workload-hash" : null },
    ],
  };
}

describe("operational workspace controls", () => {
  it("prepares Presentation Replay and advances only through Admin commands", async () => {
    const user = userEvent.setup();
    let active: "operational" | "v3-1-replay" = "operational";
    let prepared = false;
    let arrived = 10;
    const seen = stubFetch(async request => {
      const path = new URL(request.url).pathname;
      if (request.method === "POST") {
        if (path.endsWith("/prepare")) {
          expect((await request.clone().json()).mode).toBe("presentation");
          prepared = true;
        }
        if (path.endsWith("/activate")) active = path.includes("v3-1-replay") ? "v3-1-replay" : "operational";
        if (path.endsWith("/advance")) arrived += (await request.clone().json()).count;
      }
      const state = workspaceState(active, prepared);
      if (prepared) Object.assign(state.workspaces[1]!, {
        alertCount: 40 + arrived, stagedAlerts: 40 + arrived, preparationMode: "presentation",
        learningProcessed: 40, holdoutArrived: arrived, holdoutRemaining: 160 - arrived,
        playbackState: "paused", lastArrivalAt: "2026-11-03T01:00:00Z",
      });
      return jsonResponse(state);
    });
    renderApp("/admin/workspaces", { session: ADMIN });
    await screen.findByRole("heading", { name: "Operational Workspace" });
    await user.selectOptions(screen.getByLabelText("Replay preparation mode"), "presentation");
    await user.click(screen.getByRole("button", { name: "Prepare Replay" }));
    expect(await screen.findByText("40 processed")).toBeVisible();
    expect(screen.getByText("10 / 160")).toBeVisible();
    expect(screen.getByRole("button", { name: "Next Alert" })).toBeDisabled();
    await user.click(screen.getAllByRole("button", { name: "Activate" }).find(button => !button.hasAttribute("disabled"))!);
    await user.click(screen.getByRole("button", { name: "Next Alert" }));
    expect(await screen.findByText("11 / 160")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Next 5" }));
    expect(await screen.findByText("16 / 160")).toBeVisible();
    expect(seen.filter(request => request.method === "POST" && request.url.endsWith("/advance"))).toHaveLength(2);
  });

  it("shows Admin status and keeps Reset confined to Replay", async () => {
    const user = userEvent.setup();
    let active: "operational" | "v3-1-replay" = "operational";
    let prepared = false;
    const seen = stubFetch(request => {
      const path = new URL(request.url).pathname;
      if (request.method === "POST") {
        if (path.endsWith("/prepare")) prepared = true;
        if (path.endsWith("/reset")) prepared = false;
        if (path.endsWith("/activate")) active = path.includes("v3-1-replay") ? "v3-1-replay" : "operational";
      }
      return jsonResponse(workspaceState(active, prepared));
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp("/admin/workspaces", { session: ADMIN });
    expect(await screen.findByRole("heading", { name: "Operational Workspace" })).toBeVisible();
    expect(screen.getAllByText("Operational alerts:", { exact: false })).toHaveLength(2);
    expect(screen.getByText("Not prepared")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Reset Replay" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Prepare Replay" }));
    expect(await screen.findByText(/Last prepared: 2026-11-03T01:00:00Z/)).toBeVisible();
    await user.click(screen.getAllByRole("button", { name: "Activate" }).find(button => !button.hasAttribute("disabled"))!);
    expect(await screen.findByText("V3.1 Demo Replay", { selector: "p" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Reset Replay" })).toBeDisabled();
    expect(seen.some(request => request.method === "POST" && new URL(request.url).pathname.endsWith("/prepare"))).toBe(true);
  });

  it("shows Analyst the backend-selected workspace without control or oracle navigation", async () => {
    stubFetch(request => {
      const path = new URL(request.url).pathname;
      if (path === "/api/workspace/current") return jsonResponse({ id: "v3-1-replay", name: "V3.1 Demo Replay" });
      if (path === "/api/v2/alerts/summary") return jsonResponse({ totalAlerts: 0, criticalAlerts: 0, tier1Review: 0,
        tier2Cases: 0, expertReview: 0, reviewRequired: 0, noImmediateReview: 0, openTier2Cases: 0 });
      return jsonResponse({ items: [], page: { total: 0, offset: 0, limit: 50, returned: 0 } });
    });
    renderApp("/analyst/operations", { session: ANALYST });
    expect(await screen.findByText("Workspace: V3.1 Demo Replay")).toBeVisible();
    const nav = within(screen.getByRole("navigation", { name: "Main" }));
    expect(nav.queryByRole("link", { name: /Operational Workspace|Final V3.1/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Prepare Replay|Reset Replay|Activate/i })).toBeNull();
    expect(screen.queryByText(/oracle outcome/i)).toBeNull();
  });

  it("renders Packet Replay progress with step controls only", async () => {
    stubFetch(() => {
      const state = workspaceState("v3-1-replay", true);
      Object.assign(state.workspaces[1]!, {
        preparationMode: "packet", holdoutArrived: 12, holdoutRemaining: 148,
        learningProcessed: 0, playbackState: "paused", lastArrivalAt: "2026-11-03T01:00:00Z",
      });
      return jsonResponse(state);
    });
    renderApp("/admin/workspaces", { session: ADMIN });
    expect(await screen.findByText(/Capture steps arrived:/)).toBeVisible();
    expect(screen.getByText("12 / 160")).toBeVisible();
    expect(screen.getByRole("button", { name: "Next Step" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Load Remaining" })).toBeNull();
    expect(screen.queryByText(/Learning history/)).toBeNull();
  });

  it("turns the CICFlowMeter chain off as a program setting, not a replay option", async () => {
    const user = userEvent.setup();
    let flow = true;
    const seen: { path: string; body: unknown }[] = [];
    stubFetch(async request => {
      const path = new URL(request.url).pathname;
      if (request.method === "POST" && path === "/api/admin/detection/flow-chain") {
        const body = await request.clone().json();
        seen.push({ path, body });
        flow = body.enabled;
      }
      const state = workspaceState("v3-1-replay", true);
      Object.assign(state, { detection: { flowChainEnabled: flow } });
      Object.assign(state.workspaces[1]!, { preparationMode: "packet", holdoutArrived: 3, holdoutRemaining: 157,
        playbackState: "paused", lastArrivalAt: "2026-11-03T01:00:00Z" });
      return jsonResponse(state);
    });
    renderApp("/admin/workspaces", { session: ADMIN });
    const chain = await screen.findByRole("switch", { name: "CICFlowMeter flow chain" });
    expect(chain).toHaveAttribute("aria-checked", "true");
    await user.click(chain);
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0]!.path).toBe("/api/admin/detection/flow-chain");
    expect(seen[0]!.body).toMatchObject({ enabled: false });
    expect(await screen.findByRole("switch", { name: "CICFlowMeter flow chain" })).toHaveAttribute("aria-checked", "false");
  });

  it("routes Admin and Evaluator to the same frozen evidence module", async () => {
    const summary = { total: 200, learning: 40, holdout: 160, primary: 140, supplementary: 20,
      unknown: 10, drift: 10, primaryBaselineImmediateReview: 140, primaryAdaptiveImmediateReview: 103,
      primaryReviewReduction: 37, primaryReviewReductionRate: 37 / 140, primarySafeDeferrals: 37,
      primaryUnsafeDeferrals: 0, allHoldoutInitialDeferrals: 39, allHoldoutUnsafeDeferrals: 2,
      postContradictionUnsafeDeferrals: 0, postContradictionPopulation: 8, unknownFormalTier2Cases: 10,
      strata: { stable_matching_benign: 80, unseen_benign: 20, malicious: 20, suspicious: 20 },
      driftTimeline: [{ pattern: "p009", eventIndex: 191, disposition: "no_immediate_review", oracleOutcome: "malicious",
        beforeStatus: "active", afterFeedbackStatus: "conflict_review" }], runtimeSha: "frozen-sha" };
    stubFetch(request => {
      const path = new URL(request.url).pathname;
      if (path === "/api/evaluation/final-v3-1") return jsonResponse(summary);
      if (path.endsWith("/records")) return jsonResponse({ items: [], total: 200, limit: 25, offset: 0 });
      if (path.endsWith("/memory-impact")) return jsonResponse({ items: [] });
      return jsonResponse({}, 404);
    });
    const admin = renderApp("/admin/evaluation/final-v3-1", { session: ADMIN });
    expect(await screen.findByLabelText("Frozen workload composition")).toBeVisible();
    expect(screen.getByText("26.43%", { exact: false })).toBeVisible();
    expect(screen.getByText("Memory Impact")).toBeVisible();
    expect(screen.getByText("Drift proof")).toBeVisible();
    admin.unmount();
    window.sessionStorage.clear();
    renderApp("/evaluator/final-v3-1", { session: EVALUATOR });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Final Evaluation V3.1" })).toBeVisible());
    expect(screen.getByText("26.43%", { exact: false })).toBeVisible();
  });
});
