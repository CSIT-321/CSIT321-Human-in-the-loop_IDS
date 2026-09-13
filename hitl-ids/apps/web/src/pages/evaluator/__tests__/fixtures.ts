/**
 * The S14 tests are written against the committed run, typed as `Schemas[...]`.
 *
 * Every value here is the real one out of `evaluation/three-arm/runs/20260912T032022Z/results.json`
 * — commit 9fede24, 40 scripted verdicts, three arms whose detection metrics are identical by
 * construction, and a precision@50 that fell from 1.000 to 0.980 under feedback. Typing the fixtures
 * against the generated contract means a rename or a narrowed type in `openapi.json` breaks the build
 * here, where it is cheap, rather than in the demo.
 *
 * The one thing the fixture deliberately does retain is the unfavourable result: a fixture that only
 * held good news could not tell whether the screen renders bad news honestly.
 */

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";

export const EVALUATOR: Session = { username: "e.val", role: "evaluator" };

export const RUN_ID = "20260912T032022Z";

/** The real commit, as the record stores it. */
export const COMMIT = "9fede24";

/** The real sequence digest. The screen shows its first 16 characters. */
export const SEQUENCE_DIGEST = "2ac2a4ffb5a7e6811df183451fcd1b834936a22d51d3dd152ed43e284641232c";

export const RUN: Schemas["EvaluationRunOut"] = {
  runId: RUN_ID,
  commit: COMMIT,
  sequenceLength: 40,
  arms: ["A-control", "B-treatment", "C-guardrails-off"],
  detectionMetricsIdenticalAcrossArms: true,
  preregistration: {
    rule: "s15-preregistration-1",
    size: 40,
    escalate_at: 7,
    max_per_family: 5,
    min_family_size: 8,
  },
};

export const RUNS_PAGE: { items: Schemas["EvaluationRunOut"][]; page: Schemas["PageInfo"] } = {
  items: [RUN],
  page: { limit: 50, offset: 0, returned: 1, total: 1 },
};

export const NO_RUNS_PAGE: { items: Schemas["EvaluationRunOut"][]; page: Schemas["PageInfo"] } = {
  items: [],
  page: { limit: 50, offset: 0, returned: 0, total: 0 },
};

/** The demo database holds no scenario rows: each arm ran against its own copy. */
export const SCENARIOS_PAGE: {
  items: Schemas["EvaluationScenarioOut"][];
  page: Schemas["PageInfo"];
} = {
  items: [],
  page: { limit: 50, offset: 0, returned: 0, total: 0 },
};

/** A-control: no feedback, guardrails on, and the near-perfect queue the treatment disturbed. */
export const ARM_CONTROL: Schemas["ArmResultOut"] = {
  arm: "A-control",
  feedback: false,
  guardrails: true,
  verdicts: 0,
  precisionAt50: 1.0,
  falsePositivesInTop50: 0,
  mrrTruePositives: 0.00748254,
  meanRankTruePositives: 510.195,
  criticalFloorBreaches: 0,
  criticalPreservationRate: 1.0,
  signatureOverrideAlerts: 0,
  guardrailPass: true,
  guardrailActions: {},
};

export const ARM_TREATMENT: Schemas["ArmResultOut"] = {
  arm: "B-treatment",
  feedback: true,
  guardrails: true,
  verdicts: 40,
  precisionAt50: 0.98,
  falsePositivesInTop50: 1,
  mrrTruePositives: 0.00648259,
  meanRankTruePositives: 511.431,
  criticalFloorBreaches: 0,
  criticalPreservationRate: 1.0,
  signatureOverrideAlerts: 0,
  guardrailPass: true,
  guardrailActions: { capped: 40 },
};

export const ARM_GUARDRAILS_OFF: Schemas["ArmResultOut"] = {
  arm: "C-guardrails-off",
  feedback: true,
  guardrails: false,
  verdicts: 40,
  precisionAt50: 0.98,
  falsePositivesInTop50: 1,
  mrrTruePositives: 0.00648259,
  meanRankTruePositives: 511.431,
  criticalFloorBreaches: 0,
  criticalPreservationRate: 1.0,
  signatureOverrideAlerts: 0,
  guardrailPass: true,
  guardrailActions: { capped: 40 },
};

