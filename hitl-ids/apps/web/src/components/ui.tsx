/**
 * Shared visual primitives (S12-S14). Every page composes these rather than restyling a card, so the
 * three role paths — built in parallel — still read as one product.
 */

import type { ReactNode } from "react";

import type { Schemas } from "../api/client";
import { bandLabel } from "../design/bands";
import { formatDelta, formatScore } from "../design/format";

export type Tone = "accent" | "warn" | "ok" | "danger" | "violet" | "stub" | "muted";

const PILL_TONE: Record<Tone, string> = {
  accent: "border-accent/30 bg-accent-dim text-accent",
  warn: "border-warn/30 bg-warn-dim text-warn",
  ok: "border-ok/30 bg-ok-dim text-ok",
  danger: "border-danger/30 bg-danger-dim text-danger",
  violet: "border-violet/30 bg-violet-dim text-violet",
  stub: "border-stub/30 bg-stub-bg text-stub",
  muted: "border-border bg-raised text-muted",
};

export const TEXT_TONE: Record<Tone, string> = {
  accent: "text-accent",
  warn: "text-warn",
  ok: "text-ok",
  danger: "text-danger",
  violet: "text-violet",
  stub: "text-stub",
  muted: "text-muted",
};

export function Pill({ tone = "muted", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center whitespace-nowrap rounded-sm border px-1.5 py-px font-mono text-[11px] font-medium ${PILL_TONE[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-sm border border-border bg-surface ${className}`}>
      {(title !== undefined || actions !== undefined) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <div className="min-w-0">
            {title !== undefined && <h2 className="label-mono">{title}</h2>}
            {subtitle !== undefined && <p className="mt-0.5 text-xs text-dim">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-4">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight text-text">{title}</h1>
        {subtitle !== undefined && <p className="text-[13px] text-muted">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export interface Stat {
  readonly label: string;
  /** Already formatted; `null` renders a dim dash while the figure is loading or absent. */
  readonly value: ReactNode | null;
  /** A text colour class, e.g. `text-warn`. */
  readonly tone?: string;
  readonly hint?: string;
}

/**
 * A row of headline figures in the workstation's KPI-strip style (R5), for pages that are not the
 * workstation. Cells are separated by 1 px rules, and the grid wraps on narrow screens.
 */
/** Wide-screen columns per figure count, as whole literals so Tailwind's scanner can see them. */
const STRIP_COLUMNS: Readonly<Record<number, string>> = {
  1: "sm:grid-cols-1",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
  4: "sm:grid-cols-2 xl:grid-cols-4",
  5: "sm:grid-cols-3 xl:grid-cols-5",
  6: "sm:grid-cols-3 xl:grid-cols-6",
};

export function StatStrip({ stats, label }: { stats: readonly Stat[]; label?: string }) {
  // Columns follow the count, so a four-figure strip never leaves two empty cells at full width.
  const columns = STRIP_COLUMNS[stats.length] ?? "sm:grid-cols-3 xl:grid-cols-6";
  return (
    <dl
      aria-label={label}
      className={`grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-border ${columns}`}
    >
      {stats.map((stat) => (
        <div key={stat.label} className="min-w-0 bg-surface px-4 py-3" title={stat.hint}>
          <dt className="label-mono truncate text-[10px]">{stat.label}</dt>
          <dd className={`mt-1 truncate font-mono text-xl font-semibold tabular-nums ${stat.tone ?? "text-text"}`}>
            {stat.value === null ? <span className="text-dim">—</span> : stat.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** A label/value grid for panels: flow details, run metadata, and the like. */
export function KeyValues({ rows }: { rows: readonly (readonly [string, ReactNode])[] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-[13px]">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="font-mono text-[11px] uppercase leading-5 tracking-wider text-dim">{label}</dt>
          <dd className="min-w-0 break-words font-mono text-text">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

type Severity = Schemas["AlertSummary"]["severity"];
type EvidenceClass = Schemas["AlertSummary"]["evidenceClass"];
type QueueClass = Schemas["AlertSummary"]["queueClass"];

const SEVERITY_TONE: Record<Severity, Tone> = {
  Critical: "danger",
  High: "warn",
  Medium: "stub",
  Low: "accent",
  Informational: "muted",
};

const SEVERITY_DOT: Record<Severity, string> = {
  Critical: "bg-severity-critical text-severity-critical",
  High: "bg-severity-high text-severity-high",
  Medium: "bg-severity-medium text-severity-medium",
  Low: "bg-severity-low text-severity-low",
  Informational: "bg-dim text-muted",
};

/** Severity as dot + word + colour — never colour alone. */
export function SeverityBadge({ severity }: { severity: Severity }) {
  const [dot, text] = SEVERITY_DOT[severity].split(" ");
  return (
    <span
      data-tone={SEVERITY_TONE[severity]}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap font-mono text-[11px] font-semibold uppercase tracking-wider ${text}`}
    >
      <span aria-hidden className={`h-2 w-2 rounded-full ${dot}`} />
      {severity}
    </span>
  );
}

export const EVIDENCE_LABEL: Record<EvidenceClass, string> = {
  corroborated: "Rule + model agree",
  signature_override: "Rule only",
  ml_only: "Model only",
  none: "Nothing flagged",
};

const EVIDENCE_TONE: Record<EvidenceClass, Tone> = {
  corroborated: "violet",
  signature_override: "warn",
  ml_only: "accent",
  none: "muted",
};

/** What evidence exists. Never changes with feedback. */
export function EvidenceBadge({ evidenceClass }: { evidenceClass: EvidenceClass }) {
  return (
    <Pill tone={EVIDENCE_TONE[evidenceClass]} title="Evidence class — fixed at detection">
      {EVIDENCE_LABEL[evidenceClass]}
    </Pill>
  );
}

const BAND_TONE: Record<QueueClass, Tone> = {
  tier2_candidate: "danger",
  corroborated: "violet",
  signature_override: "warn",
  ml_only: "accent",
  none: "muted",
};

/** Where the alert sits in the queue now. Feedback moves this. */
export function BandBadge({ queueClass }: { queueClass: QueueClass }) {
  return (
    <Pill tone={BAND_TONE[queueClass]} title="Queue band — feedback moves this">
      {bandLabel(queueClass)}
    </Pill>
  );
}

/** The operational score, with its movement from the detection score when there is one. */
export function ScorePair({ detection, combined }: { detection: number; combined: number }) {
  const moved = Math.abs(combined - detection) > 1e-9;
  return (
    <span className="inline-flex items-baseline gap-2 font-mono tabular-nums">
      <span className="text-text">{formatScore(combined)}</span>
      {moved && (
        <span className={`text-xs ${combined > detection ? "text-ok" : "text-warn"}`}>
          {formatDelta(combined - detection)}
        </span>
      )}
    </span>
  );
}

/** A metric delta rendered as measured: signed and coloured, never hidden when unfavourable. */
export function Delta({
  value,
  higherIsBetter = true,
  format = formatDelta,
}: {
  value: number;
  higherIsBetter?: boolean;
  format?: (n: number) => string;
}) {
  const good = value === 0 ? null : value > 0 === higherIsBetter;
  const tone = good === null ? "text-muted" : good ? "text-ok" : "text-danger";
  return <span className={`font-mono tabular-nums ${tone}`}>{format(value)}</span>;
}
