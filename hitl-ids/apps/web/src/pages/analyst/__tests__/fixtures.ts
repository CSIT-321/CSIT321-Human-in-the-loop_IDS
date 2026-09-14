/**
 * The two alerts the S12 tests are written against, typed as `Schemas[...]`.
 *
 * Typing the fixtures against the generated contract is the point: a rename or a narrowed enum in
 * `openapi.json` breaks the build here, where it is cheap, rather than in a screenshot.
 *
 * The values are the demo database's, not invented: AL-00478 is the Critical Web Attack the model
 * caught alone (99.89, tier 2 candidate, no matching rule), and AL-03086 is an unflagged flow the
 * queue still lists (36.94, no evidence, Informational).
 */

import type { Schemas } from "../../../api/client";

export const AL_00478_REF = "8f22e741-c776-4999-b347-17a0c42aca6a";
export const AL_03086_REF = "048f12e7-56db-470b-a69d-714c54fe0bb7";

export const CRITICAL_ALERT: Schemas["AlertSummary"] = {
  alertRef: AL_00478_REF,
  sourceRecordId: "AL-00478",
  createdAt: "2026-09-11T22:29:50.385472Z",
  updatedAt: "2026-09-11T22:29:50.385472Z",
  detectionScore: 99.89,
  combinedScore: 99.89,
  severity: "Critical",
  confidence: 0.9989,
  queueClass: "tier2_candidate",
  queuePriority: 1,
  evidenceClass: "ml_only",
  attackCategory: "Web Attack",
  status: "new",
  requiresReview: true,
  isCritical: true,
  hasFeedback: false,
  matchedRuleIds: [],
  srcIp: "18.218.115.60",
  dstIp: "172.31.69.28",
  dstPort: 80,
  protocol: "TCP",
  flowTime: "2018-02-14 12:40:02.383338",
  owner: null,
  familySize: 61,
};

export const UNFLAGGED_ALERT: Schemas["AlertSummary"] = {
  alertRef: AL_03086_REF,
  sourceRecordId: "AL-03086",
  createdAt: "2026-09-11T22:29:51.000000Z",
  updatedAt: "2026-09-11T22:29:51.000000Z",
  detectionScore: 36.94,
  combinedScore: 36.94,
  severity: "Informational",
  confidence: 0.3611,
  queueClass: "none",
  queuePriority: 5,
  evidenceClass: "none",
  attackCategory: null,
  status: "new",
  requiresReview: false,
  isCritical: false,
  hasFeedback: false,
  matchedRuleIds: [],
  srcIp: "10.0.0.5",
  dstIp: "10.0.0.9",
  dstPort: 443,
  protocol: "TCP",
  flowTime: "2018-02-22 14:13:45.074278",
  owner: null,
  familySize: 1,
};

export const FLOW: Schemas["FlowPanel"] = {
  srcIp: "18.218.115.60",
  srcPort: 51514,
  dstIp: "172.31.69.28",
  dstPort: 80,
  protocol: "TCP",
  durationSeconds: 0.0001234,
  packets: 3,
  bytes: 240,
  sourceRecordId: "AL-00478",
  features: {
    "Destination Port": 80,
    "Flow Duration": 123,
    "Protocol": "TCP",
    "Total Fwd Packets": 2,
    "Flow Bytes/s": null,
  },
};

export const SIGNATURE: Schemas["SignaturePanel"] = {
  matched: [],
  note: "No rule matched (ML-only alert).",
  ruleSetVersion: "rules-v1",
  severityScore: null,
};

export const ML: Schemas["MlPanel"] = {
  predictedClass: "Web Attack",
  probability: 0.9989,
  modelVersion: "hist-gb-v1",
  explanationStatus: "computed",
  additivityPassed: true,
  baseValue: -2.1,
  rawMargin: 4.62,
  note: null,
  topSupporting: [
    {
      featureName: "destination_port",
      featureValue: 80,
      shapContribution: 1.421,
      direction: "supports_prediction",
    },
    {
      featureName: "flow_duration",
      featureValue: 0.0001234,
      shapContribution: 0.884,
      direction: "supports_prediction",
    },
  ],
  topOpposing: [
    {
      featureName: "total_fwd_packets",
      featureValue: 2,
      shapContribution: -0.317,
      direction: "opposes_prediction",
    },
  ],
};

