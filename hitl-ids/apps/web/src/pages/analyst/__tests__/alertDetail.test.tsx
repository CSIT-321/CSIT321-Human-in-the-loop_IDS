/**
 * The alert detail is the screen the demo stops on: the four evidence panels, each stating what it
 * knows and — where it knows nothing — saying so in the API's own words rather than showing an empty
 * list. Both empty states here are the demo's common case, not an edge case.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import {
  ALERT_DETAIL,
  AL_00478_REF,
  FALSE_POSITIVE_RECORD,
  CAPPED_ADJUSTMENT,
  NO_VERDICT_ADJUSTMENT,
} from "./fixtures";

const ANALYST: Session = { username: "g.ang", role: "security_analyst" };

const HISTORY: Schemas["FeedbackHistory"] = {
  alertRef: AL_00478_REF,
  effective: null,
  events: [],
};

function stubDetail(): Request[] {
  return stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (pathname === `/api/alerts/${AL_00478_REF}`) return jsonResponse(ALERT_DETAIL);
    if (pathname === `/api/alerts/${AL_00478_REF}/score-adjustment`) {
      return jsonResponse(NO_VERDICT_ADJUSTMENT);
    }
    if (pathname === `/api/alerts/${AL_00478_REF}/feedback-history`) return jsonResponse(HISTORY);
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

describe("Alert detail", () => {
  it("heads the page with the flow's short name and shows the four evidence panels", async () => {
    stubDetail();
    renderApp(`/analyst/alerts/${AL_00478_REF}`, { session: ANALYST });

    expect(await screen.findByRole("heading", { level: 1, name: "AL-00478" })).toBeInTheDocument();
    for (const panel of ["Flow", "Signature rules", "Model prediction", "Combined explanation"]) {
      expect(screen.getByRole("heading", { level: 2, name: panel })).toBeInTheDocument();
    }

    expect(screen.getByText("→ Tier 2 candidate")).toBeInTheDocument();
    expect(screen.getByText(AL_00478_REF)).toBeInTheDocument();
  });

  it("reports both scores, and never pretends the detection score moved", async () => {
    stubDetail();
    renderApp(`/analyst/alerts/${AL_00478_REF}`, { session: ANALYST });

    await screen.findByRole("heading", { level: 2, name: "Scores" });
    expect(screen.getAllByText("99.89").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("99.9%").length).toBeGreaterThanOrEqual(1);
  });

  it("shows the API's ML-only note when no rule matched", async () => {
    stubDetail();
    renderApp(`/analyst/alerts/${AL_00478_REF}`, { session: ANALYST });

    expect(await screen.findByText("No rule matched (ML-only alert).")).toBeInTheDocument();
    expect(screen.getByText(/Rules have high precision and low recall/)).toBeInTheDocument();
  });

  it("names what pushed the model towards its prediction, and what pushed away", async () => {
    stubDetail();
    renderApp(`/analyst/alerts/${AL_00478_REF}`, { session: ANALYST });

    expect(await screen.findByRole("heading", { name: "Pushed towards Web Attack" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Pushed away" })).toBeInTheDocument();
    // The chart's axis labels repeat the feature names, so the lists are asserted on their own.
    const towards = screen.getByRole("heading", { name: "Pushed towards Web Attack" }).closest("div");
    if (towards === null) throw new Error("no list container");
    expect(within(towards).getByText("destination_port")).toBeInTheDocument();
    expect(within(towards).getByText("+1.421")).toBeInTheDocument();

    const away = screen.getByRole("heading", { name: "Pushed away" }).closest("div");
    if (away === null) throw new Error("no list container");
    expect(within(away).getByText("total_fwd_packets")).toBeInTheDocument();
    expect(within(away).getByText("−0.317")).toBeInTheDocument();

    expect(screen.getByText("Additivity check passed")).toBeInTheDocument();
  });

  it("keeps the verdict history honest when there is none", async () => {
    stubDetail();
    renderApp(`/analyst/alerts/${AL_00478_REF}`, { session: ANALYST });

    expect(await screen.findByText("No verdicts recorded yet.")).toBeInTheDocument();
  });

  it("lists recorded verdicts oldest first, with the last one in effect", async () => {
    const amended: Schemas["FeedbackRecord"] = {
      ...FALSE_POSITIVE_RECORD,
      feedbackRef: 2,
      category: "confirm_true_positive",
      adjustment: { ...CAPPED_ADJUSTMENT, action: "applied" },
      amendedFrom: 1,
      createdAt: "2026-09-13T09:00:00.000000Z",
    };
    stubFetch((request) => {
      const { pathname } = new URL(request.url);
      if (pathname === `/api/alerts/${AL_00478_REF}`) return jsonResponse(ALERT_DETAIL);
      if (pathname === `/api/alerts/${AL_00478_REF}/score-adjustment`) {
        return jsonResponse(CAPPED_ADJUSTMENT);
      }
      if (pathname === `/api/alerts/${AL_00478_REF}/feedback-history`) {
        return jsonResponse({
          alertRef: AL_00478_REF,
          effective: amended,
          events: [FALSE_POSITIVE_RECORD, amended],
        });
      }
      return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
    });
    renderApp(`/analyst/alerts/${AL_00478_REF}`, { session: ANALYST });

    expect((await screen.findAllByText("False Positive")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Superseded")).toBeInTheDocument();
    expect(screen.getByText("In effect")).toBeInTheDocument();
    expect(screen.getByText(/requested −30\.00 → applied −29\.89 \(capped\)/)).toBeInTheDocument();
  });
});
