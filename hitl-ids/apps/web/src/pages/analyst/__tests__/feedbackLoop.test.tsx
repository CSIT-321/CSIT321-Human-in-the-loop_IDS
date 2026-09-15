/**
 * The plan's end-to-end check, at component level: a verdict moves the score, a guardrail bounds
 * how far, and the bound is still there after a reload.
 *
 * This is the loop the project exists to demonstrate, so the test drives it the way the demo does —
 * open the alert, choose "Mark false positive" on a Critical flow, submit — and then reads the four
 * things a sceptical viewer would ask for:
 *
 *   1. the request that went out (`category`, `note`),
 *   2. the guardrail's own sentence, printed rather than inferred,
 *   3. the operational score at 70.00, not the 69.89 the arithmetic alone would give,
 *   4. the same numbers again after a fresh mount, because a bound that evaporates on reload is
 *      not a bound.
 *
 * The stub is a mutable object standing in for the server: the POST mutates it, and the three GETs
 * read it back, which is what makes step 4 a real check rather than a re-render.
 */

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import {
  ALERT_DETAIL,
  AL_00478_REF,
  CAPPED_ADJUSTMENT,
  FALSE_POSITIVE_RECORD,
  NO_VERDICT_ADJUSTMENT,
} from "./fixtures";

const ANALYST: Session = { username: "g.ang", displayName: "Glenn Ang", role: "security_analyst", token: "test-token" };

const FLOOR_EXPLANATION = "This alert is Critical, so its score was held at the floor of 70.";

/** The server's state, as the four endpoints see it. */
interface Server {
  alert: Schemas["AlertSummary"];
  adjustment: Schemas["ScoreAdjustment"];
  history: Schemas["FeedbackHistory"];
  /** Bodies the client sent to the feedback endpoint, parsed. */
  readonly posted: unknown[];
}

function newServer(): Server {
  return {
    alert: { ...ALERT_DETAIL.alert },
    adjustment: NO_VERDICT_ADJUSTMENT,
    history: { alertRef: AL_00478_REF, effective: null, events: [] },
    posted: [],
  };
}

/** Record a verdict: the same state change the API makes, including the guardrail's bound. */
function recordFalsePositive(server: Server): Schemas["FeedbackResponse"] {
  server.alert = {
    ...server.alert,
    combinedScore: CAPPED_ADJUSTMENT.scoreAfter,
    requiresReview: CAPPED_ADJUSTMENT.requiresReview,
    hasFeedback: true,
  };
  server.adjustment = CAPPED_ADJUSTMENT;
  server.history = {
    alertRef: AL_00478_REF,
    effective: FALSE_POSITIVE_RECORD,
    events: [FALSE_POSITIVE_RECORD],
  };
  return {
    alert: server.alert,
    feedback: FALSE_POSITIVE_RECORD,
    family: {
      familyKey: null,
      gateOpen: false,
      gateReason: "1 learning verdict in this family; 3 are needed.",
      membersMoved: 0,
    },
    auditEventIds: [41, 42],
  };
}

function stubServer(server: Server): Request[] {
  return stubFetch(async (request) => {
    const { pathname } = new URL(request.url);
    if (pathname === `/api/alerts/${AL_00478_REF}/feedback` && request.method === "POST") {
      server.posted.push(await request.clone().json());
      return jsonResponse(recordFalsePositive(server));
    }
    if (pathname === `/api/alerts/${AL_00478_REF}/score-adjustment`) {
      return jsonResponse(server.adjustment);
    }
    if (pathname === `/api/alerts/${AL_00478_REF}/feedback-history`) {
      return jsonResponse(server.history);
    }
    if (pathname === `/api/alerts/${AL_00478_REF}`) {
      return jsonResponse({
        ...ALERT_DETAIL,
        alert: server.alert,
        currentFeedback: server.history.effective,
        feedbackCount: (server.history.events ?? []).length,
      });
    }
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

/** The `<section>` a card's `<h2>` heads, so assertions can be scoped to one card. */
function cardByHeading(name: string): HTMLElement {
  const heading = screen.getByRole("heading", { level: 2, name });
  const section = heading.closest("section");
  if (section === null) throw new Error(`No <section> around the "${name}" heading`);
  return section;
}

describe("The feedback loop", () => {
  it("records a verdict, shows the guardrail that bounded it, and keeps the bound across a reload", async () => {
    const user = userEvent.setup();
    const server = newServer();
    stubServer(server);

    const first = renderApp(`/analyst/alerts/${AL_00478_REF}`, { session: ANALYST });
    await screen.findByRole("heading", { level: 1, name: "AL-00478" });

    // Before the verdict: the operational score is still the detection score, and nothing is bound.
    expect(within(cardByHeading("Score adjustment")).getByText("Applied as requested")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /False Positive/ }));
    await user.click(screen.getByRole("button", { name: "Record verdict" }));

    // 1. The request. No note was typed, so the contract's nullable note goes out as null.
    expect(await screen.findByText("Verdict recorded")).toBeInTheDocument();
    expect(server.posted).toEqual([{ category: "mark_false_positive", note: null }]);

    // 2. The guardrail, in the API's own sentence — printed, never inferred from the numbers.
    const outcome = screen.getByRole("region", { name: "Verdict outcome" });
    expect(within(outcome).getByText("Capped by a guardrail")).toBeInTheDocument();
    expect(within(outcome).getByText(FLOOR_EXPLANATION)).toBeInTheDocument();

    // The refetch that follows the verdict must not blank the page: the outcome is in the form's own
    // state, and a full-page spinner would unmount it at the moment it is meant to be read.
    expect(screen.queryByText("Loading…")).toBeNull();

    // 3. The bound held: 70.00, not the 69.89 the requested delta alone would give.
    expect(await within(cardByHeading("Scores")).findByText("70.00")).toBeInTheDocument();

    // 4. A fresh mount reads the same state back from the server.
    first.unmount();
    renderApp(`/analyst/alerts/${AL_00478_REF}`, { session: ANALYST });
    await screen.findByRole("heading", { level: 1, name: "AL-00478" });

    const scores = cardByHeading("Scores");
    expect(within(scores).getByText("70.00")).toBeInTheDocument();
    expect(within(scores).getByText("−29.89")).toBeInTheDocument();

    const adjustment = cardByHeading("Score adjustment");
    expect(within(adjustment).getByText("Capped by a guardrail")).toBeInTheDocument();
    expect(within(adjustment).getByText(FLOOR_EXPLANATION)).toBeInTheDocument();

    const history = cardByHeading("Verdict history");
    expect(within(history).getByText("False Positive")).toBeInTheDocument();
    expect(within(history).getByText("In effect")).toBeInTheDocument();
    expect(
      within(history).getByText(/requested −30\.00 → applied −29\.89 \(capped\)/),
    ).toBeInTheDocument();
  });
});
