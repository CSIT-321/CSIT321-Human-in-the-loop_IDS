/**
 * The workstation's centre column: one alert, worked in place.
 *
 * Header — the band's colour rule, the record id, what detected it, and the triage actions (claim,
 * start, resolve, dismiss, release, reopen). Status is workflow, not judgement: these actions never
 * move a score. Verdicts do, and they live in the Verdict tab with the guardrail chain beside them.
 */

import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { api, ApiError, unwrap, type Schemas } from "../../api/client";
import type { ApiResource } from "../../api/useApi";
import { ErrorState, LoadingState } from "../../components/states";
import { BandBadge, Card, EvidenceBadge, Pill, SeverityBadge } from "../../components/ui";
import { formatDateTime, formatPercent, formatScore, humanise } from "../../design/format";
import { EvidencePanelCard } from "../alert/EvidencePanelCard";
import { FeedbackHistoryCard } from "../alert/FeedbackHistoryCard";
import { FlowPanelCard } from "../alert/FlowPanelCard";
import { MlPanelCard } from "../alert/MlPanelCard";
import { SignaturePanelCard } from "../alert/SignaturePanelCard";
import { FeedbackPanel } from "../feedback/FeedbackPanel";
import { ScoreAdjustmentChain } from "../feedback/ScoreAdjustmentChain";
import { Meter } from "./Meter";
import { BAND_RULE, shortFlowTime } from "./QueuePane";

type Detail = Schemas["AlertDetail"];
type Adjustment = Schemas["ScoreAdjustment"];
type History = Schemas["FeedbackHistory"];
type Notes = Schemas["AlertNotes"];
type AlertSummary = Schemas["AlertSummary"];
type AlertStatus = AlertSummary["status"];

const TABS = ["Overview", "Verdict", "Flow record", "Notes", "History"] as const;
type Tab = (typeof TABS)[number];

const ACTION =
  "rounded-sm border px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40";
const SECONDARY = `${ACTION} border-border bg-raised text-text hover:border-border-strong`;
const PRIMARY = `${ACTION} border-primary bg-primary text-on-primary hover:bg-primary-hover`;

function messageOf(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : String(cause);
}

