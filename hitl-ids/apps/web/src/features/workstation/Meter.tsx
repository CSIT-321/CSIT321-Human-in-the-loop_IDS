/**
 * A labelled horizontal meter for a bounded value (a 0-100 score, a 0-1 confidence).
 *
 * The number is always printed next to the bar: the bar is a glance aid, never the only carrier of
 * the value (WCAG 1.4.1).
 */

export function Meter({
  label,
  value,
  max,
  display,
  tone = "bg-accent",
  hint,
}: {
  label: string;
  value: number;
  max: number;
  display: string;
  tone?: string;
  hint?: string;
}) {
  const ratio = max <= 0 ? 0 : Math.min(1, Math.max(0, value / max));
  return (
    <div className="min-w-0 space-y-1.5" title={hint}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="label-mono">{label}</span>
        <span className="font-mono text-sm font-semibold tabular-nums text-text">{display}</span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={display}
        className="h-1.5 w-full overflow-hidden rounded-sm bg-raised"
      >
        <div className={`h-full ${tone} transition-[width] duration-500`} style={{ width: `${ratio * 100}%` }} />
      </div>
    </div>
  );
}
