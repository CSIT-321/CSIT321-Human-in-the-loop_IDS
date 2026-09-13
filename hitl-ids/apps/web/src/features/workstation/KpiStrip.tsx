/**
 * The workstation's KPI strip: the queue's shape at a glance.
 *
 * Every figure is a count the API reports — no composite "threat level", which would be a number this
 * system does not compute (console-rebuild-proposal.md §1, "Threat level meter: dropped").
 */

import type { Schemas } from "../../api/client";
import type { ApiResource } from "../../api/useApi";
import { formatNumber } from "../../design/format";

type Summary = Schemas["DashboardSummary"];
type Breakdowns = Schemas["DashboardBreakdowns"];

interface Tile {
  readonly label: string;
  readonly value: number | null;
  readonly tone: string;
  readonly hint: string;
}

function tiles(summary: Summary | null, breakdowns: Breakdowns | null): Tile[] {
  const status: Record<string, number | undefined> = breakdowns?.statusMix ?? {};
  const severity: Record<string, number | undefined> = summary?.bySeverity ?? {};
  const verdicts: Record<string, number | undefined> = breakdowns?.verdictMix ?? {};
  const unresolved =
    breakdowns === null ? null : (status.new ?? 0) + (status.claimed ?? 0) + (status.in_progress ?? 0);
  return [
    { label: "Critical", value: summary === null ? null : (severity.Critical ?? 0), tone: "text-severity-critical", hint: "Alerts at Critical severity" },
    { label: "Tier 2 candidates", value: summary?.tier2Candidates ?? null, tone: "text-danger", hint: "Alerts in the Tier 2 band" },
    { label: "Needs review", value: summary?.requiresReview ?? null, tone: "text-warn", hint: "Alerts flagged for human review" },
    { label: "Unresolved", value: unresolved, tone: "text-text", hint: "New, claimed or in progress" },
    { label: "Verdicts", value: summary?.feedbackEvents ?? null, tone: "text-accent", hint: "Analyst verdicts recorded" },
    {
      label: "False positives",
      value: breakdowns === null ? null : (verdicts.mark_false_positive ?? 0),
      tone: "text-ok",
      hint: "Alerts whose verdict in force is False Positive",
    },
    { label: "Guardrail actions", value: summary?.guardrailInterventions ?? null, tone: "text-violet", hint: "Times a guardrail capped or rejected a verdict's effect" },
    { label: "Total alerts", value: summary?.totalAlerts ?? null, tone: "text-muted", hint: "Every scored flow in the recorded run" },
  ];
}

export function KpiStrip({
  summary,
  breakdowns,
}: {
  summary: ApiResource<Summary>;
  breakdowns: ApiResource<Breakdowns>;
}) {
  const data = tiles(
    summary.status === "success" ? summary.data : null,
    breakdowns.status === "success" ? breakdowns.data : null,
  );
  return (
    <dl className="grid grid-cols-4 divide-x divide-border border-b border-border bg-surface lg:grid-cols-8">
      {data.map((tile) => (
        <div key={tile.label} className="min-w-0 px-4 py-2.5" title={tile.hint}>
          <dt className="label-mono truncate text-[10px]">{tile.label}</dt>
          <dd className={`mt-0.5 font-mono text-xl font-semibold tabular-nums ${tile.tone}`}>
            {tile.value === null ? <span className="text-dim">—</span> : formatNumber(tile.value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
