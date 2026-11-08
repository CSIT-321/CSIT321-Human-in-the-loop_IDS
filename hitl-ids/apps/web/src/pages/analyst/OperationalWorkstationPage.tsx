import { AnalystVerdictPanel, AnalystVerdictHistory } from "../../features/alert/AnalystVerdict";
import { AlertNotes } from "../../features/alert/AlertNotes";
import { AnalystWorkPanel } from "../../features/alert/AnalystWork";
import { useCallback, useEffect, useRef, useState } from "react";
import { createSearchParams, Link, useSearchParams } from "react-router";
import { api, unwrap, ApiError, type Schemas } from "../../api/client";
import { useSession } from "../../session/SessionContext";
import { useApi } from "../../api/useApi";
import { readAlertArrivals } from "../../api/alertArrivalStream";
import { ErrorState, LoadingState } from "../../components/states";
import { Pill } from "../../components/ui";
import { OperationalEvidence, flowShortName, isFlow, operationalDetector } from "../../features/alert/OperationalEvidence";
import { FlowScorePanel } from "../../features/alert/FlowScorePanel";
import { SystemRouting, attackLabel, currentRouteLabel, routingSummaryLabel } from "../../features/alert/SystemRouting";
import { RoutingDetail } from "./V2RoutingPage";
import { Tier2RecommendationPanel } from "../../features/alert/Tier2Recommendation";
import { AlertMemoryPanel } from "./TriageMemoryPage";
import { SelectiveReviewPanel } from "./SelectiveReviewPage";
import { OperationalKpis, QueueTabs, QueueItem, queueViews, attackCategories, type QueueView } from "../../features/alert/OperationalQueue";

import { needsReview, reviewLabel, reviewProjection } from "../../features/alert/EffectiveReview";

type View = Schemas["RoutingView"];
const button = "rounded-sm border border-border bg-raised px-2.5 py-1.5 text-xs hover:border-border-strong disabled:opacity-40";
const tabs = ["Overview", "Evidence", "Flow & Score", "Context & Review", "Analyst Verdict", "Triage Memory", "History & Notes", "Technical"] as const;
type Tab = typeof tabs[number];
const routeLabel = (value: string) => value === "tier2_candidate" ? "Historical routing record" : value.replaceAll("_", " ");

function useWorkstationSearchParams(active: boolean) {
  const [routeSearch, routeSet] = useSearchParams();
  const [held, setHeld] = useState(() => new URLSearchParams(active ? routeSearch : undefined));
  const heldRef = useRef(held);
  const wasActive = useRef(active);
  const activeRef = useRef(active); activeRef.current = active;
  const routeSetRef = useRef(routeSet); routeSetRef.current = routeSet;
  const search = active && routeSearch.toString() ? routeSearch : held;
  const searchRef = useRef(search); searchRef.current = search;
  useEffect(() => {
    if (active) {
      if (!wasActive.current && !routeSearch.toString() && heldRef.current.toString()) {
        routeSet(heldRef.current, { replace: true });
      } else {
        const current = new URLSearchParams(routeSearch);
        heldRef.current = current;
        setHeld(current);
      }
    }
    wasActive.current = active;
  }, [active, routeSearch, routeSet]);
  const setSearch = useCallback((next: Parameters<typeof routeSet>[0], options?: Parameters<typeof routeSet>[1]) => {
    const value = typeof next === "function" ? next(new URLSearchParams(searchRef.current)) : next;
    const updated = createSearchParams(value);
    heldRef.current = updated;
    setHeld(updated);
    if (activeRef.current) routeSetRef.current(updated, options);
  }, []);
  return [search, setSearch] as const;
}

