/**
 * The five guardrail settings an administrator may change, and the form arithmetic around them.
 *
 * The read endpoint (`GET /api/config/guardrails`) speaks snake_case `configKey`s and returns every
 * setting, read-only ones included; the write endpoint (`PUT`) speaks camelCase and takes a
 * rationale. This module is the one place that knows both spellings, so the page never has to hold
 * a second copy of the mapping.
 *
 * Validation lives here rather than in the form because the rules are statements about the
 * configuration, not about the widget: the floor must sit below the threshold, and the two
 * per-verdict caps must be positive, whichever input moved last.
 */

import type { Schemas } from "../../api/client";
import { partialBody } from "./partialBody";

export type GuardrailSetting = Schemas["GuardrailSetting"];
export type GuardrailUpdate = Schemas["GuardrailConfigUpdate"];

export const GUARDRAIL_FIELDS = [
  "criticalAlertFloor",
  "criticalAlertThreshold",
  "infiltrationAlertFloor",
  "maxFeedbackIncrease",
  "maxFeedbackReduction",
] as const;

export type GuardrailField = (typeof GUARDRAIL_FIELDS)[number];

export interface EditableSetting {
  /** The `configKey` the read endpoint returns. */
  readonly key: string;
  /** The field name the update endpoint takes. */
  readonly field: GuardrailField;
  /** Bound to the input, and used verbatim in validation messages. */
  readonly label: string;
}

export const EDITABLE_SETTINGS = [
  { key: "critical_alert_floor", field: "criticalAlertFloor", label: "Critical alert floor" },
  { key: "critical_alert_threshold", field: "criticalAlertThreshold", label: "Critical alert threshold" },
  { key: "infiltration_alert_floor", field: "infiltrationAlertFloor", label: "Infiltration alert floor" },
  { key: "max_feedback_increase", field: "maxFeedbackIncrease", label: "Largest increase per verdict" },
  { key: "max_feedback_reduction", field: "maxFeedbackReduction", label: "Largest reduction per verdict" },
] as const satisfies readonly EditableSetting[];

/** What the form holds: the raw text of each input, because that is what the user typed. */
export type FormValues = Record<GuardrailField, string>;

export const EMPTY_SETTINGS: readonly GuardrailSetting[] = [];

export function formValues(settings: readonly GuardrailSetting[]): FormValues {
  const values: FormValues = {
    criticalAlertFloor: "",
    criticalAlertThreshold: "",
    infiltrationAlertFloor: "",
    maxFeedbackIncrease: "",
    maxFeedbackReduction: "",
  };
  for (const setting of EDITABLE_SETTINGS) {
    const found = settings.find((entry) => entry.configKey === setting.key);
    values[setting.field] = found === undefined ? "" : String(found.configValue);
  }
  return values;
}

export function withField(values: FormValues, field: GuardrailField, value: string): FormValues {
  const next: FormValues = { ...values };
  next[field] = value;
  return next;
}

export function settingFor(
  settings: readonly GuardrailSetting[],
  key: string,
): GuardrailSetting | undefined {
  return settings.find((entry) => entry.configKey === key);
}

/** Settings that are not among the five: reported, never editable from this screen. */
export function readOnlySettings(
  settings: readonly GuardrailSetting[],
): readonly GuardrailSetting[] {
  return settings.filter(
    (entry) => !EDITABLE_SETTINGS.some((setting) => setting.key === entry.configKey),
  );
}

/** The fields whose value differs from what the API last reported, and what they now are. */
export function changedFields(
  values: FormValues,
  baseline: FormValues,
): Partial<Record<GuardrailField, number>> {
  const changed: Partial<Record<GuardrailField, number>> = {};
  for (const setting of EDITABLE_SETTINGS) {
    const next = Number(values[setting.field]);
    if (!Number.isFinite(next)) continue;
    if (next !== Number(baseline[setting.field])) changed[setting.field] = next;
  }
  return changed;
}

export function hasChanges(values: FormValues, baseline: FormValues): boolean {
  return Object.keys(changedFields(values, baseline)).length > 0;
}

/**
 * Every reason the form refuses to send, in the order a reader would fix them: the values
 * themselves, then the relationship between them, then the reason for the change.
 *
 * A message is a sentence the administrator can act on, and it names the setting by the label the
 * input carries, so the message and the field it refers to read the same.
 */
export function validateForm(
  values: FormValues,
  baseline: FormValues,
  rationale: string,
): readonly string[] {
  const problems: string[] = [];
  const parsed = new Map<GuardrailField, number>();

  for (const setting of EDITABLE_SETTINGS) {
    const raw = values[setting.field].trim();
    const value = raw === "" ? Number.NaN : Number(raw);
    if (!Number.isFinite(value) || value < 0 || value > 100) {
      problems.push(`${setting.label} must be between 0 and 100`);
      continue;
    }
    parsed.set(setting.field, value);
  }

  const floor = parsed.get("criticalAlertFloor");
  const threshold = parsed.get("criticalAlertThreshold");
  if (floor !== undefined && threshold !== undefined && floor >= threshold) {
    problems.push("The critical alert floor must be below the critical alert threshold");
  }

  for (const field of ["maxFeedbackIncrease", "maxFeedbackReduction"] as const) {
    const value = parsed.get(field);
    if (value !== undefined && value <= 0) {
      const setting = EDITABLE_SETTINGS.find((entry) => entry.field === field);
      if (setting !== undefined) problems.push(`${setting.label} must be greater than 0`);
    }
  }

  if (rationale.trim().length < 10) {
    problems.push("Give a reason of at least 10 characters");
  }

  if (problems.length === 0 && !hasChanges(values, baseline)) {
    problems.push("Nothing has changed");
  }

  return problems;
}

/** Only the changed settings and the reason reach the API; everything else is left alone. */
export function updatePayload(
  changed: Partial<Record<GuardrailField, number>>,
  rationale: string,
): GuardrailUpdate {
  return partialBody<GuardrailUpdate>({ ...changed, rationale });
}
