/**
 * S13 — Audit Trail.
 *
 * Two things here are contracts rather than presentation. The filters must reach the API in the
 * spelling the API asks for — `eventType=FEEDBACK`, and the day boundaries as fixed-width UTC text,
 * because the API compares those two as strings. And the export must carry every entry the filters
 * match, not the hundred on screen, which is what the Blob assertion pins down.
 */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CSV_HEADER, auditCsv, type AuditEntry } from "../../../features/admin/audit";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { ADMIN, AUDIT_ENTRIES, auditPage } from "./fixtures";

function stubApi(entries = AUDIT_ENTRIES): Request[] {
  return stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/audit-log") return jsonResponse(auditPage(entries, entries.length));
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
  });
}

const auditRequests = (seen: Request[]) =>
  seen.filter((request) => new URL(request.url).pathname === "/api/audit-log");

/** The first of a query's results, or a failure that says the query found nothing at all. */
function first(nodes: readonly HTMLElement[]): HTMLElement {
  const [node] = nodes;
  if (node === undefined) throw new Error("expected at least one element, found none");
  return node;
}

/** The table's rows, so an assertion about "Feedback" means the row and not the filter's option. */
async function entryTable() {
  await screen.findByText("Config change");
  return within(screen.getByRole("table"));
}

describe("admin audit: the trail", () => {
  it("renders each entry as a row, with its event type humanised", async () => {
    stubApi();
    renderApp("/admin/audit", { session: ADMIN });

    const table = await entryTable();
    expect(table.getByText("Config change")).toBeInTheDocument();
    expect(table.getByText("Guardrail intervention")).toBeInTheDocument();
    expect(table.getByText("Similar alert learning")).toBeInTheDocument();
    expect(table.getByText("Feedback")).toBeInTheDocument();
    expect(table.getByText("Detection run")).toBeInTheDocument();
    expect(table.getAllByRole("row")).toHaveLength(AUDIT_ENTRIES.length + 1);
  });

  it("names an actor who has none as the system", async () => {
    stubApi();
    renderApp("/admin/audit", { session: ADMIN });

    const table = await entryTable();
    expect(table.getAllByText("Ada Admin")).toHaveLength(2);
    expect(table.getAllByText("Grace Ang")).toHaveLength(2);
    // The detection run was the batch's own act: it has neither a display name nor a role.
    expect(table.getByText("system")).toBeInTheDocument();
  });

  it("shortens an alert reference and leaves a missing one blank", async () => {
    stubApi();
    renderApp("/admin/audit", { session: ADMIN });

    const table = await entryTable();
    expect(table.getAllByText("3f9c1a2b")).toHaveLength(2);
    expect(table.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("folds the details blob into a disclosure rather than into columns", async () => {
    stubApi();
    renderApp("/admin/audit", { session: ADMIN });

    const table = await entryTable();
    const disclosure = first(table.getAllByText("View"));
    expect(disclosure.tagName).toBe("SUMMARY");
    expect(disclosure.parentElement?.tagName).toBe("DETAILS");

    // The first row is the configuration change, and its blob is shown as the API stored it.
    const json = disclosure.parentElement?.querySelector("pre")?.textContent ?? "";
    const parsed: unknown = JSON.parse(json);
    expect(parsed).toEqual({
      changes: { critical_alert_floor: 65 },
      rationale: "Rehearsal: loosen floor for demo",
    });
  });

  it("reports the total it is paging through", async () => {
    stubApi();
    renderApp("/admin/audit", { session: ADMIN });

    expect(await screen.findByText(`Showing 1–${AUDIT_ENTRIES.length} of ${AUDIT_ENTRIES.length}`)).toBeInTheDocument();
  });

  it("says so when the filters match nothing", async () => {
    stubApi([]);
    renderApp("/admin/audit", { session: ADMIN });

    expect(await screen.findByText("No audit entries match these filters")).toBeInTheDocument();
  });
});

describe("admin audit: filters", () => {
  it("offers every event type the contract defines, and asks for the chosen one", async () => {
    const user = userEvent.setup();
    const seen = stubApi();
    renderApp("/admin/audit", { session: ADMIN });

    const select = await screen.findByLabelText("Event type");
    expect(within(select).getAllByRole("option")).toHaveLength(16); // All events + 15 types
    expect(within(select).getByRole("option", { name: "Feedback amend" })).toBeInTheDocument();

    await user.selectOptions(select, "FEEDBACK");

    await waitFor(() => {
      const last = auditRequests(seen).at(-1);
      expect(last).toBeDefined();
      expect(new URL(last?.url ?? "").searchParams.get("eventType")).toBe("FEEDBACK");
    });
  });

  it("sends a day filter as the fixed-width UTC bounds the API compares", async () => {
    const seen = stubApi();
    renderApp("/admin/audit", { session: ADMIN });
    await screen.findByText("Config change");

    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-11" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-09-12" } });

    await waitFor(() => {
      const last = auditRequests(seen).at(-1);
      const query = new URL(last?.url ?? "").searchParams;
      expect(query.get("since")).toBe("2026-09-11T00:00:00.000000Z");
      expect(query.get("until")).toBe("2026-09-12T23:59:59.999999Z");
    });
  });

  it("clears the filters again", async () => {
    const user = userEvent.setup();
    const seen = stubApi();
    renderApp("/admin/audit", { session: ADMIN });

    await user.selectOptions(await screen.findByLabelText("Event type"), "FEEDBACK");
    await waitFor(() => expect(auditRequests(seen).length).toBeGreaterThan(1));

    await user.click(screen.getByRole("button", { name: "Clear filters" }));

    await waitFor(() => {
      const last = auditRequests(seen).at(-1);
      const query = new URL(last?.url ?? "").searchParams;
      expect(query.get("eventType")).toBeNull();
      expect(screen.getByLabelText("Event type")).toHaveValue("");
    });
  });
});

