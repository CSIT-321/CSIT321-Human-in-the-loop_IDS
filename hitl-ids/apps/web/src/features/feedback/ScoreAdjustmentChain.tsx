/**
 * The screen the project turns on: original → requested Δ → guardrail bound → actual Δ → final.
 *
 * **Guardrails are shown, never silent** (plan S12 exit criterion). Every intervention is printed with
 * the API's own sentence and the configured value that caused it, so a reader can redo the arithmetic.
 * A refusal is presented as the system working — the verdict was recorded, the score was protected —
 * not as a failed action, which is why the API returns it as a 200.
 */

import type { Schemas } from "../../api/client";
import { Pill, type Tone } from "../../components/ui";
import { bandLabel } from "../../design/bands";
import { formatDelta, formatScore, humanise } from "../../design/format";

type Adjustment = Schemas["ScoreAdjustment"];
type Action = Adjustment["action"];

const ACTION: Record<Action, { tone: Tone; label: string; meaning: string }> = {
  applied: {
    tone: "ok",
    label: "Applied as requested",
    meaning: "No guardrail needed to act.",
  },
  capped: {
    tone: "warn",
    label: "Capped by a guardrail",
    meaning:
      "The verdict is recorded in full. The guardrail limited how far the score moved, not the finding.",
  },
  rejected: {
    tone: "danger",
    label: "Refused by a guardrail",
    meaning:
      "The verdict is recorded, and the score was not changed. The disagreement is now on the record for an administrator.",
  },
};

function Step({
  label,
  value,
  emphasis = false,
  tone = "text-text",
}: {
  label: string;
  value: string;
  emphasis?: boolean;
  tone?: string;
}) {
  return (
    <div className="flex min-w-24 flex-col rounded-sm border border-border bg-raised px-3 py-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`font-mono tabular-nums ${emphasis ? "text-xl font-semibold" : "text-base"} ${tone}`}>
        {value}
      </dd>
    </div>
  );
}

function Arrow() {
  return (
    <span aria-hidden className="self-center text-dim">
      →
    </span>
  );
}

function deltaTone(value: number): string {
  if (value > 0) return "text-ok";
  if (value < 0) return "text-warn";
  return "text-muted";
}

function present(value: number | null | undefined): value is number {
  return value !== null && value !== undefined;
}

export function ScoreAdjustmentChain({ adjustment }: { adjustment: Adjustment }) {
  const action = ACTION[adjustment.action];
  const interventions = adjustment.interventions ?? [];
  const bandMoved = adjustment.queueClassBefore !== adjustment.queueClassAfter;
  const bound =
    adjustment.action !== "applied" ||
    adjustment.requestedDelta !== adjustment.actualDelta ||
    interventions.length > 0;
  const guardrailValue = !bound ? "None" : adjustment.action === "rejected" ? "Refused" : "Bound";
  const guardrailTone = !bound ? "text-muted" : adjustment.action === "rejected" ? "text-danger" : "text-warn";

  return (
    <div role="group" aria-label="Score adjustment" className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Pill tone={action.tone}>{action.label}</Pill>
        <p className="text-sm text-text">{adjustment.summary}</p>
      </div>

      <dl className="flex flex-wrap items-stretch gap-2">
        <Step label="Detection score" value={formatScore(adjustment.detectionScore)} />
        <Arrow />
        <Step label="Score before" value={formatScore(adjustment.scoreBefore)} />
        <Arrow />
        <Step
          label="Requested change"
          value={formatDelta(adjustment.requestedDelta)}
          tone={deltaTone(adjustment.requestedDelta)}
        />
        <Arrow />
        <Step label="Guardrail" value={guardrailValue} tone={guardrailTone} />
        <Arrow />
        <Step
          label="Applied change"
          value={formatDelta(adjustment.actualDelta)}
          tone={deltaTone(adjustment.actualDelta)}
        />
        <Arrow />
        <Step label="Operational score" value={formatScore(adjustment.scoreAfter)} emphasis />
      </dl>

      {adjustment.action !== "applied" && <p className="text-sm text-muted">{action.meaning}</p>}

      {interventions.length > 0 && (
        <ul aria-label="Guardrail interventions" className="space-y-2">
          {interventions.map((intervention, index) => (
            <li
              key={`${intervention.code}-${index}`}
              className="rounded-sm border border-warn/40 bg-warn-dim/30 px-4 py-3 text-sm"
            >
              <p className="text-text">{intervention.explanation}</p>
              <p className="mt-1 font-mono text-xs text-muted">
                {humanise(intervention.code)} · configured {formatScore(intervention.configuredValue)}
                {present(intervention.originalValue) ? ` · requested ${formatScore(intervention.originalValue)}` : ""}
                {present(intervention.appliedValue) ? ` · applied ${formatScore(intervention.appliedValue)}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}

      <p className="text-sm text-muted">
        Queue band:{" "}
        {bandMoved ? (
          <>
            <span className="text-text">{bandLabel(adjustment.queueClassBefore)}</span> →{" "}
            <span className="font-semibold text-accent">{bandLabel(adjustment.queueClassAfter)}</span>
          </>
        ) : (
          <span className="text-text">{bandLabel(adjustment.queueClassAfter)} (unchanged)</span>
        )}
        {adjustment.requiresReview ? " · stays flagged for review" : " · no longer flagged for review"}
      </p>
    </div>
  );
}
