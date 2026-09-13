/**
 * S13 — the administrator's landing view: is the service answering, and what did the last batch
 * produce.
 *
 * Detection is an offline batch (D3). `POST /api/detection/run` cannot start one from here: it
 * answers 202 with the run that already exists, or 409 when the database holds none. So the button
 * reads "Check again" and not "Run detection", the 409 gets an empty state naming the command that
 * really builds a run, and the note under the card says the same thing in words. A button that
 * looked like it started a 21-second job and started nothing would be the demo's worst lie.
 */

import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState, ErrorState, LoadingState } from "../../components/states";
import { Card, KeyValues, PageHeader, Pill, type Tone } from "../../components/ui";
import { QUEUE_BANDS } from "../../design/bands";
import { formatDateTime, formatNumber, humanise } from "../../design/format";
import { partialBody } from "../../features/admin/partialBody";

const RUN_TONE: Record<Schemas["DetectionRunSummary"]["status"], Tone> = {
  completed: "ok",
  running: "accent",
  pending: "muted",
  aborted: "danger",
};

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
      <h3 className="text-sm font-semibold text-text">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">The run reports no breakdown for this dimension.</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
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
              {rows.map(([key, count]) => (
                <tr key={key} className="border-t border-border">
                  <th scope="row" className="px-3 py-1.5 text-left font-normal text-text">
                    {dimensionLabel(key)}
                  </th>
                  <td className="px-3 py-1.5 font-mono tabular-nums text-text">
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

function RunDetail({ run }: { run: Schemas["DetectionRunSummary"] }) {
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
          ["Seed", run.seed === null ? "—" : run.seed],
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

function ServiceHealthCard() {
  const summary = useApi((signal) => unwrap(api.GET("/api/dashboard/summary", { signal })), []);

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

function LatestRunCard() {
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
      <p className="mt-5 text-sm text-muted">
        Detection is an offline batch. This view reports the most recent run; a new run is built from
        the command line with <RunCommand />, never inside a web request.
      </p>
    </Card>
  );
}

export function StatusPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="System Status"
        subtitle="What has run, what it produced, and whether the service is answering."
      />
      <ServiceHealthCard />
      <LatestRunCard />
    </div>
  );
}
