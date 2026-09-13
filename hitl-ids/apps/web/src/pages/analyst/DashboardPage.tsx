/**
 * The analyst's landing view (plan step S12): four headline numbers, how the queue is made up, the
 * five alerts that most need a human, and the two breakdowns behind the counts.
 *
 * Every number comes from `GET /api/dashboard/summary`; nothing here is computed client-side beyond
 * formatting, because the API is the one place the demo's arithmetic is defined. The two bar charts
 * repeat their own figures in a table underneath — a chart alone is not readable by everyone, and it
 * is not assertable in jsdom either.
 */

import { Link } from "react-router";
import { Bar, BarChart, XAxis, YAxis } from "recharts";

import { unwrap, api } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, EvidenceBadge } from "../../components/ui";
import { QUEUE_BANDS } from "../../design/bands";
import { formatNumber, formatScore } from "../../design/format";

const NUMBER_FORMAT = "en-US";

const CHART_WIDTH = 640;
const CHART_HEIGHT = 260;

interface Kpi {
  readonly label: string;
  readonly value: number;
  readonly tone: string;
  readonly caption: string;
}

interface CountRow {
  readonly name: string;
  readonly value: number;
}

function countRows(counts: { [key: string]: number } | undefined): readonly CountRow[] {
  return Object.entries(counts ?? {})
    .map(([name, value]) => ({ name, value }))
    .sort((left, right) => right.value - left.value);
}

function CountChart({ rows }: { rows: readonly CountRow[] }) {
  return (
    <div className="overflow-x-auto">
      <BarChart
        width={CHART_WIDTH}
        height={CHART_HEIGHT}
        data={[...rows]}
        margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
      >
        <XAxis dataKey="name" stroke="var(--color-border)" tick={{ fill: "var(--color-muted)", fontSize: 11 }} />
        <YAxis
          stroke="var(--color-border)"
          tick={{ fill: "var(--color-muted)", fontSize: 11 }}
          allowDecimals={false}
        />
        <Bar dataKey="value" fill="var(--color-accent)" isAnimationActive={false} />
      </BarChart>
    </div>
  );
}

/** One breakdown: the chart, then the same numbers as a table. */
function CountCard({
  title,
  dimension,
  counts,
}: {
  title: string;
  dimension: string;
  counts: { [key: string]: number } | undefined;
}) {
  const rows = countRows(counts);

  return (
    <Card title={title}>
      {rows.length === 0 ? (
        <EmptyState title="Nothing to break down yet" />
      ) : (
        <>
          <CountChart rows={rows} />
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-muted">
                  <th scope="col" className="px-3 py-2 font-medium">
                    {dimension}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Alerts
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.name} className="border-t border-border">
                    <th scope="row" className="px-3 py-1.5 text-left font-normal text-text">
                      {row.name}
                    </th>
                    <td className="px-3 py-1.5 font-mono tabular-nums text-text">
                      {formatNumber(row.value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}

/** The five highest-ranked alerts still flagged for review, in the queue's own order. */
function NeedsHumanCard() {
  const alerts = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/alerts", {
          params: { query: { requiresReview: true, limit: 5, sort: "queue" } },
          signal,
        }),
      ),
    [],
  );

  return (
    <Card title="Needs a human" subtitle="The highest-ranked alerts still flagged for review.">
      <ApiView
        resource={alerts}
        isEmpty={(data) => data.items.length === 0}
        empty={<EmptyState title="Nothing is flagged for review." />}
      >
        {(data) => (
          <>
            <ul className="divide-y divide-border">
              {data.items.map((alert) => (
                <li
                  key={alert.alertRef}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <span className="flex flex-wrap items-center gap-2">
                    <Link
                      to={`/analyst/alerts/${alert.alertRef}`}
                      className="font-mono text-sm text-accent hover:text-text"
                    >
                      {alert.sourceRecordId}
                    </Link>
                    <span className="text-sm text-muted">{alert.attackCategory ?? "—"}</span>
                    <EvidenceBadge evidenceClass={alert.evidenceClass} />
                  </span>
                  <span className="font-mono text-sm tabular-nums text-text">
                    {formatScore(alert.combinedScore)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-3">
              <Link to="/analyst/queue" className="text-sm text-accent hover:text-text">
                Open the full queue
              </Link>
            </p>
          </>
        )}
      </ApiView>
    </Card>
  );
}

export function DashboardPage() {
  const summary = useApi((signal) => unwrap(api.GET("/api/dashboard/summary", { signal })), []);
  const runId = summary.status === "success" ? summary.data.runId : null;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-text">Dashboard</h1>
        {runId !== null && <p className="text-sm text-muted">Detection run #{runId}</p>}
      </div>

      <ApiView
        resource={summary}
        isEmpty={(data) => data.totalAlerts === 0}
        empty={
          <EmptyState
            title="No alerts yet"
            hint={
              <>
                Build the demo database with <code>python scripts/run_detection.py</code>, then reload.
              </>
            }
          />
        }
      >
        {(data) => {
          const kpis: readonly Kpi[] = [
            {
              label: "Alerts in queue",
              value: data.totalAlerts,
              tone: "text-accent",
              caption: "every flow becomes an alert",
            },
            {
              label: "Awaiting review",
              value: data.requiresReview,
              tone: "text-warn",
              caption: "flagged by fusion or a guardrail",
            },
            {
              label: "Tier 2 candidates",
              value: data.tier2Candidates,
              tone: "text-danger",
              caption: "would escalate past Tier 1",
            },
            {
              label: "Moved by feedback",
              value: data.alertsMovedByFeedback,
              tone: "text-ok",
              caption:
                data.feedbackEvents === 0
                  ? "no verdicts recorded yet"
                  : `${data.feedbackEvents.toLocaleString(NUMBER_FORMAT)} verdicts recorded`,
            },
          ];
          const bands = data.byQueueClass ?? [];

          return (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {kpis.map((kpi) => (
                  <div key={kpi.label} className="rounded-sm border border-border bg-surface p-5">
                    <p className="text-sm text-muted">{kpi.label}</p>
                    <p className={`mt-2 text-3xl font-semibold ${kpi.tone}`}>
                      {kpi.value.toLocaleString(NUMBER_FORMAT)}
                    </p>
                    <p className="mt-1 text-xs text-dim">{kpi.caption}</p>
                  </div>
                ))}
              </div>

              <section className="rounded-sm border border-border bg-surface p-5">
                <h2 className="text-lg font-semibold text-text">Queue composition</h2>
                <ul className="mt-4 space-y-4">
                  {QUEUE_BANDS.map((band) => {
                    const row = bands.find((entry) => entry.queueClass === band.key);
                    if (row === undefined) return null;
                    const share = data.totalAlerts === 0 ? 0 : (row.count / data.totalAlerts) * 100;
                    return (
                      <li key={band.key} className="space-y-1">
                        <div className="flex items-baseline justify-between text-sm">
                          <span className="text-text">{band.label}</span>
                          <span className={band.tone}>
                            {row.count.toLocaleString(NUMBER_FORMAT)}
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-raised">
                          <div
                            role="meter"
                            aria-label={band.label}
                            aria-valuemin={0}
                            aria-valuemax={data.totalAlerts}
                            aria-valuenow={row.count}
                            className={`h-2 rounded-full ${band.bar}`}
                            style={{ width: `${share}%` }}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>

              <NeedsHumanCard />

              <CountCard title="Alerts by attack class" dimension="Class" counts={data.byAttackCategory} />
              <CountCard title="Alerts by severity" dimension="Severity" counts={data.bySeverity} />
            </>
          );
        }}
      </ApiView>
    </div>
  );
}
