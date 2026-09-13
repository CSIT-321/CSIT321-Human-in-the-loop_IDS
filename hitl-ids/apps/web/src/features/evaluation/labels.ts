/**
 * The labels and direction rules the evaluator screens share (S14).
 *
 * `humaniseKey` is deliberately not `design/format.humanise`. The evaluation record's keys carry
 * tokens that are already meaningful in capitals — `guardrail_actions_in_B`, and movement blocks
 * keyed `B-treatment` / `C-guardrails-off` — and lower-casing those prints "in b" and a nameless
 * group. For every other key, including all of the metric names, the two agree.
 */

import { formatDelta, humanise } from "../../design/format";

/**
 * "precision_at_50" -> "Precision at 50"; "guardrail_actions_in_B" -> "Guardrail actions in B";
 * "max_per_family" -> "Max per family".
 */
export function humaniseKey(key: string): string {
  const spaced = key
    .split("_")
    .map((word) => (/[A-Z]/.test(word) ? word : word.toLowerCase()))
    .join(" ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** A delta group's human name. An unknown key — a future arm pair — falls back to a plain humanise. */
const DELTA_GROUP_LABEL: Readonly<Record<string, string>> = {
  B_minus_A: "Treatment − Control",
  C_minus_A: "Guardrails off − Control",
  C_minus_B: "Guardrails off − Treatment",
};

export function deltaGroupLabel(key: string): string {
  return DELTA_GROUP_LABEL[key] ?? humanise(key);
}

/** The three movement groups, in reading order, with the name each is shown under. */
export const MOVEMENT_ROWS: readonly (readonly [string, string])[] = [
  ["judged", "Judged by the analyst"],
  ["family_untouched", "Same family, untouched"],
  ["unrelated", "Unrelated"],
];

/**
 * Metrics where a fall is the good news. Everything else the comparison reports — precision@k, MRR,
 * macro F1 — improves upward, and every other key is a count of things we do not want.
 */
const LOWER_IS_BETTER: ReadonlySet<string> = new Set([
  "false_positives_in_top_50",
  "mean_rank_true_positives",
  "critical_floor_breaches",
  "true_positives_suppressed",
]);

export function higherIsBetter(metric: string): boolean {
  return !LOWER_IS_BETTER.has(metric);
}

/** A 0..1 metric (precision@k, MRR, macro F1, a rate) rather than a count or a rank. */
function isRatioMetric(metric: string): boolean {
  return (
    metric.startsWith("precision_at") ||
    metric.startsWith("mrr") ||
    metric.includes("f1") ||
    metric.endsWith("_rate")
  );
}

/**
 * A change to a ratio metric: three decimals and a true minus sign, so precision@50 falling from
 * 1.000 to 0.980 reads "−0.020" rather than being rounded away to "−0.02". Counts and ranks keep
 * `formatDelta`'s two decimals, which is the resolution they were measured at.
 */
export function formatMetricDelta(metric: string, value: number): string {
  if (!isRatioMetric(metric)) return formatDelta(value);
  if (value === 0) return "±0.000";
  const magnitude = Math.abs(value).toFixed(3);
  return value > 0 ? `+${magnitude}` : `−${magnitude}`;
}
