/**
 * Overview (console rebuild R4): the corpus at a glance — when the recorded traffic was captured, who
 * talked most, what the detectors called it, and what humans have decided since.
 *
 * Every number comes from `GET /api/dashboard/breakdowns`, with `runId` and the attack-class mix from
 * `GET /api/dashboard/summary`; nothing here is computed client-side beyond sorting and formatting,
 * because the API is the one place the demo's arithmetic is defined.
 *
 * These are recorded flows, not a feed: the histogram says when the traffic was captured, so the page
 * never claims a rate. The chart repeats its own figures in a table underneath, for the same reason
 * the dashboard does — a chart alone is not readable by everyone, and it is not assertable in jsdom.
 */

import { Link } from "react-router";
import { Bar, BarChart, XAxis, YAxis } from "recharts";

import { unwrap, api, type Schemas } from "../../api/client";
import { useApi, type ApiResource } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, PageHeader } from "../../components/ui";
import { formatNumber, humanise } from "../../design/format";
import { categoryLabel } from "../../features/feedback/categories";

type TopValue = Schemas["TopValue"];
type TimeBucket = Schemas["TimeBucket"];

const CHART_WIDTH = 1080;
const CHART_HEIGHT = 240;

interface CountRow {
  readonly name: string;
  readonly value: number;
}

function countRows(counts: { [key: string]: number } | undefined): readonly CountRow[] {
  return Object.entries(counts ?? {})
    .map(([name, value]) => ({ name, value }))
    .sort((left, right) => right.value - left.value);
}

function byCountDescending(left: TopValue, right: TopValue): number {
  return right.count - left.count;
}

/**
 * The histogram: one stacked bar per capture hour, flagged at the base and the rest above it, so the
 * bar's height is the hour's flow count. Side-by-side pairs over ~100 hours drew as invisible slivers.
 */
function VolumeChart({ buckets }: { buckets: readonly TimeBucket[] }) {
  const data = buckets.map((bucket) => ({
    name: bucket.bucket,
    flagged: bucket.flagged,
    notFlagged: Math.max(0, bucket.count - bucket.flagged),
  }));

  return (
    <div className="overflow-x-auto">
      <p className="mb-2 flex gap-4 font-mono text-[11px] text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-2 w-2 rounded-sm bg-warn" /> flagged
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-2 w-2 rounded-sm bg-accent" /> not flagged
        </span>
      </p>
      <BarChart
        width={CHART_WIDTH}
        height={CHART_HEIGHT}
        data={data}
        barCategoryGap={1}
        margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
      >
        <XAxis
          dataKey="name"
          stroke="var(--color-border)"
          tick={{ fill: "var(--color-muted)", fontSize: 11 }}
        />
        <YAxis
          stroke="var(--color-border)"
          tick={{ fill: "var(--color-muted)", fontSize: 11 }}
          allowDecimals={false}
        />
        <Bar dataKey="flagged" stackId="flows" fill="var(--color-warn)" isAnimationActive={false} />
        <Bar dataKey="notFlagged" stackId="flows" fill="var(--color-accent)" isAnimationActive={false} />
      </BarChart>
    </div>
  );
}

