/**
 * Similar-alert learning is the product's claim, so the screen that shows it is tested for what it
 * *states*, not only for what it renders.
 *
 * Two failures would otherwise be invisible: a grouped queue that does not say how many alerts
 * moved without being judged, and a "what makes these similar" explanation that drifts from the
 * membership rule the engine actually applies. Both are checked here against the API's own shapes.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../../api/client";
import { BREAKDOWNS, CRITICAL_ALERT, SUMMARY, alertsPage } from "../../../pages/analyst/__tests__/fixtures";
import type { Session } from "../../../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { MovedAlerts, SimilarityFacets } from "../SimilarAlerts";

const ANALYST: Session = {
  username: "g.ang",
  displayName: "Glenn Ang",
  role: "security_analyst",
  token: "test-token",
};

const BASIS: Schemas["SimilarityBasis"] = {
  attackCategory: "Botnet",
  dstPort: 8080,
  protocol: "tcp",
  ruleId: null,
  dstIp: null,
  rule: "Alerts are one family when the attack class, destination port, protocol and matched rule all match exactly. There is no similarity score and no threshold.",
};

const FAMILY_ROW: Schemas["FamilyRow"] = {
  familyKey: '["Botnet",8080,"tcp","-"]',
  familyLabel: "Botnet · port 8080 · tcp",
  basis: BASIS,
  members: 150,
  judged: 3,
  requiresReview: 150,
  bestRank: 27,
  bestAlertRef: CRITICAL_ALERT.alertRef,
  bestSeverity: "Critical",
  bestScore: 91,
  bestQueueClass: "corroborated",
  attackCategory: "Botnet",
  gateOpen: true,
  gateReason: "3 of 3 verdicts agree: mark_false_positive",
  dominantCategory: "mark_false_positive",
  agreementRatio: 1,
  appliedAdjustment: -9,
  appliedOffset: 1,
  learnedAt: "2026-09-18T10:00:00Z",
};

function stubGroupedQueue(): Request[] {
  return stubFetch((request) => {
    const url = new URL(request.url);
    if (url.pathname === "/api/dashboard/summary") return jsonResponse(SUMMARY);
    if (url.pathname === "/api/dashboard/breakdowns") return jsonResponse(BREAKDOWNS);
    if (url.pathname === "/api/alerts/families") {
      return jsonResponse({ items: [FAMILY_ROW], page: { total: 1, limit: 50, offset: 0, returned: 1 } });
    }
    if (url.pathname === "/api/alerts") return jsonResponse(alertsPage([CRITICAL_ALERT], 150));
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${url.pathname}` } }, 404);
  });
}

describe("Grouping the queue by similar-alert family", () => {
  it("folds the queue into families and reports what each one has learned", async () => {
    const user = userEvent.setup();
    const seen = stubGroupedQueue();
    renderApp("/analyst/workstation", { session: ANALYST });

    await user.click(await screen.findByRole("button", { name: "Family" }));

    const group = await screen.findByRole("button", { name: /Botnet/ });
    // The numbers that carry the claim: how many alerts, how many a person judged, and that the
    // remainder carry the family's adjustment without anyone having touched them.
    expect(within(group).getByText(/150 alerts/)).toBeInTheDocument();
    expect(within(group).getByText(/3 judged/)).toBeInTheDocument();
    expect(within(group).getByText(/gate open/)).toBeInTheDocument();
    expect(within(group).getByText(/147 unjudged alerts carry this/)).toBeInTheDocument();
    expect(seen.some((request) => new URL(request.url).pathname === "/api/alerts/families")).toBe(true);
  });

  it("reads a family's members back through the queue endpoint, filtered by its key", async () => {
    const user = userEvent.setup();
    const seen = stubGroupedQueue();
    renderApp("/analyst/workstation", { session: ANALYST });

    await user.click(await screen.findByRole("button", { name: "Family" }));
    await user.click(await screen.findByRole("button", { name: /Botnet/ }));

    const members = await screen.findByRole("list", { name: "Family members" });
    expect(within(members).getByRole("button", { name: /AL-00478/ })).toBeInTheDocument();
    const filtered = seen.filter((request) => {
      const url = new URL(request.url);
      return url.pathname === "/api/alerts" && url.searchParams.get("familyKey") === FAMILY_ROW.familyKey;
    });
    expect(filtered.length).toBeGreaterThan(0);
  });

  it("does not ask for families while the flat queue is on screen", async () => {
    const seen = stubGroupedQueue();
    renderApp("/analyst/workstation", { session: ANALYST });

    await screen.findByRole("tablist", { name: "Alert filter" });
    expect(seen.some((request) => new URL(request.url).pathname === "/api/alerts/families")).toBe(false);
  });
});

const MOVED: Schemas["MovedMember"][] = [
  {
    alertRef: "11111111-1111-4111-8111-111111111111",
    sourceRecordId: "AL-00932",
    scoreBefore: 100,
    scoreAfter: 91,
    queueClassBefore: "tier2_candidate",
    queueClassAfter: "corroborated",
    rankBefore: 28,
    rankAfter: 31,
  },
];

describe("The alerts a verdict moved", () => {
  it("names each moved alert with its score, band and queue rank", () => {
    render(
      <MemoryRouter>
        <MovedAlerts rows={MOVED} total={147} familyKey={FAMILY_ROW.familyKey} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/147 similar alerts re-ranked/)).toBeInTheDocument();
    // The cap is stated, never silently applied: a table showing 1 of 147 without saying so would
    // understate the very effect it exists to demonstrate.
    expect(screen.getByText(/showing the top 1/)).toBeInTheDocument();
    const row = screen.getByRole("link", { name: "AL-00932" }).closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("100")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("91")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("28")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("31")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("tier2_candidate")).toBeInTheDocument();
  });

  it("states the membership test rather than asserting similarity", () => {
    render(
      <MemoryRouter>
        <SimilarityFacets basis={BASIS} />
      </MemoryRouter>,
    );

    expect(screen.getByText("Botnet")).toBeInTheDocument();
    expect(screen.getByText("8080")).toBeInTheDocument();
    expect(screen.getByText("tcp")).toBeInTheDocument();
    expect(screen.getByText("none matched")).toBeInTheDocument();
    expect(screen.getByText(/match exactly. There is no similarity score and no threshold/)).toBeInTheDocument();
  });
});
