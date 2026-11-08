// Real-shaped payloads of the 3 legacy GETs the Flow & Score panel reads, for one judged flow alert.
// Shapes measured on a demo copy (analysis/phase-c/c5_fields.py). Shared by the C5 and D2 tests.
import { jsonResponse } from "./renderApp";

export const FLOW_REF = "c12d8bb2-46ce-4d38-a0fe-63ffe5398002";
export const adjustment = { detectionScore: 100, scoreBefore: 100, requestedDelta: 15, actualDelta: 0, scoreAfter: 100, action: "capped",
  interventions: [{ code: "score_range_clamped", configuredValue: 100, originalValue: null, appliedValue: null,
    explanation: "Scores are bounded to 0-100, so the change was clamped at 100." }],
  requiresReview: true, queueClassBefore: "tier2_candidate", queueClassAfter: "tier2_candidate",
  summary: "The alert was escalated for higher-priority review, requesting +15 points; +0 was applied." };
export const event = { feedbackRef: 2, category: "escalate", note: "Same DDoS source as alert f742e96c.",
  actor: { userId: 1, displayName: "Glenn Ang", role: "security_analyst" }, createdAt: "2026-11-08T06:44:35.354777Z", adjustment, amendedFrom: null };
export const detail = (ref = FLOW_REF) => ({
  alert: { alertRef: ref, combinedScore: 100, detectionScore: 100, severity: "High", queueClass: "tier2_candidate", queuePriority: 1,
    evidenceClass: "ml_only", confidence: 0.99998713 },
  flow: { srcIp: "18.218.11.51", dstIp: "172.31.69.25", srcPort: 51178, dstPort: 80, protocol: "TCP", durationSeconds: 27.614783,
    packets: 9, bytes: 984, sourceRecordId: "AL-00114", features: { "ACK Flag Count": 8, "Active Max": 1069969 } },
  family: { familyKey: "[\"DDoS\",80,\"tcp\",\"-\"]", familyLabel: "DDoS · port 80 · tcp",
    basis: { attackCategory: "DDoS", dstPort: 80, protocol: "tcp", ruleId: null, dstIp: null, rule: "Exact match." },
    members: 199, gateOpen: false, gateReason: "not enough learning verdicts: 1 of 3 required", dominantCategory: "confirm_true_positive",
    agreementRatio: 1, appliedAdjustment: 0, appliedOffset: 0, note: null },
  feedbackCount: 1,
});

/** The panel's response for a legacy path, or null when the path is not one of the 3 GETs. */
export function flowPanelResponse(path: string, ref = FLOW_REF): Response | null {
  if (path === `/api/alerts/${ref}`) return jsonResponse(detail(ref));
  if (path === `/api/alerts/${ref}/score-adjustment`) return jsonResponse(adjustment);
  if (path === `/api/alerts/${ref}/feedback-history`) return jsonResponse({ alertRef: ref, events: [event], effective: event });
  return null;
}
