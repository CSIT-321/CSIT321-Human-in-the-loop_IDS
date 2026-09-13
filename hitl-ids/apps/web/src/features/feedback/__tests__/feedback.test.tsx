/**
 * The guardrail story must be visible, never silent (plan S12 exit criterion). These tests pin the
 * three outcomes the chain can show and the verdict form's contract with the API.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Schemas } from "../../../api/client";
import { jsonResponse, stubFetch } from "../../../test/renderApp";
import { FeedbackPanel } from "../FeedbackPanel";
import { ScoreAdjustmentChain } from "../ScoreAdjustmentChain";

const CAPPED: Schemas["ScoreAdjustment"] = {
  detectionScore: 99.89,
  scoreBefore: 99.89,
  requestedDelta: -30,
  actualDelta: -29.89,
  scoreAfter: 70,
  action: "capped",
  interventions: [
    {
      code: "critical_alert_floor",
      configuredValue: 70,
      originalValue: 69.89,
      appliedValue: 70,
      explanation: "This alert is Critical, so its score was held at the floor of 70.",
    },
  ],
  requiresReview: false,
  queueClassBefore: "tier2_candidate",
  queueClassAfter: "ml_only",
  summary: "Marked as a false positive; the score was held at the critical floor.",
};

describe("ScoreAdjustmentChain", () => {
  it("shows every step of a capped change, and the guardrail's own sentence", () => {
    render(<ScoreAdjustmentChain adjustment={CAPPED} />);
    const chain = screen.getByRole("group", { name: "Score adjustment" });

    expect(within(chain).getByText("Capped by a guardrail")).toBeInTheDocument();
    // Detection score and score before are both 99.89: the chain always starts from detection.
    expect(within(chain).getAllByText("99.89")).toHaveLength(2);
    expect(within(chain).getByText("−30.00")).toBeInTheDocument();
    expect(within(chain).getByText("−29.89")).toBeInTheDocument();
    expect(within(chain).getByText("70.00")).toBeInTheDocument();
    expect(within(chain).getByText("Bound")).toBeInTheDocument();
    expect(
      within(chain).getByText("This alert is Critical, so its score was held at the floor of 70."),
    ).toBeInTheDocument();
    expect(within(chain).getByText(/configured 70\.00/)).toBeInTheDocument();
    expect(within(chain).getByText(/limited how far the score moved, not the finding/)).toBeInTheDocument();
    expect(within(chain).getByText("Tier 2 candidate")).toBeInTheDocument();
    expect(within(chain).getByText("Model only")).toBeInTheDocument();
  });

  it("presents a refusal as a recorded verdict with a protected score", () => {
    render(
      <ScoreAdjustmentChain
        adjustment={{
          ...CAPPED,
          action: "rejected",
          actualDelta: 0,
          scoreAfter: 99.89,
          queueClassAfter: "tier2_candidate",
          interventions: [
            {
              code: "signature_override_feedback_immune",
              configuredValue: 1,
              originalValue: null,
              appliedValue: null,
              explanation: "A signature-backed alert cannot be decayed by feedback.",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("Refused by a guardrail")).toBeInTheDocument();
    expect(screen.getByText("Refused")).toBeInTheDocument();
    expect(screen.getByText(/The verdict is recorded, and the score was not changed/)).toBeInTheDocument();
    expect(screen.getByText(/\(unchanged\)/)).toBeInTheDocument();
  });

  it("says plainly when no guardrail acted", () => {
    render(
      <ScoreAdjustmentChain
        adjustment={{
          ...CAPPED,
          action: "applied",
          requestedDelta: 10,
          actualDelta: 10,
          scoreBefore: 36.94,
          detectionScore: 36.94,
          scoreAfter: 46.94,
          interventions: [],
          queueClassBefore: "none",
          queueClassAfter: "none",
        }}
      />,
    );
    expect(screen.getByText("Applied as requested")).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Guardrail interventions" })).toBeNull();
  });
});

describe("FeedbackPanel", () => {
  const REF = "8f22e741-c776-4999-b347-17a0c42aca6a";

  function response(): Schemas["FeedbackResponse"] {
    return {
      alert: {
        alertRef: REF,
        sourceRecordId: "AL-00478",
        createdAt: "2026-09-11T22:29:50.385472Z",
        updatedAt: "2026-09-13T08:00:00.000000Z",
        detectionScore: 99.89,
        combinedScore: 70,
        severity: "Critical",
        confidence: 0.9989,
        queueClass: "ml_only",
        queuePriority: 3,
        evidenceClass: "ml_only",
        attackCategory: "Web Attack",
        status: "new",
        requiresReview: false,
        isCritical: true,
        hasFeedback: true,
        matchedRuleIds: [],
        srcIp: "18.218.115.60",
        dstIp: "172.31.69.28",
        dstPort: 80,
        protocol: "TCP",
        flowTime: "2018-02-14 12:40:02.383338",
        owner: null,
        familySize: 61,
      },
      feedback: {
        feedbackRef: 1,
        category: "mark_false_positive",
        note: "Benign browsing, confirmed with the site owner",
        createdAt: "2026-09-13T08:00:00.000000Z",
        actor: { userId: 1, displayName: "Demo security analyst", role: "security_analyst" },
        adjustment: CAPPED,
        amendedFrom: null,
      },
      family: {
        familyKey: "Web Attack|80|TCP|",
        gateOpen: false,
        gateReason: "1 learning verdict in this family; 3 are needed.",
        membersMoved: 0,
        guardrailInterventions: {},
      },
      auditEventIds: [1, 2],
    };
  }

  it("cannot submit until a verdict is chosen, then sends exactly the chosen verdict and note", async () => {
    const user = userEvent.setup();
    const seen = stubFetch(() => jsonResponse(response()));
    const onRecorded = vi.fn();
    render(<FeedbackPanel alertRef={REF} current={null} onRecorded={onRecorded} />);

    const submit = screen.getByRole("button", { name: "Record verdict" });
    expect(submit).toBeDisabled();

    await user.click(screen.getByRole("radio", { name: /False Positive/ }));
    expect(screen.getByText(/The applied change is decided by the guardrails/)).toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Investigation note (optional)"),
      "Benign browsing, confirmed with the site owner",
    );
    await user.click(submit);

    await waitFor(() => expect(onRecorded).toHaveBeenCalledTimes(1));
    expect(seen).toHaveLength(1);
    const request = seen[0];
    expect(request?.method).toBe("POST");
    expect(new URL(request?.url ?? "").pathname).toBe(`/api/alerts/${REF}/feedback`);
    expect(await request?.clone().json()).toEqual({
      category: "mark_false_positive",
      note: "Benign browsing, confirmed with the site owner",
    });

    const outcome = screen.getByRole("region", { name: "Verdict outcome" });
    expect(within(outcome).getByText("Verdict recorded")).toBeInTheDocument();
    expect(within(outcome).getByText("Capped by a guardrail")).toBeInTheDocument();
    expect(within(outcome).getByText("Similar-alert learning did not apply.")).toBeInTheDocument();
  });

  it("shows the API's error envelope when the verdict cannot be recorded", async () => {
    const user = userEvent.setup();
    stubFetch(() => jsonResponse({ error: { code: "NOT_FOUND", message: "No alert with reference x" } }, 404));
    const onRecorded = vi.fn();
    render(<FeedbackPanel alertRef="x" current={null} onRecorded={onRecorded} />);

    await user.click(screen.getByRole("radio", { name: /Escalate/ }));
    await user.click(screen.getByRole("button", { name: "Record verdict" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No alert with reference x");
    expect(onRecorded).not.toHaveBeenCalled();
  });
});
