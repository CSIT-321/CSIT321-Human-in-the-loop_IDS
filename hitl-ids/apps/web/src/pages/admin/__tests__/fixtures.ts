/**
 * The administrator path's fixtures, taken from the demo database itself: run 1, model
 * `xgb-8class-20260911`, rule set `s4b-1`, 5,000 flows, one alert per flow, and the twelve guardrail
 * settings `packages/contracts/models.py::GUARDRAIL_DEFAULTS` seeds with their own descriptions.
 *
 * Using the real strings matters here more than usual: this screen's job is to report what the batch
 * produced, and a fixture with invented counts would let a page that quietly computed its own
 * numbers still pass.
 */

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";

export const ADMIN: Session = { username: "a.admin", role: "system_admin" };

export const SUMMARY: Schemas["DashboardSummary"] = {
  generatedAt: "2026-09-12T10:00:00.000000Z",
  runId: 1,
  totalAlerts: 5000,
  requiresReview: 996,
  tier2Candidates: 644,
  feedbackEvents: 12,
  guardrailInterventions: 3,
  alertsMovedByFeedback: 4,
  byQueueClass: [
    { queueClass: "tier2_candidate", count: 644, requiresReview: 644 },
    { queueClass: "ml_only", count: 352, requiresReview: 352 },
    { queueClass: "none", count: 4004, requiresReview: 0 },
  ],
  byEvidenceClass: { corroborated: 200, ml_only: 796, none: 4004 },
  bySeverity: { Critical: 187, High: 809 },
  byAttackCategory: { "Port Scan": 300, "Web Attack": 200 },
};

export const RUN: Schemas["DetectionRunSummary"] = {
  runId: 1,
  status: "completed",
  datasetId: 1,
  modelVersion: "xgb-8class-20260911",
  ruleSetVersion: "s4b-1",
  seed: 20260911,
  startedAt: "2026-09-11T22:29:50.385472Z",
  completedAt: "2026-09-11T22:30:11.402318Z",
  flows: 5000,
  alerts: 5000,
  explanationsComputed: true,
  byEvidenceClass: { corroborated: 200, ml_only: 796, none: 4004 },
  byQueueClass: { tier2_candidate: 644, ml_only: 352, none: 4004 },
};

const UPDATED_AT = "2026-09-11T22:29:50.385472Z";

/** Every setting `GET /api/config/guardrails` returns, in the order `models.py` declares them. */
export const GUARDRAIL_SETTINGS: readonly Schemas["GuardrailSetting"][] = [
  {
    configKey: "max_feedback_reduction",
    configValue: 30,
    description: "Largest score reduction one feedback event may apply (magnitude)",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "critical_alert_floor",
    configValue: 70,
    description: "Negative feedback cannot push a Critical alert below this score",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "critical_alert_threshold",
    configValue: 80,
    description: "Score at or above which an alert is critical",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "learned_exception_min_occurrences",
    configValue: 3,
    description: "Minimum occurrences before a learned exception (TDM)",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "learned_exception_min_confidence",
    configValue: 60,
    description: "Minimum confidence (%) for a learned exception (TDM)",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "infiltration_alert_floor",
    configValue: 75,
    description: "Negative feedback cannot push an Infiltration alert below this score",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "max_feedback_increase",
    configValue: 20,
    description: "Largest score increase one feedback event may apply",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "review_threshold",
    configValue: 70,
    description: "adaptation-config guardrails.reviewThreshold",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "high_risk_threshold",
    configValue: 70,
    description: "adaptation-config guardrails.highRiskThreshold",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "aggregation_min_feedback_count",
    configValue: 3,
    description: "Similar feedback events required before aggregated adaptation",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "aggregation_min_agreement_ratio",
    configValue: 0.67,
    description: "Analyst agreement ratio for a moderate adjustment",
    updatedAt: UPDATED_AT,
  },
  {
    configKey: "aggregation_strong_agreement_ratio",
    configValue: 0.8,
    description: "Analyst agreement ratio for a strong adjustment",
    updatedAt: UPDATED_AT,
  },
];

export const GUARDRAILS: Schemas["GuardrailConfig"] = { settings: [...GUARDRAIL_SETTINGS] };

