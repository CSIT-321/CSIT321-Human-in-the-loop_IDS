/**
 * The queue's five bands, in the contract's order (`QueueBandCount.queueClass`).
 *
 * `tone` and `bar` are written out as whole class literals, not composed at runtime, because
 * Tailwind's scanner only sees strings it can read in the source. `bandLabel` gives the API's key a
 * human name wherever a view has the key but not the row.
 */

import type { Schemas } from "../api/client";

export type QueueClass = Schemas["QueueBandCount"]["queueClass"];

export interface QueueBand {
  readonly key: QueueClass;
  /** Human name, as the dashboard's composition card shows it. */
  readonly label: string;
  /** Text colour for this band's counts. */
  readonly tone: string;
  /** Fill colour for this band's composition bar. */
  readonly bar: string;
}

export const QUEUE_BANDS: readonly QueueBand[] = [
  { key: "tier2_candidate", label: "Tier 2 candidate", tone: "text-danger", bar: "bg-danger" },
  { key: "corroborated", label: "Corroborated", tone: "text-violet", bar: "bg-violet" },
  { key: "signature_override", label: "Signature override", tone: "text-warn", bar: "bg-warn" },
  { key: "ml_only", label: "Model only", tone: "text-accent", bar: "bg-accent" },
  { key: "none", label: "Nothing flagged it", tone: "text-dim", bar: "bg-dim" },
];

export function bandLabel(key: QueueClass): string {
  return QUEUE_BANDS.find((band) => band.key === key)?.label ?? key;
}
