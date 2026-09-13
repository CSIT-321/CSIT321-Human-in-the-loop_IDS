/**
 * S13 — System Status.
 *
 * The page has to tell three answers apart, and the third is the one worth testing hardest: a 409
 * from `POST /api/detection/run` is not a failure, it is a fresh database, and it must not render as
 * "something went wrong". It has to name the command that actually builds a run instead.
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { ADMIN, RUN, SUMMARY } from "./fixtures";

const CONFLICT = { error: { code: "CONFLICT", message: "No detection run has been recorded yet." } };

const RUN_COMMAND = "python scripts/run_detection.py";

/**
 * Route by pathname and method, so no test depends on request order. `run` is a factory because a
 * `Response` body can be read once, and the reload test asks for it twice.
 */
function stubApi(run: () => Response = () => jsonResponse(RUN, 202)): Request[] {
  return stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/dashboard/summary" && request.method === "GET") {
      return jsonResponse(SUMMARY);
    }
    if (pathname === "/api/detection/run" && request.method === "POST") return run();
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

describe("admin status: service health", () => {
  it("says the API is answering, and reports the numbers it returned", async () => {
    stubApi();
    renderApp("/admin/status", { session: ADMIN });

    expect(await screen.findByText("API answering")).toBeInTheDocument();
    expect(screen.getByText("Alerts in the database")).toBeInTheDocument();
    expect(screen.getByText("Verdicts recorded")).toBeInTheDocument();
    expect(screen.getByText("Guardrail interventions")).toBeInTheDocument();
    expect(screen.getByText("Checked at")).toBeInTheDocument();
  });
});

describe("admin status: the latest run", () => {
  it("shows the run's model, rule set and status as the API reported them", async () => {
    stubApi();
    renderApp("/admin/status", { session: ADMIN });

    expect(await screen.findByText("xgb-8class-20260911")).toBeInTheDocument();
    expect(screen.getByText("s4b-1")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("20260911")).toBeInTheDocument();
  });

  it("breaks the run down by evidence class and by queue band", async () => {
    stubApi();
    renderApp("/admin/status", { session: ADMIN });

    const evidence = (await screen.findByText("By evidence class")).closest("section");
    const band = screen.getByText("By queue band").closest("section");
    expect(evidence).not.toBeNull();
    expect(band).not.toBeNull();
    if (evidence === null || band === null) return;

    // `ml_only` is a band name and an evidence name: the band's own words win in the band table.
    expect(within(evidence).getByText("Model only")).toBeInTheDocument();
    expect(within(evidence).getByText("Nothing flagged it")).toBeInTheDocument();
    expect(within(band).getByText("Tier 2 candidate")).toBeInTheDocument();
    expect(within(band).getByText("644")).toBeInTheDocument();
  });

  it("says detection is an offline batch, not something this page can start", async () => {
    stubApi();
    renderApp("/admin/status", { session: ADMIN });

    await screen.findByText("xgb-8class-20260911");
    expect(screen.getByText(/Detection is an offline batch/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run detection/i })).toBeNull();
  });

  it("reads a 409 as an empty database, and names the command that fills it", async () => {
    stubApi(() => jsonResponse(CONFLICT, 409));
    renderApp("/admin/status", { session: ADMIN });

    expect(await screen.findByText("No detection run yet")).toBeInTheDocument();
    expect(screen.getByText(/Build one with/)).toBeInTheDocument();
    // Named twice on purpose: once as the way out of the empty state, once in the note below it.
    expect(screen.getAllByText(RUN_COMMAND)).toHaveLength(2);
    expect(screen.queryByText("Something went wrong")).toBeNull();
  });

  it("asks the API again when the administrator presses Check again", async () => {
    const user = userEvent.setup();
    const seen = stubApi();
    renderApp("/admin/status", { session: ADMIN });

    await screen.findByText("xgb-8class-20260911");
    await user.click(screen.getByRole("button", { name: "Check again" }));

    await waitFor(() => {
      const runs = seen.filter((request) => new URL(request.url).pathname === "/api/detection/run");
      expect(runs).toHaveLength(2);
    });
    expect(await screen.findByText("xgb-8class-20260911")).toBeInTheDocument();
  });
});
