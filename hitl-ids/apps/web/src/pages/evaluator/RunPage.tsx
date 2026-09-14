/**
 * One evaluation run, as measured (plan step S14).
 *
 * The run is a committed record, not a query: three arms over the same data, model, rules and seed,
 * with only feedback and the guardrails differing. The screen's job is to report the comparison
 * honestly — every delta is rendered in the direction it actually moved, including the ones that went
 * the wrong way, and the banner says so before the reader meets them.
 *
 * The layout is the workstation's: a headline strip of the run's shape, then the comparison and the
 * guardrail outcomes side by side, then the tables that carry the detail.
 */

import { Link, useParams } from "react-router";

import type { Schemas } from "../../api/client";
import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, Delta, KeyValues, PageHeader, Pill, StatStrip, type Stat } from "../../components/ui";
import { formatNumber, formatRatio, formatScore } from "../../design/format";
import {
  MOVEMENT_ROWS,
  deltaGroupLabel,
  formatMetricDelta,
  higherIsBetter,
  humaniseKey,
} from "../../features/evaluation/labels";
import { scalarRows, shortDigest } from "../../features/evaluation/values";

type Comparison = Schemas["EvaluationComparison"];
type Deltas = Comparison["deltas"];
type Movement = Comparison["movement"];
type MovementBlock = { [group: string]: Schemas["MovementGroup"] };

const TH = "px-3 py-2 font-medium";
const TD = "px-3 py-1.5";

/** "On"/"Off" as a pill: the two axes that differ between the arms. */
function Switch({ on }: { on: boolean }) {
  return <Pill tone={on ? "ok" : "muted"}>{on ? "On" : "Off"}</Pill>;
}

function PassFail({ pass }: { pass: boolean }) {
  return <Pill tone={pass ? "ok" : "danger"}>{pass ? "Pass" : "Fail"}</Pill>;
}

/**
 * The warning this whole screen is arranged around: the deltas below are not all favourable, and the
 * page says so in words before showing the table that proves it.
 */
function MeasuredBanner({ deltas }: { deltas: Deltas }) {
  // Any precision@k that fell, in any arm pair — the B−A and C−A groups both report it here.
  const precisionFell = Object.values(deltas ?? {}).some((group) =>
    Object.entries(group).some(([metric, change]) => metric.startsWith("precision_at") && change < 0),
  );

  return (
    <div role="note" className="rounded-sm border border-stub/40 bg-stub-bg p-4 text-sm text-stub">
      <p>Deltas are shown as measured, including those that went the wrong way.</p>
      {precisionFell && (
        <p className="mt-2">
          Precision fell under feedback on this sample: the control queue was already near-perfect, so
          feedback could only disturb it.
        </p>
      )}
    </div>
  );
}

/** The run's shape in four figures — what the strip is for, before the tables get into the detail. */
function runStats(run: Comparison): readonly Stat[] {
  return [
    {
      label: "Verdicts in sequence",
      value: formatNumber(run.sequenceLength),
      hint: "Analyst verdicts replayed through each arm",
    },
    {
      label: "Arms",
      value: formatNumber((run.arms ?? []).length),
      hint: "How many arms this run recorded",
    },
    {
      label: "Detection identical",
      value: run.detectionMetricsIdenticalAcrossArms ? "Yes" : "No",
      tone: run.detectionMetricsIdenticalAcrossArms ? "text-ok" : "text-danger",
      hint: "Proof that feedback reordered the queue and did not touch the detector",
    },
    {
      label: "Commit",
      value: run.commit === null ? "—" : run.commit.slice(0, 8),
      hint: "The commit the run was recorded at",
    },
  ];
}

function ComparisonCard({ run }: { run: Comparison }) {
  return (
    <Card title="What was compared">
      <KeyValues
        rows={[
          ["Verdicts in the sequence", formatNumber(run.sequenceLength)],
          [
            "Detection identical across arms",
            <Pill
              key="identical"
              tone={run.detectionMetricsIdenticalAcrossArms ? "ok" : "danger"}
              title="Proof that feedback reordered the queue and did not touch the detector"
            >
              {run.detectionMetricsIdenticalAcrossArms ? "Yes" : "No"}
            </Pill>,
          ],
          [
            "Commit",
            <span key="commit" className="font-mono">
              {run.commit ?? "—"}
            </span>,
          ],
          [
            "Sequence digest",
            <span key="digest" className="font-mono">
              {shortDigest(run.sequenceDigest)}
            </span>,
          ],
        ]}
      />
    </Card>
  );
}

