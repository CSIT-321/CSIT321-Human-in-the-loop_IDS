import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { BREAKDOWNS, CRITICAL_ALERT, SUMMARY, alertsPage } from "./fixtures";

const ANALYST: Session = {
  username: "g.ang",
  displayName: "Glenn Ang",
  role: "security_analyst",
  token: "test-token",
};

const WORKSTATION_SUMMARY: Schemas["DashboardSummary"] = {
  ...SUMMARY,
  totalAlerts: 5000,
  requiresReview: 996,
  tier2Candidates: 644,
  byQueueClass: [
    { queueClass: "tier2_candidate", count: 644, requiresReview: 644 },
    { queueClass: "ml_only", count: 352, requiresReview: 352 },
    { queueClass: "none", count: 4004, requiresReview: 0 },
  ],
  byEvidenceClass: {
    corroborated: 200,
    signature_override: 0,
    ml_only: 796,
    none: 4004,
  },
};

const CORROBORATED_TIER2: Schemas["AlertSummary"] = {
  ...CRITICAL_ALERT,
  sourceRecordId: "AL-RULE-MODEL",
  evidenceClass: "corroborated",
  queueClass: "tier2_candidate",
  attackCategory: "Brute Force",
  matchedRuleIds: ["SIG-SSH-BRUTE-FORCE"],
};

function queryOf(request: Request): URLSearchParams {
  return new URL(request.url).searchParams;
}

function stubWorkstation(corroboratedItem = false): Request[] {
  return stubFetch((request) => {
    const url = new URL(request.url);
    if (url.pathname === "/api/dashboard/summary") return jsonResponse(WORKSTATION_SUMMARY);
    if (url.pathname === "/api/dashboard/breakdowns") return jsonResponse(BREAKDOWNS);
    if (url.pathname === "/api/alerts") {
      const items = corroboratedItem && url.searchParams.get("evidenceClass") === "corroborated"
        ? [CORROBORATED_TIER2]
        : [];
      return jsonResponse(alertsPage(items, items.length));
    }
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${url.pathname}` } }, 404);
  });
}

describe("Analyst Workstation tabs", () => {
  it("renders queue counts and evidence counts from their separate summary fields", async () => {
    stubWorkstation();
    renderApp("/analyst/workstation", { session: ANALYST });

    const tabs = await screen.findByRole("tablist", { name: "Alert filter" });
    expect(within(tabs).getByRole("tab", { name: /All\s*5,000/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: /Tier 2\s*644/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: /Needs review\s*996/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: /Rule \+ model\s*200/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: /Rule only\s*0/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: /Model only\s*796/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: /Not flagged\s*4,004/ })).toBeInTheDocument();
  });

  it("keeps Tier 2 and Needs review as queue and workflow filters", async () => {
    const user = userEvent.setup();
    const seen = stubWorkstation();
    renderApp("/analyst/workstation", { session: ANALYST });

    await user.click(await screen.findByRole("tab", { name: /Tier 2\s*644/ }));
    await waitFor(() => {
      expect(seen.some((request) => {
        const query = queryOf(request);
        return query.get("queueClass") === "tier2_candidate" && !query.has("evidenceClass");
      })).toBe(true);
    });

    await user.click(screen.getByRole("tab", { name: /Needs review\s*996/ }));
    await waitFor(() => {
      expect(seen.some((request) => {
        const query = queryOf(request);
        return query.get("requiresReview") === "true"
          && !query.has("queueClass")
          && !query.has("evidenceClass");
      })).toBe(true);
    });
  });

  it("uses evidenceClass for detector-evidence tabs and preserves the alert's queue band", async () => {
    const user = userEvent.setup();
    const seen = stubWorkstation(true);
    renderApp("/analyst/workstation", { session: ANALYST });

    await user.click(await screen.findByRole("tab", { name: /Rule \+ model\s*200/ }));
    const row = await screen.findByRole("button", { name: /AL-RULE-MODEL/ });
    expect(within(row).getByText("TIER 2")).toBeInTheDocument();
    expect(seen.some((request) => {
      const query = queryOf(request);
      return query.get("evidenceClass") === "corroborated" && !query.has("queueClass");
    })).toBe(true);

    await user.click(screen.getByRole("tab", { name: /Model only\s*796/ }));
    await waitFor(() => {
      expect(seen.some((request) => {
        const query = queryOf(request);
        return query.get("evidenceClass") === "ml_only" && !query.has("queueClass");
      })).toBe(true);
    });

    await user.click(screen.getByRole("tab", { name: /Rule only\s*0/ }));
    await user.click(screen.getByRole("tab", { name: /Not flagged\s*4,004/ }));
    await waitFor(() => {
      const evidence = seen
        .filter((request) => new URL(request.url).pathname === "/api/alerts")
        .map((request) => queryOf(request).get("evidenceClass"));
      expect(evidence).toContain("signature_override");
      expect(evidence).toContain("none");
    });
  });
});