/** As measured: B−A and C−A both report precision@50 down 0.02 and MRR down 0.001. */
const B_MINUS_A: { [metric: string]: number } = {
  precision_at_10: -0.1,
  precision_at_25: -0.04,
  precision_at_50: -0.02,
  precision_at_100: -0.01,
  precision_at_200: -0.005,
  mrr_true_positives: -0.001,
  mean_rank_true_positives: -1.236,
  false_positives_in_top_50: -1,
  critical_floor_breaches: 0,
  true_positives_suppressed: 0,
  macro_f1_detection: 0,
};

const C_MINUS_B: { [metric: string]: number } = {
  precision_at_10: 0,
  precision_at_25: 0,
  precision_at_50: 0,
  precision_at_100: 0,
  precision_at_200: 0,
  mrr_true_positives: 0,
  mean_rank_true_positives: 0,
  false_positives_in_top_50: 0,
  critical_floor_breaches: 0,
  true_positives_suppressed: 0,
  macro_f1_detection: 0,
};

export const DELTAS: { [group: string]: { [metric: string]: number } } = {
  B_minus_A: B_MINUS_A,
  C_minus_A: B_MINUS_A,
  C_minus_B: C_MINUS_B,
};

/**
 * Every precision@k flat or up across every group: the case where the banner's second sentence must
 * not appear. Built from the real deltas with only the precision@k keys zeroed, so the fixture stays
 * a real record and one stale negative key cannot make the test pass for the wrong reason.
 */
const precisionFlat = (group: { [metric: string]: number }): { [metric: string]: number } => {
  const flat: { [metric: string]: number } = {};
  for (const [metric, change] of Object.entries(group)) {
    flat[metric] = metric.startsWith("precision_at") ? 0 : change;
  }
  return flat;
};

export const DELTAS_WITHOUT_A_FALL: { [group: string]: { [metric: string]: number } } = {
  B_minus_A: precisionFlat(B_MINUS_A),
  C_minus_A: precisionFlat(B_MINUS_A),
  C_minus_B: precisionFlat(C_MINUS_B),
};

const JUDGED: Schemas["MovementGroup"] = {
  alerts: 40,
  adjusted: 6,
  promoted: 0,
  demoted: 6,
  bandChanged: 5,
  scoreChanged: 1,
  rankChanged: 40,
  attacksPromoted: 0,
  benignPromoted: 0,
  benignDemoted: 0,
  meanRankChange: 146.375,
  bestRankReachedByABenignAlert: null,
};

const FAMILY_UNTOUCHED: Schemas["MovementGroup"] = {
  alerts: 805,
  adjusted: 205,
  promoted: 200,
  demoted: 5,
  bandChanged: 197,
  scoreChanged: 11,
  rankChanged: 805,
  attacksPromoted: 198,
  benignPromoted: 2,
  benignDemoted: 0,
  meanRankChange: -8.0832,
  bestRankReachedByABenignAlert: 1,
};

const UNRELATED: Schemas["MovementGroup"] = {
  alerts: 4155,
  adjusted: 0,
  promoted: 0,
  demoted: 0,
  bandChanged: 0,
  scoreChanged: 0,
  rankChanged: 151,
  attacksPromoted: 0,
  benignPromoted: 0,
  benignDemoted: 0,
  meanRankChange: 0.1569,
  bestRankReachedByABenignAlert: null,
};

export const MOVEMENT: {
  [arm: string]: { [group: string]: Schemas["MovementGroup"] } | null;
} = {
  "B-treatment": { judged: JUDGED, family_untouched: FAMILY_UNTOUCHED, unrelated: UNRELATED },
  "C-guardrails-off": { judged: JUDGED, family_untouched: FAMILY_UNTOUCHED, unrelated: UNRELATED },
};

/** Every count zero: on this sequence the guardrails never bound. */
export const GUARDRAILS_PREVENTED: { [key: string]: unknown } = {
  critical_floor_breaches_in_B: 0,
  critical_floor_breaches_in_C: 0,
  extra_breaches_without_guardrails: 0,
  extra_suppressions_without_guardrails: 0,
  true_positives_suppressed_in_B: 0,
  true_positives_suppressed_in_C: 0,
  signature_override_changed_in_C: 0,
  guardrail_pass: { "B-treatment": true, "C-guardrails-off": true },
  guardrail_actions_in_B: { capped: 40 },
  guardrail_actions_in_C: { capped: 40 },
};