function Assistance({ view, onReview, active }: { view: View; onReview: (review: Schemas["ReviewView"]) => void; active: boolean }) {
  const ref = view.operationalAlertRef;
  const review = useApi(signal => unwrap(api.GET("/api/v2/alerts/{alertRef}/selective-review", { params: { path: { alertRef: ref } }, signal })), [ref, view.stateVersion, view.effectiveReview?.version]);
  const memory = useApi(signal => unwrap(api.GET("/api/v2/alerts/{alertRef}/triage-memory/matches", { params: { path: { alertRef: ref }, query: { limit: 5, offset: 0 } }, signal })), [ref, view.stateVersion, view.effectiveReview?.version]);
  const onReviewRef = useRef(onReview); onReviewRef.current = onReview;
  useEffect(() => { if (review.status === "success") onReviewRef.current(review.data); }, [review.status === "success" ? review.data.version : ""]);
  const refreshReview = review.reload; const refreshMemory = memory.reload;
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => { refreshReview(); refreshMemory(); }, 15000);
    return () => clearInterval(timer);
  }, [active, refreshReview, refreshMemory]);
  return <aside aria-label="Context and assistance" className="ops-context divide-y divide-border overflow-y-auto border-l border-border bg-surface text-xs">
    <section className="space-y-2 p-4">
      <h2 className="label-mono">Why this alert needs attention</h2>
      <p>Review Required: <strong>{needsReview(view) ? "Yes" : "No"}</strong></p>
      {(view.effectiveReview ? [view.effectiveReview.explanation] : view.reviewReasons).map((reason, index) => <p className="break-words text-muted" key={index}>{reason}</p>)}
    </section>
    <section className="space-y-2 p-4">
      <h2 className="label-mono">Routing summary</h2>
      <p>Current Route: <strong>{currentRouteLabel(view.state.handlingRoute)}</strong></p>
      {view.systemRouting && <p>{routingSummaryLabel(view)}</p>}
      <p className="text-muted">{view.state.decisionSource === "analyst" ? "Manual analyst override" : view.systemRouting ? "System Policy" : "Historical routing record"}</p>
    </section>
    <section className="space-y-2 p-4" aria-label="Review and trusted context summary">
      <h2 className="label-mono">Review Disposition / Trusted Context</h2>
      {review.status === "loading" && <p role="status">Checking review context…</p>}
      {review.status === "error" && <p role="alert">{review.error.message}</p>}
      {review.status === "success" && <>
        <p className="font-semibold capitalize">{reviewLabel(view)}</p>
        <p className="text-muted">No Immediate Review is an automation decision, not a human verdict.</p>
        <p>Trusted fields: {review.data.policyEvaluation.contextProvenance?.fields.filter(field => field.status === "trusted").length ?? 0} / {review.data.policyEvaluation.contextProvenance?.fields.length ?? 0}</p>
        <p className="text-muted">Inspect provenance and evaluate policy in Context &amp; Review.</p>
      </>}
    </section>
    <section className="space-y-2 p-4" aria-label="Triage Memory summary">
      <h2 className="label-mono">Related Triage Memory</h2>
      <p className="text-muted">Memory provides guidance; current attention follows Review Disposition.</p>
      {memory.status === "loading" && <p role="status">Looking up lessons…</p>}
      {memory.status === "error" && <p role="alert">{memory.error.message}</p>}
      {memory.status === "success" && <>
        <p>{memory.data.page.total} related lessons</p>
        {memory.data.items.map(match => <div className="space-y-1 border-t border-border pt-2" key={match.memory.lesson.lessonRef}>
          <p className="capitalize">{match.memory.lesson.outcome.replaceAll("_", " ")}</p>
          <p>Active guidance: {match.guidanceActive ? "Yes" : "No"}</p>
          <p>Support: {match.memory.supportCount} · Conflicts: {match.memory.conflictCount}</p>
          <Link className="text-accent underline" to={"/analyst/triage-memory?lessonRef=" + match.memory.lesson.lessonRef}>Inspect lesson</Link>
        </div>)}
      </>}
      <button className={button} onClick={() => { refreshReview(); refreshMemory(); }}>Refresh assistance</button>
    </section>
  </aside>;
}