export const EVIDENCE: Schemas["EvidencePanel"] = {
  evidenceClass: "ml_only",
  queueClass: "tier2_candidate",
  agreement: false,
  explanation:
    "The model flagged this flow as Web Attack with 99.9% confidence and no rule matched it. With one source of evidence the alert is a Tier 2 candidate rather than corroborated.",
  fusionScheme: "weighted_sum_v1",
  tier2Candidate: true,
};

export const FAMILY: Schemas["FamilyPanel"] = {
  familyKey: "Web Attack|80|TCP|",
  members: 4,
  gateOpen: false,
  gateReason: "1 learning verdict in this family; 3 are needed.",
  agreementRatio: null,
  dominantCategory: null,
  appliedAdjustment: 0,
  appliedOffset: 0,
  note: null,
};

export const ALERT_DETAIL: Schemas["AlertDetail"] = {
  alert: CRITICAL_ALERT,
  flow: FLOW,
  signature: SIGNATURE,
  ml: ML,
  evidence: EVIDENCE,
  family: FAMILY,
  currentFeedback: null,
  feedbackCount: 0,
};

/** The chain an alert with no verdict yet returns: nothing bound, nothing moved. */
export const NO_VERDICT_ADJUSTMENT: Schemas["ScoreAdjustment"] = {
  detectionScore: 99.89,
  scoreBefore: 99.89,
  requestedDelta: 0,
  actualDelta: 0,
  scoreAfter: 99.89,
  action: "applied",
  interventions: [],
  requiresReview: true,
  queueClassBefore: "tier2_candidate",
  queueClassAfter: "tier2_candidate",
  summary: "No verdict recorded; the operational score is still the detection score.",
};

/** What the critical-alert floor does to "mark false positive" on AL-00478. */
export const CAPPED_ADJUSTMENT: Schemas["ScoreAdjustment"] = {
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
  summary: "Marked as a false positive. The guardrail held the score at the critical floor.",
};

/** The demo corpus's headline shape: every flow is an alert, most are flagged for review. */
export const SUMMARY: Schemas["DashboardSummary"] = {
  runId: 3,
  generatedAt: "2026-09-13T08:00:00.000000Z",
  totalAlerts: 5000,
  requiresReview: 4112,
  tier2Candidates: 187,
  feedbackEvents: 12,
  alertsMovedByFeedback: 9,
  guardrailInterventions: 3,
  byQueueClass: [
    { queueClass: "tier2_candidate", count: 187, requiresReview: 187 },
    { queueClass: "corroborated", count: 0, requiresReview: 0 },
    { queueClass: "signature_override", count: 0, requiresReview: 0 },
    { queueClass: "ml_only", count: 3925, requiresReview: 3925 },
    { queueClass: "none", count: 888, requiresReview: 0 },
  ],
  byAttackCategory: { "Web Attack": 1204, "Port Scan": 902, DoS: 611, Benign: 888 },
  bySeverity: { Critical: 41, High: 620, Informational: 888 },
  byEvidenceClass: { ml_only: 3925, corroborated: 0, signature_override: 0, none: 1075 },
};

/**
 * `GET /api/dashboard/breakdowns?limit=5` on the demo database (R4), with two verdicts and one
 * guardrail intervention added so the mixes are not empty; the real database has none yet.
 */
