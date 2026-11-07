import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Schemas } from "../../api/client";
import { jsonResponse, stubFetch } from "../../test/renderApp";
import { ClaimedAlerts } from "./ClaimedAlerts";

// Admin claimed-alerts list (user decision 2026-11-08): the admin's only way to the Release (admin) button.
type Work = Schemas["WorkView"];
const claimed = (ref: string, owner: string, extra: Partial<Work> = {}) => ({
  operationalAlertRef: ref, title: `Alert ${owner}`,
  work: { status: "in_review", revision: 2, canClaim: false, canMutate: false, isOwner: false, canRelease: true,
    releaseReasonRequired: true, idle: false, explanation: `In Review — ${owner}`, claimedAt: "2026-11-08T01:00:00Z",
    finishedAt: null, finishedByActorId: null, finishedByName: null, ownerActorId: 1, ownerName: owner,
    roundRef: null, verdictRef: null, verdictOutcome: null, ...extra } as Work,
});
const A = "aaaaaaaa-1111-4111-8111-111111111111";
const B = "bbbbbbbb-2222-4222-8222-222222222222";

afterEach(() => vi.unstubAllGlobals());

function setup(items: ReturnType<typeof claimed>[], total = items.length) {
  let rows = [...items];
  let released = false;
  const seen = stubFetch(async request => {
    const url = new URL(request.url);
    if (url.pathname === "/api/v2/alerts") return jsonResponse({ items: rows, page: { total: released ? rows.length : total, limit: 50, offset: 0, returned: rows.length } });
    if (url.pathname.endsWith("/work/release")) {
      released = true;
      rows = rows.filter(row => !url.pathname.includes(row.operationalAlertRef));
      return jsonResponse({ replayed: false, work: { ...items[0]!.work, status: "available", canRelease: false } });
    }
    return jsonResponse({ error: { code: "NOT_FOUND", message: url.pathname } }, 404);
  });
  return seen;
}

describe("admin claimed-alerts list", () => {
  it("asks the server for claimed alerts only and shows owner and idle state per row", async () => {
    const seen = setup([claimed(A, "Alice", { idle: true }), claimed(B, "Bob")]);
    render(<ClaimedAlerts />);
    const list = await screen.findByRole("list", { name: "Claimed alerts" });
    expect(new URL(seen[0]!.url).searchParams.get("workScope")).toBe("in_review");
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Alice");
    expect(rows[0]).toHaveTextContent(/idle/i);
    expect(rows[1]).toHaveTextContent("Bob");
    expect(rows[1]).not.toHaveTextContent(/idle/i);
    expect(within(rows[0]!).getByRole("button", { name: "Release (admin)" })).toBeVisible();
  });

  it("releases one row with a required reason and reloads the list", async () => {
    const seen = setup([claimed(A, "Alice"), claimed(B, "Bob")]);
    const onReleased = vi.fn();
    const user = userEvent.setup();
    render(<ClaimedAlerts onReleased={onReleased} />);
    const list = await screen.findByRole("list", { name: "Claimed alerts" });
    const row = within(list).getAllByRole("listitem")[0]!;
    await user.click(within(row).getByRole("button", { name: "Release (admin)" }));
    const confirm = within(row).getByRole("button", { name: "Release" });
    expect(confirm).toBeDisabled();
    await user.type(within(row).getByLabelText(/Reason/), "Alice is off shift");
    await user.click(confirm);
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Claimed alerts" })).getAllByRole("listitem")).toHaveLength(1));
    const release = seen.find(request => request.url.endsWith("/work/release"))!;
    expect(new URL(release.url).pathname).toBe(`/api/v2/alerts/${A}/work/release`);
    expect(await release.json()).toMatchObject({ reason: "Alice is off shift", expectedRevision: 2 });
    expect(onReleased).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("list", { name: "Claimed alerts" })).not.toHaveTextContent("Alice");
  });

  it("hides the button on a row the server does not allow", async () => {
    setup([claimed(A, "Alice", { canRelease: false })]);
    render(<ClaimedAlerts />);
    const list = await screen.findByRole("list", { name: "Claimed alerts" });
    expect(within(list).queryByRole("button", { name: /Release/ })).toBeNull();
  });

  it("says so when no alert is claimed", async () => {
    setup([]);
    render(<ClaimedAlerts />);
    expect(await screen.findByText("No alert is claimed.")).toBeVisible();
  });

  it("says when the list shows only part of the claimed alerts", async () => {
    setup([claimed(A, "Alice")], 73);
    render(<ClaimedAlerts />);
    expect(await screen.findByText("Showing 1 of 73 claimed alerts.")).toBeVisible();
  });
});