function AlertWorkspace({ view, onChanged, refresh, onReview, starting }: { view: View; onChanged: (view: View) => void; refresh: () => void; onReview: (review: Schemas["ReviewView"]) => void; starting: boolean }) {
  const [tab, setTab] = useState<Tab>("Overview");
  const tabBeforeTour = useRef<Tab | null>(null);
  const currentTab = useRef(tab); currentTab.current = tab;
  useEffect(() => {
    const selectTourTab = (event: Event) => {
      const selected = (event as CustomEvent<string | null>).detail;
      if (selected && tabs.includes(selected as Tab)) {
        if (tabBeforeTour.current === null) tabBeforeTour.current = currentTab.current;
        setTab(selected as Tab);
      } else if (tabBeforeTour.current !== null) {
        setTab(tabBeforeTour.current);
        tabBeforeTour.current = null;
      }
    };
    window.addEventListener("analyst-tour-tab", selectTourTab);
    return () => window.removeEventListener("analyst-tour-tab", selectTourTab);
  }, []);
  const evidence = useApi(signal => unwrap(api.GET("/api/v2/alerts/{alertRef}/evidence", { params: { path: { alertRef: view.operationalAlertRef } }, signal })), [view.operationalAlertRef]);
  // C5: the Flow & Score tab exists only for a flow alert (its operational ref is its legacy alert_ref).
  const flowAlert = evidence.status === "success" && isFlow(evidence.data);
  return <section aria-label="Operational alert workspace" className="ops-detail flex min-h-0 min-w-0 flex-col bg-bg">
    <header className="shrink-0 space-y-2 border-b border-l-4 border-border border-l-primary bg-surface p-4">
      <p className="break-all font-mono text-xs text-accent">{view.operationalAlertRef}
        {evidence.status === "success" && flowShortName(evidence.data) && <span className="text-text"> · {flowShortName(evidence.data)}</span>}</p>
      <h2 className="break-words text-lg font-semibold">{view.title}</h2>
      <div className="flex flex-wrap gap-2 text-xs">
        <span>{operationalDetector(view.detectorSource, view.detectorName)}</span>
        <Pill tone="accent">{view.state.priorityBand ?? "Unassigned"} / {view.state.operationalPriority ?? "—"}</Pill>
        <Pill>{routeLabel(view.state.handlingRoute)}</Pill>
        <span>Review Disposition: <strong>{reviewLabel(view)}</strong></span>
      </div>
    </header>
    <div role="tablist" aria-label="Operational alert sections" className="flex shrink-0 overflow-x-auto whitespace-nowrap border-b border-border bg-surface px-2">
      {tabs.filter(name => name !== "Flow & Score" || flowAlert).map(name => <button key={name} id={"ops-tab-" + name} role="tab" aria-selected={tab === name} aria-controls="ops-alert-panel"
        onClick={() => setTab(name)} className={`border-b-2 px-3 py-2 text-xs ${tab === name ? "border-primary text-text" : "border-transparent text-muted hover:text-text"}`}>{name}</button>)}
    </div>
    <div id="ops-alert-panel" role="tabpanel" aria-label={tab} className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
      {view.work&&<AnalystWorkPanel work={view.work} starting={starting} alertRef={view.operationalAlertRef}
        onReleased={work=>{onChanged({...view,work});refresh();}}/>}
      {(tab === "Overview" || tab === "Evidence") && <>
        {view.classification && <p className="text-sm capitalize">{view.classification.status === "informational_policy_signal" ? "Classification" : "Attack Category"}: <strong>{attackLabel(view.classification.attackCategory)}</strong></p>}
        {evidence.status === "loading" && <LoadingState label="Loading canonical evidence…" />}
        {evidence.status === "error" && <ErrorState error={evidence.error} onRetry={evidence.reload} />}
        {evidence.status === "success" && <OperationalEvidence alert={evidence.data} summaryOnly={tab === "Overview"} />}
      </>}
      <div hidden={tab !== "Overview"}>
        <Tier2RecommendationPanel key={view.stateVersion} view={view} onChanged={changed => { onChanged(changed); refresh(); }} />
      </div>
      <div hidden={tab !== "Overview" && tab !== "Analyst Verdict"}>
        <AnalystVerdictPanel alertRef={view.operationalAlertRef} stateVersion={view.stateVersion+":"+view.work?.revision} onUseMemory={()=>setTab("Triage Memory")} onRecorded={refresh}/>
      </div>
      {/* Keep this mounted across tabs so draft reasons, retry IDs and success remain stable. */}
      <div hidden={tab !== "Overview"} className="space-y-4">
        <SystemRouting view={view} panelShown />
        <RoutingDetail initial={view} refresh={refresh} compact onChanged={onChanged} />
      </div>
      {tab === "Flow & Score" && flowAlert && <FlowScorePanel alertRef={view.operationalAlertRef} />}
      {tab === "Context & Review" && <SelectiveReviewPanel key={view.stateVersion} alertRef={view.operationalAlertRef} readOnly={view.work?.status==='in_review'&&!view.work.isOwner} onReview={onReview} />}
      {tab === "Triage Memory" && <AlertMemoryPanel key={view.stateVersion} view={view} onVerdict={()=>setTab("Analyst Verdict")} onContributed={refresh} />}
      {tab === "History & Notes" && <section className="space-y-3" aria-label="Operational decision history">
        <AlertNotes key={view.operationalAlertRef} alertRef={view.operationalAlertRef} work={view.work} />
        <AnalystVerdictHistory alertRef={view.operationalAlertRef}/>
        <h3 className="label-mono">Latest routing decision</h3>
        {view.latestDecision ? <>
          <p className="capitalize">{view.latestDecision.action.replaceAll("_", " ")} · {view.latestDecision.decisionSource === "system_policy" ? "System Policy" : `Actor #${view.latestDecision.actorId}`}</p>
          <p className="whitespace-pre-wrap break-words text-sm">{view.latestDecision.reason}</p>
          <p className="text-xs text-muted">{view.latestDecision.createdAt}</p>
        </> : <p className="text-sm text-muted">No routing decision recorded.</p>}
        {view.caseRef && <Link className="text-accent underline" to={"/analyst/tier2-cases/" + view.caseRef}>Open case notes and timeline</Link>}
      </section>}
      {tab === "Technical" && <section className="space-y-3" aria-label="Operational technical snapshots">
        <h3 className="label-mono">Read-only snapshots</h3>
        <details><summary className="cursor-pointer">Operational state / latest routing audit</summary><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(view, null, 2)}</pre></details>
        <details><summary className="cursor-pointer">Immutable canonical detector snapshot</summary><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{evidence.status === "success" ? JSON.stringify(evidence.data, null, 2) : "Evidence not available"}</pre></details>
      </section>}
    </div>
  </section>;
}

