import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { Schemas } from "../../api/client";
import { jsonResponse, stubFetch } from "../../test/renderApp";
import { ExternalAdmissionDetail } from "./ExternalAdmissionPage";

const staged: Schemas["ExternalAdmissionView"] = {
  externalInboxId: 1, canonicalAlertId: "fe130e6f-af86-4fc6-89f2-bc76b6cad68b", detector: "Suricata",
  signature: "Suspicious connection", category: "Potentially Bad Traffic", nativeSeverity: 2, confidence: null,
  sourceIp: "192.0.2.10", destinationIp: "198.51.100.20", sourcePort: null, destinationPort: 443,
  protocol: "TCP", occurredAt: "2026-10-31T00:00:00Z", occurredAtTimezoneOffset: "+00:00",
  status: "staged", statusReason: "Explicit eligibility review required", stagingDecision: "hold_for_review",
  proposedPriority: 65, proposalPolicyVersion: "suricata-offline-v1", reviewId: null, reviewDecision: null,
  reviewReason: null, reviewActorId: null, operationalAlertRef: null, operationalAlertId: null,
  admittedAt: null, admissionActorId: null, canReview: true, canAdmit: false,
};
const eligible = { ...staged, status: "eligible" as const, reviewId: 1, reviewDecision: "accepted" as const,
  reviewReason: "Reviewed", reviewActorId: 1, canAdmit: true };

function mount(view = staged) {
  return render(<MemoryRouter><ExternalAdmissionDetail initial={view} refresh={vi.fn()} prefix="/analyst" /></MemoryRouter>);
}

describe("Suricata admission", () => {
  it("separates staging priority, native severity and missing confidence", () => {
    mount();
    expect(screen.getByText("Not provided")).toBeInTheDocument();
    expect(screen.getByText("Staging Priority Proposal")).toBeInTheDocument();
    expect(screen.getByText("hold_for_review")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Admit to HITL Workflow" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Eligibility decision")).toHaveValue("held");
  });

  it("requires explicit review then a separate admission decision", async () => {
    const bodies: unknown[] = [];
    stubFetch(async request => {
      bodies.push(await request.json());
      if (request.url.endsWith("/eligibility")) return jsonResponse(eligible);
      return jsonResponse({ replayed: false, view: { ...eligible, status: "admitted", canReview: false, canAdmit: false,
        operationalAlertRef: staged.canonicalAlertId, operationalAlertId: 1, admittedAt: "2026-10-31T01:00:00Z", admissionActorId: 1 } });
    });
    mount();
    expect(screen.getByRole("button", { name: "Record eligibility review" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Eligibility decision"), "accepted");
    await userEvent.type(screen.getByLabelText("Decision reason"), "Reviewed");
    await userEvent.click(screen.getByRole("button", { name: "Record eligibility review" }));
    await screen.findByRole("button", { name: "Admit to HITL Workflow" });
    expect(screen.getByRole("button", { name: "Admit to HITL Workflow" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Decision reason"), "Admit reviewed event");
    await userEvent.click(screen.getByRole("button", { name: "Admit to HITL Workflow" }));
    const link = await screen.findByRole("link", { name: "Open Alert Triage" });
    expect(link).toHaveAttribute("href", "/analyst/v2-triage?alertRef=" + staged.canonicalAlertId);
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toMatchObject({ expectedReviewId: 1, reason: "Admit reviewed event" });
    expect(bodies[1]).not.toHaveProperty("trustedContext");
  });

  it("does not offer mutation controls to a read-only evaluator", () => {
    mount({ ...staged, canReview: false, canAdmit: false });
    expect(screen.queryByLabelText("Decision reason")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record eligibility review" })).not.toBeInTheDocument();
  });

  it("keeps status unchanged on conflict and reuses retry identity", async () => {
    const bodies: unknown[] = [];
    stubFetch(async request => {
      bodies.push(await request.json());
      return jsonResponse({ error: { code: "ADMISSION_CONFLICT", message: "Review changed; refresh" } }, 409);
    });
    mount(eligible);
    await userEvent.type(screen.getByLabelText("Decision reason"), "Admit");
    await userEvent.click(screen.getByRole("button", { name: "Admit to HITL Workflow" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Review changed");
    await userEvent.click(screen.getByRole("button", { name: "Admit to HITL Workflow" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual(bodies[0]);
    expect(screen.getByText("eligible")).toBeInTheDocument();
  });
});
