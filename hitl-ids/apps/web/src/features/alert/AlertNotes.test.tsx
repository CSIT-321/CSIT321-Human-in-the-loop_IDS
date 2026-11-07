import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Schemas } from "../../api/client";
import { jsonResponse, stubFetch } from "../../test/renderApp";
import { AlertNotes } from "./AlertNotes";

// C6 (decision Q7 option A, layout approved 2026-11-08): append-only notes in History & Notes. Only the claim owner adds.
type Work = Schemas["WorkView"];
const REF = "aaaaaaaa-1111-4111-8111-111111111111";
const note = (id: number, actorName: string, body: string) =>
  ({ id, actorId: id, actorName, body, createdAt: `2026-11-08T0${id}:00:00.000000Z` });
const work = (extra: Partial<Work> = {}) => ({ status: "in_review", revision: 1, isOwner: true, canMutate: true,
  canClaim: false, canRelease: true, releaseReasonRequired: false, idle: false, explanation: "In Review — You", ...extra } as Work);

afterEach(() => vi.unstubAllGlobals());

function setup(initial: ReturnType<typeof note>[], post?: (body: { requestId: string; body: string }) => Response | Promise<Response>) {
  const rows = [...initial];
  return stubFetch(async request => {
    const url = new URL(request.url);
    if (url.pathname !== `/api/v2/alerts/${REF}/notes`) return jsonResponse({ error: { code: "NOT_FOUND", message: url.pathname } }, 404);
    if (request.method === "GET") return jsonResponse(rows);
    const body = await request.clone().json();
    if (post) return post(body);
    const created = note(rows.length + 1, "Glenn Ang", body.body);
    rows.push(created);
    return jsonResponse({ replayed: false, note: created });
  });
}

describe("Tier 1 investigation notes", () => {
  it("lists notes oldest first with author and time, for every reader", async () => {
    setup([note(1, "Glenn Ang", "Source host is the lab scanner."), note(2, "LIOW CHEE KUANG", "Confirmed by IT ticket 4471.")]);
    render(<AlertNotes alertRef={REF} work={work({ isOwner: false, canMutate: false })} />);
    const list = await screen.findByRole("list", { name: "Investigation notes" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Glenn Ang");
    expect(rows[0]).toHaveTextContent("Source host is the lab scanner.");
    expect(rows[1]).toHaveTextContent("LIOW CHEE KUANG");
    expect(rows[0]!.querySelector("time")).toHaveAttribute("datetime", "2026-11-08T01:00:00.000000Z");
  });

  it("shows the add form only to the claim owner", async () => {
    setup([]);
    const { unmount } = render(<AlertNotes alertRef={REF} work={work({ isOwner: false, canMutate: false })} />);
    expect(await screen.findByText("No notes yet.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add note" })).toBeNull();
    expect(screen.getByText(/Only the analyst who owns this alert can add a note/)).toBeVisible();
    unmount();
    render(<AlertNotes alertRef={REF} work={null} />);
    expect(await screen.findByText("No notes yet.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add note" })).toBeNull();
  });

  it("the owner adds a note; it appears at the end and the box clears", async () => {
    const seen = setup([note(1, "Glenn Ang", "First")]);
    const user = userEvent.setup();
    render(<AlertNotes alertRef={REF} work={work()} />);
    await screen.findByRole("list", { name: "Investigation notes" });
    const add = screen.getByRole("button", { name: "Add note" });
    expect(add).toBeDisabled();
    await user.type(screen.getByLabelText("New note"), "  Asked IT to confirm.  ");
    await user.click(add);
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Investigation notes" })).getAllByRole("listitem")).toHaveLength(2));
    expect(within(screen.getByRole("list", { name: "Investigation notes" })).getAllByRole("listitem")[1]).toHaveTextContent("Asked IT to confirm.");
    expect(screen.getByLabelText("New note")).toHaveValue("");
    const posted = seen.find(request => request.method === "POST")!;
    expect(await posted.json()).toMatchObject({ body: "Asked IT to confirm." });
    expect(screen.getByText("Notes cannot be edited or deleted.")).toBeVisible();
  });

  it("keeps the text and the request id when the add fails, and shows the server message", async () => {
    const ids: string[] = [];
    let fail = true;
    setup([], body => {
      ids.push(body.requestId);
      if (fail) { fail = false; return jsonResponse({ error: { code: "WORK_RETRY", message: "Could not be confirmed. Retry." } }, 409); }
      return jsonResponse({ replayed: false, note: note(1, "Glenn Ang", body.body) });
    });
    const user = userEvent.setup();
    render(<AlertNotes alertRef={REF} work={work()} />);
    await screen.findByText("No notes yet.");
    await user.type(screen.getByLabelText("New note"), "Retry me");
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not be confirmed. Retry.");
    expect(screen.getByLabelText("New note")).toHaveValue("Retry me");
    await user.click(screen.getByRole("button", { name: "Add note" }));
    await screen.findByRole("list", { name: "Investigation notes" });
    expect(ids).toHaveLength(2);
    expect(ids[0]).toBe(ids[1]);
  });

  it("a second note with the same text is a new note, not a replay", async () => {
    const seen = setup([]);
    const user = userEvent.setup();
    render(<AlertNotes alertRef={REF} work={work()} />);
    await screen.findByText("No notes yet.");
    for (let round = 0; round < 2; round++) {
      await user.type(screen.getByLabelText("New note"), "Still active");
      await user.click(screen.getByRole("button", { name: "Add note" }));
      await waitFor(() => expect(screen.getByLabelText("New note")).toHaveValue(""));
    }
    const posts = await Promise.all(seen.filter(request => request.method === "POST").map(request => request.json()));
    expect(posts).toHaveLength(2);
    expect(posts[0].requestId).not.toBe(posts[1].requestId);
  });

  it("does not break the page when the server sends something that is not a list", async () => {
    stubFetch(() => jsonResponse({ items: [], page: { total: 0 } }));
    render(<AlertNotes alertRef={REF} work={work()} />);
    expect(await screen.findByText("No notes yet.")).toBeVisible();
  });

  it("refuses a note over 2000 characters before sending", async () => {
    const seen = setup([]);
    const user = userEvent.setup();
    render(<AlertNotes alertRef={REF} work={work()} />);
    await screen.findByText("No notes yet.");
    const box = screen.getByLabelText("New note");
    await user.click(box);
    await user.paste("x".repeat(2001));
    expect(screen.getByRole("button", { name: "Add note" })).toBeDisabled();
    expect(screen.getByText("2001 / 2000")).toBeVisible();
    expect(seen.filter(request => request.method === "POST")).toHaveLength(0);
  });
});
