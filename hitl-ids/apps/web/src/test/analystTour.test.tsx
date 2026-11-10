import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { jsonResponse, renderApp, stubFetch } from "./renderApp";

const analyst = { username: "g.ang", displayName: "Glenn Ang", role: "security_analyst" as const, token: "test" };
const admin = { username: "admin", displayName: "LIOW CHEE KUANG", role: "system_admin" as const, token: "test" };
const evaluator = { username: "evaluator", displayName: "Evaluator", role: "evaluator" as const, token: "test" };
const titles = [
  "Your Analyst Workstation", "Find the next alert", "Claim shared work", "Overview and routing",
  "Evidence", "Context and review", "Analyst Verdict", "Triage history for this alert",
  "History and notes", "Technical snapshots", "Escalated", "Tier 2 investigation and closure",
  "Triage history library", "Deferred review queue", "Alert intake", "Ready to work",
];

function stubReads() {
  return stubFetch(request => {
    const path = new URL(request.url).pathname;
    if (path === "/api/workspace/current") return jsonResponse({ id: "operational", name: "Operational" });
    if (path === "/api/v2/alerts/summary") return jsonResponse({
      totalAlerts: 0, activeAlerts: 0, criticalAlerts: 0, tier1Review: 0, tier2Cases: 0,
      expertReview: 0, reviewRequired: 0, noImmediateReview: 0, openTier2Cases: 0,
      completedWork: 0, escalatedWork: 0,
    });
    return jsonResponse({ items: [], page: { total: 0, offset: 0, limit: 50, returned: 0 } });
  });
}

describe("current Analyst feature tour", () => {
  it("keeps exactly 16 read-only steps, opens current routes and uses a safe empty-state fallback", async () => {
    const requests = stubReads();
    const user = userEvent.setup();
    const { router } = renderApp("/analyst/operations", { session: analyst });
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    const tour = screen.getByRole("region", { name: "Analyst feature tour" });

    for (const [index, title] of titles.entries()) {
      expect(within(tour).getByText(`Analyst guide · ${index + 1} / 16`)).toBeVisible();
      expect(within(tour).getByRole("heading", { name: title })).toBeVisible();
      if (index === 2) {
        expect(tour).toHaveTextContent("750 ms Auto-Claim arbitration");
        expect(tour).toHaveTextContent("Viewer");
        expect(tour).not.toHaveTextContent("Start Review");
      }
      if (index === 3) {
        expect(router.state.location.search).toBe("");
        expect(document.querySelector('[data-tour="analyst-main"]')).toHaveClass("analyst-tour-highlight");
      }
      if (index === 5) expect(router.state.location.search).toBe("");
      if (index === 6) expect(tour).toHaveTextContent("Confirmed Malicious, Suspicious, Expected Activity, or False Positive");
      if (index === 7) expect(tour).toHaveTextContent("does not automatically suppress review");
      if (index === 10) await waitFor(() => expect(router.state.location.pathname).toBe("/analyst/tier2-cases"));
      if (index === 11) expect(tour).toHaveTextContent("Approved — Not Executed");
      if (index === 13) expect(tour).toHaveTextContent("neither a human Verdict nor an alert closure");
      if (index === 14) await waitFor(() => expect(router.state.location.pathname).toBe("/analyst/external-admission"));
      if (index < titles.length - 1) await user.click(within(tour).getByRole("button", { name: "Next" }));
    }
    await user.click(within(tour).getByRole("button", { name: "Finish" }));
    await waitFor(() => expect(router.state.location.pathname + router.state.location.search).toBe("/analyst/operations"));
    expect(screen.queryByRole("region", { name: "Analyst feature tour" })).toBeNull();
    expect(requests.every(request => request.method === "GET")).toBe(true);
    expect(requests.some(request => new URL(request.url).pathname.endsWith("/work/claim"))).toBe(false);
  });

  it("supports Back, Skip, close and Escape, restoring the starting route", async () => {
    stubReads();
    const user = userEvent.setup();
    const { router } = renderApp("/analyst/triage-memory", { session: analyst });
    const start = screen.getByRole("button", { name: "Start tour" });
    await user.click(start);
    const tour = screen.getByRole("region", { name: "Analyst feature tour" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/analyst/operations"));
    await user.click(within(tour).getByRole("button", { name: "Next" }));
    expect(within(tour).getByText("Analyst guide · 2 / 16")).toBeVisible();
    await user.click(within(tour).getByRole("button", { name: "Back" }));
    expect(within(tour).getByText("Analyst guide · 1 / 16")).toBeVisible();
    await user.click(within(tour).getByRole("button", { name: "Skip tour" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/analyst/triage-memory"));
    await user.click(start);
    await user.click(screen.getByRole("button", { name: "Close analyst tour" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/analyst/triage-memory"));
    await user.click(start);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(router.state.location.pathname).toBe("/analyst/triage-memory"));
    expect(screen.queryByRole("region", { name: "Analyst feature tour" })).toBeNull();
  });

  it("restores a different starting page after Finish", async () => {
    stubReads();
    const user = userEvent.setup();
    const { router } = renderApp("/analyst/selective-review", { session: analyst });
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    const tour = screen.getByRole("region", { name: "Analyst feature tour" });
    for (let index = 0; index < titles.length - 1; index += 1) {
      await user.click(within(tour).getByRole("button", { name: "Next" }));
    }
    await user.click(within(tour).getByRole("button", { name: "Finish" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/analyst/selective-review"));
    expect(screen.queryByRole("region", { name: "Analyst feature tour" })).toBeNull();
  });

  it("offers the entry to Security Analysts only", () => {
    stubReads();
    const analystView = renderApp("/analyst/operations", { session: analyst });
    expect(screen.getByRole("button", { name: "Start tour" })).toBeVisible();
    analystView.unmount();
    renderApp("/admin/overview", { session: admin });
    expect(screen.queryByRole("button", { name: "Start tour" })).toBeNull();
  });

  it("does not offer the entry to the legacy evaluator compatibility role", () => {
    stubReads();
    renderApp("/evaluator/metrics", { session: evaluator });
    expect(screen.queryByRole("button", { name: "Start tour" })).toBeNull();
  });
});