export const BREAKDOWNS: Schemas["DashboardBreakdowns"] = {
  generatedAt: "2026-09-14T08:00:00.000000Z",
  topSourceIps: [
    { value: "18.219.193.20", count: 197, flagged: 197 },
    { value: "172.31.69.13", count: 106, flagged: 98 },
    { value: "172.31.69.24", count: 96, flagged: 87 },
    { value: "18.221.219.4", count: 80, flagged: 80 },
    { value: "18.218.115.60", count: 77, flagged: 76 },
  ],
  topDestinationIps: [
    { value: "172.31.69.25", count: 452, flagged: 452 },
    { value: "172.31.69.28", count: 210, flagged: 207 },
    { value: "18.219.211.138", count: 150, flagged: 150 },
    { value: "172.31.69.15", count: 34, flagged: 34 },
    { value: "172.31.69.21", count: 33, flagged: 29 },
  ],
  topDestinationPorts: [
    { value: "80", count: 803, flagged: 462 },
    { value: "8080", count: 150, flagged: 150 },
    { value: "21", count: 146, flagged: 146 },
    { value: "22", count: 58, flagged: 56 },
    { value: "31337", count: 27, flagged: 27 },
  ],
  verdictMix: { mark_false_positive: 1, confirm_true_positive: 1 },
  statusMix: { new: 4998, claimed: 2 },
  guardrailInterventions: { critical_alert_floor: 1 },
  flowTimeHistogram: [
    { bucket: "2018-02-14 12:00", count: 28, flagged: 1 },
    { bucket: "2018-02-14 13:00", count: 44, flagged: 0 },
    { bucket: "2018-02-14 14:00", count: 76, flagged: 23 },
    { bucket: "2018-02-14 15:00", count: 94, flagged: 50 },
  ],
};

/** `GET /api/entities/ip/18.218.115.60?limit=10` on the demo database: the Web Attack source. */
export const ATTACKER_ENTITY: Schemas["EntityIp"] = {
  ip: "18.218.115.60",
  alerts: 77,
  asSource: 77,
  asDestination: 0,
  flagged: 76,
  firstSeen: "2018-02-20 14:34:14.574275",
  lastSeen: "2018-02-23 19:17:03.720682",
  byQueueClass: { none: 1, tier2_candidate: 76 },
  byAttackCategory: { DDoS: 17, "Web Attack": 59 },
  verdictMix: {},
  topPeers: [
    { value: "172.31.69.28", count: 69, flagged: 68 },
    { value: "172.31.69.25", count: 8, flagged: 8 },
  ],
  topDestinationPorts: [{ value: "80", count: 77, flagged: 76 }],
};

const DEMO_ACTOR: Schemas["Actor"] = {
  userId: 1,
  displayName: "Demo security analyst",
  role: "security_analyst",
};

/** The audit entry a verdict writes: what Investigations lists and Feedback Impact counts. */
export const FEEDBACK_AUDIT_ENTRY: Schemas["AuditEntryOut"] = {
  eventId: 41,
  eventType: "FEEDBACK",
  alertRef: AL_00478_REF,
  actor: DEMO_ACTOR,
  createdAt: "2026-09-13T08:00:00.000000Z",
  rationale: null,
  details: { category: "mark_false_positive", note: "Confirmed with the network team." },
};

/** A guardrail entry, as `FeedbackImpactPage` reads it out of the audit trail. */
export const GUARDRAIL_AUDIT_ENTRY: Schemas["AuditEntryOut"] = {
  eventId: 42,
  eventType: "GUARDRAIL_INTERVENTION",
  alertRef: AL_00478_REF,
  actor: DEMO_ACTOR,
  createdAt: "2026-09-13T08:00:01.000000Z",
  rationale: null,
  details: {
    outcome: {
      interventions: [
        {
          code: "critical_alert_floor",
          configuredValue: 70,
          originalValue: 69.89,
          appliedValue: 70,
          explanation: "This alert is Critical, so its score was held at the floor of 70.",
        },
      ],
    },
  },
};

export const FALSE_POSITIVE_RECORD: Schemas["FeedbackRecord"] = {
  feedbackRef: 1,
  category: "mark_false_positive",
  note: null,
  createdAt: "2026-09-13T08:00:00.000000Z",
  actor: { userId: 1, displayName: "Demo security analyst", role: "security_analyst" },
  adjustment: CAPPED_ADJUSTMENT,
  amendedFrom: null,
};

export function alertsPage(
  items: readonly Schemas["AlertSummary"][],
  total = items.length,
  offset = 0,
): { items: Schemas["AlertSummary"][]; page: Schemas["PageInfo"] } {
  return {
    items: [...items],
    page: { limit: 50, offset, returned: items.length, total },
  };
}

export function auditPage(
  items: readonly Schemas["AuditEntryOut"][],
): { items: Schemas["AuditEntryOut"][]; page: Schemas["PageInfo"] } {
  return {
    items: [...items],
    page: { limit: 50, offset: 0, returned: items.length, total: items.length },
  };
}
