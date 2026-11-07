import { useRef, useState } from "react";
import { api, unwrap, type Schemas } from "../../api/client";

type Work = Schemas["WorkView"];
const button = "rounded-sm border border-border bg-raised px-2.5 py-1.5 text-xs hover:border-border-strong disabled:opacity-40";

export function workLabel(work: Work) {
  if (work.status === "in_review") return work.isOwner ? "In Review — You" : `In Review — ${work.ownerName}`;
  if (work.status === "completed") return `Completed — Reviewed by ${work.finishedByName}`;
  if (work.status === "escalated") return `Escalated — ${work.finishedByName}`;
  return work.status === "available" ? "Available" : "No active Tier 1 work";
}

/** Release (C7 screen, decision D5; layout approved 2026-11-08). Shown only when the server says canRelease.
 *  The owner's reason is optional; an administrator's reason is required (releaseReasonRequired). */
function ReleaseControl({ work, alertRef, onReleased }: { work: Work; alertRef: string; onReleased: (work: Work) => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<{ requestId: string; reason: string | null } | null>(null);
  const admin = work.releaseReasonRequired;
  const trimmed = reason.trim();
  const ready = !busy && (!admin || trimmed !== "");

  async function submit() {
    if (!ready) return;
    const sent = trimmed === "" ? null : trimmed;
    // Same request id for a retry of the same release; the server replays it instead of releasing twice.
    if (!pending.current || pending.current.reason !== sent) pending.current = { requestId: crypto.randomUUID(), reason: sent };
    setBusy(true); setError("");
    try {
      const result = await unwrap(api.POST("/api/v2/alerts/{alertRef}/work/release", {
        params: { path: { alertRef } },
        body: { requestId: pending.current.requestId, expectedRevision: work.revision, reason: sent },
      }));
      pending.current = null; setOpen(false); setReason("");
      onReleased(result.work);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The release could not be confirmed.");
    } finally { setBusy(false); }
  }

  if (!open) return <button type="button" className={button + (admin ? " text-warn" : "")} onClick={() => setOpen(true)}>
    {admin ? "Release (admin)" : "Release claim"}</button>;
  return <div className="space-y-2 rounded-sm border border-border bg-surface p-2">
    <p>Release this alert back to the queue?</p>
    <label className="block">
      <span className="sr-only">Reason</span>
      <input className="w-full min-w-0 rounded-sm border border-border bg-raised p-1.5 text-xs" value={reason} maxLength={500}
        placeholder={admin ? "Reason (required)" : "Reason (optional for your own claim)"} onChange={event => setReason(event.target.value)} />
    </label>
    {admin && <p className="text-muted">Admin release requires a reason. The release is audited.</p>}
    {error && <p role="alert" className="break-words text-warn">{error}</p>}
    <div className="flex gap-2">
      <button type="button" className={button} disabled={!ready} onClick={() => void submit()}>Release</button>
      <button type="button" className={button} disabled={busy} onClick={() => { setOpen(false); setError(""); setReason(""); pending.current = null; }}>Cancel</button>
    </div>
  </div>;
}

function idleFor(claimedAt: string | null) {
  if (!claimedAt) return "";
  const minutes = Math.floor((Date.now() - Date.parse(claimedAt)) / 60000);
  return Number.isFinite(minutes) && minutes >= 0 ? ` ${minutes} min` : "";
}

/** Claim submission belongs to the explicit queue selection gesture in the Workstation. */
export function AnalystWorkPanel({ work, starting = false, alertRef, onReleased }: {
  work: Work; starting?: boolean; alertRef?: string; onReleased?: (work: Work) => void;
}) {
  const status = starting ? "Starting review…" : work.status === "available" ? "Available for Review" :
    work.status === "in_review" ? "In Review" : workLabel(work);
  return <section aria-label="Human work status" className="min-w-0 space-y-2 rounded-sm border border-border p-3 text-xs">
    <p>Work Status: <strong>{status}</strong></p>
    {!starting && work.status === "in_review" && <>
      <p>Owner: <strong>{work.isOwner ? `${work.ownerName ?? "You"} (You)` : work.ownerName ?? "Unknown"}</strong>
        {work.idle && <span className="text-warn"> · idle{idleFor(work.claimedAt)}</span>}</p>
      <p>Your Access: <strong>{work.isOwner ? "Owner" : "Viewer"}</strong></p>
    </>}
    <p className="break-words text-muted">{starting ? "Waiting for review ownership…" :
      work.status === "available" && work.canClaim ? "Selecting this alert starts your review." : work.explanation}</p>
    {work.finishedAt && <p>Finished at: {work.finishedAt}</p>}
    {work.verdictOutcome && <p className="capitalize">Verdict: {work.verdictOutcome.replaceAll("_", " ")}</p>}
    {!starting && work.canRelease && alertRef && onReleased &&
      <ReleaseControl key={alertRef + ":" + work.revision} work={work} alertRef={alertRef} onReleased={onReleased} />}
  </section>;
}