export const COMPARISON: Schemas["EvaluationComparison"] = {
  runId: RUN_ID,
  commit: COMMIT,
  sequenceDigest: SEQUENCE_DIGEST,
  sequenceLength: 40,
  detectionMetricsIdenticalAcrossArms: true,
  arms: [ARM_CONTROL, ARM_TREATMENT, ARM_GUARDRAILS_OFF],
  deltas: DELTAS,
  movement: MOVEMENT,
  guardrailsPrevented: GUARDRAILS_PREVENTED,
  preregistration: { rule: "s15-preregistration-1", size: 40, escalate_at: 7 },
};

/** The same run with no precision@k falling, for the banner's negative case. */
export const COMPARISON_NO_FALL: Schemas["EvaluationComparison"] = {
  ...COMPARISON,
  deltas: DELTAS_WITHOUT_A_FALL,
};

/** Identical across the three arms by construction, which is the point the run record makes. */
export const DETECTION: Schemas["EvaluationDetectionMetrics"] = {
  alerts: 5000,
  attacks: 1000,
  macroF1: 0.988443,
  flaggedVsBenign: {
    support: 1000,
    predicted: 996,
    precision: 0.997992,
    recall: 0.994,
    f1: 0.995992,
    fpr: 0.0005,
    fnr: 0.006,
  },
  perClass: {
    Benign: {
      support: 4000,
      predicted: 4004,
      precision: 0.998501,
      recall: 0.9995,
      f1: 0.999,
      fpr: 0.006,
      fnr: 0.0005,
    },
    Botnet: {
      support: 150,
      predicted: 150,
      precision: 1.0,
      recall: 1.0,
      f1: 1.0,
      fpr: 0.0,
      fnr: 0.0,
    },
    "Brute Force": {
      support: 200,
      predicted: 200,
      precision: 1.0,
      recall: 1.0,
      f1: 1.0,
      fpr: 0.0,
      fnr: 0.0,
    },
    DDoS: {
      support: 200,
      predicted: 200,
      precision: 1.0,
      recall: 1.0,
      f1: 1.0,
      fpr: 0.0,
      fnr: 0.0,
    },
    DoS: {
      support: 200,
      predicted: 200,
      precision: 1.0,
      recall: 1.0,
      f1: 1.0,
      fpr: 0.0,
      fnr: 0.0,
    },
    Infiltration: {
      support: 40,
      predicted: 35,
      precision: 1.0,
      recall: 0.875,
      f1: 0.933333,
      fpr: 0.0,
      fnr: 0.125,
    },
    "Port Scan": {
      support: 150,
      predicted: 150,
      precision: 1.0,
      recall: 1.0,
      f1: 1.0,
      fpr: 0.0,
      fnr: 0.0,
    },
    "Web Attack": {
      support: 60,
      predicted: 61,
      precision: 0.967213,
      recall: 0.983333,
      f1: 0.975207,
      fpr: 0.000405,
      fnr: 0.016667,
    },
  },
  precisionAt: [
    { k: 10, precision: 1.0, attacks: 10, falsePositives: 0 },
    { k: 25, precision: 1.0, attacks: 25, falsePositives: 0 },
    { k: 50, precision: 1.0, attacks: 50, falsePositives: 0 },
    { k: 100, precision: 1.0, attacks: 100, falsePositives: 0 },
    { k: 200, precision: 1.0, attacks: 200, falsePositives: 0 },
  ],
  saturation: {
    flaggedAlerts: 996,
    atMaximumScore: 975,
    shareAtMaximum: 0.978916,
    distinctScoresAmongFlagged: 13,
  },
  signatureOverride: {
    alerts: 0,
    changed: 0,
    preservationRate: null,
    note:
      "no signature_override alert exists in this database (signature_only = 0 on the corrected "
      + "dataset); I3 is guaranteed by S7's unit tests, not measured here",
  },
};

/** The eight classes the per-class table must show, in the contract's order. */
export const CLASS_NAMES: readonly string[] = [
  "Benign",
  "Botnet",
  "Brute Force",
  "DDoS",
  "DoS",
  "Infiltration",
  "Port Scan",
  "Web Attack",
];
