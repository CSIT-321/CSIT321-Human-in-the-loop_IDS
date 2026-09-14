/**
 * The Overview page reads the recorded corpus from the API and prints it three ways: a table under
 * every chart, an entity link on every address, and an on-screen label on every raw enum key.
 *
 * These tests pin that contract — a link where there is a page to open and plain text where there is
 * not, the verdict labels rather than `mark_false_positive`, and the loading/error/empty states the
 * page owes a viewer when the database is mid-build.
 */

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { BREAKDOWNS, SUMMARY } from "./fixtures";

const ANALYST: Session = { username: "g.ang", role: "security_analyst" };

function stubOverview(handler: (request: Request) => Response | undefined): Request[] {
  return stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/dashboard/breakdowns") return handler(request) ?? jsonResponse(BREAKDOWNS);
    if (pathname === "/api/dashboard/summary") return jsonResponse(SUMMARY);
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

/** The `section` a card renders, found by its heading. */
async function card(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole("heading", { level: 2, name });
  const section = heading.closest("section");
  if (section === null) throw new Error(`no section for ${name}`);
  return section;
}

describe("Overview", () => {
  it("says which detection run the recorded flows came from", async () => {
    stubOverview(() => undefined);
    renderApp("/analyst/overview", { session: ANALYST });

    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
    // The run id lives in the summary, which lands after the heading does.
    expect(await screen.findByText("Recorded flows · detection run #3")).toBeInTheDocument();
  });

  it("links each top source address to its entity page and prints its flow count", async () => {
    stubOverview(() => undefined);
    renderApp("/analyst/overview", { session: ANALYST });

    const section = await card("Top source addresses");
    expect(within(section).getByRole("columnheader", { name: "Address" })).toBeInTheDocument();

    const link = await within(section).findByRole("link", { name: "18.219.193.20" });
    expect(link).toHaveAttribute("href", "/analyst/entities/ip/18.219.193.20");

    const row = link.closest("tr");
    if (row === null) throw new Error("no row");
    // This address's Flows and Flagged counts are both 197, so the number appears in both cells.
    expect(within(row).getAllByText("197").length).toBe(2);
  });

  it("prints destination ports as text, because a port has no page to open", async () => {
    stubOverview(() => undefined);
    renderApp("/analyst/overview", { session: ANALYST });

    const section = await card("Top destination ports");
    expect(within(section).getByRole("columnheader", { name: "Port" })).toBeInTheDocument();
    expect(await within(section).findByRole("rowheader", { name: "8080" })).toBeInTheDocument();
    expect(within(section).queryByRole("link", { name: "8080" })).toBeNull();
  });

  it("names verdicts with their on-screen labels, never the raw API key", async () => {
    stubOverview(() => undefined);
    renderApp("/analyst/overview", { session: ANALYST });

    const section = await card("Verdicts in force");
    expect(
      await within(section).findByRole("rowheader", { name: "False Positive" }),
    ).toBeInTheDocument();
    expect(within(section).getByRole("rowheader", { name: "True Positive" })).toBeInTheDocument();
    expect(screen.queryByText(/mark_false_positive/)).toBeNull();
  });

  it("names guardrail interventions the same way", async () => {
    stubOverview(() => undefined);
    renderApp("/analyst/overview", { session: ANALYST });

    const section = await card("Guardrail interventions");
    expect(
      await within(section).findByRole("rowheader", { name: "Critical alert floor" }),
    ).toBeInTheDocument();
    expect(within(section).getByRole("columnheader", { name: "Times applied" })).toBeInTheDocument();
  });

  it("repeats the capture-hour histogram as a table as well as a chart", async () => {
    stubOverview(() => undefined);
    renderApp("/analyst/overview", { session: ANALYST });

    const section = await card("Flow volume by capture hour");
    const table = within(section).getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Hour" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Flows" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Flagged" })).toBeInTheDocument();
    expect(
      await within(table).findByRole("rowheader", { name: "2018-02-14 15:00" }),
    ).toBeInTheDocument();
  });

  it("explains itself when no verdict or guardrail has been recorded yet", async () => {
    const noVerdicts: Schemas["DashboardBreakdowns"] = {
      ...BREAKDOWNS,
      verdictMix: {},
      guardrailInterventions: {},
    };
    stubOverview(() => jsonResponse(noVerdicts));
    renderApp("/analyst/overview", { session: ANALYST });

    const verdicts = await card("Verdicts in force");
    expect(await within(verdicts).findByText("No verdicts recorded yet")).toBeInTheDocument();

    const guardrails = await card("Guardrail interventions");
    expect(
      await within(guardrails).findByText("No guardrail has intervened yet"),
    ).toBeInTheDocument();
  });

  it("shows the API's error and refetches when Try again is pressed", async () => {
    const user = userEvent.setup();
    let breakdownCalls = 0;
    const seen = stubOverview(() => {
      breakdownCalls += 1;
      if (breakdownCalls === 1) {
        return jsonResponse(
          { error: { code: "SERVICE_UNAVAILABLE", message: "The database is not ready yet." } },
          503,
        );
      }
      return undefined;
    });
    renderApp("/analyst/overview", { session: ANALYST });

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("The database is not ready yet.")).toBeInTheDocument();
    expect(within(alert).getByText("SERVICE_UNAVAILABLE · HTTP 503")).toBeInTheDocument();

    await user.click(within(alert).getByRole("button", { name: "Try again" }));

    expect(
      await screen.findByRole("heading", { level: 2, name: "Top source addresses" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      seen.filter((request) => new URL(request.url).pathname === "/api/dashboard/breakdowns").length,
    ).toBe(2);
  });

  it("tells the reader how to fill an empty database", async () => {
    stubOverview(() =>
      jsonResponse({
        ...BREAKDOWNS,
        flowTimeHistogram: [],
        topSourceIps: [],
        topDestinationIps: [],
        topDestinationPorts: [],
      }),
    );
    renderApp("/analyst/overview", { session: ANALYST });

    expect(await screen.findByText("No alerts yet")).toBeInTheDocument();
    expect(screen.getByText(/python scripts\/run_detection\.py/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Top source addresses" })).toBeNull();
  });
});
