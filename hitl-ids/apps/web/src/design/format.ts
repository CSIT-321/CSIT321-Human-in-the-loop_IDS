/**
 * Number and date formatting, in one place, so every screen prints a score the same way.
 *
 * Scores are shown to two decimals because the demo's centrepiece numbers (99.89, 36.94) are quoted
 * that way; a screen that rounds 99.89 to 100 would make the ranking look saturated when it is not.
 */

const NUMBER = new Intl.NumberFormat("en-US");
const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function formatNumber(value: number): string {
  return NUMBER.format(value);
}

export function formatScore(value: number): string {
  return value.toFixed(2);
}

/** A signed change: "+10.00", "−30.00" (true minus sign), "±0.00". */
export function formatDelta(value: number): string {
  if (value === 0) return "±0.00";
  const magnitude = Math.abs(value).toFixed(2);
  return value > 0 ? `+${magnitude}` : `−${magnitude}`;
}

/** A 0..1 ratio as a percentage: 0.98 -> "98.0%". */
export function formatPercent(ratio: number, digits = 1): string {
  return `${(ratio * 100).toFixed(digits)}%`;
}

/** A 0..1 metric to three decimals, the precision the evaluation report quotes. */
export function formatRatio(ratio: number): string {
  return ratio.toFixed(3);
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : `${DATE_TIME.format(date)} UTC`;
}

/** "mark_false_positive" -> "Mark false positive". For enum values with no dedicated label. */
export function humanise(value: string): string {
  const spaced = value.replace(/_/g, " ").toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
