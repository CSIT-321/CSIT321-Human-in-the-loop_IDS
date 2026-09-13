/**
 * The evaluator's entry screen (plan step S14).
 *
 * Three things, in the order a reader needs them. The committed three-arm runs, so the run id is a
 * click rather than something typed from a terminal. The newest run's pre-registration, because the
 * result only means something once you can see the rule was fixed before the arms ran. And the
 * scenario rows, which the demo database does not hold — each arm ran against its own copy — and
 * which therefore read as an explanation rather than as an empty table.
 */

import { Link } from "react-router";

import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, KeyValues, PageHeader, Pill } from "../../components/ui";
import { formatDateTime, formatNumber } from "../../design/format";
import { scalarRows } from "../../features/evaluation/values";

const TH = "px-3 py-2 font-medium";
const TD = "px-3 py-1.5";

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
        <Card title="Pre-registration">
          <KeyValues rows={scalarRows(newest.preregistration)} />
          <p className="mt-4 text-sm text-muted">
            The verdict sequence was fixed before the arms were run, so the result could not be tuned
            after it was seen.
          </p>
        </Card>
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