export function OperationalWorkstationPage({ active = true }: { active?: boolean }) {
  const { session, signOut } = useSession();
  const [search, setSearch] = useWorkstationSearchParams(active);
  const requested = search.get("alertRef");
  const parsed = Number(search.get("offset") ?? 0);
  const offset = Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0;
  const filter = search.get("q") ?? "";
  const activeView = queueViews.find(view => view.key === search.get("view")) ?? queueViews[0];
  const attackCategory = attackCategories.find(([key]) => key === search.get("attackCategory"))?.[0];
  // Only one supported ranking. Missing/unknown URL values safely use this default.
  const sort = "priority_desc" as const;
  const [overrides, setOverrides] = useState<Record<string, View>>({});
  const [claimConflict,setClaimConflict]=useState('');
  const [claimError,setClaimError]=useState('');
  const [startingRef,setStartingRef]=useState<string|null>(null);
  const claimInFlight=useRef(false);
  const pendingClaims=useRef(new Map<string,Schemas['ClaimCommand']>());
  const [mustReselect,setMustReselect]=useState(false);
  const [streamWorkspace, setStreamWorkspace] = useState<string | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);
  const summary = useApi(signal => unwrap(api.GET("/api/v2/alerts/summary", { signal })), [], { keepPreviousData: true });
  const queue = useApi(async signal => {
    const result=await api.GET("/api/v2/alerts", { params: { query: { limit: 50, offset, ...activeView.query, attackCategory, q: filter || undefined, sort } }, signal });
    return {...await unwrap(Promise.resolve(result)),workspaceId:result.response.headers.get('X-Operational-Workspace')};
  }, [offset, activeView.key, attackCategory, filter, sort], { keepPreviousData: true });
  const linked = useApi(async signal => requested ? unwrap(api.GET("/api/v2/alerts/{alertRef}/triage-state", { params: { path: { alertRef: requested } }, signal })) : null, [requested]);
  const items = queue.status === "success" && (!streamWorkspace || queue.data.workspaceId === streamWorkspace)
    ? queue.data.items.map(item => overrides[item.operationalAlertRef] ?? item) : [];
  const visible = items;
  const [lastCurrent, setLastCurrent] = useState<View>();
  const selected = mustReselect ? undefined : requested ?? lastCurrent?.operationalAlertRef ?? visible[0]?.operationalAlertRef;
  const fresh = selected ? overrides[selected] ?? items.find(item => item.operationalAlertRef === selected)
    ?? (linked.status === "success" && linked.data?.operationalAlertRef === selected ? linked.data : undefined) : undefined;
  const current = fresh ?? (lastCurrent?.operationalAlertRef === selected ? lastCurrent : undefined);
  useEffect(() => { if (fresh) setLastCurrent(fresh); }, [fresh]);
  function reviewChanged(review: Schemas["ReviewView"]) {
    if (!current || current.operationalAlertRef !== review.operationalAlertRef || current.effectiveReview?.version === review.version) return;
    changed({ ...current, effectiveReview: reviewProjection(review) });
  }
  function select(ref: string) { setMustReselect(false);setClaimConflict('');setClaimError('');setSearch(previous => { const next = new URLSearchParams(previous); next.set("alertRef", ref); return next; }, { replace: true }); }
  function conflict(message:string){setClaimConflict(message);setMustReselect(true);setLastCurrent(undefined);setOverrides({});setSearch(previous=>{const next=new URLSearchParams(previous);next.delete('alertRef');return next;},{replace:true});queue.reload();summary.reload();}
  async function claimAvailable(ref:string,workspaceId:string){
    claimInFlight.current=true;setStartingRef(ref);
    const claimKey=`${workspaceId}:${ref}`;
    let submitted=false;
    try{
      // The read and POST both name the workspace of the clicked queue row. A switch rejects the
      // action before the claim domain can write to another operational database.
      const checked=await api.GET('/api/v2/alerts/{alertRef}/work',{params:{path:{alertRef:ref}}});
      const work=await unwrap(Promise.resolve(checked));
      if(checked.response.headers.get('X-Operational-Workspace')!==workspaceId){
        pendingClaims.current.delete(claimKey);conflict('The active workspace changed. Please select an alert again.');return;
      }
      if(work.status!=='available'||!work.canClaim){pendingClaims.current.delete(claimKey);refresh();return;}
      let command=pendingClaims.current.get(claimKey);
      if(!command){command={requestId:crypto.randomUUID(),expectedRevision:work.revision};pendingClaims.current.set(claimKey,command);}
      submitted=true;
      await unwrap(api.POST('/api/v2/alerts/{alertRef}/work/claim',{
        params:{path:{alertRef:ref}},headers:{'X-Operational-Workspace':workspaceId},body:command}));
      pendingClaims.current.delete(claimKey);refresh();
    }catch(cause){
      if(cause instanceof ApiError&&cause.code==='CLAIM_CONTENTION'){
        pendingClaims.current.delete(claimKey);
        conflict('Another analyst selected this alert at the same time. No owner was assigned. Please select an alert again.');
      }else if(cause instanceof ApiError&&cause.code==='WORKSPACE_CHANGED'){
        pendingClaims.current.delete(claimKey);conflict('The active workspace changed. Please select an alert again.');
      }else if(cause instanceof ApiError&&cause.status===409&&cause.code!=='WORK_RETRY'){
        pendingClaims.current.delete(claimKey);refresh();
      }else{
        setClaimError(submitted?'Could not confirm review ownership. Select this alert again to retry.':
          'Could not check review availability. Select this alert again to retry.');
      }
    }finally{claimInFlight.current=false;setStartingRef(null);}
  }
  function selectIntentional(item:View){
    if(claimInFlight.current)return;
    select(item.operationalAlertRef);
    if(session?.role!=='security_analyst'||item.state.handlingRoute!=='tier1_review'||!needsReview(item)||
      item.work?.status!=='available'||!item.work.canClaim)return;
    const workspaceId=queue.status==='success'?queue.data.workspaceId:null;
    if(!workspaceId){setClaimError('Current workspace is unavailable. Refresh the queue and select again.');return;}
    void claimAvailable(item.operationalAlertRef,workspaceId);
  }
  function page(nextOffset: number) { setLastCurrent(undefined); setSearch(previous => { const next = new URLSearchParams(previous); next.set("offset", String(nextOffset)); next.delete("alertRef"); return next; }); }
  function setFilter(key: string, value: string, replace = false) {
    setOverrides({}); setLastCurrent(undefined);
    setSearch(previous => { const next = new URLSearchParams(previous); if (value) next.set(key, value); else next.delete(key);
      next.set("sort", sort); next.delete("offset"); next.delete("alertRef"); return next; }, { replace, flushSync: true });
  }
  function chooseView(view: QueueView) { setFilter("view", view); }
  function refresh() { setOverrides({}); queue.reload(); linked.reload(); summary.reload(); }
  function changed(updated: View) { select(updated.operationalAlertRef); setOverrides(previous => ({ ...previous, [updated.operationalAlertRef]: updated })); queue.reload(); summary.reload(); }
  const silentRefresh = () => { queue.reload(); summary.reload(); };
  const refreshRef = useRef(silentRefresh); refreshRef.current = silentRefresh;
  const connectedRef = useRef(streamConnected); connectedRef.current = streamConnected;
  // Polling remains a recovery path when a proxy/browser cannot maintain the stream.
  useEffect(() => { let ticks = 0; const timer = setInterval(() => {
    ticks += 1;
    if (!connectedRef.current || ticks % 4 === 0) refreshRef.current();
  }, 15000);
    return () => clearInterval(timer); }, []);
  useEffect(() => {
    if (!session?.token) return;
    const controller = new AbortController();
    let pending: ReturnType<typeof setTimeout> | undefined;
    const reconcile = () => {
      if (pending) clearTimeout(pending);
      pending = setTimeout(() => { if (!controller.signal.aborted) refreshRef.current(); }, 200);
    };
    const run = async () => {
      while (!controller.signal.aborted) {
        try {
          await readAlertArrivals(session.token, controller.signal, {
            connected: workspaceId => { setStreamConnected(true); if (workspaceId) setStreamWorkspace(workspaceId); reconcile(); },
            arrived: event => { if (event.workspaceId) reconcile(); },
            workspaceChanged: workspaceId => {
              setStreamWorkspace(workspaceId); setStreamConnected(false); setLastCurrent(undefined); setOverrides({});
              setSearch(previous => { const next = new URLSearchParams(previous); next.delete("alertRef"); return next; }, { replace: true });
              reconcile();
            },
          });
        } catch (error) {
          if (controller.signal.aborted) return;
          if (error instanceof Error && error.message === "UNAUTHORIZED") { signOut(); return; }
        }
        if (controller.signal.aborted) return;
        setStreamConnected(false);
        reconcile();
        await new Promise<void>(resolve => {
          const timer = setTimeout(resolve, 2000);
          controller.signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
        });
      }
    };
    void run();
    return () => { controller.abort(); if (pending) clearTimeout(pending); };
  }, [session?.token, signOut, setSearch]);
  useEffect(() => {
    if (!active) return;
    function key(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || (event.target instanceof HTMLElement && (event.target.isContentEditable || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)))) return;
      if (event.key === "/") { event.preventDefault(); document.getElementById("ops-search")?.focus(); }
      if ((event.key === "j" || event.key === "k") && visible.length) {
        const index = visible.findIndex(item => item.operationalAlertRef === selected);
        const next = visible[Math.max(0, Math.min(visible.length - 1, index + (event.key === "j" ? 1 : -1)))];
        if (next) { event.preventDefault(); selectIntentional(next); }
      }
    }
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, [active, visible, selected, setSearch]);
  return <div className="operational-workstation flex h-full min-h-0 flex-col">
    <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border bg-bg px-4 py-2">
      <h1 className="text-sm font-semibold">Analyst Workstation</h1>
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="hidden text-dim md:inline">j / k select · / search</span>
        <span className="hidden text-dim md:inline" aria-live="polite">{streamConnected ? "Arrival updates connected" : "Arrival updates reconnecting"}</span>
        <button className={button} onClick={refresh}>Refresh operational queue</button>

      </div>
    </header>
    <OperationalKpis data={summary.status === "success" ? summary.data : undefined} onView={chooseView} />
    {claimConflict&&<p role="alert" className="shrink-0 break-words border-b border-border p-3 text-sm text-warn">Claim Conflict — {claimConflict}</p>}
    {claimError&&<p role="alert" className="shrink-0 break-words border-b border-border p-3 text-sm text-warn">{claimError}</p>}
    {summary.status === "loading" && <p role="status" className="px-3 text-xs text-muted">Loading operational workload…</p>}
    {summary.status === "error" && <div role="alert" className="flex shrink-0 gap-2 px-3 py-1 text-xs">Workload unavailable: {summary.error.message} <button className={button} onClick={summary.reload}>Retry workload</button></div>}
    <div className="ops-grid grid min-h-0 flex-1">
      <section aria-label="Operational alert queue" className="ops-queue flex min-h-0 flex-col border-r border-border bg-surface">
        <div className="shrink-0 space-y-2 border-b border-border p-3">
          <h2 className="label-mono">Operational Alerts</h2>
          <QueueTabs active={activeView.key} data={summary.status === "success" ? summary.data : undefined} onView={chooseView} />
          <label htmlFor="ops-attack" className="block text-xs text-muted">Attack Type</label>
          <select id="ops-attack" value={attackCategory ?? ""} onChange={event => setFilter("attackCategory", event.target.value)} className="w-full min-w-0 rounded-sm border border-border bg-bg p-1.5 text-xs">
            <option value="">All attack categories</option>{attackCategories.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
          <label htmlFor="ops-search" className="sr-only">Search operational alerts</label>
          <input id="ops-search" maxLength={200} value={filter} onChange={event => setFilter("q", event.target.value, true)} placeholder="Search operational alerts…" className="w-full min-w-0 rounded-sm border border-border bg-bg p-2 text-xs" />
          <p className="text-[10px] text-muted">Severity first · flagged first · Operational Priority ↓ · newest first on ties</p>
        </div>
        <div id="operational-queue-panel" role="tabpanel" aria-labelledby={"queue-view-" + activeView.key} className="min-h-0 flex-1 overflow-y-auto">
          {queue.status === "loading" && <p role="status" className="p-3 text-xs">Loading operational alerts…</p>}
          {queue.status === "error" && <ErrorState error={queue.error} onRetry={queue.reload} />}
          {queue.status === "success" && visible.length === 0 && <p className="p-4 text-sm text-muted">No operational alerts match this view.</p>}
          <ul aria-label="Operational alerts">{visible.map(item => <li key={item.operationalAlertRef}>
            <button data-alert-ref={item.operationalAlertRef} aria-pressed={selected === item.operationalAlertRef} disabled={startingRef!==null} onClick={() => selectIntentional(item)}
              className={`relative block w-full space-y-2 border-b border-l-2 border-b-border px-3 py-3 text-left text-xs ${selected === item.operationalAlertRef ? "border-l-primary bg-raised" : "border-l-transparent hover:bg-raised"}`}>
              <QueueItem item={item} />
            </button>
          </li>)}</ul>
        </div>
        <footer className="flex shrink-0 items-center justify-between gap-1 border-t border-border p-2 text-xs">
          <button className={button} disabled={offset === 0} onClick={() => page(Math.max(0, offset - 50))}>Previous alerts</button>
          <span aria-live="polite">{queue.status === "success" ? `${queue.data.items.length ? offset + 1 : 0}–${queue.data.items.length ? offset + queue.data.items.length : 0} of ${queue.data.page.total}` : "…"}</span>
          <button className={button} disabled={queue.status !== "success" || offset + 50 >= queue.data.page.total} onClick={() => page(offset + 50)}>Next alerts</button>
        </footer>
      </section>
      {current ? <AlertWorkspace key={current.operationalAlertRef} view={current} onChanged={changed} refresh={refresh} onReview={reviewChanged} starting={startingRef===current.operationalAlertRef} />
        : <section aria-label="Operational alert workspace" className="p-5 text-sm text-muted">{linked.status === "error" ? <ErrorState error={linked.error} onRetry={linked.reload} /> : "Select an operational alert."}</section>}
      {current && <Assistance key={"assistance-" + current.operationalAlertRef} view={current} onReview={reviewChanged} active={active} />}
    </div>
  </div>;
}
