import { useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { PageHeader, Pill } from "../../components/ui";

type View = Schemas["RoutingView"];
type Action = View["allowedActions"][number];
const labels: Record<Action, string> = {
  admit_tier1: "Admit to Tier 1", approve_tier2: "Approve Tier 2",
  reject_tier2: "Keep in Tier 1", manual_escalate: "Manual Escalate",
};
const paths = {
  admit_tier1: "/api/v2/alerts/{alertRef}/admit-tier1",
  approve_tier2: "/api/v2/alerts/{alertRef}/tier2/approve",
  reject_tier2: "/api/v2/alerts/{alertRef}/tier2/reject",
  manual_escalate: "/api/v2/alerts/{alertRef}/tier2/escalate",
} as const;
const button = "rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";
const pretty = (value: string) => value.replaceAll("_", " ");

export function RoutingDetail({ initial, refresh }: { initial: View; refresh: () => void }) {
  const [view, setView] = useState(initial);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const pending = useRef<{ action: Action; body: Schemas["RoutingRequest"] } | null>(null);
  async function decide(action: Action) {
    if (busy || !reason.trim()) return;
    const previous = pending.current;
    if (!previous || previous.action !== action || previous.body.reason !== reason.trim()) {
      pending.current = { action, body: { requestId: crypto.randomUUID(),
        expectedStateVersion: view.stateVersion, reason: reason.trim() } };
    }
    setBusy(true); setError(""); setDone("");
    try {
      const result = await unwrap(api.POST(paths[action], {
        params: { path: { alertRef: view.operationalAlertRef } }, body: pending.current!.body,
      }));
      setView(result.view); setReason(""); pending.current = null;
      setDone(`${labels[action]} recorded. Audit #${result.audit.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Decision could not be confirmed.");
    } finally { setBusy(false); }
  }
  const state = view.state;
  return <section className="min-w-0 space-y-5 border-t border-border pt-5" aria-label="V2 alert routing">
    <header className="space-y-1 break-words">
      <h2 className="text-lg font-semibold">{view.title}</h2>
      <p className="text-sm text-muted">{view.detectorName}</p>
      <p className="break-all font-mono text-xs text-dim">{view.operationalAlertRef}</p>
    </header>
    <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <div><dt className="text-sm text-muted">Operational Priority</dt><dd>{state.operationalPriority ?? "Not assigned"}</dd></div>
      <div><dt className="text-sm text-muted">Priority Band</dt><dd>{state.priorityBand ?? "Not assigned"}</dd></div>
      <div><dt className="text-sm text-muted">Review Required</dt><dd>{state.reviewRequired ? "Yes" : "No"}</dd></div>
      <div><dt className="text-sm text-muted">Current Route</dt><dd className="capitalize"><Pill tone="accent">{pretty(state.handlingRoute)}</Pill></dd></div>
      <div><dt className="text-sm text-muted">Workflow Stage</dt><dd className="capitalize">{pretty(state.workflowStage)}</dd></div>
      <div><dt className="text-sm text-muted">Tier 2 Recommended</dt><dd><Pill tone={state.tier2Recommended ? "warn" : "muted"}>{state.tier2Recommended ? "YES" : "NO"}</Pill></dd></div>
    </dl>
    <section className="space-y-2 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Policy Recommendation</h3>
      <p className="text-xs text-dim">Policy: {state.triagePolicyVersion ?? "Not applied"}</p>
      <ul className="space-y-1 text-sm">{state.tier2RecommendationReasons.map((text, i) => <li key={i}>{text}</li>)}</ul>
      <h3 className="text-sm font-semibold">Review Reasons</h3>
      <ul className="space-y-1 text-sm">{view.reviewReasons.map((text, i) => <li key={i}>{text}</li>)}</ul>
    </section>
    {view.latestDecision && <section className="space-y-1 border-t border-border pt-4" aria-label="Latest routing decision">
      <h3 className="text-sm font-semibold">Latest Analyst Decision</h3>
      <p className="text-sm">{labels[view.latestDecision.action]} · Actor #{view.latestDecision.actorId}</p>
      <p className="break-words whitespace-pre-wrap text-sm">{view.latestDecision.reason}</p>
      <p className="text-xs text-muted">{pretty(view.latestDecision.beforeState.handlingRoute)} → {pretty(view.latestDecision.afterState.handlingRoute)}</p>
      <p className="text-xs text-dim">{view.latestDecision.createdAt}</p>
    </section>}
    {view.allowedActions.length > 0 && <div className="space-y-3 border-t border-border pt-4">
      <label className="block text-sm" htmlFor="routing-reason">Decision reason</label>
      <textarea id="routing-reason" rows={3} maxLength={2000} value={reason} disabled={busy}
        onChange={event => setReason(event.target.value)}
        className="w-full rounded-sm border border-border bg-surface p-2 text-sm" />
      <div className="flex flex-wrap gap-2">{view.allowedActions.map(action =>
        <button className={button} key={action} disabled={busy || !reason.trim()} onClick={() => void decide(action)}>{labels[action]}</button>)}</div>
    </div>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {done && <p role="status" className="text-sm text-ok">{done}</p>}
    <button className={button} disabled={busy} onClick={refresh}>Refresh state</button>
  </section>;
}

export function V2RoutingPage() {
  const [search, setSearch] = useSearchParams();
  const requestedRef = search.get("alertRef");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const resource = useApi(async signal => {
    if (requestedRef) {
      const item = await unwrap(api.GET("/api/v2/alerts/{alertRef}/triage-state", {
        params: { path: { alertRef: requestedRef } }, signal,
      }));
      return { items: [item], page: { total: 1, returned: 1, limit: 50, offset: 0 } };
    }
    return unwrap(api.GET("/api/v2/alerts", { params: { query: { limit: 50, offset } }, signal }));
  }, [offset, requestedRef]);
  const current = resource.status === "success"
    ? resource.data.items.find(item => item.operationalAlertRef === selected) ?? resource.data.items[0] : undefined;
  return <div className="min-w-0 space-y-5 p-4 sm:p-6">
    <PageHeader title="V2 Triage Routing" />
    {requestedRef && <button className={button} onClick={() => { setOffset(0); setSearch({}); }}>All V2 alerts</button>}
    {resource.status === "loading" && <p role="status">Loading V2 alerts...</p>}
    {resource.status === "error" && <div><p role="alert">{resource.error.message}</p><button className={button} onClick={resource.reload}>Retry</button></div>}
    {resource.status === "success" && <>
      {resource.data.items.length === 0 ? <p>No materialized V2 alerts.</p> : <>
        <label className="block text-sm" htmlFor="v2-alert">Operational alert</label>
        <select id="v2-alert" className="w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm"
          value={current?.operationalAlertRef ?? ""} onChange={event => setSelected(event.target.value)}>
          {resource.data.items.map(item => <option key={item.operationalAlertRef} value={item.operationalAlertRef}>{item.title} ({item.operationalAlertRef.slice(0, 8)})</option>)}
        </select>
      </>}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <button className={button} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>
        <span>{resource.data.page.total} alerts</span>
        <button className={button} disabled={offset + 50 >= resource.data.page.total} onClick={() => setOffset(offset + 50)}>Next</button>
      </div>
      {current && <RoutingDetail key={current.operationalAlertRef + current.stateVersion} initial={current} refresh={resource.reload} />}
    </>}
  </div>;
}
