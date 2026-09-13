/**
 * The two screens an analyst uses to check their own work: Investigations (the verdicts they recorded)
 * and Feedback Impact (what those verdicts did to the queue).
 *
 * Both read the audit trail rather than recomputing anything, so both are pinned to the entry shapes
 * the API actually writes — including the guardrail entry, whose explanation is nested two levels deep
 * inside `details` and is the one string the screen must print verbatim.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import {
  AL_00478_REF,
  FEEDBACK_AUDIT_ENTRY,
  GUARDRAIL_AUDIT_ENTRY,
  SUMMARY,
  auditPage,
} from "./fixtures";

const ANALYST: Session = { username: "g.ang", role: "security_analyst" };

const FLOOR_EXPLANATION = "This alert is Critical, so its score was held at the floor of 70.";

/** Route `/api/audit-log` by the event types asked for, the way the API filters them. */
function stubTrail(entries: readonly Schemas["AuditEntryOut"][]): Request[] {
  return stubFetch((request) => {
    const { pathname, searchParams } = new URL(request.url);
    if (pathname === "/api/dashboard/summary") return jsonResponse(SUMMARY);
    if (pathname === "/api/audit-log") {
      const wanted = searchParams.getAll("eventType");
      return jsonResponse(auditPage(entries.filter((entry) => wanted.includes(entry.eventType))));
    }
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

describe("Investigations", () => {
  it("lists a recorded verdict against the alert it belongs to", async () => {
    stubTrail([FEEDBACK_AUDIT_ENTRY]);
    renderApp("/analyst/investigations", { session: ANALYST });

    expect(await screen.findByRole("heading", { level: 1, name: "Investigations" })).toBeInTheDocument();

    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Verdict" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "False Positive" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "Demo security analyst" })).toBeInTheDocument();

    const link = within(table).getByRole("link");
    expect(link).toHaveAttribute("href", `/analyst/alerts/${AL_00478_REF}`);
    expect(link).toHaveTextContent(AL_00478_REF.slice(0, 8));
  });

  it("says so when no verdict has been recorded", async () => {
    stubTrail([]);
    renderApp("/analyst/investigations", { session: ANALYST });

    expect(await screen.findByText("No verdicts recorded yet")).toBeInTheDocument();
  });
});

describe("Feedback Impact", () => {
  it("counts what the verdicts moved, in three headline numbers", async () => {
    stubTrail([FEEDBACK_AUDIT_ENTRY]);
    renderApp("/analyst/feedback-impact", { session: ANALYST });

    expect(await screen.findByRole("heading", { level: 1, name: "Feedback Impact" })).toBeInTheDocument();
    expect(screen.getByText("Verdicts recorded")).toBeInTheDocument();
    expect(screen.getByText("Alerts moved by feedback")).toBeInTheDocument();
    expect(screen.getByText("Guardrail interventions")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
  });

  it("admits when no family has learned anything yet", async () => {
    // Only guardrail entries exist: the learning query answers with an empty page.
    stubTrail([GUARDRAIL_AUDIT_ENTRY]);
    renderApp("/analyst/feedback-impact", { session: ANALYST });

    expect(await screen.findByText("No family has learned from verdicts yet.")).toBeInTheDocument();
  });

  it("prints the guardrail's own sentence, not a paraphrase", async () => {
    stubTrail([GUARDRAIL_AUDIT_ENTRY]);
    renderApp("/analyst/feedback-impact", { session: ANALYST });

    const heading = await screen.findByRole("heading", { level: 2, name: "Guardrail actions" });
    const section = heading.closest("section");
    if (section === null) throw new Error("no section");

    expect(within(section).getByText(FLOOR_EXPLANATION)).toBeInTheDocument();
    expect(within(section).getByText("Guardrail intervention")).toBeInTheDocument();
    expect(within(section).queryByText("No guardrail has acted yet.")).toBeNull();
  });

  it("keeps the caution about what family learning can promote", async () => {
    stubTrail([FEEDBACK_AUDIT_ENTRY]);
    renderApp("/analyst/feedback-impact", { session: ANALYST });

    expect(
      await screen.findByText(/learning promoted a benign alert to rank 1/),
    ).toBeInTheDocument();
  });
});