function TriageActions({ alert, onChanged }: { alert: AlertSummary; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(call: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await call();
      onChanged();
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(false);
    }
  }

  const path = { alertRef: alert.alertRef };
  const setStatus = (status: AlertStatus) =>
    run(() => unwrap(api.POST("/api/alerts/{alertRef}/status", { params: { path }, body: { status, reason: null } })));
  const setOwner = (owner: "me" | null) =>
    run(() => unwrap(api.POST("/api/alerts/{alertRef}/assign", { params: { path }, body: { owner, reason: null } })));

  const closed = alert.status === "resolved" || alert.status === "dismissed";
  const owned = alert.owner !== null && alert.owner !== undefined;

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        {closed ? (
          <button type="button" disabled={busy} onClick={() => void setStatus("in_progress")} className={SECONDARY}>
            Reopen
          </button>
        ) : (
          <>
            {owned ? (
              <button type="button" disabled={busy} onClick={() => void setOwner(null)} className={SECONDARY}>
                Release
              </button>
            ) : (
              <button type="button" disabled={busy} onClick={() => void setOwner("me")} className={PRIMARY}>
                Claim
              </button>
            )}
            {alert.status !== "in_progress" && (
              <button type="button" disabled={busy} onClick={() => void setStatus("in_progress")} className={SECONDARY}>
                Start work
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => void setStatus("resolved")}
              className={`${ACTION} border-ok/40 bg-ok-dim text-ok hover:border-ok`}
            >
              Resolve
            </button>
            <button type="button" disabled={busy} onClick={() => void setStatus("dismissed")} className={SECONDARY}>
              Dismiss
            </button>
          </>
        )}
      </div>
      {error !== null && (
        <p role="alert" className="text-right text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

function NotesTab({ alertRef, notes }: { alertRef: string; notes: ApiResource<Notes> }) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (draft.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/alerts/{alertRef}/notes", { params: { path: { alertRef } }, body: { body: draft } }));
      setDraft("");
      notes.reload();
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {notes.status === "loading" && <LoadingState label="Loading notes…" />}
      {notes.status === "error" && <ErrorState error={notes.error} onRetry={notes.reload} />}
      {notes.status === "success" &&
        ((notes.data.notes ?? []).length === 0 ? (
          <p className="text-sm text-muted">No notes yet. Notes are permanent: a correction is a new note.</p>
        ) : (
          <ol className="space-y-2">
            {(notes.data.notes ?? []).map((note) => (
              <li key={note.noteId} className="rounded-sm border border-border bg-surface p-3">
                <p className="flex flex-wrap justify-between gap-2 font-mono text-[11px] text-dim">
                  <span className="text-muted">{note.author.displayName ?? "Unknown user"}</span>
                  <span>{formatDateTime(note.createdAt)}</span>
                </p>
                <p className="mt-1.5 whitespace-pre-wrap text-[13px] text-text">{note.body}</p>
              </li>
            ))}
          </ol>
        ))}
      <form onSubmit={(event) => void submit(event)} className="space-y-2">
        <label htmlFor="note-body" className="label-mono block">
          Add a note
        </label>
        <textarea
          id="note-body"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={2000}
          rows={3}
          placeholder="What you checked, what you found."
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-[13px] text-text placeholder:text-dim focus:border-primary"
        />
        {error !== null && (
          <p role="alert" className="text-xs text-danger">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || draft.trim() === ""} className={PRIMARY}>
          Add note
        </button>
      </form>
    </div>
  );
}

export function AlertPane({
  detail,
  detailResource,
  adjustment,
  adjustmentResource,
  history,
  historyResource,
  notes,
  refreshing,
  onChanged,
}: {
  detail: Detail | null;
  detailResource: ApiResource<Detail>;
  adjustment: Adjustment | null;
  adjustmentResource: ApiResource<Adjustment>;
  history: History | null;
  historyResource: ApiResource<History>;
  notes: ApiResource<Notes>;
  refreshing: boolean;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<Tab>("Overview");

  if (detail === null) {
    return (
      <section aria-label="Alert detail" className="min-h-0 overflow-y-auto p-5">
        {detailResource.status === "error" ? (
          <ErrorState error={detailResource.error} onRetry={detailResource.reload} />
        ) : (
          <LoadingState label="Loading alert…" />
        )}
      </section>
    );
  }

  const alert = detail.alert;

  return (
    <section aria-label="Alert detail" className="flex min-h-0 flex-col overflow-hidden bg-bg">
      <header className={`border-b border-l-4 border-b-border bg-surface px-5 py-3 ${BAND_RULE[alert.queueClass]}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs font-semibold text-accent">{alert.sourceRecordId}</span>
              <BandBadge queueClass={alert.queueClass} />
              <EvidenceBadge evidenceClass={alert.evidenceClass} />
              {detail.evidence.tier2Candidate && alert.queueClass !== "tier2_candidate" && (
                <Pill tone="danger">→ Tier 2 candidate</Pill>
              )}
              {alert.requiresReview && <Pill tone="warn">Needs review</Pill>}
              {refreshing && (
                <span role="status" aria-live="polite" className="font-mono text-[10px] text-dim">
                  refreshing…
                </span>
              )}
            </p>
            <h2 className="flex flex-wrap items-center gap-3 text-lg font-semibold text-text">
              {alert.attackCategory ?? "No detection"}
              <SeverityBadge severity={alert.severity} />
            </h2>
            <p className="font-mono text-[11px] text-muted">
              {alert.srcIp} → {alert.dstIp}:{alert.dstPort}/{alert.protocol} · captured {shortFlowTime(alert.flowTime)} ·{" "}
              {humanise(alert.status)}
              {alert.owner !== null && alert.owner !== undefined && ` · ${alert.owner.displayName ?? "owned"}`}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <TriageActions alert={alert} onChanged={onChanged} />
            <Link to={`/analyst/alerts/${alert.alertRef}`} className="font-mono text-[11px] text-dim hover:text-accent">
              Open full page ↗
            </Link>
          </div>
        </div>

        <div className="mt-3 grid gap-4 sm:grid-cols-3">
          <Meter label="Operational score" value={alert.combinedScore} max={100} display={formatScore(alert.combinedScore)} tone="bg-primary" hint="What analyst feedback moves" />
          <Meter label="Detection score" value={alert.detectionScore} max={100} display={formatScore(alert.detectionScore)} tone="bg-muted" hint="What detection produced; never changes" />
          <Meter
            label="Model confidence"
            value={alert.confidence}
            max={1}
            display={formatPercent(alert.confidence)}
            tone="bg-accent"
            hint="The model's probability for its predicted class — not a false-positive probability"
          />
        </div>
      </header>

      <div role="tablist" aria-label="Alert sections" className="flex gap-1 border-b border-border bg-surface px-4">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            className={`-mb-px border-b-2 px-3 py-2 text-[13px] ${
              tab === name ? "border-primary text-text" : "border-transparent text-muted hover:text-text"
            }`}
          >
            {name}
            {name === "Verdict" && detail.feedbackCount > 0 && (
              <span className="ml-1.5 font-mono text-[10px] text-ok">{detail.feedbackCount}</span>
            )}
          </button>
        ))}
      </div>

      <div role="tabpanel" aria-label={tab} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
        {tab === "Overview" && (
          <>
            <EvidencePanelCard evidence={detail.evidence} />
            <div className="grid gap-4 2xl:grid-cols-2">
              <SignaturePanelCard signature={detail.signature} />
              <MlPanelCard ml={detail.ml} />
            </div>
          </>
        )}
        {tab === "Verdict" && (
          <>
            <Card title="Score adjustment">
              {adjustment !== null ? (
                <ScoreAdjustmentChain adjustment={adjustment} />
              ) : adjustmentResource.status === "error" ? (
                <ErrorState error={adjustmentResource.error} onRetry={adjustmentResource.reload} />
              ) : (
                <LoadingState />
              )}
            </Card>
            <FeedbackPanel alertRef={alert.alertRef} current={detail.currentFeedback} onRecorded={onChanged} />
          </>
        )}
        {tab === "Flow record" && <FlowPanelCard flow={detail.flow} />}
        {tab === "Notes" && <NotesTab alertRef={alert.alertRef} notes={notes} />}
        {tab === "History" &&
          (history !== null ? (
            <FeedbackHistoryCard history={history} />
          ) : historyResource.status === "error" ? (
            <ErrorState error={historyResource.error} onRetry={historyResource.reload} />
          ) : (
            <LoadingState />
          ))}
      </div>
    </section>
  );
}