function ArmsCard({ arms }: { arms: readonly Schemas["ArmResultOut"][] }) {
  if (arms.length === 0) {
    return (
      <Card title="Arms">
        <EmptyState title="This run records no arms" />
      </Card>
    );
  }

  return (
    <Card title="Arms" subtitle="The same detection everywhere; only feedback and the guardrails differ.">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[13px]">
          <thead className="text-muted">
            <tr>
              <th scope="col" className={TH}>
                Arm
              </th>
              <th scope="col" className={TH}>
                Feedback
              </th>
              <th scope="col" className={TH}>
                Guardrails
              </th>
              <th scope="col" className={TH}>
                Verdicts
              </th>
              <th scope="col" className={TH} title="Precision at 50">
                P@50
              </th>
              <th scope="col" className={TH} title="False positives in top 50">
                FP top 50
              </th>
              <th scope="col" className={TH} title="MRR (true positives)">
                MRR TP
              </th>
              <th scope="col" className={TH} title="Mean rank (true positives)">
                Mean rank TP
              </th>
              <th scope="col" className={TH} title="Critical floor breaches">
                Floor breaches
              </th>
              <th scope="col" className={TH} title="Guardrail pass or fail">
                Guardrail check
              </th>
              <th scope="col" className={TH} title="Guardrail actions, as the arm recorded them">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {arms.map((arm) => {
              const actions = Object.entries(arm.guardrailActions ?? {});
              return (
                <tr key={arm.arm} className="border-t border-border">
                  <th scope="row" className={`${TD} whitespace-nowrap text-left font-normal text-text`}>
                    {arm.arm}
                  </th>
                  <td className={TD}>
                    <Switch on={arm.feedback} />
                  </td>
                  <td className={TD}>
                    <Switch on={arm.guardrails} />
                  </td>
                  <td className={`${TD} font-mono tabular-nums text-text`}>
                    {formatNumber(arm.verdicts)}
                  </td>
                  <td className={`${TD} font-mono tabular-nums text-text`}>
                    {formatRatio(arm.precisionAt50)}
                  </td>
                  <td className={`${TD} font-mono tabular-nums text-text`}>
                    {formatNumber(arm.falsePositivesInTop50)}
                  </td>
                  <td className={`${TD} font-mono tabular-nums text-text`}>
                    {formatRatio(arm.mrrTruePositives)}
                  </td>
                  <td className={`${TD} font-mono tabular-nums text-text`}>
                    {formatScore(arm.meanRankTruePositives)}
                  </td>
                  <td className={`${TD} font-mono tabular-nums text-text`}>
                    {formatNumber(arm.criticalFloorBreaches)}
                  </td>
                  <td className={TD}>
                    <PassFail pass={arm.guardrailPass} />
                  </td>
                  <td className={`${TD} text-muted`}>
                    {actions.length === 0
                      ? "none"
                      : actions.map(([action, count]) => `${action} ${formatNumber(count)}`).join(", ")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/** One table per arm pair, the three pairs side by side. Nothing is sorted, filtered or dropped. */
function DeltasCard({ deltas }: { deltas: Deltas }) {
  const groups = Object.entries(deltas ?? {});

  return (
    <Card
      title="Deltas"
      subtitle="Each pair, measured against the same detection. A metric that fell is shown as a fall."
    >
      {groups.length === 0 ? (
        <EmptyState title="This run records no deltas" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {groups.map(([group, metrics]) => (
            <div key={group} className="min-w-0">
              <h3 className="text-sm font-semibold text-text">{deltaGroupLabel(group)}</h3>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <thead className="text-muted">
                    <tr>
                      <th scope="col" className={TH}>
                        Metric
                      </th>
                      <th scope="col" className={TH}>
                        Change
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(metrics).map(([metric, change]) => (
                      <tr key={metric} className="border-t border-border">
                        <th scope="row" className={`${TD} text-left font-normal text-text`}>
                          {humaniseKey(metric)}
                        </th>
                        <td className={TD}>
                          <Delta
                            value={change}
                            higherIsBetter={higherIsBetter(metric)}
                            format={(value) => formatMetricDelta(metric, value)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/** Who moved, split by how they relate to the 40 judged alerts. */
function MovementCard({ movement }: { movement: Movement }) {
  const blocks: { readonly arm: string; readonly groups: MovementBlock }[] = [];
  for (const [arm, groups] of Object.entries(movement ?? {})) {
    if (groups !== null) blocks.push({ arm, groups });
  }

  return (
    <Card
      title="Who moved"
      subtitle="Movement is grouped by the analyst's verdicts; the unrelated group is the leakage check."
    >
      {blocks.length === 0 ? (
        <EmptyState title="This run records no movement" />
      ) : (
        <div className="space-y-6">
          {blocks.map(({ arm, groups }) => {
            const rows = MOVEMENT_ROWS.map(([key, label]) => [key, label, groups[key]] as const).filter(
              (row): row is readonly [string, string, Schemas["MovementGroup"]] => row[2] !== undefined,
            );
            const benignBestRanks = rows
              .map(([key, , group]) => ({ key, rank: group.bestRankReachedByABenignAlert }))
              .filter((entry) => entry.rank !== null);

            return (
              <div key={arm}>
                <h3 className="text-sm font-semibold text-text">{arm}</h3>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-left text-[13px]">
                    <thead className="text-muted">
                      <tr>
                        <th scope="col" className={TH}>
                          Group
                        </th>
                        <th scope="col" className={TH}>
                          Alerts
                        </th>
                        <th scope="col" className={TH}>
                          Promoted
                        </th>
                        <th scope="col" className={TH}>
                          Demoted
                        </th>
                        <th scope="col" className={TH}>
                          Band changed
                        </th>
                        <th scope="col" className={TH}>
                          Attacks promoted
                        </th>
                        <th scope="col" className={TH}>
                          Benign promoted
                        </th>
                        <th scope="col" className={TH}>
                          Mean rank change
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(([key, label, group]) => (
                        <tr key={key} className="border-t border-border">
                          <th scope="row" className={`${TD} text-left font-normal text-text`}>
                            {label}
                          </th>
                          <td className={`${TD} font-mono tabular-nums text-text`}>
                            {formatNumber(group.alerts)}
                          </td>
                          <td className={`${TD} font-mono tabular-nums text-text`}>
                            {formatNumber(group.promoted)}
                          </td>
                          <td className={`${TD} font-mono tabular-nums text-text`}>
                            {formatNumber(group.demoted)}
                          </td>
                          <td className={`${TD} font-mono tabular-nums text-text`}>
                            {formatNumber(group.bandChanged)}
                          </td>
                          <td className={`${TD} font-mono tabular-nums text-text`}>
                            {formatNumber(group.attacksPromoted)}
                          </td>
                          <td className={`${TD} font-mono tabular-nums text-text`}>
                            {formatNumber(group.benignPromoted)}
                          </td>
                          <td className={`${TD} font-mono tabular-nums text-text`}>
                            {formatMetricDelta("mean_rank_change", group.meanRankChange)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {benignBestRanks.map((entry) => (
                  <p key={entry.key} className="mt-2 text-sm text-warn">
                    {`A benign alert reached rank ${entry.rank} in ${arm}.`}
                  </p>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

/**
 * What the guardrails held back. The run records this as an open dict; every entry is printed as it
 * stands, including the ones that are zero, because "the guardrails never bound here" is a result.
 */
function GuardrailsCard({ prevented }: { prevented: Comparison["guardrailsPrevented"] }) {
  const rows = scalarRows(prevented);

  return (
    <Card title="What the guardrails prevented">
      {rows.length === 0 ? (
        <EmptyState title="This run records no guardrail outcomes" />
      ) : (
        <KeyValues rows={rows} />
      )}
      <p className="mt-4 text-sm text-muted">
        Zero everywhere means the guardrails did not bind on this sequence — a result, not a failed
        run.
      </p>
    </Card>
  );
}

export function RunPage() {
  const { runId = "" } = useParams();
  const run = useApi(
    (signal) =>
      unwrap(api.GET("/api/evaluation/runs/{runId}", { params: { path: { runId } }, signal })),
    [runId],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Evaluation run ${runId}`}
        subtitle={
          <>
            <Link to="/evaluator/metrics" className="text-accent hover:text-text">
              Detection metrics for this run
            </Link>
            {" · "}
            <Link to="/evaluator/scenarios" className="text-accent hover:text-text">
              ← All runs
            </Link>
          </>
        }
      />

      <ApiView resource={run}>
        {(data) => (
          <>
            <MeasuredBanner deltas={data.deltas} />
            <div className="mt-6 space-y-6">
              <StatStrip label="Run" stats={runStats(data)} />

              <div className="grid gap-4 xl:grid-cols-2">
                <ComparisonCard run={data} />
                <GuardrailsCard prevented={data.guardrailsPrevented} />
              </div>

              <ArmsCard arms={data.arms ?? []} />
              <DeltasCard deltas={data.deltas} />
              <MovementCard movement={data.movement} />
            </div>
          </>
        )}
      </ApiView>
    </div>
  );
}
