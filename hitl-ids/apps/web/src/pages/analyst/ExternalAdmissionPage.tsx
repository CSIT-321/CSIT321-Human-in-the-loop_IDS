import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { PageHeader, Pill } from "../../components/ui";
import { useSession } from "../../session/SessionContext";

// openapi-fetch omits null-only fields from its response type. The wire contract fixes
// confidence to null; this view never converts it into a numeric confidence.
type View = Omit<Schemas["ExternalAdmissionView"], "confidence">;
const button = "rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";

export function ExternalAdmissionDetail({ initial, refresh, prefix, onUpdate }: {
  initial: View; refresh: () => void; prefix: string; onUpdate?: (view: View) => void;
}) {
  const [view, setView] = useState(initial);
  const [decision, setDecision] = useState<"accepted" | "held">("held");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const pending = useRef<{ signature: string; id: string } | null>(null);
  async function submit(action: "review" | "admit") {
    if (busy || !reason.trim()) return;
    const signature = JSON.stringify([action, decision, reason.trim(), view.reviewId]);
    if (pending.current?.signature !== signature) pending.current = { signature, id: crypto.randomUUID() };
    const body = { requestId: pending.current.id, expectedReviewId: view.reviewId, reason: reason.trim() };
    setBusy(true); setError(""); setMessage("");
    try {
      const params = { path: { inboxId: view.externalInboxId } };
      if (action === "review") {
        const updated = await unwrap(api.POST("/api/v2/external-alerts/{inboxId}/eligibility", {
          params, body: { ...body, decision },
        }));
        setView(updated); onUpdate?.(updated);
        setMessage("Eligibility decision recorded.");
      } else {
        const result = await unwrap(api.POST("/api/v2/external-alerts/{inboxId}/admit", { params, body }));
        setView(result.view); onUpdate?.(result.view); setMessage("Operational admission completed.");
      }
      pending.current = null; setReason("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Decision could not be confirmed."); }
    finally { setBusy(false); }
  }
  return <section className="min-w-0 space-y-5 border-t border-border pt-5" aria-label="External alert admission">
    <header className="space-y-2 break-words">
      <h2 className="text-lg font-semibold">{view.signature}</h2>
      <Pill tone={view.status === "admitted" ? "ok" : view.status === "eligible" ? "accent" : "warn"}>{view.status}</Pill>
      <p className="text-sm">{view.statusReason}</p>
    </header>
    <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 text-sm">
      <div><dt className="text-muted">Detector</dt><dd>{view.detector}</dd></div>
      <div><dt className="text-muted">Category</dt><dd>{view.category}</dd></div>
      <div><dt className="text-muted">Native Severity</dt><dd>{view.nativeSeverity}</dd></div>
      <div><dt className="text-muted">Confidence</dt><dd>Not provided</dd></div>
      <div className="break-all"><dt className="text-muted">Source</dt><dd>{view.sourceIp} / {view.sourcePort ?? "No port"}</dd></div>
      <div className="break-all"><dt className="text-muted">Destination</dt><dd>{view.destinationIp} / {view.destinationPort ?? "No port"}</dd></div>
      <div><dt className="text-muted">Protocol</dt><dd>{view.protocol}</dd></div>
      <div className="break-all"><dt className="text-muted">Occurred At</dt><dd>{view.occurredAt}</dd></div>
      <div><dt className="text-muted">Staging Priority Proposal</dt><dd>{view.proposedPriority}</dd></div>
      <div><dt className="text-muted">Proposal Policy</dt><dd>{view.proposalPolicyVersion}</dd></div>
      <div><dt className="text-muted">Original Staging Decision</dt><dd>{view.stagingDecision}</dd></div>
      <div><dt className="text-muted">Eligibility Review</dt><dd>{view.reviewDecision ?? "Not reviewed"}</dd></div>
    </dl>
    {view.reviewReason && <p className="break-words text-sm">Review #{view.reviewId}, actor #{view.reviewActorId}: {view.reviewReason}</p>}
    {view.operationalAlertRef && <section className="space-y-2 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Operational V2 Reference</h3>
      <p className="break-all font-mono text-xs">{view.operationalAlertRef}</p>
      {view.admittedAt && <p className="text-sm">Admitted by actor #{view.admissionActorId} at {view.admittedAt}</p>}
      <Link className="inline-block text-sm text-accent underline" to={prefix + "/v2-triage?alertRef=" + view.operationalAlertRef}>Open Alert Triage</Link>
    </section>}
    {(view.canReview || view.canAdmit) && <section className="space-y-3 border-t border-border pt-4">
      {view.canReview && <div className="space-y-2">
        <label htmlFor="eligibility-decision" className="block text-sm">Eligibility decision</label>
        <select id="eligibility-decision" value={decision} disabled={busy}
          onChange={event => setDecision(event.target.value as "accepted" | "held")}
          className="w-full rounded-sm border border-border bg-surface p-2 text-sm">
          <option value="held">Keep held</option><option value="accepted">Accept eligibility</option>
        </select>
      </div>}
      <label htmlFor="admission-reason" className="block text-sm">Decision reason</label>
      <textarea id="admission-reason" rows={3} maxLength={2000} value={reason} disabled={busy}
        onChange={event => setReason(event.target.value)} className="w-full rounded-sm border border-border bg-surface p-2 text-sm" />
      <div className="flex flex-wrap gap-2">
        {view.canReview && <button className={button} disabled={busy || !reason.trim()} onClick={() => void submit("review")}>Record eligibility review</button>}
        {view.canAdmit && <button className={button} disabled={busy || !reason.trim()} onClick={() => void submit("admit")}>Admit to HITL Workflow</button>}
      </div>
    </section>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {message && <p role="status" className="text-sm text-ok">{message}</p>}
    <button className={button} disabled={busy} onClick={refresh}>Refresh status</button>
  </section>;
}

export function ExternalAdmissionPage() {
  const { session } = useSession();
  const prefix = session?.role === "system_admin" ? "/admin" : session?.role === "evaluator" ? "/evaluator" : "/analyst";
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(0);
  const [updated, setUpdated] = useState<Record<number, View>>({});
  const resource = useApi(signal => unwrap(api.GET("/api/v2/external-alerts", {
    params: { query: { limit: 50, offset } }, signal,
  })), [offset]);
  const items = resource.status === "success" ? resource.data.items.map(item => updated[item.externalInboxId] ?? item) : [];
  const current = items.find(item => item.externalInboxId === selected) ?? items[0];
  const refresh = () => { setUpdated({}); resource.reload(); };
  return <div className="min-w-0 space-y-5 p-4 sm:p-6">
    <PageHeader title="Incoming Alerts" />
    {resource.status === "loading" && <p role="status">Loading staged alerts...</p>}
    {resource.status === "error" && <div><p role="alert">{resource.error.message}</p><button className={button} onClick={resource.reload}>Retry</button></div>}
    {resource.status === "success" && <>
      {resource.data.items.length === 0 ? <p>No staged external alerts.</p> : <>
        <label htmlFor="external-alert" className="block text-sm">Staged alert</label>
        <select id="external-alert" value={current?.externalInboxId ?? 0} onChange={event => setSelected(Number(event.target.value))}
          className="w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm">
          {items.map(item => <option key={item.externalInboxId} value={item.externalInboxId}>#{item.externalInboxId} {item.signature} ({item.status})</option>)}
        </select>
      </>}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <button className={button} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>
        <span>{resource.data.page.total} staged records</span>
        <button className={button} disabled={offset + 50 >= resource.data.page.total} onClick={() => setOffset(offset + 50)}>Next</button>
      </div>
      {current && <ExternalAdmissionDetail key={current.externalInboxId} initial={current} refresh={refresh} prefix={prefix}
        onUpdate={item => setUpdated(previous => ({ ...previous, [item.externalInboxId]: item }))} />}
    </>}
  </div>;
}
