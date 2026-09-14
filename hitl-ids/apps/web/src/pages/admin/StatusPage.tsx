/**
 * S13 — the administrator's landing view: is the service answering, and what did the last batch
 * produce.
 *
 * Detection is an offline batch (D3). `POST /api/detection/run` cannot start one from here: it
 * answers 202 with the run that already exists, or 409 when the database holds none. So the button
 * reads "Check again" and not "Run detection", the 409 gets an empty state naming the command that
 * really builds a run, and the note under the card says the same thing in words. A button that
 * looked like it started a 21-second job and started nothing would be the demo's worst lie.
 *
 * The page is laid out as an instrument panel: a strip of headline figures over the two panels that
 * explain them. Every figure is one the API reports — `GET /api/dashboard/summary` and
 * `GET /api/dashboard/breakdowns` between them supply all six tiles, and nothing here computes a
 * number of its own. Each request is made once and passed down to every card that reads it, so the
 * strip and the cards can never disagree about what the API said.
 */

import { api, unwrap, type Schemas } from "../../api/client";
import { useApi, type ApiResource } from "../../api/useApi";
import { ApiView, EmptyState, ErrorState, LoadingState } from "../../components/states";
import {
  Card,
  EVIDENCE_LABEL,
  KeyValues,
  PageHeader,
  Pill,
  StatStrip,
  type Stat,
  type Tone,
} from "../../components/ui";
import { QUEUE_BANDS } from "../../design/bands";
import { formatDateTime, formatNumber, humanise } from "../../design/format";
import { partialBody } from "../../features/admin/partialBody";
import { Meter } from "../../features/workstation/Meter";

type Summary = Schemas["DashboardSummary"];
type Breakdowns = Schemas["DashboardBreakdowns"];
type Run = Schemas["DetectionRunSummary"];
type EvidenceClass = Schemas["AlertSummary"]["evidenceClass"];

const RUN_TONE: Record<Run["status"], Tone> = {
  completed: "ok",
  running: "accent",
  pending: "muted",
  aborted: "danger",
};

/**
 * The evidence classes a detector produced, strongest evidence first. `none` is left out: an alert
 * nothing flagged is not a detector hit, and the queue-band table beside it already counts those.
 */
const EVIDENCE_ORDER: readonly EvidenceClass[] = ["corroborated", "signature_override", "ml_only"];

/** Each class's bar colour, as whole class literals so Tailwind's scanner can read them. */
const EVIDENCE_BAR: Record<EvidenceClass, string> = {
  corroborated: "bg-violet",
  signature_override: "bg-warn",
  ml_only: "bg-accent",
  none: "bg-dim",
};

/**
 * The six headline figures. Every one is a count the API reported; a tile whose request has not
 * answered yet — or failed — is `null`, which `StatStrip` prints as a dash rather than as a zero this
 * page made up.
 */
function operationStats(
  summary: ApiResource<Summary>,
  breakdowns: ApiResource<Breakdowns>,
): readonly Stat[] {
  const data = summary.status === "success" ? summary.data : null;
  const status: Record<string, number | undefined> =
    breakdowns.status === "success" ? (breakdowns.data.statusMix ?? {}) : {};
  const unresolved =
    breakdowns.status === "success"
      ? (status.new ?? 0) + (status.claimed ?? 0) + (status.in_progress ?? 0)
      : null;

  return [
    {
      label: "Total alerts",
      value: data === null ? null : formatNumber(data.totalAlerts),
      tone: "text-text",
      hint: "Every scored flow in the recorded run",
    },
    {
      label: "Needs review",
      value: data === null ? null : formatNumber(data.requiresReview),
      tone: "text-warn",
      hint: "Alerts flagged for human review",
    },
    {
      label: "Tier 2 flagged",
      value: data === null ? null : formatNumber(data.tier2Candidates),
      tone: "text-danger",
      hint: "Alerts in the Tier 2 band",
    },
    {
      label: "Verdicts",
      value: data === null ? null : formatNumber(data.feedbackEvents),
      tone: "text-accent",
      hint: "Analyst verdicts recorded",
    },
    {
      label: "Guardrail actions",
      value: data === null ? null : formatNumber(data.guardrailInterventions),
      tone: "text-violet",
      hint: "Times a guardrail capped or rejected a verdict's effect",
    },
    {
      label: "Unresolved",
      value: unresolved === null ? null : formatNumber(unresolved),
      tone: "text-text",
      hint: "New, claimed or in progress",
    },
  ];
}

/** The command that actually builds a run; named wherever this page has to explain the 409. */
function RunCommand() {
  return <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-xs">python scripts/run_detection.py</code>;
}

/**
 * A band's key is not always a band: `byEvidenceClass` uses `ml_only` too. Anything the queue bands
 * name is labelled with the band's own words; everything else is humanised.
 */
function dimensionLabel(key: string): string {
  return QUEUE_BANDS.find((band) => band.key === key)?.label ?? humanise(key);
}

