import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { PageHeader, Pill } from "../../components/ui";
import { CreateCasePanel } from "./Tier2CasesPage";
import { AlertMemoryPanel } from "./TriageMemoryPage";
import { reviewLanguage } from "./reviewLanguage";
import { DetectorEvidence } from "../../features/alert/DetectorEvidence";
import { SelectiveReviewPanel } from "./SelectiveReviewPage";

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
      setView(result.view); if (result.view.state.handlingRoute === "tier2_candidate") requestAnimationFrame(() => document.getElementById("overview")?.scrollIntoView({block:"start"})); setReason(""); pending.current = null;
      setDone(`${labels[action]} recorded. Audit #${result.audit.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Decision could not be confirmed.");
    } finally { setBusy(false); }
  }
  const review = useApi(signal => unwrap(api.GET("/api/v2/alerts/{alertRef}/selective-review", {params:{path:{alertRef:view.operationalAlertRef}},signal})), [view.operationalAlertRef,view.stateVersion]);
  useEffect(() => { const timer = setInterval(review.reload,15000); return () => clearInterval(timer); }, [review.reload]);
  const state = view.state;
  const detector = review.status === "success" ? review.data.policyEvaluation.inputs.alert?.detectorEvidence : null;
  const candidate = state.handlingRoute === "tier2_candidate" && state.workflowStage === "assessment";
  const step = state.workflowStage === "investigation" ? 4 : state.handlingRoute === "tier2_case" ? 3 : state.handlingRoute === "tier2_candidate" ? 2 : state.handlingRoute === "tier1_review" || state.handlingRoute === "no_immediate_review" ? 1 : 0;
  return <section className="min-w-0 space-y-5" aria-label="Analyst alert workspace">
    <section id="overview" className="workspace-section space-y-4">
      <header><p className="label-mono">Overview / Detection</p><h2 className="mt-2 text-xl font-semibold">{view.title}</h2><p className="mt-1 text-muted">{detector?.detectorSource === "current_flow" ? "Legacy Flow Detector" : view.detectorName}</p></header>
      <dl className="grid grid-cols-2 gap-3 text-sm xl:grid-cols-4">
        <div><dt className="text-muted">Operational Priority</dt><dd className="text-lg font-semibold"><span>{state.operationalPriority ?? "Not assigned"}</span> · <span>{state.priorityBand ?? "Unassigned"}</span></dd></div>
        <div><dt className="text-muted">Review Disposition</dt><dd>{review.status === "success" ? ({must_review:"Must Review",recommended_review:"Recommended Review",no_immediate_review:"No Immediate Review"}[review.data.disposition]) : "Not available"}</dd></div>
        <div><dt className="text-muted">Current Route</dt><dd><Pill tone="accent">{pretty(state.handlingRoute)}</Pill></dd></div>
        <div><dt className="text-muted">Workflow Stage</dt><dd>{pretty(state.workflowStage)}</dd></div>
        <div><dt className="text-muted">Native Severity</dt><dd>{detector?.detectorSeverity ?? "Not provided"}</dd></div>
        <div><dt className="text-muted">Confidence</dt><dd>{detector?.confidence == null ? "Not provided" : `${(detector.confidence*100).toFixed(1)}%`}</dd></div>
        <div><dt className="text-muted">Tier 2 Recommended</dt><dd>{state.tier2Recommended ? "YES" : "NO"}</dd></div>
      </dl>
      <ol className="workflow" aria-label="Workflow progress">{["Incoming","Tier 1 Review","Tier 2 Candidate","Tier 2 Case","Investigation"].map((name,index)=><li key={name} aria-current={step===index ? "step" : undefined}>{index+1}. {name}{step===index ? " · Current" : ""}</li>)}</ol>
      {review.status === "success" && <p className="text-sm">{reviewLanguage(review.data.reasonCodes.includes("UNKNOWN_REQUIRED_CONTEXT") ? "UNKNOWN_REQUIRED_CONTEXT" : review.data.reasonCodes[0] ?? review.data.explanation)}. See Evidence & Safety for the full explanation.</p>}
      {review.status === "error" && <p className="text-danger">Review disposition unavailable. {review.error.message}</p>}
      <p className="text-xs text-muted">No Immediate Review is an automation decision, not a human verdict.</p>
      {candidate ? <div role="status" className="rounded border border-accent bg-accent-dim p-4"><h3 className="font-semibold">Escalated to Tier 2 Candidate</h3><p className="mt-1 text-sm">A formal Tier 2 Case has not been created yet.</p><p className="mt-3 label-mono">Next step</p><a className="primary-action mt-2" href="#create-case">Create Tier 2 Case</a></div>
        : <div><h3 className="label-mono">Recommended Next Action</h3>{view.allowedActions.length > 0 ? <a className="primary-action mt-2" href="#actions">{state.handlingRoute === "unassigned" ? "Review admission" : "Complete Tier 1 Review"}</a> : <p className="mt-2">{state.handlingRoute === "tier2_case" ? <Link className="primary-action" to="../tier2-cases">Continue Investigation</Link> : "Review the evidence and current workflow state."}</p>}</div>}
      {candidate && <div id="create-case"><CreateCasePanel alert={view}/></div>}
    </section>
    <nav aria-label="Workspace sections" className="flex flex-wrap gap-4 text-sm text-accent">{["Overview","Evidence & Safety","Memory","Actions","Technical Details"].map((label,i)=><a key={label} className="underline" href={"#"+["overview","evidence","memory","actions","technical"][i]}>{label}</a>)}</nav>
    <section id="evidence" className="workspace-section space-y-4"><h2 className="text-lg font-semibold">Evidence & Safety</h2>
      {detector ? <DetectorEvidence detector={detector}/> : <p>Detector evidence is not available.</p>}
      <h3 className="font-semibold">Policy Recommendation</h3><ul>{state.tier2RecommendationReasons.map((text,i)=><li key={i}>{text}</li>)}</ul>
      <SelectiveReviewPanel key={view.stateVersion} alertRef={view.operationalAlertRef} onChange={review.reload}/>
    </section>
    <section id="memory" className="workspace-section"><h2 className="text-lg font-semibold">Memory</h2><AlertMemoryPanel key={view.stateVersion} view={view}/></section>
    <section id="actions" className="workspace-section space-y-3"><h2 className="text-lg font-semibold">Actions</h2>
      {view.allowedActions.length > 0 ? <><label className="block text-sm" htmlFor="routing-reason">Decision reason</label><textarea id="routing-reason" rows={3} maxLength={2000} value={reason} disabled={busy} onChange={event=>setReason(event.target.value)} className="w-full rounded border border-border bg-surface p-2"/><div className="flex flex-wrap gap-2">{view.allowedActions.map(action=><button className={button} key={action} disabled={busy || !reason.trim()} onClick={()=>void decide(action)}>{labels[action]}</button>)}</div></> : <p className="text-sm text-muted">No Tier 1 routing actions available in this state.</p>}
      {error && <p role="alert" className="text-danger">{error}</p>}{done && <p role="status" className="text-ok">{done}</p>}
      {view.latestDecision && <p role="region" aria-label="Latest routing decision" className="text-sm">Latest analyst decision: {labels[view.latestDecision.action]} — {view.latestDecision.reason}</p>}
    </section>
    <details id="technical" className="workspace-section"><summary className="cursor-pointer font-semibold">Technical Details</summary><p className="mt-3 break-all text-xs">{view.operationalAlertRef}</p><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({routing:view,detector},null,2)}</pre></details>
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
    <PageHeader title="Analyst Workspace" />
    {requestedRef && <button className="text-sm text-accent underline" onClick={() => { setOffset(0); setSearch({}); }}>All operational alerts</button>}
    {resource.status === "loading" && <p role="status">Loading operational alerts...</p>}
    {resource.status === "error" && <div><p role="alert">{resource.error.message}</p><button className={button} onClick={resource.reload}>Retry</button></div>}
    {resource.status === "success" && <>
      {!requestedRef && <>{resource.data.items.length === 0 ? <p>No operational alerts. Admit eligible incoming alerts to begin.</p> : <>
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
      </>}
      {current && <RoutingDetail key={current.operationalAlertRef + current.stateVersion} initial={current} refresh={resource.reload} />}
    </>}
  </div>;
}
