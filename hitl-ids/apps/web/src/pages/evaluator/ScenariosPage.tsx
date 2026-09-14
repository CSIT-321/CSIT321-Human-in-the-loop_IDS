/**
 * The evaluator's entry screen (plan step S14).
 *
 * Three things, in the order a reader needs them. The committed three-arm runs, so the run id is a
 * click rather than something typed from a terminal. The newest run's arms at a glance and the
 * pre-registration behind them, because the result only means something once you can see both the
 * three-way comparison and the rule that was fixed before the arms ran. And the scenario rows, which
 * the demo database does not hold — each arm ran against its own copy — and which therefore read as
 * an explanation rather than as an empty table.
 *
 * The glance panel keeps the same honesty rule the run screen does: a non-control arm's precision@50
 * is shown against the control's as a signed delta, whether it improved or not.
 */

import { Link } from "react-router";

import type { Schemas } from "../../api/client";
import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, Delta, KeyValues, PageHeader, Pill } from "../../components/ui";
import { formatDateTime, formatNumber, formatRatio } from "../../design/format";
import { formatMetricDelta } from "../../features/evaluation/labels";
import { scalarRows } from "../../features/evaluation/values";

const TH = "px-3 py-2 font-medium";
const TD = "px-3 py-1.5";

/** The metric the glance panel compares between arms. */
const GLANCE_METRIC = "precision_at_50";

/**
 * One arm as a mini panel: what was switched on, how the queue ended up, and — for every arm but the
 * control — how its precision@50 moved against the control's.
 */
function ArmPanel({
  arm,
  control,
}: {
  arm: Schemas["ArmResultOut"];
  control: Schemas["ArmResultOut"] | undefined;
}) {
  const change = control === undefined ? null : arm.precisionAt50 - control.precisionAt50;

  return (
    <div className="min-w-0 bg-surface p-3">
      <p className="label-mono truncate" title={arm.arm}>
        {arm.arm}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Pill tone={arm.feedback ? "ok" : "muted"} title="Analyst feedback applied">
          Feedback {arm.feedback ? "On" : "Off"}
        </Pill>
        <Pill tone={arm.guardrails ? "ok" : "muted"} title="Guardrails active">
          Guardrails {arm.guardrails ? "On" : "Off"}
        </Pill>
      </div>
      <p className="label-mono mt-3 text-[10px]">Precision@50</p>
      <p className="mt-0.5 flex flex-wrap items-baseline gap-2 font-mono text-lg font-semibold tabular-nums text-text">
        {formatRatio(arm.precisionAt50)}
        {change !== null && (
          <Delta
            value={change}
            higherIsBetter
            format={(value) => formatMetricDelta(GLANCE_METRIC, value)}
          />
        )}
      </p>
      <p className="label-mono mt-2 text-[10px]">False positives in top 50</p>
      <p className="mt-0.5 font-mono text-sm tabular-nums text-text">
        {formatNumber(arm.falsePositivesInTop50)}
      </p>
    </div>
  );
}

/**
 * The newest run's three arms side by side. The link lives in the card header rather than in the
 * body, so the way into the run survives the comparison failing to load.
 */
function NewestRunCard({ runId }: { runId: string }) {
  const comparison = useApi(
    (signal) =>
      unwrap(api.GET("/api/evaluation/runs/{runId}", { params: { path: { runId } }, signal })),
    [runId],
  );

  return (
    <Card
      title="Newest run at a glance"
      subtitle="The same detection in every arm; only feedback and the guardrails differ."
      actions={
        <Link to={`/evaluator/runs/${runId}`} className="text-sm text-accent hover:text-text">
          Open run →
        </Link>
      }
    >
      <ApiView resource={comparison}>
        {(data) => {
          const arms = data.arms ?? [];
          if (arms.length === 0) return <EmptyState title="This run records no arms" />;
          // The control is the run's first arm; every other arm is read against it.
          const control = arms[0];
          return (
            <div className="grid gap-px bg-border sm:grid-cols-3">
              {arms.map((arm) => (
                <ArmPanel
                  key={arm.arm}
                  arm={arm}
                  control={control === undefined || arm.arm === control.arm ? undefined : control}
                />
              ))}
            </div>
          );
        }}
      </ApiView>
    </Card>
  );
}