describe("admin audit: the CSV export", () => {
  it("hands a blob of the whole trail to the browser, and revokes its URL", async () => {
    const user = userEvent.setup();
    stubApi();

    const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:audit-log");
    const revokeObjectURL = vi.fn<(url: string) => void>();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, writable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, writable: true, value: revokeObjectURL });

    renderApp("/admin/audit", { session: ADMIN });
    await screen.findByText("Config change");

    await user.click(screen.getByRole("button", { name: "Export CSV" }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:audit-log");

    const blob = createObjectURL.mock.calls[0]?.[0];
    if (blob === undefined) throw new Error("no Blob reached URL.createObjectURL");
    expect(blob.type).toBe("text/csv");

    const lines = (await blob.text()).split("\n");
    expect(lines[0]).toBe(CSV_HEADER);
    expect(lines.filter((line) => line !== "")).toHaveLength(AUDIT_ENTRIES.length + 1);
    expect(lines[1]).toContain('"CONFIG_CHANGE"');
    expect(lines[1]).toContain('"Ada Admin"');
  });

  it("exports what the filters match, at the export page size", async () => {
    const user = userEvent.setup();
    const seen = stubApi();
    const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:audit-log");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, writable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, writable: true, value: vi.fn() });

    renderApp("/admin/audit", { session: ADMIN });
    await user.selectOptions(await screen.findByLabelText("Event type"), "FEEDBACK");
    await waitFor(() => expect(auditRequests(seen).length).toBeGreaterThan(1));

    const before = auditRequests(seen).length;
    await user.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));

    const exported = auditRequests(seen).slice(before).at(-1);
    const query = new URL(exported?.url ?? "").searchParams;
    expect(query.get("limit")).toBe("500");
    expect(query.get("eventType")).toBe("FEEDBACK");
  });
});

describe("the export's escaping", () => {
  it("doubles quotes, and quotes every field", () => {
    const awkward: AuditEntry = {
      eventId: 7,
      eventType: "CONFIG_CHANGE",
      actor: { displayName: 'Grace "G" Ang', role: "system_admin", userId: 2 },
      alertRef: null,
      rationale: 'Rehearsal, second pass: raise the cap by "10"',
      details: null,
      createdAt: "2026-09-12T10:00:00.000000Z",
    };

    expect(auditCsv([awkward])).toBe(
      `${CSV_HEADER}\n` +
        '"7","2026-09-12T10:00:00.000000Z","CONFIG_CHANGE","system_admin","Grace ""G"" Ang","","Rehearsal, second pass: raise the cap by ""10""",""\n',
    );
  });
});
