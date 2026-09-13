/**
 * S14 — the scenario list: the committed runs, the pre-registration behind the newest one, and the
 * scenario rows the demo database does not hold.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { EVALUATOR, NO_RUNS_PAGE, RUNS_PAGE, RUN_ID, SCENARIOS_PAGE } from "./fixtures";

/** Route by pathname, so a test never depends on request order. */
function stubApi(overrides: { runs?: unknown } = {}): void {
  stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/evaluation/runs") return jsonResponse(overrides.runs ?? RUNS_PAGE);
    if (pathname === "/api/evaluation/scenarios") return jsonResponse(SCENARIOS_PAGE);
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

describe("evaluator: scenarios", () => {
  it("links the committed run to its own page", async () => {
    stubApi();
    renderApp("/evaluator/scenarios", { session: EVALUATOR });

    const link = await screen.findByRole("link", { name: RUN_ID });
    expect(link).toHaveAttribute("href", `/evaluator/runs/${RUN_ID}`);
  });

  it("shows the newest run's pre-registration rule", async () => {
    stubApi();
    renderApp("/evaluator/scenarios", { session: EVALUATOR });

    expect(
      await screen.findByRole("heading", { level: 2, name: "Pre-registration" }),
    ).toBeInTheDocument();
    expect(screen.getByText("s15-preregistration-1")).toBeInTheDocument();
    expect(
      screen.getByText(/the result could not be tuned after it was seen/),
    ).toBeInTheDocument();
  });

  it("lists the arms and the detection-identical verdict of the run", async () => {
    stubApi();
    renderApp("/evaluator/scenarios", { session: EVALUATOR });

    const row = (await screen.findByRole("link", { name: RUN_ID })).closest("tr");
    expect(row).not.toBeNull();
    expect(row).toHaveTextContent("A-control · B-treatment · C-guardrails-off");
    expect(row).toHaveTextContent("Yes");
  });

  it("explains why the demo database holds no scenario rows", async () => {
    stubApi();
    renderApp("/evaluator/scenarios", { session: EVALUATOR });

    expect(
      await screen.findByText(/each arm ran against its own copy of the database/),
    ).toBeInTheDocument();
  });

  it("says so when no run has been recorded", async () => {
    stubApi({ runs: NO_RUNS_PAGE });
    renderApp("/evaluator/scenarios", { session: EVALUATOR });

    expect(await screen.findByText("No evaluation runs recorded")).toBeInTheDocument();
    // No run means no pre-registration to show.
    expect(screen.queryByRole("heading", { level: 2, name: "Pre-registration" })).toBeNull();
  });
});