export function ScenariosPage() {
  const runs = useApi((signal) => unwrap(api.GET("/api/evaluation/runs", { signal })), []);
  const scenarios = useApi((signal) => unwrap(api.GET("/api/evaluation/scenarios", { signal })), []);

  // The runs arrive newest first, so the first row is the one the pre-registration belongs to.
  const newest = runs.status === "success" ? runs.data.items[0] : undefined;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Evaluation scenarios"
        subtitle="Each run compares three arms over the same data, model, rules and seed; only analyst feedback and the guardrails differ."
      />

      <Card title="Evaluation runs">
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
          {(data) => (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-muted">
                  <tr>
                    <th scope="col" className={TH}>
                      Run
                    </th>
                    <th scope="col" className={TH}>
                      Commit
                    </th>
                    <th scope="col" className={TH}>
                      Verdicts
                    </th>
                    <th scope="col" className={TH}>
                      Arms
                    </th>
                    <th scope="col" className={TH}>
                      Detection identical
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((run) => (
                    <tr key={run.runId} className="border-t border-border">
                      <th scope="row" className={`${TD} text-left font-normal`}>
                        <Link
                          to={`/evaluator/runs/${run.runId}`}
                          className="font-mono text-accent hover:text-text"
                        >
                          {run.runId}
                        </Link>
                      </th>
                      <td className={`${TD} font-mono text-muted`}>
                        {run.commit === null ? "—" : run.commit.slice(0, 8)}
                      </td>
                      <td className={`${TD} font-mono tabular-nums text-text`}>
                        {formatNumber(run.sequenceLength)}
                      </td>
                      <td className={`${TD} text-muted`}>{(run.arms ?? []).join(" · ") || "—"}</td>
                      <td className={TD}>
                        <Pill tone={run.detectionMetricsIdenticalAcrossArms ? "ok" : "danger"}>
                          {run.detectionMetricsIdenticalAcrossArms ? "Yes" : "No"}
                        </Pill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ApiView>
      </Card>

      {newest !== undefined && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <NewestRunCard runId={newest.runId} />

          <Card title="Pre-registration">
            <KeyValues rows={scalarRows(newest.preregistration)} />
            <p className="mt-4 text-sm text-muted">
              The verdict sequence was fixed before the arms were run, so the result could not be
              tuned after it was seen.
            </p>
          </Card>
        </div>
      )}

      <Card title="Scenario records">
        <ApiView
          resource={scenarios}
          isEmpty={(data) => data.items.length === 0}
          empty={
            <EmptyState
              title="No scenario records in this database"
              hint="The demo database holds no scenario rows: each arm ran against its own copy of the database, and the committed run record above is the result."
            />
          }
        >
          {(data) => (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-muted">
                  <tr>
                    <th scope="col" className={TH}>
                      Scenario
                    </th>
                    <th scope="col" className={TH}>
                      Guardrails
                    </th>
                    <th scope="col" className={TH}>
                      Model
                    </th>
                    <th scope="col" className={TH}>
                      Rule set
                    </th>
                    <th scope="col" className={TH}>
                      Verdicts
                    </th>
                    <th scope="col" className={TH}>
                      Created
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((scenario) => (
                    <tr key={scenario.scenarioId} className="border-t border-border">
                      <th scope="row" className={`${TD} text-left font-normal text-text`}>
                        {scenario.name}
                      </th>
                      <td className={TD}>
                        <Pill tone={scenario.guardrailsActive ? "ok" : "danger"}>
                          {scenario.guardrailsActive ? "On" : "Off"}
                        </Pill>
                      </td>
                      <td className={`${TD} font-mono text-muted`}>{scenario.modelVersion}</td>
                      <td className={`${TD} font-mono text-muted`}>{scenario.ruleSetVersion}</td>
                      <td className={`${TD} font-mono tabular-nums text-text`}>
                        {formatNumber(scenario.sequenceLength)}
                      </td>
                      <td className={`${TD} text-muted`}>{formatDateTime(scenario.createdAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ApiView>
      </Card>
    </div>
  );
}