function CountTable({
  title,
  dimension,
  counts,
}: {
  title: string;
  dimension: string;
  counts: { [key: string]: number } | undefined;
}) {
  const rows = Object.entries(counts ?? {}).sort((left, right) => right[1] - left[1]);

  return (
    <section>
      <h3 className="label-mono text-[10px]">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-2 text-[13px] text-muted">The run reports no breakdown for this dimension.</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="text-dim">
                <th scope="col" className="px-2 py-1.5 font-medium">
                  {dimension}
                </th>
                <th scope="col" className="px-2 py-1.5 text-right font-medium">
                  Alerts
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([key, count]) => (
                <tr key={key} className="border-t border-border">
                  <th scope="row" className="px-2 py-1 text-left font-normal text-text">
                    {dimensionLabel(key)}
                  </th>
                  <td className="px-2 py-1 text-right font-mono tabular-nums text-text">
                    {formatNumber(count)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RunDetail({ run }: { run: Run }) {
  return (
    <div className="space-y-6">
      <KeyValues
        rows={[
          ["Run", run.runId],
          ["Status", <Pill tone={RUN_TONE[run.status]}>{run.status}</Pill>],
          ["Model", <span className="font-mono">{run.modelVersion}</span>],
          ["Rule set", <span className="font-mono">{run.ruleSetVersion}</span>],
          ["Dataset", run.datasetId],
          ["Flows", formatNumber(run.flows)],
          ["Alerts", formatNumber(run.alerts)],
          ["Seed", <span className="font-mono">{run.seed === null ? "—" : run.seed}</span>],
          ["Started", formatDateTime(run.startedAt)],
          ["Completed", run.completedAt === null ? "—" : formatDateTime(run.completedAt)],
          ["Explanations computed", run.explanationsComputed ? "Yes" : "No"],
        ]}
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <CountTable title="By evidence class" dimension="Evidence class" counts={run.byEvidenceClass} />
        <CountTable title="By queue band" dimension="Queue band" counts={run.byQueueClass} />
      </div>
    </div>
  );
}

/** The API's own answer, read back over HTTP. Shares the page's one summary request. */
function ServiceHealthCard({ summary }: { summary: ApiResource<Summary> }) {
  return (
    <Card title="Service health" subtitle="The API's own answer, read back over HTTP.">
      <ApiView resource={summary}>
        {(data) => (
          <div className="space-y-4">
            <Pill tone="ok">API answering</Pill>
            <KeyValues
              rows={[
                ["Latest run", data.runId ?? "none"],
                ["Alerts in the database", formatNumber(data.totalAlerts)],
                ["Verdicts recorded", formatNumber(data.feedbackEvents)],
                ["Guardrail interventions", formatNumber(data.guardrailInterventions)],
                ["Checked at", formatDateTime(data.generatedAt)],
              ]}
            />
          </div>
        )}
      </ApiView>
    </Card>
  );
}

/**
 * One meter per evidence class the run reported, each read against the run's own alert count, so the
 * bar answers "what share of this run's alerts did each detector flag?" and the number beside it is
 * the count itself.
 */
function EvidenceHits({ run }: { run: Run }) {
  const counts = run.byEvidenceClass ?? {};
  const present = EVIDENCE_ORDER.filter((key) => counts[key] !== undefined);

  if (present.length === 0) {
    return <p className="text-[13px] text-muted">The run reports no evidence classes.</p>;
  }

  return (
    <div className="space-y-3">
      {present.map((key) => {
        const count = counts[key] ?? 0;
        return (
          <Meter
            key={key}
            label={`${EVIDENCE_LABEL[key]} hits`}
            value={count}
            max={run.alerts}
            display={formatNumber(count)}
            tone={EVIDENCE_BAR[key]}
          />
        );
      })}
    </div>
  );
}

/** The latest run's evidence classes as bars. Shares the page's one run request. */
function DetectorHitsCard({ run }: { run: ApiResource<Run> }) {
  return (
    <Card title="Detector hits" subtitle="Which detectors flagged each alert in the latest run.">
      {run.status === "loading" && <LoadingState label="Waiting for the run…" />}
      {run.status === "error" && <p className="text-[13px] text-muted">No run to break down.</p>}
      {run.status === "success" && <EvidenceHits run={run.data} />}
    </Card>
  );
}

function LatestRunCard({ run }: { run: ApiResource<Run> }) {
  return (
    <Card
      title="Latest detection run"
      actions={
        <button
          type="button"
          onClick={run.reload}
          className="rounded-sm border border-border bg-raised px-3 py-1.5 text-sm text-text hover:bg-surface"
        >
          Check again
        </button>
      }
    >
      {run.status === "loading" && <LoadingState label="Reading the latest run…" />}
      {run.status === "error" && run.error.status === 409 && (
        <EmptyState
          title="No detection run yet"
          hint={
            <>
              Build one with <RunCommand />, then check again.
            </>
          }
        />
      )}
      {run.status === "error" && run.error.status !== 409 && (
        <ErrorState error={run.error} onRetry={run.reload} />
      )}
      {run.status === "success" && <RunDetail run={run.data} />}
      <p className="mt-5 text-[13px] text-muted">
        Detection is an offline batch. This view reports the most recent run; a new run is built from
        the command line with <RunCommand />, never inside a web request.
      </p>
    </Card>
  );
}

export function StatusPage() {
  const summary = useApi((signal) => unwrap(api.GET("/api/dashboard/summary", { signal })), []);
  const breakdowns = useApi(
    (signal) => unwrap(api.GET("/api/dashboard/breakdowns", { params: { query: { limit: 5 } }, signal })),
    [],
  );
  const run = useApi(
    (signal) =>
      unwrap(
        api.POST("/api/detection/run", {
          body: partialBody<Schemas["DetectionRunRequest"]>({}),
          signal,
        }),
      ),
    [],
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="System Status"
        subtitle="What has run, what it produced, and whether the service is answering."
      />

      <StatStrip label="Operations" stats={operationStats(summary, breakdowns)} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="space-y-4">
          <ServiceHealthCard summary={summary} />
          <DetectorHitsCard run={run} />
        </div>
        <LatestRunCard run={run} />
      </div>
    </div>
  );
}
