import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { jsonResponse, renderApp, stubFetch } from "./renderApp";

const session = { username: "g.ang", displayName: "Analyst", role: "security_analyst" as const, token: "test" };
const empty = { items: [], page: { total: 0, offset: 0, limit: 50, returned: 0 } };
function reads() {
  return stubFetch(req => jsonResponse(new URL(req.url).pathname === "/api/v2/alerts/summary"
    ? { totalAlerts: 0, criticalAlerts: 0, tier1Review: 0, tier2Cases: 0, expertReview: 0, reviewRequired: 0, noImmediateReview: 0, openTier2Cases: 0 }
    : empty));
}

describe("final current product surface", () => {
  it.each(["overview", "queue", "alerts/old-alert", "entities/ip/192.0.2.1", "investigations", "feedback-impact", "dashboard"])("retires /analyst/%s without legacy requests", async path => {
    const seen = reads();
    renderApp("/analyst/" + path, { session });
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Analyst Workstation" })).toHaveAttribute("href", "/analyst/operations");
    // Only current, read-only requests: the workspace banner and the actor-name directory (who acted).
    expect(seen.map(request => new URL(request.url).pathname).sort()).toEqual(["/api/auth/actors", "/api/workspace/current"]);
  });
  it.each(["workstation", "v2-triage"])("redirects %s and preserves only the operational alert identity", async path => {
    stubFetch(() => jsonResponse({ error: { code: "NOT_FOUND", message: "Alert no longer available" } }, 404));
    const { router } = renderApp(`/analyst/${path}?alertRef=current-ref&familyKey=old`, { session });
    await waitFor(() => expect(router.state.location.pathname).toBe("/analyst/operations"));
    expect(router.state.location.search).toBe("?alertRef=current-ref");
    expect(await screen.findByRole("heading", { name: "Analyst Workstation" })).toBeVisible();
    expect(screen.queryByText("Advanced / Historical")).toBeNull();
    expect(screen.queryByText("Legacy Flow Workstation")).toBeNull();
  });
  it("exposes exactly the five current analyst destinations", async () => {
    reads(); renderApp("/analyst/operations", { session });
    const links = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link");
    expect(links.map(link => link.getAttribute("href"))).toEqual([
      "/analyst/operations", "/analyst/tier2-cases", "/analyst/triage-memory", "/analyst/selective-review", "/analyst/external-admission",
    ]);
    expect(screen.queryByText("Advanced / Historical")).toBeNull();
  });
});
