/**
 * The dashboard is the analyst's landing view, and the first thing a viewer sees. Four states are
 * pinned here: the happy path, the "needs a human" work list, the loading state, the error state with
 * a working retry, and the empty database — because the demo runs against a freshly built corpus and
 * an empty database must explain itself rather than render four zeroes.
 */

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { AL_00478_REF, CRITICAL_ALERT, SUMMARY, alertsPage } from "./fixtures";

const ANALYST: Session = { username: "g.ang", displayName: "Glenn Ang", role: "security_analyst", token: "test-token" };

function summaryResponse(body: Schemas["DashboardSummary"]): Response {
  return jsonResponse(body);
}

function stubDashboard(
  handler: (request: Request) => Response | undefined,
): Request[] {
  return stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/dashboard/summary") {
      return handler(request) ?? summaryResponse(SUMMARY);
    }
    if (pathname === "/api/alerts") return jsonResponse(alertsPage([CRITICAL_ALERT], 1));
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

describe("Dashboard", () => {
  it("leads with the corpus's own counts, not numbers computed here", async () => {
    stubDashboard(() => undefined);
    renderApp("/analyst/dashboard", { session: ANALYST });

    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByText("Detection run #3")).toBeInTheDocument();

    expect(screen.getByText("5,000")).toBeInTheDocument();
    expect(screen.getByText("4,112")).toBeInTheDocument();
    // The tier 2 count appears twice: once as a headline KPI, once as a queue-composition band.
    expect(screen.getAllByText("187").length).toBe(2);
    expect(screen.getByText("12 verdicts recorded")).toBeInTheDocument();
  });

  it("repeats each breakdown as a table as well as a chart", async () => {
    stubDashboard(() => undefined);
    renderApp("/analyst/dashboard", { session: ANALYST });

    const byClass = await screen.findByRole("heading", { level: 2, name: "Alerts by attack class" });
    const section = byClass.closest("section");
    if (section === null) throw new Error("no section");
    const table = within(section).getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Class" })).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "Web Attack" })).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "Port Scan" })).toBeInTheDocument();
  });

  it("names the highest-ranked alerts still flagged for review", async () => {
    stubDashboard(() => undefined);
    renderApp("/analyst/dashboard", { session: ANALYST });

    const card = await screen.findByRole("heading", { level: 2, name: "Needs a human" });
    const section = card.closest("section");
    if (section === null) throw new Error("no section");

    // The card's rows come from their own request, which can land after the heading renders.
    const link = await within(section).findByRole("link", { name: "AL-00478" });
    expect(link).toHaveAttribute("href", `/analyst/alerts/${AL_00478_REF}`);
    expect(within(section).getByText("99.89")).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "Open the full queue" })).toBeInTheDocument();
  });

  it("shows a loading state while the summary is in flight", async () => {
    stubFetch((request) => {
      const { pathname } = new URL(request.url);
      if (pathname === "/api/dashboard/summary") return new Promise<Response>(() => undefined);
      if (pathname === "/api/alerts") return jsonResponse(alertsPage([], 0));
      return jsonResponse({ error: { code: "NOT_FOUND", message: pathname } }, 404);
    });
    renderApp("/analyst/dashboard", { session: ANALYST });

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getAllByText("Loading…").length).toBeGreaterThanOrEqual(1);
  });

  it("shows the API's error and refetches when Try again is pressed", async () => {
    const user = userEvent.setup();
    let summaryCalls = 0;
    const seen = stubDashboard(() => {
      summaryCalls += 1;
      if (summaryCalls === 1) {
        return jsonResponse(
          { error: { code: "SERVICE_UNAVAILABLE", message: "The database is not ready yet." } },
          503,
        );
      }
      return undefined;
    });
    renderApp("/analyst/dashboard", { session: ANALYST });

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("The database is not ready yet.")).toBeInTheDocument();
    expect(within(alert).getByText("SERVICE_UNAVAILABLE · HTTP 503")).toBeInTheDocument();

    await user.click(within(alert).getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("5,000")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(seen.filter((request) => new URL(request.url).pathname === "/api/dashboard/summary").length).toBe(2);
  });

  it("tells the reader how to fill an empty database", async () => {
    stubDashboard(() =>
      summaryResponse({
        ...SUMMARY,
        totalAlerts: 0,
        requiresReview: 0,
        tier2Candidates: 0,
        alertsMovedByFeedback: 0,
        feedbackEvents: 0,
        byQueueClass: [],
        byAttackCategory: {},
        bySeverity: {},
      }),
    );
    renderApp("/analyst/dashboard", { session: ANALYST });

    expect(await screen.findByText("No alerts yet")).toBeInTheDocument();
    expect(screen.getByText(/python scripts\/run_detection\.py/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Needs a human" })).toBeNull();
  });
});
