import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Schemas } from "../../api/client";
import { jsonResponse, stubFetch } from "../../test/renderApp";
import { AnalystWorkPanel } from "./AnalystWork";

// Release button (C7 screen, decision D5). Layout approved 2026-11-08: analysis/phase-c/SCREEN-REVIEW-PACK.html §2.
// The panel trusts the server's canRelease / releaseReasonRequired / idle; it never decides from the role.
const ref = "11111111-1111-4111-8111-111111111111";
const base: Schemas["WorkView"] = {
  status: "in_review", revision: 3, canClaim: false, canMutate: true, isOwner: true, canRelease: true,
  releaseReasonRequired: false, idle: false, explanation: "In Review — You",
  claimedAt: "2026-11-08T01:00:00Z", finishedAt: null, finishedByActorId: null, finishedByName: null,
  ownerActorId: 1, ownerName: "Glenn Ang", roundRef: null, verdictRef: null, verdictOutcome: null,
};
const released: Schemas["WorkView"] = { ...base, status: "available", revision: 4, canMutate: false, isOwner: false,
  canRelease: false, canClaim: true, ownerActorId: null, ownerName: null, claimedAt: null,
  explanation: "Available for Review. Selecting this alert starts your review." };

afterEach(() => vi.unstubAllGlobals());

function stubRelease(response: () => Response = () => jsonResponse({ replayed: false, work: released })) {
  return stubFetch(request => new URL(request.url).pathname.endsWith("/work/release") ? response() : jsonResponse({}, 404));
}

describe("Release button", () => {
  it("shows no button when the server does not allow a release", () => {
    render(<AnalystWorkPanel work={{ ...base, isOwner: false, canMutate: false, canRelease: false, ownerName: "Alice" }} alertRef={ref} />);
    expect(screen.queryByRole("button", { name: /Release/ })).toBeNull();
  });

  it("lets the owner release with no reason, sends the revision, and reports the new work state", async () => {
    const seen = stubRelease();
    const onReleased = vi.fn();
    const user = userEvent.setup();
    render(<AnalystWorkPanel work={base} alertRef={ref} onReleased={onReleased} />);
    await user.click(screen.getByRole("button", { name: "Release claim" }));
    expect(screen.getByText("Release this alert back to the queue?")).toBeVisible();
    expect(screen.getByLabelText(/Reason/)).toHaveAttribute("placeholder", "Reason (optional for your own claim)");
    await user.click(screen.getByRole("button", { name: "Release" }));
    await waitFor(() => expect(onReleased).toHaveBeenCalledWith(released));
    const body = await seen[0]!.json();
    expect(body).toMatchObject({ expectedRevision: 3 });
    expect(body.requestId).toMatch(/^[0-9a-f-]{36}$/);
    expect(body.reason ?? null).toBeNull();
  });

  it("requires a reason for an administrator release of another analyst's claim", async () => {
    const seen = stubRelease();
    const user = userEvent.setup();
    render(<AnalystWorkPanel work={{ ...base, isOwner: false, canMutate: false, releaseReasonRequired: true, ownerName: "Alice" }}
      alertRef={ref} onReleased={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Release (admin)" }));
    expect(screen.getByText("Admin release requires a reason. The release is audited.")).toBeVisible();
    const confirm = screen.getByRole("button", { name: "Release" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/Reason/), "   ");
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/Reason/), "Alice is off shift");
    await user.click(confirm);
    await waitFor(() => expect(seen).toHaveLength(1));
    expect((await seen[0]!.json()).reason).toBe("Alice is off shift");
  });

  it("Cancel closes the form and sends nothing", async () => {
    const seen = stubRelease();
    const user = userEvent.setup();
    render(<AnalystWorkPanel work={base} alertRef={ref} onReleased={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Release claim" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Release this alert back to the queue?")).toBeNull();
    expect(seen).toHaveLength(0);
  });

  it("shows the server's refusal and keeps the form open", async () => {
    stubRelease(() => jsonResponse({ error: { code: "WORK_CONFLICT", message: "Work changed; refresh before releasing." } }, 409));
    const onReleased = vi.fn();
    const user = userEvent.setup();
    render(<AnalystWorkPanel work={base} alertRef={ref} onReleased={onReleased} />);
    await user.click(screen.getByRole("button", { name: "Release claim" }));
    await user.click(screen.getByRole("button", { name: "Release" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Work changed; refresh before releasing.");
    expect(onReleased).not.toHaveBeenCalled();
    expect(screen.getByText("Release this alert back to the queue?")).toBeVisible();
  });

  it("retries with the same request id after a failure", async () => {
    let calls = 0;
    const seen = stubRelease(() => (++calls === 1 ? new Response("down", { status: 503 }) : jsonResponse({ replayed: true, work: released })));
    const user = userEvent.setup();
    render(<AnalystWorkPanel work={base} alertRef={ref} onReleased={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Release claim" }));
    await user.click(screen.getByRole("button", { name: "Release" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Release" }));
    await waitFor(() => expect(seen).toHaveLength(2));
    expect((await seen[0]!.json()).requestId).toBe((await seen[1]!.json()).requestId);
  });

  it("marks an idle claim", () => {
    render(<AnalystWorkPanel work={{ ...base, idle: true, isOwner: false, releaseReasonRequired: true, ownerName: "Alice" }} alertRef={ref} />);
    expect(screen.getByText(/idle/i)).toBeVisible();
  });
});
