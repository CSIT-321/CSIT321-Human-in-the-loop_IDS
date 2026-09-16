/**
 * The queue is a ranked list an analyst works down, so these tests pin the three things that would
 * break it: the row must show the name an analyst says aloud and link to the alert by its reference,
 * the filters and the page must travel to the API as query parameters, and the rank must be the page's
 * own offset rather than a running client-side count.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { AL_00478_REF, CRITICAL_ALERT, UNFLAGGED_ALERT, alertsPage } from "./fixtures";

const ANALYST: Session = { username: "g.ang", displayName: "Glenn Ang", role: "security_analyst", token: "test-token" };

function queryOf(request: Request | undefined): URLSearchParams {
  return new URL(request?.url ?? "http://localhost/").searchParams;
}

function stubQueue(items: readonly Schemas["AlertSummary"][], total = items.length): Request[] {
  return stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/alerts") return jsonResponse(alertsPage(items, total));
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

describe("Alert Queue", () => {
  it("lists a row by the flow's short name, linking to its alert reference", async () => {
    stubQueue([CRITICAL_ALERT, UNFLAGGED_ALERT]);
    renderApp("/analyst/queue", { session: ANALYST });

    const link = await screen.findByRole("link", { name: "AL-00478" });
    expect(link).toHaveAttribute("href", `/analyst/alerts/${AL_00478_REF}`);
    expect(screen.getByRole("link", { name: "AL-03086" })).toBeInTheDocument();
    expect(screen.getByText("Showing 1–2 of 2")).toBeInTheDocument();
  });

  it("sends the chosen band to the API as queueClass", async () => {
    const user = userEvent.setup();
    const seen = stubQueue([CRITICAL_ALERT]);
    renderApp("/analyst/queue", { session: ANALYST });

    await screen.findByRole("link", { name: "AL-00478" });
    await user.selectOptions(screen.getByLabelText("Band"), "ml_only");

    await waitFor(() => {
      expect(seen.some((request) => queryOf(request).get("queueClass") === "ml_only")).toBe(true);
    });
  });

  it("sends the not-saturated ceiling as detectionMaxScore", async () => {
    const user = userEvent.setup();
    const seen = stubQueue([CRITICAL_ALERT]);
    renderApp("/analyst/queue", { session: ANALYST });

    await screen.findByRole("link", { name: "AL-00478" });
    await user.selectOptions(screen.getByLabelText("Detection score"), "99.999");

    await waitFor(() => {
      expect(
        seen.some((request) => queryOf(request).get("detectionMaxScore") === "99.999"),
      ).toBe(true);
    });
  });

  it("sends the chosen verdict as the verdict parameter", async () => {
    const user = userEvent.setup();
    const seen = stubQueue([CRITICAL_ALERT]);
    renderApp("/analyst/queue", { session: ANALYST });

    await screen.findByRole("link", { name: "AL-00478" });
    await user.selectOptions(screen.getByLabelText("Judged"), "mark_false_positive");

    await waitFor(() => {
      expect(
        seen.some((request) => queryOf(request).get("verdict") === "mark_false_positive"),
      ).toBe(true);
    });
  });

  it("sends 'Not yet judged' as unjudged, never as a verdict", async () => {
    const user = userEvent.setup();
    const seen = stubQueue([CRITICAL_ALERT]);
    renderApp("/analyst/queue", { session: ANALYST });

    await screen.findByRole("link", { name: "AL-00478" });
    await user.selectOptions(screen.getByLabelText("Judged"), "unjudged");

    await waitFor(() => {
      expect(seen.some((request) => queryOf(request).get("unjudged") === "true")).toBe(true);
    });
    // The absence of a verdict is not a verdict: the two parameters must never both be sent.
    expect(seen.every((request) => queryOf(request).get("verdict") === null)).toBe(true);
  });

  it("submits the search box as the search parameter", async () => {
    const user = userEvent.setup();
    const seen = stubQueue([UNFLAGGED_ALERT]);
    renderApp("/analyst/queue", { session: ANALYST });

    await screen.findByRole("link", { name: "AL-03086" });
    await user.type(screen.getByLabelText("Search"), "AL-03086");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(seen.some((request) => queryOf(request).get("search") === "AL-03086")).toBe(true);
    });
  });

  it("pages forward by the page size and reports where the window sits", async () => {
    const user = userEvent.setup();
    const seen = stubQueue([CRITICAL_ALERT, UNFLAGGED_ALERT], 120);
    renderApp("/analyst/queue", { session: ANALYST });

    await screen.findByRole("link", { name: "AL-00478" });
    expect(screen.getByText("Showing 1–2 of 120")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(seen.some((request) => queryOf(request).get("offset") === "50")).toBe(true);
    });
  });

  it("says so when the filters match nothing", async () => {
    stubQueue([]);
    renderApp("/analyst/queue", { session: ANALYST });

    expect(await screen.findByText("No alerts match these filters")).toBeInTheDocument();
  });
});
