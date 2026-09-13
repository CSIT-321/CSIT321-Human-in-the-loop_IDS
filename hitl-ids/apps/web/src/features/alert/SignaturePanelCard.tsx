/**
 * Panel 2 — the rules that fired, and the clauses that fired them (plan S12).
 *
 * The empty state is the common case and it is not a failure: the corpus is dominated by ML-only
 * alerts, and the panel says so in the API's own words rather than showing an empty list.
 *
 * `matchedConditions` arrives as `{ [key: string]: unknown }`, so every field is narrowed here. The
 * expected value is either a scalar (`= 80`) or a range object (`≥ 40 ≤ 1024`), which is why it is
 * rendered rather than cast.
 */

import type { Schemas } from "../../api/client";
import { EmptyState } from "../../components/states";
import { Card, SeverityBadge } from "../../components/ui";
import { formatNumber } from "../../design/format";

type SignaturePanel = Schemas["SignaturePanel"];
type RuleMatchPanel = Schemas["RuleMatchPanel"];
type Condition = { [key: string]: unknown };

const EMPTY_HINT =
  "Rules have high precision and low recall: they give a checkable reason when they fire, and most attacks are caught by the model alone.";

function conditionFeature(condition: Condition): string {
  const feature = condition["feature"];
  return typeof feature === "string" ? feature : "—";
}

/** What the clause required: a scalar equality, or a bound (or both). */
function renderExpected(value: unknown): string {
  if (typeof value === "number") return `= ${formatNumber(value)}`;
  if (typeof value === "string") return `= ${value}`;
  if (typeof value === "object" && value !== null) {
    const bounds: string[] = [];
    if ("min" in value && typeof value.min === "number") bounds.push(`≥ ${formatNumber(value.min)}`);
    if ("max" in value && typeof value.max === "number") bounds.push(`≤ ${formatNumber(value.max)}`);
    if (bounds.length > 0) return bounds.join(" · ");
  }
  return "—";
}

function renderObserved(value: unknown): string {
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "string") return value;
  return "—";
}

function ConditionTable({ rule }: { rule: RuleMatchPanel }) {
  const conditions = rule.matchedConditions ?? [];
  if (conditions.length === 0) return null;

  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-muted">
            <th scope="col" className="px-3 py-2 font-medium">
              Condition
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Required
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Observed
            </th>
          </tr>
        </thead>
        <tbody>
          {conditions.map((condition, index) => (
            <tr key={`${conditionFeature(condition)}-${index}`} className="border-t border-border">
              <th scope="row" className="px-3 py-1.5 text-left font-mono text-xs font-normal text-muted">
                {conditionFeature(condition)}
              </th>
              <td className="px-3 py-1.5 font-mono tabular-nums text-text">
                {renderExpected(condition["expected"])}
              </td>
              <td className="px-3 py-1.5 font-mono tabular-nums text-text">
                {renderObserved(condition["observed"])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SignaturePanelCard({ signature }: { signature: SignaturePanel }) {
  const matched = signature.matched ?? [];

  if (matched.length === 0) {
    return (
      <Card title="Signature rules">
        <EmptyState title={signature.note ?? "No rule matched this flow."} hint={EMPTY_HINT} />
      </Card>
    );
  }

  return (
    <Card
      title="Signature rules"
      subtitle={
        signature.ruleSetVersion !== null ? (
          <span className="font-mono text-xs">{signature.ruleSetVersion}</span>
        ) : undefined
      }
    >
      <ul className="space-y-3">
        {matched.map((rule) => (
          <li key={rule.ruleId} className="rounded-sm border border-border bg-raised p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-text">{rule.name}</span>
              <SeverityBadge severity={rule.severity} />
              <span className="font-mono text-xs text-muted">{rule.ruleId}</span>
              {rule.attackCategory !== null && (
                <span className="text-xs text-muted">{rule.attackCategory}</span>
              )}
            </div>
            {rule.rationale !== null && <p className="mt-2 text-sm text-muted">{rule.rationale}</p>}
            <ConditionTable rule={rule} />
          </li>
        ))}
      </ul>
    </Card>
  );
}
