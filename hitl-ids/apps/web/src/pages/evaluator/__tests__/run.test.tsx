/**
 * S14 — one evaluation run, and the two things this screen exists to get right:
 *
 * 1. An unfavourable delta is shown as measured. Precision@50 fell 1.000 → 0.980 under feedback, the
 *    banner says why in words, and the table prints "−0.020" rather than rounding it into noise.
 * 2. The banner's second sentence is conditional. A screen that printed it unconditionally would be
 *    asserting a result it had not measured, so the flat case is tested too.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import {
  COMPARISON,
  COMPARISON_NO_FALL,
  EVALUATOR,
  RUN_ID,
  SEQUENCE_DIGEST,
} from "./fixtures";

/** U+2212 MINUS SIGN, the one `formatDelta` prints. Written as an escape so the byte cannot drift. */
const MINUS = "−";

function stubApi(comparison: unknown = COMPARISON): void {
  stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (pathname === `/api/evaluation/runs/${RUN_ID}`) return jsonResponse(comparison);
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

const RUN_PATH = `/evaluator/runs/${RUN_ID}`;

describe("evaluator: one run", () => {
  it("heads the page with the run id and links on to the metrics", async () => {
    stubApi();
    renderApp(RUN_PATH, { session: EVALUATOR });

    expect(
      await screen.findByRole("heading", { level: 1, name: `Evaluation run ${RUN_ID}` }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Detection metrics for this run" })).toHaveAttribute(
      "href",
      "/evaluator/metrics",
    );
    expect(screen.getByRole("link", { name: "← All runs" })).toHaveAttribute(
      "href",
      "/evaluator/scenarios",
    );
  });

  it("warns that precision fell under feedback when it did", async () => {
    stubApi();
    renderApp(RUN_PATH, { session: EVALUATOR });

    const banner = await screen.findByRole("note");
    expect(banner).toHaveTextContent(
      "Deltas are shown as measured, including those that went the wrong way.",
    );
    expect(banner).toHaveTextContent(/Precision fell under feedback/);
  });

  it("keeps the second sentence out when no precision@k fell", async () => {
    stubApi(COMPARISON_NO_FALL);
    renderApp(RUN_PATH, { session: EVALUATOR });

    const banner = await screen.findByRole("note");
    expect(banner).toHaveTextContent(
      "Deltas are shown as measured, including those that went the wrong way.",
    );
    expect(within(banner).queryByText(/Precision fell under feedback/)).toBeNull();
  });

  it("renders precision@50's fall to three decimals, in every group that reports it", async () => {
    stubApi();
    renderApp(RUN_PATH, { session: EVALUATOR });

    await screen.findByRole("note");
    // B−A and C−A both report the fall; C−B is flat at zero.
    expect(screen.getAllByText(`${MINUS}0.020`)).toHaveLength(2);
    expect(screen.getAllByText("±0.000").length).toBeGreaterThan(0);
  });

  it("names each delta group rather than printing its key", async () => {
    stubApi();
    renderApp(RUN_PATH, { session: EVALUATOR });

    expect(
      await screen.findByRole("heading", { level: 3, name: `Treatment ${MINUS} Control` }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: `Guardrails off ${MINUS} Control` }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: `Guardrails off ${MINUS} Treatment` }),
    ).toBeInTheDocument();
  });

  it("lists all three arms with their feedback and guardrail switches", async () => {
    stubApi();
    renderApp(RUN_PATH, { session: EVALUATOR });

    const control = await screen.findByRole("rowheader", { name: "A-control" });
    const treatment = screen.getByRole("rowheader", { name: "B-treatment" });
    const guardrailsOff = screen.getByRole("rowheader", { name: "C-guardrails-off" });

    expect(control.closest("tr")).toHaveTextContent("1.000");
    expect(treatment.closest("tr")).toHaveTextContent("0.980");
    expect(guardrailsOff.closest("tr")).toHaveTextContent("0.980");
    // The guardrail actions column is the arm's own record, joined: "capped 40", or "none".
    expect(treatment.closest("tr")).toHaveTextContent("capped 40");
    expect(control.closest("tr")).toHaveTextContent("none");
  });

  it("reports the sequence digest truncated to sixteen characters", async () => {
    stubApi();
    renderApp(RUN_PATH, { session: EVALUATOR });

    expect(await screen.findByText(`${SEQUENCE_DIGEST.slice(0, 16)}…`)).toBeInTheDocument();
  });

  it("raises a benign alert that reached the top of the queue", async () => {
    stubApi();
    renderApp(RUN_PATH, { session: EVALUATOR });

    const warnings = await screen.findAllByText(/A benign alert reached rank 1 in /);
    // Both B and C reach rank 1: with the guardrails off the outcome is the same here.
    expect(warnings).toHaveLength(2);
    expect(warnings[0]).toHaveTextContent("A benign alert reached rank 1 in B-treatment.");
  });

  it("shows the guardrail outcomes even though every count is zero", async () => {
    stubApi();
    renderApp(RUN_PATH, { session: EVALUATOR });

    expect(await screen.findByText("Critical floor breaches in B")).toBeInTheDocument();
    expect(screen.getByText("Guardrail pass · B-treatment")).toBeInTheDocument();
    expect(screen.getByText(/a result, not a failed/)).toBeInTheDocument();
  });

  it("shows an error rather than a blank page when the run does not exist", async () => {
    stubFetch(() =>
      jsonResponse(
        { error: { code: "NOT_FOUND", message: "No evaluation run 'nope'" } },
        404,
      ),
    );
    renderApp("/evaluator/runs/nope", { session: EVALUATOR });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No evaluation run 'nope'");
    expect(alert).toHaveTextContent("NOT_FOUND");
  });
});
