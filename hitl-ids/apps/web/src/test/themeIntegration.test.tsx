import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { TopBar } from "../components/layout/TopBar";
import { SessionProvider, type Session } from "../session/SessionContext";
import { ThemeProvider, THEME_STORAGE_KEY, useTheme } from "../theme/ThemeContext";
import { jsonResponse, renderApp, stubFetch } from "./renderApp";

const SESSIONS: Readonly<Record<Session["role"], Session>> = {
  security_analyst: {
    username: "g.ang",
    displayName: "Glenn Ang",
    role: "security_analyst",
    token: "analyst-token",
  },
  system_admin: {
    username: "admin",
    displayName: "System Administrator",
    role: "system_admin",
    token: "admin-token",
  },
  evaluator: {
    username: "evaluator",
    displayName: "Evaluator",
    role: "evaluator",
    token: "evaluator-token",
  },
};

function stubUnavailableApi(): Request[] {
  return stubFetch((request) =>
    jsonResponse(
      { error: { code: "NOT_FOUND", message: `No theme-test fixture for ${new URL(request.url).pathname}` } },
      404,
    ),
  );
}

describe("theme integration", () => {
  it.each(["light", "dark"] as const)("renders the login page in %s mode", (theme) => {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    stubUnavailableApi();
    renderApp("/login");

    expect(screen.getByRole("heading", { level: 1, name: "IDS Console" })).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("data-theme", theme);
    expect(screen.getByRole("button", { name: `Switch to ${theme === "light" ? "dark" : "light"} theme` })).toBeInTheDocument();
  });

  const shellCases = [
    { role: "security_analyst", path: "/analyst/investigations", heading: "Investigations" },
    { role: "system_admin", path: "/admin/status", heading: "System Status" },
    { role: "evaluator", path: "/evaluator/scenarios", heading: "Evaluation scenarios" },
  ] as const;

  for (const theme of ["light", "dark"] as const) {
    for (const { role, path, heading } of shellCases) {
      it(`renders the ${role} shell in ${theme} mode`, async () => {
        window.localStorage.setItem(THEME_STORAGE_KEY, theme);
        stubUnavailableApi();
        renderApp(path, { session: SESSIONS[role] });

        expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
        expect(screen.getAllByText(SESSIONS[role].displayName).length).toBeGreaterThan(0);
        expect(document.documentElement).toHaveAttribute("data-theme", theme);
      });
    }
  }

  it("changes presentation without changing role, requests, ranking, feedback, or guardrails", async () => {
    const user = userEvent.setup();
    const requests = stubUnavailableApi();
    window.sessionStorage.setItem("hitl-ids.session.v1", JSON.stringify(SESSIONS.security_analyst));

    const domain = Object.freeze({
      ranking: Object.freeze(["AL-0007", "AL-0012", "AL-0021"]),
      feedbackAdjustment: -25,
      criticalFloor: 70,
    });

    function DomainProbe() {
      const { theme } = useTheme();
      return (
        <div>
          <TopBar />
          <output aria-label="Theme value">{theme}</output>
          <output aria-label="Ranking value">{domain.ranking.join(",")}</output>
          <output aria-label="Feedback value">{domain.feedbackAdjustment}</output>
          <output aria-label="Guardrail value">{domain.criticalFloor}</output>
        </div>
      );
    }

    render(
      <ThemeProvider>
        <SessionProvider>
          <MemoryRouter>
            <DomainProbe />
          </MemoryRouter>
        </SessionProvider>
      </ThemeProvider>,
    );

    const before = {
      ranking: screen.getByLabelText("Ranking value").textContent,
      feedback: screen.getByLabelText("Feedback value").textContent,
      guardrail: screen.getByLabelText("Guardrail value").textContent,
      requests: requests.length,
    };
    await user.click(screen.getByRole("button", { name: /Switch to .* theme/ }));

    expect(screen.getByText("Glenn Ang")).toBeInTheDocument();
    expect(screen.getByLabelText("Ranking value")).toHaveTextContent(before.ranking ?? "");
    expect(screen.getByLabelText("Feedback value")).toHaveTextContent(before.feedback ?? "");
    expect(screen.getByLabelText("Guardrail value")).toHaveTextContent(before.guardrail ?? "");
    expect(requests).toHaveLength(before.requests);
  });
});
