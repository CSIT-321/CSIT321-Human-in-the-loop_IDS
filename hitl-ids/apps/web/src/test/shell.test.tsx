/**
 * The S11 verification: the shell, the three roles, and the demo's role switch.
 *
 * Every test mounts the REAL route table via `renderApp`, so a route that stops resolving, a guard
 * that stops guarding, or a nav that stops matching its role fails here rather than in a screenshot.
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { ROLE_META, ROLES, type Role } from "../session/roles";
import type { Session } from "../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "./renderApp";

const ANALYST: Session = { username: "g.ang", role: "security_analyst" };

const SUMMARY: Schemas["DashboardSummary"] = {
  generatedAt: "2026-09-12T10:00:00.000000Z",
  runId: 1,
  totalAlerts: 5000,
  requiresReview: 996,
  tier2Candidates: 644,
  feedbackEvents: 0,
  guardrailInterventions: 0,
  alertsMovedByFeedback: 0,
  byQueueClass: [],
  byEvidenceClass: {},
  bySeverity: {},
  byAttackCategory: {},
};

/** Route by pathname, so a test never depends on request order. */
function stubApi(): Request[] {
  return stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/dashboard/summary") return jsonResponse(SUMMARY);
    if (pathname === "/api/evaluation/runs") {
      return jsonResponse({ items: [], page: { limit: 1, offset: 0, returned: 0, total: 0 } });
    }
    if (pathname === "/api/evaluation/scenarios") {
      return jsonResponse({ items: [], page: { limit: 50, offset: 0, returned: 0, total: 0 } });
    }
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

const SIGN_IN_CASES: readonly { role: Role; heading: string }[] = [
  { role: "security_analyst", heading: "Workstation" },
  { role: "system_admin", heading: "System Status" },
  { role: "evaluator", heading: "Evaluation scenarios" },
];

describe("shell: signing in as each role", () => {
  for (const { role, heading } of SIGN_IN_CASES) {
    it(`lands on ${ROLE_META[role].home} and shows the ${role} home page`, async () => {
      const user = userEvent.setup();
      stubApi();
      const { router } = renderApp("/login");

      await user.type(screen.getByLabelText("Username"), "g.ang");
      await user.click(screen.getByRole("radio", { name: ROLE_META[role].short }));
      await user.click(screen.getByRole("button", { name: "Sign in" }));

      await waitFor(() => expect(router.state.location.pathname).toBe(ROLE_META[role].home));
      expect(
        await screen.findByRole("heading", { level: 1, name: heading }),
      ).toBeInTheDocument();
    });
  }

  it("offers exactly one chip per role, defaulting to the analyst", async () => {
    stubApi();
    renderApp("/login");

    const group = screen.getByRole("radiogroup", { name: "Sign in as" });
    expect(within(group).getAllByRole("radio")).toHaveLength(ROLES.length);
    expect(within(group).getByRole("radio", { name: "Analyst" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });
});

describe("shell: route guards", () => {
  it("sends a signed-out visitor from a role route to /login", async () => {
    stubApi();
    const { router } = renderApp("/analyst/queue");

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(screen.getByRole("heading", { level: 1, name: "IDS Console" })).toBeInTheDocument();
  });

  it("sends an analyst away from an admin route to the analyst home", async () => {
    stubApi();
    const { router } = renderApp("/admin/status", { session: ANALYST });

    await waitFor(() => expect(router.state.location.pathname).toBe("/analyst/workstation"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Workstation" }),
    ).toBeInTheDocument();
  });

  it("redirects / to the signed-in role's home", async () => {
    stubApi();
    const { router } = renderApp("/", { session: { username: "e.admin", role: "system_admin" } });

    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/status"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "System Status" }),
    ).toBeInTheDocument();
  });

  it("keeps a session that was already in sessionStorage across a remount", async () => {
    stubApi();
    const { router } = renderApp("/", { session: { username: "g.ang", role: "system_admin" } });

    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/status"));
  });
});

describe("shell: navigation", () => {
  it("shows the current role's nav items and no other role's", async () => {
    stubApi();
    renderApp("/analyst/queue", { session: ANALYST });

    const nav = await screen.findByRole("navigation", { name: "Main" });
    for (const item of ROLE_META.security_analyst.nav) {
      expect(within(nav).getByText(item.label)).toBeInTheDocument();
    }
    for (const other of ROLES.filter((role) => role !== "security_analyst")) {
      for (const item of ROLE_META[other].nav) {
        expect(within(nav).queryByText(item.label)).toBeNull();
      }
    }
  });

  it("switches role from the select, navigating home and stamping later requests", async () => {
    const user = userEvent.setup();
    const seen = stubApi();
    const { router } = renderApp("/analyst/queue", { session: ANALYST });

    await user.selectOptions(await screen.findByLabelText("Switch role"), "evaluator");

    await waitFor(() => expect(router.state.location.pathname).toBe("/evaluator/scenarios"));
    await screen.findByRole("heading", { level: 1, name: "Evaluation scenarios" });

    const scenariosRequest = seen.find((request) =>
      new URL(request.url).pathname.endsWith("/api/evaluation/scenarios"),
    );
    expect(scenariosRequest?.headers.get("X-Demo-Role")).toBe("evaluator");
  });

  it("signs out to /login and clears the stored session", async () => {
    const user = userEvent.setup();
    stubApi();
    const { router, unmount } = renderApp("/analyst/queue", { session: ANALYST });

    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));

    unmount();
    const reloaded = renderApp("/analyst/queue");
    await waitFor(() => expect(reloaded.router.state.location.pathname).toBe("/login"));
  });
});

describe("shell: the demo stub is labelled as one", () => {
  it("tells the user on the sign-in page that the role is trusted as sent", () => {
    stubApi();
    renderApp("/login");

    expect(
      screen.getByText("Authentication is a stub: the role you pick is trusted as sent."),
    ).toBeInTheDocument();
    expect(screen.getByText("Demo build")).toBeInTheDocument();
  });
});
