/**
 * Reading the evaluation record's open `{ [key: string]: unknown }` blocks without `any` (S14).
 *
 * `preregistration` and `guardrailsPrevented` are deliberately untyped in the contract: they are a
 * dict of whatever the run recorded, and the run records them itself. Everything here narrows with
 * `typeof`, prints the value as it stands, and drops anything that is not a scalar — a screen that
 * invented a value for an unknown shape would be the one thing this view exists not to do.
 */

import type { Schemas } from "../../api/client";
import { formatNumber, formatRatio } from "../../design/format";
import { humaniseKey } from "./labels";

export type Row = readonly [string, string];

type Scalar = string | number | boolean;

function isRecord(value: unknown): value is { [key: string]: unknown } {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isScalar(value: unknown): value is Scalar {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

/** A scalar as the screen prints it. Booleans read as Yes/No; nothing is recomputed. */
export function scalarText(value: Scalar): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return formatNumber(value);
  return value;
}

/**
 * Flatten a record into label/value rows. A nested record becomes one row per child, labelled
 * "Parent · Child" — how `guardrails_prevented`'s `guardrail_pass` block reads.
 */
export function scalarRows(source: { [key: string]: unknown } | undefined): readonly Row[] {
  const rows: Row[] = [];
  for (const [key, value] of Object.entries(source ?? {})) {
    if (isScalar(value)) {
      rows.push([humaniseKey(key), scalarText(value)]);
      continue;
    }
    if (!isRecord(value)) continue;
    for (const [childKey, childValue] of Object.entries(value)) {
      if (isScalar(childValue)) {
        rows.push([`${humaniseKey(key)} · ${humaniseKey(childKey)}`, scalarText(childValue)]);
      }
    }
  }
  return rows;
}

/**
 * One `ClassMetrics` block — a single class, or the flagged-vs-benign pair — as label/value rows.
 * Counts print as counts; the five rates print as 0..1 ratios to three decimals.
 */
export function classMetricRows(metrics: Schemas["ClassMetrics"]): readonly Row[] {
  return [
    ["Support", formatNumber(metrics.support)],
    ["Predicted", formatNumber(metrics.predicted)],
    ["Precision", formatRatio(metrics.precision)],
    ["Recall", formatRatio(metrics.recall)],
    ["F1", formatRatio(metrics.f1)],
    ["False-positive rate", formatRatio(metrics.fpr)],
    ["False-negative rate", formatRatio(metrics.fnr)],
  ];
}

/** A run's sequence digest shortened for a cell: the whole SHA would dominate the row. */
export function shortDigest(digest: string | null): string {
  if (digest === null || digest === "") return "—";
  return `${digest.slice(0, 16)}…`;
}