/** When the recorded traffic was captured — the same hours again as a table. */
function VolumeCard({ buckets }: { buckets: readonly TimeBucket[] }) {
  return (
    <Card
      title="Flow volume by capture hour"
      subtitle="When the recorded traffic was captured — not a live rate."
    >
      {buckets.length === 0 ? (
        <EmptyState title="No flows recorded" />
      ) : (
        <>
          <VolumeChart buckets={buckets} />
          {/* ~100 capture hours: the table scrolls inside the card rather than lengthening the page. */}
          <div className="mt-4 max-h-72 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-muted">
                  <th scope="col" className="px-3 py-2 font-medium">
                    Hour
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Flows
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Flagged
                  </th>
                </tr>
              </thead>
              <tbody>
                {buckets.map((bucket) => (
                  <tr key={bucket.bucket} className="border-t border-border">
                    <th scope="row" className="px-3 py-1.5 text-left font-normal text-text">
                      {bucket.bucket}
                    </th>
                    <td className="px-3 py-1.5 font-mono tabular-nums text-text">
                      {formatNumber(bucket.count)}
                    </td>
                    <td className="px-3 py-1.5 font-mono tabular-nums text-warn">
                      {formatNumber(bucket.flagged)}
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

/**
 * One top-talker list. Addresses are links into the entity page — the analyst's next question is
 * always "what else did this address do?" — while a port has no page of its own, so it stays text.
 */
function TopValuesCard({
  title,
  dimension,
  values,
  linkAddresses = false,
}: {
  title: string;
  dimension: string;
  values: readonly TopValue[];
  linkAddresses?: boolean;
}) {
  const rows = [...values].sort(byCountDescending);
  // The widest bar in the list is the full width; every other bar is read against it.
  const max = rows.length === 0 ? 1 : Math.max(...rows.map((row) => row.count));

  return (
    <Card title={title}>
      {rows.length === 0 ? (
        <EmptyState title="No flows recorded" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-muted">
                <th scope="col" className="px-3 py-2 font-medium">
                  {dimension}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Flows
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Flagged
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.value} className="border-t border-border">
                  <th scope="row" className="px-3 py-1.5 text-left font-normal text-text">
                    <span className="flex flex-col gap-1">
                      {linkAddresses ? (
                        <Link
                          to={`/analyst/entities/ip/${encodeURIComponent(row.value)}`}
                          className="font-mono text-accent hover:text-text"
                        >
                          {row.value}
                        </Link>
                      ) : (
                        <span className="font-mono text-text">{row.value}</span>
                      )}
                      <span
                        aria-hidden
                        className="h-1 rounded-full bg-accent"
                        style={{ width: `${(row.count / max) * 100}%` }}
                      />
                    </span>
                  </th>
                  <td className="px-3 py-1.5 font-mono tabular-nums text-text">
                    {formatNumber(row.count)}
                  </td>
                  <td className="px-3 py-1.5 font-mono tabular-nums text-warn">
                    {formatNumber(row.flagged)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/** A `{value: count}` mix as a two-column table, with the value's on-screen label. */
function MixCard({
  title,
  dimension,
  countLabel = "Alerts",
  counts,
  label,
  emptyTitle,
}: {
  title: string;
  dimension: string;
  countLabel?: string;
  counts: { [key: string]: number } | undefined;
  label: (value: string) => string;
  emptyTitle?: string;
}) {
  const rows = countRows(counts);

  return (
    <Card title={title}>
      {rows.length === 0 ? (
        <EmptyState title={emptyTitle ?? "Nothing recorded yet"} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-muted">
                <th scope="col" className="px-3 py-2 font-medium">
                  {dimension}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {countLabel}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.name} className="border-t border-border">
                  <th scope="row" className="px-3 py-1.5 text-left font-normal text-text">
                    {label(row.name)}
                  </th>
                  <td className="px-3 py-1.5 font-mono tabular-nums text-text">
                    {formatNumber(row.value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/**
 * What the model called the recorded flows, read from the summary the page already fetched. Titled
 * "predicted class" rather than "attack class" because Benign is one of the eight.
 */
function AttackClassCard({ summary }: { summary: ApiResource<Schemas["DashboardSummary"]> }) {
  return (
    <Card title="Alerts by predicted class">
      <ApiView resource={summary}>
        {(data) => {
          const rows = countRows(data.byAttackCategory);
          if (rows.length === 0) return <EmptyState title="Nothing recorded yet" />;
          return (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-muted">
                    <th scope="col" className="px-3 py-2 font-medium">
                      Class
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
          );
        }}
      </ApiView>
    </Card>
  );
}

export function OverviewPage() {
  const breakdowns = useApi(
    (signal) => unwrap(api.GET("/api/dashboard/breakdowns", { params: { query: { limit: 10 } }, signal })),
    [],
  );
  const summary = useApi((signal) => unwrap(api.GET("/api/dashboard/summary", { signal })), []);
  const runId = summary.status === "success" ? summary.data.runId : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        subtitle={runId === null ? "Recorded flows" : `Recorded flows · detection run #${runId}`}
      />

      <ApiView
        resource={breakdowns}
        isEmpty={(data) =>
          (data.flowTimeHistogram ?? []).length === 0 && (data.topSourceIps ?? []).length === 0
        }
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
        {(data) => (
          <>
            <VolumeCard buckets={data.flowTimeHistogram ?? []} />

            <div className="grid gap-4 lg:grid-cols-3">
              <TopValuesCard
                title="Top source addresses"
                dimension="Address"
                values={data.topSourceIps ?? []}
                linkAddresses
              />
              <TopValuesCard
                title="Top destination addresses"
                dimension="Address"
                values={data.topDestinationIps ?? []}
                linkAddresses
              />
              <TopValuesCard
                title="Top destination ports"
                dimension="Port"
                values={data.topDestinationPorts ?? []}
              />
            </div>

            <AttackClassCard summary={summary} />

            <MixCard
              title="Verdicts in force"
              dimension="Verdict"
              counts={data.verdictMix}
              label={categoryLabel}
              emptyTitle="No verdicts recorded yet"
            />
            <MixCard
              title="Triage status"
              dimension="Status"
              counts={data.statusMix}
              label={humanise}
            />
            <MixCard
              title="Guardrail interventions"
              dimension="Guardrail"
              countLabel="Times applied"
              counts={data.guardrailInterventions}
              label={humanise}
              emptyTitle="No guardrail has intervened yet"
            />
          </>
        )}
      </ApiView>
    </div>
  );
}
