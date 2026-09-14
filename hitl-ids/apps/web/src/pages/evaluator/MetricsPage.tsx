/**
 * Detection metrics for the newest evaluation run (plan step S14).
 *
 * This is the one screen in the console that scores the detector rather than describing what the
 * queue is doing, and it scores it against ground truth the system never sees. Two cards carry the
 * caveats that make the headline numbers readable: the F1 is a property of this testbed dataset (one
 * tool per attack class), and the score distribution is saturated, so a promotion among the top band
 * has nowhere to go.
 *
 * The per-class figures appear twice on purpose. Once as a table, which is the readable and assertable
 * copy, and once as small multiples below it: one panel per class, one meter per metric. Small
 * multiples rather than a single bar chart because eight classes scoring between 0.98 and 1.0 read as
 * eight identical bars — a class that is not perfect is visible here as itself, and its meter turns
 * warn rather than merely being shorter.
 *
 * The run is found rather than typed: the runs list is asked for one row, and that row's id drives
 * the metrics request.
 */

import { Link } from "react-router";

import type { Schemas } from "../../api/client";
import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, KeyValues, PageHeader, StatStrip, type Stat } from "../../components/ui";
import { formatNumber, formatPercent, formatRatio } from "../../design/format";
import { classMetricRows } from "../../features/evaluation/values";
import { Meter } from "../../features/workstation/Meter";

const TH = "px-3 py-2 font-medium";
const TD = "px-3 py-1.5";

/** A metric below this is imperfect, and its meter says so in colour rather than in width alone. */
const IMPERFECT_BELOW = 0.99;

function metricTone(value: number): string {
  return value < IMPERFECT_BELOW ? "bg-warn" : "bg-accent";
}

/** Why a promotion can be inert, in the run's own numbers. One string, so it reads as one sentence. */
function saturationSentence(saturation: Schemas["SaturationMetrics"]): string {
  return (
    `${formatNumber(saturation.atMaximumScore)} of ${formatNumber(saturation.flaggedAlerts)} flagged ` +
    "alerts share the maximum score, so a promotion among them can have nowhere to go."
  );
}

/** The caveat the headline strip and the per-class table sit under. */
function TestbedCaution() {
  return (
    <div role="note" className="rounded-sm border border-stub/40 bg-stub-bg p-4 text-sm text-stub">
      <p>
        The headline F1 is a property of this testbed dataset, where each attack class was generated
        by a single tool; it is not a claim about real-world traffic.
      </p>
    </div>
  );
}

/** The headline figures, in the workstation's strip style. */
function detectionStats(data: Schemas["EvaluationDetectionMetrics"], runId: string): readonly Stat[] {
  return [
    {
      label: "Macro F1",
      value: formatRatio(data.macroF1),
      hint: "The macro-averaged F1 over the eight classes",
    },
    { label: "Alerts", value: formatNumber(data.alerts), hint: "Scored alerts in the recorded run" },
    { label: "Attacks", value: formatNumber(data.attacks), hint: "Ground-truth attack flows" },
    {
      label: "Run",
      value: (
        <Link to={`/evaluator/runs/${runId}`} className="text-accent hover:text-text">
          {runId}
        </Link>
      ),
      hint: "The run these metrics were measured on",
    },
  ];
}

/** One class as a mini panel: its support, then a meter per metric. */
function ClassPanel({ name, metrics }: { name: string; metrics: Schemas["ClassMetrics"] }) {
  return (
    <div className="min-w-0 bg-surface p-3">
      <p className="label-mono truncate" title={name}>
        {name}
      </p>
      <p className="mt-0.5 font-mono text-[11px] text-muted">support {formatNumber(metrics.support)}</p>
      <div className="mt-3 space-y-2.5">
        <Meter
          label="Precision"
          value={metrics.precision}
          max={1}
          display={formatRatio(metrics.precision)}
          tone={metricTone(metrics.precision)}
        />
        <Meter
          label="Recall"
          value={metrics.recall}
          max={1}
          display={formatRatio(metrics.recall)}
          tone={metricTone(metrics.recall)}
        />
        <Meter
          label="F1"
          value={metrics.f1}
          max={1}
          display={formatRatio(metrics.f1)}
          tone={metricTone(metrics.f1)}
        />
      </div>
    </div>
  );
}

