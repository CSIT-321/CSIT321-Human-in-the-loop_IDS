/**
 * S13 — Guardrails.
 *
 * The load-bearing test here is the one that counts PUTs. A form that shows a validation message and
 * sends the request anyway looks identical on screen to one that does not, so every refusal is
 * asserted twice: the message is on screen, and the wire is untouched.
 */

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { ADMIN, GUARDRAILS, GUARDRAIL_ENTRIES, auditPage, guardrailsWith } from "./fixtures";

const FLOOR_BELOW_THRESHOLD = "The critical alert floor must be below the critical alert threshold";
const REASON_TOO_SHORT = "Give a reason of at least 10 characters";
const SAVED = "Saved. The change and its reason are in the audit trail.";
const REASON = "Rehearsal: loosen floor for demo";

interface Stub {
  /** Every request the page made, in order. */
  readonly seen: Request[];
  /** The JSON body of each `PUT /api/config/guardrails`, parsed as the API would receive it. */
  readonly puts: unknown[];
}

/**
 * Route by pathname and method. `PUT` answers with the configuration the API would hold after the one
 * change these tests make — the floor at 65 — so the form's baseline is the server's answer rather
 * than the browser's optimism.
 */
function stubApi(options: { log?: () => Response } = {}): Stub {
  const puts: unknown[] = [];
  const seen = stubFetch(async (request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/config/guardrails" && request.method === "GET") {
      return jsonResponse(GUARDRAILS);
    }
    if (pathname === "/api/config/guardrails" && request.method === "PUT") {
      puts.push(await request.json());
      return jsonResponse(guardrailsWith({ critical_alert_floor: 65 }));
    }
    if (pathname === "/api/audit-log") {
      return options.log?.() ?? jsonResponse(auditPage([], 0));
    }
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
  return { seen, puts };
}

const putCount = (stub: Stub) => stub.seen.filter((request) => request.method === "PUT").length;

async function typeValue(user: ReturnType<typeof userEvent.setup>, label: string, value: string) {
  const input = await screen.findByLabelText(label);
  await user.clear(input);
  await user.type(input, value);
}

describe("admin guardrails: reading the configuration", () => {
  it("fills each editable input from the API", async () => {
    stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    expect(await screen.findByLabelText("Critical alert floor")).toHaveValue(70);
    expect(screen.getByLabelText("Critical alert threshold")).toHaveValue(80);
    expect(screen.getByLabelText("Infiltration alert floor")).toHaveValue(75);
    expect(screen.getByLabelText("Largest increase per verdict")).toHaveValue(20);
    expect(screen.getByLabelText("Largest reduction per verdict")).toHaveValue(30);
    expect(screen.getByLabelText("Reason for this change")).toHaveValue("");
  });

  it("uses the API's own description as each input's help text", async () => {
    stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    expect(
      await screen.findByText("Negative feedback cannot push a Critical alert below this score"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Largest score increase one feedback event may apply"),
    ).toBeInTheDocument();
  });

  it("reports the settings it will not let anyone edit here", async () => {
    stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    const card = (await screen.findByText("Other settings")).closest("section");
    expect(card).not.toBeNull();
    if (card === null) return;

    expect(within(card).getByText("Aggregation min agreement ratio")).toBeInTheDocument();
    expect(within(card).getByText("Learned exception min confidence")).toBeInTheDocument();
    expect(within(card).getByText("0.67")).toBeInTheDocument();
    // The five editable keys belong to the form, and are not repeated in the read-only table.
    for (const label of [
      "Critical alert floor",
      "Critical alert threshold",
      "Infiltration alert floor",
      "Largest increase per verdict",
      "Largest reduction per verdict",
    ]) {
      expect(within(card).queryByText(label)).toBeNull();
    }
  });
});

describe("admin guardrails: refusing a change before it is sent", () => {
  it("refuses a floor at or above the threshold, and sends nothing", async () => {
    const user = userEvent.setup();
    const stub = stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    await typeValue(user, "Critical alert floor", "85");
    await user.type(await screen.findByLabelText("Reason for this change"), REASON);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    const message = await screen.findByText(FLOOR_BELOW_THRESHOLD);
    expect(message.closest('[role="alert"]')).not.toBeNull();
    expect(putCount(stub)).toBe(0);
    expect(screen.queryByText(SAVED)).toBeNull();
  });

  it("asks for a reason of at least ten characters, and sends nothing", async () => {
    const user = userEvent.setup();
    const stub = stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    await typeValue(user, "Critical alert floor", "65");
    await user.type(await screen.findByLabelText("Reason for this change"), "demo");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    const message = await screen.findByText(REASON_TOO_SHORT);
    expect(message.closest('[role="alert"]')).not.toBeNull();
    expect(putCount(stub)).toBe(0);
  });

  it("refuses a submission that changes nothing", async () => {
    const user = userEvent.setup();
    const stub = stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    await screen.findByLabelText("Critical alert floor");
    await user.type(await screen.findByLabelText("Reason for this change"), REASON);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Nothing has changed")).toBeInTheDocument();
    expect(putCount(stub)).toBe(0);
  });
});

describe("admin guardrails: saving a change", () => {
  it("sends only the changed field plus the reason, and confirms the save", async () => {
    const user = userEvent.setup();
    const stub = stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    await typeValue(user, "Critical alert floor", "65");
    await user.type(await screen.findByLabelText("Reason for this change"), REASON);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    const saved = await screen.findByText(SAVED);
    expect(saved).toHaveAttribute("role", "status");
    expect(stub.puts).toEqual([{ criticalAlertFloor: 65, rationale: REASON }]);
    expect(putCount(stub)).toBe(1);
  });

  it("keeps the values the API answered with after a save", async () => {
    const user = userEvent.setup();
    stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    await typeValue(user, "Critical alert floor", "65");
    await user.type(await screen.findByLabelText("Reason for this change"), REASON);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await screen.findByText(SAVED);
    expect(screen.getByLabelText("Critical alert floor")).toHaveValue(65);
    // The reason is cleared with the save: a stale reason would silently authorise the next change.
    expect(screen.getByLabelText("Reason for this change")).toHaveValue("");
  });
});

describe("admin guardrails: the log", () => {
  it("says so when no guardrail has acted yet", async () => {
    stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    expect(await screen.findByText("No guardrail has acted yet.")).toBeInTheDocument();
    expect(
      screen.getByText("Guardrail actions appear here when an analyst verdict is capped or refused."),
    ).toBeInTheDocument();
  });

  it("names each action and quotes the sentence the analyst was given", async () => {
    stubApi({ log: () => jsonResponse(auditPage(GUARDRAIL_ENTRIES, GUARDRAIL_ENTRIES.length)) });
    renderApp("/admin/guardrails", { session: ADMIN });

    expect(await screen.findByText("Capped")).toBeInTheDocument();
    expect(screen.getByText("Refused")).toBeInTheDocument();
    expect(
      screen.getByText("Critical alert held at the floor of 70."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("A signature override is immune to feedback (invariant I3)."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("3f9c1a2b")).toHaveLength(GUARDRAIL_ENTRIES.length);
  });

  it("asks only for the two guardrail event types", async () => {
    const stub = stubApi();
    renderApp("/admin/guardrails", { session: ADMIN });

    await screen.findByText("No guardrail has acted yet.");
    const log = stub.seen.find((request) => new URL(request.url).pathname === "/api/audit-log");
    expect(log).toBeDefined();
    if (log === undefined) return;

    const query = new URL(log.url).searchParams;
    expect(query.getAll("eventType")).toEqual([
      "GUARDRAIL_INTERVENTION",
      "GUARDRAIL_REJECTION",
    ]);
    expect(query.get("limit")).toBe("50");
  });
});
