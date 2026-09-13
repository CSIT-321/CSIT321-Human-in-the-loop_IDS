/**
 * The five scoring verdicts (plan S12; `deviations.md` A6).
 *
 * Labels are the industry closing classifications the user chose for the console rebuild
 * (docs/console-rebuild-proposal.md §0; research §4 — Sentinel and Elastic close incidents as True
 * Positive, Benign Positive or False Positive). The API values are unchanged.
 *
 * The deltas mirror `packages/detection/feedback/service.py` FEEDBACK_EFFECTS and are shown only as
 * what a verdict *requests*. What was actually applied always comes back from the API, because the
 * guardrails decide that — the form must never present a requested delta as the outcome.
 *
 * `duplicate` is absent on purpose: it is a queue action (link and suppress), not a score change.
 */

import type { Schemas } from "../../api/client";

export type FeedbackCategory = Schemas["FeedbackRequest"]["category"];

export interface CategoryMeta {
  readonly value: FeedbackCategory;
  readonly label: string;
  /** The score change the verdict requests before any guardrail applies. */
  readonly requestedDelta: number;
  /** Whether the verdict keeps the alert flagged for review. */
  readonly forcesReview: boolean;
  readonly description: string;
  /** Whether the verdict counts towards similar-alert learning for the alert's family. */
  readonly teachesFamily: boolean;
}

export const FEEDBACK_CATEGORIES: readonly CategoryMeta[] = [
  {
    value: "confirm_true_positive",
    label: "True Positive",
    requestedDelta: 10,
    forcesReview: true,
    teachesFamily: true,
    description: "This is a real attack.",
  },
  {
    value: "escalate",
    label: "Escalate to Tier 2",
    requestedDelta: 15,
    forcesReview: true,
    teachesFamily: true,
    description: "Real, and it needs higher-priority review.",
  },
  {
    value: "needs_investigation",
    label: "Needs investigation",
    requestedDelta: 0,
    forcesReview: true,
    teachesFamily: false,
    description: "Not decided yet. Keeps the alert open without moving it.",
  },
  {
    value: "mark_expected_activity",
    label: "Benign Positive",
    requestedDelta: -15,
    forcesReview: false,
    teachesFamily: true,
    description: "The detection was right about the traffic, but it is activity this network is meant to carry.",
  },
  {
    value: "mark_false_positive",
    label: "False Positive",
    requestedDelta: -30,
    forcesReview: false,
    teachesFamily: true,
    description: "The detectors were wrong about this flow.",
  },
];

/**
 * The on-screen label for a category that arrived as plain text (an audit entry's details, a family's
 * dominant verdict). Unknown values fall back to a readable form rather than throwing: an old or
 * unexpected audit row must never take a page down.
 */
export function categoryLabel(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const meta = FEEDBACK_CATEGORIES.find((category) => category.value === value);
  if (meta !== undefined) return meta.label;
  const spaced = value.replace(/_/g, " ").toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function categoryMeta(value: FeedbackCategory): CategoryMeta {
  const meta = FEEDBACK_CATEGORIES.find((category) => category.value === value);
  if (meta === undefined) throw new Error(`Unknown feedback category ${value}`);
  return meta;
}
