import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../api/client";
import { AnalystWorkPanel } from "./AnalystWork";

const available: Schemas["WorkView"] = {
  status: "available", revision: 0, canClaim: true, canMutate: false, isOwner: false, canRelease: false, releaseReasonRequired: false, idle: false,
  explanation: "Available for Review. Selecting this alert starts your review.",
  claimedAt: null, finishedAt: null, finishedByActorId: null, finishedByName: null,
  ownerActorId: null, ownerName: null, roundRef: null, verdictRef: null, verdictOutcome: null,
};

describe("human work presentation", () => {
  it("shows Available and pending ownership without a separate Start Review action", () => {
    const mounted = render(<AnalystWorkPanel work={available} />);
    expect(screen.getByText("Available for Review")).toBeVisible();
    expect(screen.getByText("Selecting this alert starts your review.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Start Review" })).toBeNull();
    mounted.rerender(<AnalystWorkPanel work={available} starting />);
    expect(screen.getByText("Starting review…")).toBeVisible();
  });

  it("distinguishes the owner from a viewer without a second claim control", () => {
    const mounted = render(<AnalystWorkPanel work={{ ...available, status: "in_review", canClaim: false,
      canMutate: true, isOwner: true, ownerName: "Alice" }} />);
    expect(screen.getByText("In Review")).toBeVisible();
    expect(screen.getByText("Alice (You)")).toBeVisible();
    expect(screen.getByText("Owner", { exact: true })).toBeVisible();
    mounted.rerender(<AnalystWorkPanel work={{ ...available, status: "in_review", canClaim: false,
      ownerName: "Alice" }} />);
    expect(screen.getByText("Alice", { exact: true })).toBeVisible();
    expect(screen.getByText("Viewer", { exact: true })).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("keeps Completed and Escalated as historical states", () => {
    const mounted = render(<AnalystWorkPanel work={{ ...available, status: "completed", canClaim: false,
      finishedByName: "Alice", verdictOutcome: "expected_activity" }} />);
    expect(screen.getByText("Completed — Reviewed by Alice")).toBeVisible();
    expect(screen.getByText("Verdict: expected activity")).toBeVisible();
    mounted.rerender(<AnalystWorkPanel work={{ ...available, status: "escalated", canClaim: false,
      finishedByName: "Alice" }} />);
    expect(screen.getByText("Escalated — Alice")).toBeVisible();
  });
});
