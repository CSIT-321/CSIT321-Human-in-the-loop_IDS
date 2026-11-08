import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../api/client";
import { QueueItem, queueViews } from "./OperationalQueue";

// C2 (screen review pack, approved 2026-11-08): row badges and the two new tab filters.
const reason = "E3: score 100 and Botnet has attack severity 9. A Tier 1 analyst confirms before escalation. (5 of 5 members; first shown.)";
function row(over: Partial<Schemas["RoutingView"]> = {}, state: Partial<Schemas["RoutingView"]["state"]> = {}) {
  return { operationalAlertRef: "c2", title: "Botnet group", detectorName: "XGBoost", detectorSource: "current_flow",
    stateVersion: "a".repeat(64), reviewReasons: [], latestDecision: null, allowedActions: [], tier2RecommendationOpen: false,
    groupMemberCount: null, ...over,
    state: { operationalAlertId: 1, decisionSource: "system_policy", operationalPriority: 100, priorityBand: "P1", reviewRequired: true,
      handlingRoute: "tier1_review", workflowStage: "triage", tier2Recommended: false, tier2RecommendationReasons: [], ...state },
  } as unknown as Schemas["RoutingView"];
}

describe("C2 queue rows and tabs", () => {
  it("shows the TIER 2 RECOMMENDED strip with the first reason only while the recommendation is open", () => {
    const { rerender } = render(<QueueItem item={row({ tier2RecommendationOpen: true }, { tier2Recommended: true, tier2RecommendationReasons: [reason, "Second"] })} />);
    expect(screen.getByText("TIER 2 RECOMMENDED")).toBeVisible();
    expect(screen.getByText(reason)).toBeVisible();
    expect(screen.queryByText("Second")).not.toBeInTheDocument();
    // After "Keep in Tier 1" the stored flag stays, but the recommendation is closed: no strip.
    rerender(<QueueItem item={row({ tier2RecommendationOpen: false }, { tier2Recommended: true, tier2RecommendationReasons: [reason], decisionSource: "analyst" })} />);
    expect(screen.queryByText("TIER 2 RECOMMENDED")).not.toBeInTheDocument();
  });

  it("names a group by its size and says nothing for a single", () => {
    const { rerender } = render(<QueueItem item={row({ groupMemberCount: 5 })} />);
    expect(screen.getByText(/Group of 5/)).toBeVisible();
    rerender(<QueueItem item={row({ groupMemberCount: 1 })} />);
    expect(screen.getByText(/Group of 1/)).toBeVisible();
    rerender(<QueueItem item={row()} />);
    expect(screen.queryByText(/Group of/)).not.toBeInTheDocument();
  });

  it("labels an auto-escalated Tier 2 case apart from a manual one", () => {
    const system = { routeClass: "CRITICAL_ESCALATION", route: "tier2_case", decisionSource: "system_policy", policyVersion: "v", reasons: [] };
    const { rerender } = render(<QueueItem item={row({ systemRouting: system } as never, { handlingRoute: "tier2_case" })} />);
    expect(screen.getByText("Auto-escalated")).toBeVisible();
    rerender(<QueueItem item={row({ systemRouting: system } as never, { handlingRoute: "tier2_case", decisionSource: "analyst" })} />);
    expect(screen.getByText("Manual Override")).toBeVisible();
    expect(screen.queryByText("Auto-escalated")).not.toBeInTheDocument();
  });

  it("asks the server for the C3 rule and for system-opened cases", () => {
    const byKey = Object.fromEntries(queueViews.map(view => [view.key, view.query]));
    expect(byKey["tier2-candidates"]).toEqual({ tier2Candidate: true, workScope: "active" });
    expect(byKey["auto-escalated"]).toEqual({ handlingRoute: "tier2_case", decisionSource: "system_policy" });
  });
});
