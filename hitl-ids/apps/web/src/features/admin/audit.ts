/**
 * The audit trail's vocabulary: its event types, its two date filters, the row shapes two screens
 * read out of `details`, and the CSV the administrator can take away.
 *
 * `details` is contract-typed as `{ [key: string]: unknown }` — the API deliberately does not
 * promise a shape per event type, because the trail records what happened rather than a fixed
 * schema. Everything here that reaches into it narrows with `typeof`/`Array.isArray` checks and
 * returns nothing it cannot prove, so a detail shape that changes shows as an em dash rather than
 * as a crash or a stringified `undefined`.
 */

import type { Schemas } from "../../api/client";

export type AuditEntry = Schemas["AuditEntryOut"];
export type AuditEventType = AuditEntry["eventType"];

/**
 * Every value `AuditEntryOut.eventType` accepts, in the contract's order. `satisfies` makes this
 * list fail to compile the moment the generated enum grows a value, and `audit.test.tsx` checks the
 * page offers a filter option for each of them.
 */
export const EVENT_TYPES = [
  "LOGIN",
  "LOGOUT",
  "DETECTION_RUN",
  "FEEDBACK",
  "FEEDBACK_AMEND",
  "GUARDRAIL_INTERVENTION",
  "GUARDRAIL_REJECTION",
  "SIMILAR_ALERT_LEARNING",
  "ALERT_STATUS_CHANGE",
  "ALERT_DUPLICATE",
  "CONFIG_CHANGE",
  "RULE_CREATE",
  "RULE_UPDATE",
  "MODEL_STATUS_CHANGE",
  "EVALUATION_RUN",
] as const satisfies readonly AuditEventType[];

/** A `?eventType=` value read back out of the URL, or null when it is absent or unrecognised. */
export function asEventType(value: string): AuditEventType | null {
  return EVENT_TYPES.find((known) => known === value) ?? null;
}

/** An alert's public UUID, shortened to the eight characters a person reads aloud. */
export function shortAlertRef(alertRef: string | null): string {
  return alertRef === null ? "—" : alertRef.slice(0, 8);
}

/**
 * The two `since`/`until` bounds are fixed-width UTC text on the wire, not dates: the API compares
 * them as strings. A date input gives `yyyy-mm-dd`, so the bounds are the day's first and last
 * microsecond, covering the whole of the day named.
 */
export function dayStart(date: string): string | null {
  return date === "" ? null : `${date}T00:00:00.000000Z`;
}

export function dayEnd(date: string): string | null {
  return date === "" ? null : `${date}T23:59:59.999999Z`;
}

export interface AuditFilters {
  readonly eventType: AuditEventType | null;
  readonly since: string | null;
  readonly until: string | null;
}

export function auditQuery(filters: AuditFilters, limit: number, offset: number) {
  return {
    limit,
    offset,
    eventType: filters.eventType === null ? null : [filters.eventType],
    since: filters.since,
    until: filters.until,
  };
}

/** A JSON object as a keyed record, or null. Details arrive from `JSON.parse`, never from code. */
export function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const record: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) record[key] = item;
  return record;
}

/**
 * The sentences behind a guardrail action: `details.outcome.interventions[].explanation`, which is
 * what the analyst was told their verdict was capped or refused by.
 */
export function interventionExplanations(
  details: { readonly [key: string]: unknown } | null,
): readonly string[] {
  const outcome = details === null ? undefined : details["outcome"];
  const interventions = asRecord(outcome)?.["interventions"];
  if (!Array.isArray(interventions)) return [];
  const items: readonly unknown[] = interventions;

  const explanations: string[] = [];
  for (const item of items) {
    const explanation = asRecord(item)?.["explanation"];
    if (typeof explanation === "string") explanations.push(explanation);
  }
  return explanations;
}

/** The trail as a spreadsheet: the header is the contract's field names, every cell is quoted. */
export const CSV_HEADER = "eventId,createdAt,eventType,actorRole,actorName,alertRef,rationale,details";

function csvField(value: string): string {
  return `"${value.replace(/"/g, '""')}"`;
}

export function auditCsv(entries: readonly AuditEntry[]): string {
  const lines = entries.map((entry) =>
    [
      String(entry.eventId),
      entry.createdAt,
      entry.eventType,
      entry.actor.role ?? "",
      entry.actor.displayName ?? "",
      entry.alertRef ?? "",
      entry.rationale ?? "",
      entry.details === null ? "" : JSON.stringify(entry.details),
    ]
      .map(csvField)
      .join(","),
  );
  return [CSV_HEADER, ...lines].join("\n") + "\n";
}
