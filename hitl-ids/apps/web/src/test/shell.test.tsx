/**
 * The S11 verification: the shell, the three accounts, and real sign-in.
 *
 * Every test mounts the REAL route table via `renderApp`, so a route that stops resolving, a guard
 * that stops guarding, or a nav that stops matching its account fails here rather than in a
 * screenshot. Sign-in goes through the real form against a stubbed `/api/auth/login`, mirroring the
 * three seeded accounts (apps/api/auth.py::DEMO_ACCOUNTS).
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { ROLE_META, ROLES } from "../session/roles";
import type { Session } from "../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "./renderApp";

const ANALYST: Session = {
  username: "g.ang",
  displayName: "Glenn Ang",
  role: "security_analyst",
  token: "analyst-token",
};

/** The seeded accounts, as `/api/auth/login` answers them: one account per role. */
const ACCOUNTS: Readonly<Record<"g.ang" | "admin" | "evaluator", Schemas["LoginResponse"]>> = {
  "g.ang": { token: "analyst-token", username: "g.ang", displayName: "Glenn Ang", role: "security_analyst" },
  admin: { token: "admin-token", username: "admin", displayName: "System Administrator", role: "system_admin" },
  evaluator: { token: "evaluator-token", username: "evaluator", displayName: "Evaluator", role: "evaluator" },
};
const PASSWORDS: Readonly<Record<"g.ang" | "admin" | "evaluator", string>> = {
  "g.ang": "analyst-demo",
  admin: "admin-demo",
  evaluator: "evaluator-demo",
};

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
  return stubFetch(async (request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/auth/login") {
      const body = (await request.json()) as { username: string; password: string };
      const account: Schemas["LoginResponse"] | undefined =
        body.username in ACCOUNTS
          ? ACCOUNTS[body.username as keyof typeof ACCOUNTS]
          : undefined;
      return account !== undefined && body.password === PASSWORDS[body.username as keyof typeof ACCOUNTS]
        ? jsonResponse(account)
        : jsonResponse(
            { error: { code: "UNAUTHORIZED", message: "Invalid username or password" } },
            401,
          );
    }
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

/** Fill the real sign-in form and submit, as a presenter does. */
async function signInAs(user: ReturnType<typeof userEvent.setup>, username: keyof typeof ACCOUNTS) {
  await user.type(screen.getByLabelText("Username"), username);
  await user.type(screen.getByLabelText("Password"), PASSWORDS[username]);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}
const SIGN_IN_CASES = [
  { username: "g.ang", heading: "Workstation" },
  { username: "admin", heading: "System Status" },
  { username: "evaluator", heading: "Evaluation scenarios" },
] as const;

describe("shell: signing in as each account", () => {
  for (const { username, heading } of SIGN_IN_CASES) {
    const role = ACCOUNTS[username].role;
    it(`lands ${username} on ${ROLE_META[role].home} and shows the ${role} home page`, async () => {
      const user = userEvent.setup();
      stubApi();
      const { router } = renderApp("/login");

      await signInAs(user, username);

      await waitFor(() => expect(router.state.location.pathname).toBe(ROLE_META[role].home));
      expect(
        await screen.findByRole("heading", { level: 1, name: heading }),
      ).toBeInTheDocument();
    });
  }

  it("offers no role picker: the role comes from the account, not the form", () => {
    stubApi();
    renderApp("/login");

    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.queryByLabelText("Sign in as")).toBeNull();
  });

  it("refuses a wrong password and stays on the sign-in page", async () => {
    const user = userEvent.setup();
    stubApi();
    const { router } = renderApp("/login");

    await user.type(screen.getByLabelText("Username"), "g.ang");
    await user.type(screen.getByLabelText("Password"), "admin-demo");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(router.state.location.pathname).toBe("/login");
  });

  it("reveals the password only while the eye is held, hiding it when the pointer leaves", async () => {
    const user = userEvent.setup();
    stubApi();
    renderApp("/login");

    const field = screen.getByLabelText("Password");
    await user.type(field, "analyst-demo");
    expect(field).toHaveAttribute("type", "password");

    await user.hover(screen.getByRole("button", { name: "Show password" }));
    expect(field).toHaveAttribute("type", "text");
    expect(field).toHaveDisplayValue("analyst-demo");

    await user.unhover(screen.getByRole("button", { name: "Show password" }));
    expect(field).toHaveAttribute("type", "password");

    // Touch and keyboard users press instead of hover: hold shows, release hides.
    const eye = screen.getByRole("button", { name: "Show password" });
    await user.pointer({ keys: "[MouseLeft>]", target: eye });
    expect(field).toHaveAttribute("type", "text");
    await user.pointer({ keys: "[/MouseLeft]", target: eye });
    expect(field).toHaveAttribute("type", "password");
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

  it("redirects / to the signed-in account's home", async () => {
    stubApi();
    const { router } = renderApp("/", {
      session: { username: "a.admin", displayName: "System Administrator", role: "system_admin", token: "t" },
    });

    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/status"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "System Status" }),
    ).toBeInTheDocument();
  });

  it("keeps a session that was already in sessionStorage across a remount", async () => {
    stubApi();
    const { router } = renderApp("/", {
      session: { username: "g.ang", displayName: "Glenn Ang", role: "system_admin", token: "t" },
    });

    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/status"));
  });

  it("treats a pre-S18a session in storage as signed out", async () => {
    stubApi();
    window.sessionStorage.setItem(
      "hitl-ids.session.v1",
      JSON.stringify({ username: "g.ang", role: "system_admin" }),
    );
    const { router } = renderApp("/analyst/queue");

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  });
});

describe("shell: navigation", () => {
  it("shows the current account's nav items and no other role's", async () => {
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

  it("signs out and signs in as another account: the only way to another view", async () => {
    const user = userEvent.setup();
    const seen = stubApi();
    const { router } = renderApp("/analyst/queue", { session: ANALYST });

    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));

    await signInAs(user, "admin");

    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/status"));
    await screen.findByRole("heading", { level: 1, name: "System Status" });

    const summaryRequest = seen.filter((request) =>
      new URL(request.url).pathname.endsWith("/api/dashboard/summary"),
    ).at(-1);
    expect(summaryRequest?.headers.get("Authorization")).toBe("Bearer admin-token");
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

describe("shell: the sign-in page states the account separation", () => {
  it("tells the user that the view belongs to the account, and no longer mentions a role stub", () => {
    stubApi();
    renderApp("/login");

    expect(
      screen.getByText("One account per view: the role you get is the role of the account you sign in as."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/role switch stub/i)).toBeNull();
    expect(screen.queryByText(/trusted as sent/i)).toBeNull();
  });
});