/** The same configuration with some settings changed: what a `PUT` answers with. */
export function guardrailsWith(changes: Record<string, number>): Schemas["GuardrailConfig"] {
  return {
    settings: GUARDRAIL_SETTINGS.map((setting) => {
      const value = changes[setting.configKey];
      return value === undefined ? { ...setting } : { ...setting, configValue: value };
    }),
  };
}

export const ALERT_REF = "3f9c1a2b-7d4e-4c8f-9a1b-2c3d4e5f6a7b";

const ADMIN_ACTOR: Schemas["Actor"] = {
  displayName: "Ada Admin",
  role: "system_admin",
  userId: 2,
};

const ANALYST_ACTOR: Schemas["Actor"] = {
  displayName: "Grace Ang",
  role: "security_analyst",
  userId: 1,
};

export const AUDIT_ENTRIES: readonly Schemas["AuditEntryOut"][] = [
  {
    eventId: 5,
    eventType: "CONFIG_CHANGE",
    actor: ADMIN_ACTOR,
    alertRef: null,
    rationale: "Rehearsal: loosen floor for demo",
    details: { changes: { critical_alert_floor: 65 }, rationale: "Rehearsal: loosen floor for demo" },
    createdAt: "2026-09-12T09:58:00.000000Z",
  },
  {
    eventId: 4,
    eventType: "GUARDRAIL_INTERVENTION",
    actor: ANALYST_ACTOR,
    alertRef: ALERT_REF,
    rationale: null,
    details: {
      outcome: {
        action: "capped",
        interventions: [
          {
            code: "critical_alert_floor",
            explanation: "Critical alert held at the floor of 70.",
          },
        ],
      },
    },
    createdAt: "2026-09-12T09:40:12.000000Z",
  },
  {
    eventId: 3,
    eventType: "SIMILAR_ALERT_LEARNING",
    actor: ADMIN_ACTOR,
    alertRef: null,
    rationale: null,
    details: {
      family_key: "dst-10.0.0.7:445",
      members_moved: 2,
      before: { mean_score: 71.2 },
      after: { mean_score: 64.8 },
      guardrail_interventions: { critical_alert_floor: 1 },
    },
    createdAt: "2026-09-12T09:40:12.000000Z",
  },
  {
    eventId: 2,
    eventType: "FEEDBACK",
    actor: ANALYST_ACTOR,
    alertRef: ALERT_REF,
    rationale: null,
    details: { category: "mark_false_positive" },
    createdAt: "2026-09-12T09:40:11.000000Z",
  },
  {
    eventId: 1,
    eventType: "DETECTION_RUN",
    actor: { displayName: null, role: null, userId: null },
    alertRef: null,
    rationale: "batch detection over csv-replay:demo_sample.csv (5000 flows)",
    details: {
      run_id: 1,
      model_version: "xgb-8class-20260911",
      rule_set_version: "s4b-1",
      seed: 20260911,
      status: "completed",
      dataset_id: 1,
      alert_count: 5000,
      rationale: "batch detection over csv-replay:demo_sample.csv (5000 flows)",
    },
    createdAt: "2026-09-11T22:30:08.992565Z",
  },
];

/** A guardrail action as the log renders it: an intervention and a refusal. */
export const GUARDRAIL_ENTRIES: readonly Schemas["AuditEntryOut"][] = [
  {
    eventId: 12,
    eventType: "GUARDRAIL_REJECTION",
    actor: ANALYST_ACTOR,
    alertRef: ALERT_REF,
    rationale: null,
    details: {
      outcome: {
        action: "rejected",
        interventions: [
          {
            code: "signature_override_feedback_immune",
            explanation: "A signature override is immune to feedback (invariant I3).",
          },
        ],
      },
    },
    createdAt: "2026-09-12T09:45:00.000000Z",
  },
  ...AUDIT_ENTRIES.filter((entry) => entry.eventType === "GUARDRAIL_INTERVENTION"),
];

/** The shape both audit endpoints answer with: `{ items, page }`. */
export function auditPage(
  items: readonly Schemas["AuditEntryOut"][],
  total: number,
  offset = 0,
): { items: Schemas["AuditEntryOut"][]; page: Schemas["PageInfo"] } {
  return {
    items: [...items],
    page: { limit: 100, offset, returned: items.length, total },
  };
}
