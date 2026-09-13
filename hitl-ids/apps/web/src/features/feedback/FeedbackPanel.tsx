/**
 * Record a verdict, then show exactly what the guardrails did with it (plan S12 — Claude's part).
 *
 * The write path is the one place a mistake is costly: it moves scores. So the panel states the
 * request before submission, sends one verdict, and renders the outcome *from the API response*. It
 * never predicts the applied change locally, because only the guardrails know it.
 */

import { useState, type FormEvent } from "react";

import { api, ApiError, CLIENT_ERROR, unwrap, type Schemas } from "../../api/client";
import { ErrorState } from "../../components/states";
import { Card, Pill } from "../../components/ui";
import { formatDelta } from "../../design/format";
import { categoryMeta, FEEDBACK_CATEGORIES, type FeedbackCategory } from "./categories";
import { ScoreAdjustmentChain } from "./ScoreAdjustmentChain";

type FeedbackResponse = Schemas["FeedbackResponse"];

export function FamilyEffectNotice({ family }: { family: Schemas["FamilyEffect"] }) {
  const moved = family.membersMoved ?? 0;
  return (
    <div
      role="status"
      aria-label="Similar-alert learning"
      className="rounded-sm border border-border bg-raised px-4 py-3 text-sm"
    >
      <p className="font-medium text-text">
        {family.gateOpen
          ? `Similar-alert learning applied: ${moved} other ${moved === 1 ? "alert" : "alerts"} in this family moved.`
          : "Similar-alert learning did not apply."}
      </p>
      {family.gateReason !== null && family.gateReason !== undefined && (
        <p className="mt-1 text-muted">{family.gateReason}</p>
      )}
    </div>
  );
}

export function FeedbackPanel({
  alertRef,
  current,
  onRecorded,
}: {
  alertRef: string;
  current: Schemas["FeedbackRecord"] | null | undefined;
  onRecorded: (response: FeedbackResponse) => void;
}) {
  const [category, setCategory] = useState<FeedbackCategory | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<FeedbackResponse | null>(null);

  const selected = category === null ? null : categoryMeta(category);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (category === null || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await unwrap(
        api.POST("/api/alerts/{alertRef}/feedback", {
          params: { path: { alertRef } },
          body: { category, note: note.trim() === "" ? null : note.trim() },
        }),
      );
      setResult(response);
      setCategory(null);
      setNote("");
      onRecorded(response);
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause
          : new ApiError(0, { code: CLIENT_ERROR.unexpected, message: String(cause) }),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card
      title="Record a verdict"
      subtitle="The decision is yours. Guardrails bound how far it may move the score."
    >
      {current !== null && current !== undefined && (
        <p className="mb-4 text-sm text-muted">
          Current verdict: <span className="text-text">{categoryMeta(current.category).label}</span>. A
          new verdict replaces it rather than stacking on it; both stay in the history.
        </p>
      )}

      <form onSubmit={(event) => void submit(event)} className="space-y-4">
        <fieldset className="@container">
          <legend className="mb-2 text-sm text-muted">Verdict</legend>
          {/* Sized by the panel, not the viewport: the workstation's centre column is narrow. */}
          <div
            role="radiogroup"
            aria-label="Verdict"
            className="grid grid-cols-1 gap-2 @md:grid-cols-2 @4xl:grid-cols-5"
          >
            {FEEDBACK_CATEGORIES.map((option) => {
              const checked = option.value === category;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={checked}
                  onClick={() => setCategory(option.value)}
                  className={`rounded-sm border px-3 py-2 text-left text-sm ${
                    checked
                      ? "border-accent bg-accent-dim text-accent"
                      : "border-border bg-raised text-text hover:border-accent/60"
                  }`}
                >
                  <span className="block font-medium">{option.label}</span>
                  <span className="block font-mono text-xs text-muted">
                    requests {formatDelta(option.requestedDelta)}
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="space-y-1">
          <label htmlFor="feedback-note" className="block text-sm text-muted">
            Investigation note (optional)
          </label>
          <textarea
            id="feedback-note"
            value={note}
            maxLength={2000}
            rows={3}
            onChange={(event) => setNote(event.target.value)}
            className="w-full rounded-sm border border-border bg-raised px-3 py-2 text-sm text-text placeholder:text-dim"
            placeholder="What did you check, and what did you find?"
          />
        </div>

        {selected !== null && (
          <p aria-live="polite" className="text-sm text-muted">
            <span className="text-text">{selected.label}</span> requests{" "}
            <span className="font-mono">{formatDelta(selected.requestedDelta)}</span>. {selected.description}{" "}
            {selected.teachesFamily
              ? "It counts towards what this alert's family learns once three verdicts agree."
              : "It does not teach the alert's family."}{" "}
            The applied change is decided by the guardrails and shown after you submit.
          </p>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={category === null || submitting}
            className="rounded-sm bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? "Recording…" : "Record verdict"}
          </button>
          {category === null && <span className="text-xs text-dim">Choose a verdict first.</span>}
        </div>
      </form>

      {error !== null && (
        <div className="mt-4">
          <ErrorState error={error} />
        </div>
      )}

      {result !== null && (
        <section aria-label="Verdict outcome" className="mt-6 space-y-4 border-t border-border pt-5">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="ok">Verdict recorded</Pill>
            <span className="text-sm text-text">{categoryMeta(result.feedback.category).label}</span>
          </div>
          <ScoreAdjustmentChain adjustment={result.feedback.adjustment} />
          <FamilyEffectNotice family={result.family} />
        </section>
      )}
    </Card>
  );
}