/** Everything below the page header, once the newest run id is known. */
function DetectionSection({ runId }: { runId: string }) {
  const detection = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/evaluation/runs/{runId}/detection", {
          params: { path: { runId } },
          signal,
        }),
      ),
    [runId],
  );

  return (
    <>
      <TestbedCaution />
      <div className="mt-6">
        <ApiView resource={detection} loadingLabel="Loading detection metrics…">
          {(data) => {
            const perClass = Object.entries(data.perClass ?? {});
            const precisionAt = data.precisionAt ?? [];
            const { saturation, signatureOverride } = data;

            return (
              <div className="space-y-6">
                <StatStrip label="Detection" stats={detectionStats(data, runId)} />

                <Card
                  title="Per class"
                  subtitle="Ground truth the detector never saw. Support is how many flows truly carry the class."
                >
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="text-muted">
                        <tr>
                          <th scope="col" className={TH}>
                            Class
                          </th>
                          <th scope="col" className={TH}>
                            Support
                          </th>
                          <th scope="col" className={TH}>
                            Predicted
                          </th>
                          <th scope="col" className={TH}>
                            Precision
                          </th>
                          <th scope="col" className={TH}>
                            Recall
                          </th>
                          <th scope="col" className={TH}>
                            F1
                          </th>
                          <th scope="col" className={TH}>
                            False-positive rate
                          </th>
                          <th scope="col" className={TH}>
                            False-negative rate
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {perClass.map(([name, metrics]) => (
                          <tr key={name} className="border-t border-border">
                            <th scope="row" className={`${TD} text-left font-normal text-text`}>
                              {name}
                            </th>
                            <td className={`${TD} font-mono tabular-nums text-text`}>
                              {formatNumber(metrics.support)}
                            </td>
                            <td className={`${TD} font-mono tabular-nums text-text`}>
                              {formatNumber(metrics.predicted)}
                            </td>
                            <td className={`${TD} font-mono tabular-nums text-text`}>
                              {formatRatio(metrics.precision)}
                            </td>
                            <td className={`${TD} font-mono tabular-nums text-text`}>
                              {formatRatio(metrics.recall)}
                            </td>
                            <td className={`${TD} font-mono tabular-nums text-text`}>
                              {formatRatio(metrics.f1)}
                            </td>
                            <td className={`${TD} font-mono tabular-nums text-text`}>
                              {formatRatio(metrics.fpr)}
                            </td>
                            <td className={`${TD} font-mono tabular-nums text-text`}>
                              {formatRatio(metrics.fnr)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/*
                    The same figures again as small multiples. A class below the accent threshold turns
                    warn, so an imperfect class is visible without comparing bar heights.
                  */}
                  {perClass.length > 0 && (
                    <div className="mt-6 grid gap-px bg-border sm:grid-cols-2 xl:grid-cols-4">
                      {perClass.map(([name, metrics]) => (
                        <ClassPanel key={name} name={name} metrics={metrics} />
                      ))}
                    </div>
                  )}
                </Card>

                <div className="grid gap-4 xl:grid-cols-2">
                  <Card title="Flagged vs benign">
                    <KeyValues rows={classMetricRows(data.flaggedVsBenign)} />
                  </Card>

                  <Card
                    title="Precision at k"
                    subtitle="Of the top k alerts in the queue, how many are attacks."
                  >
                    {precisionAt.length === 0 ? (
                      <EmptyState title="This run records no precision@k" />
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                          <thead className="text-muted">
                            <tr>
                              <th scope="col" className={TH}>
                                k
                              </th>
                              <th scope="col" className={TH}>
                                Precision
                              </th>
                              <th scope="col" className={TH}>
                                Attacks
                              </th>
                              <th scope="col" className={TH}>
                                False positives
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {precisionAt.map((row) => (
                              <tr key={row.k} className="border-t border-border">
                                <th scope="row" className={`${TD} text-left font-normal text-text`}>
                                  {formatNumber(row.k)}
                                </th>
                                <td className={`${TD} font-mono tabular-nums text-text`}>
                                  {formatRatio(row.precision)}
                                </td>
                                <td className={`${TD} font-mono tabular-nums text-text`}>
                                  {formatNumber(row.attacks)}
                                </td>
                                <td className={`${TD} font-mono tabular-nums text-text`}>
                                  {formatNumber(row.falsePositives)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </Card>

                  <Card title="Score saturation">
                    <KeyValues
                      rows={[
                        ["Flagged alerts", formatNumber(saturation.flaggedAlerts)],
                        ["At maximum score", formatNumber(saturation.atMaximumScore)],
                        ["Share at maximum", formatPercent(saturation.shareAtMaximum)],
                        [
                          "Distinct scores among flagged",
                          formatNumber(saturation.distinctScoresAmongFlagged),
                        ],
                      ]}
                    />
                    <p className="mt-4 text-sm text-muted">{saturationSentence(saturation)}</p>
                  </Card>

                  <Card
                    title="Signature-backed alerts (invariant I3)"
                    subtitle="A rule-only alert the model disputes cannot be moved by feedback at all: the disagreement goes to an administrator."
                  >
                    <KeyValues
                      rows={[
                        ["Alerts", formatNumber(signatureOverride.alerts)],
                        ["Changed by feedback", formatNumber(signatureOverride.changed)],
                        [
                          "Preservation rate",
                          signatureOverride.preservationRate === null
                            ? "—"
                            : formatPercent(signatureOverride.preservationRate),
                        ],
                      ]}
                    />
                    {signatureOverride.note !== null && (
                      <p className="mt-4 text-sm text-muted">{signatureOverride.note}</p>
                    )}
                  </Card>
                </div>
              </div>
            );
          }}
        </ApiView>
      </div>
    </>
  );
}

export function MetricsPage() {
  // The contract declares no query parameters here, and the API answers newest first, so the newest
  // run is simply the first row. Asking for one row would be a second thing to keep true.
  const runs = useApi((signal) => unwrap(api.GET("/api/evaluation/runs", { signal })), []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Detection Metrics"
        subtitle="Measured against ground truth the system itself never sees."
      />

      <ApiView
        resource={runs}
        isEmpty={(data) => data.items.length === 0}
        empty={
          <EmptyState
            title="No evaluation runs recorded"
            hint={
              <>
                Run <code>python scripts/run_evaluation.py</code> to record the three arms.
              </>
            }
          />
        }
      >
        {(data) => {
          const newest = data.items[0];
          if (newest === undefined) return <EmptyState title="No evaluation runs recorded" />;
          return <DetectionSection runId={newest.runId} />;
        }}
      </ApiView>
    </div>
  );
}
