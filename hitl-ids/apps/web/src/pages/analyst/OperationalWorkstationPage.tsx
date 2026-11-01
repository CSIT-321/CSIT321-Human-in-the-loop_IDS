import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ErrorState, LoadingState } from "../../components/states";
import { Pill } from "../../components/ui";
import { OperationalEvidence, operationalDetector } from "../../features/alert/OperationalEvidence";
import { SystemRouting, attackLabel, currentRouteLabel, routingSummaryLabel } from "../../features/alert/SystemRouting";
import { RoutingDetail } from "./V2RoutingPage";
import { AlertMemoryPanel } from "./TriageMemoryPage";
import { SelectiveReviewPanel } from "./SelectiveReviewPage";
import { OperationalKpis, QueueTabs, QueueItem, queueViews, attackCategories, type QueueView } from "../../features/alert/OperationalQueue";

import { needsReview, reviewLabel, reviewProjection } from "../../features/alert/EffectiveReview";

type View = Schemas["RoutingView"];
const button = "rounded-sm border border-border bg-raised px-2.5 py-1.5 text-xs hover:border-border-strong disabled:opacity-40";
const tabs = ["Overview", "Evidence", "Context & Review", "Triage Memory", "History & Notes", "Technical"] as const;
type Tab = typeof tabs[number];
const routeLabel = (value: string) => value === "tier2_candidate" ? "Tier 2 · recovery pending" : value.replaceAll("_", " ");

function Assistance({ view, onReview }: { view: View; onReview: (review: Schemas["ReviewView"]) => void }) {
  const ref = view.operationalAlertRef;
  const review = useApi(signal => unwrap(api.GET("/api/v2/alerts/{alertRef}/selective-review", { params: { path: { alertRef: ref } }, signal })), [ref, view.stateVersion]);
  const memory = useApi(signal => unwrap(api.GET("/api/v2/alerts/{alertRef}/triage-memory/matches", { params: { path: { alertRef: ref }, query: { limit: 5, offset: 0 } }, signal })), [ref, view.stateVersion]);
  const onReviewRef = useRef(onReview); onReviewRef.current = onReview;
  useEffect(() => { if (review.status === "success") onReviewRef.current(review.data); }, [review.status === "success" ? review.data.version : ""]);
  const refreshReview = review.reload; const refreshMemory = memory.reload;
  useEffect(() => { const timer = setInterval(() => { refreshReview(); refreshMemory(); }, 15000); return () => clearInterval(timer); }, [refreshReview, refreshMemory]);
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

function AlertWorkspace({ view, onChanged, refresh, onReview }: { view: View; onChanged: (view: View) => void; refresh: () => void; onReview: (review: Schemas["ReviewView"]) => void }) {
  const [tab, setTab] = useState<Tab>("Overview");
  const evidence = useApi(signal => unwrap(api.GET("/api/v2/alerts/{alertRef}/evidence", { params: { path: { alertRef: view.operationalAlertRef } }, signal })), [view.operationalAlertRef]);
  return <section aria-label="Operational alert workspace" className="ops-detail flex min-h-0 min-w-0 flex-col bg-bg">
    <header className="shrink-0 space-y-2 border-b border-l-4 border-border border-l-primary bg-surface p-4">
      <p className="break-all font-mono text-xs text-accent">{view.operationalAlertRef}</p>
      <h2 className="break-words text-lg font-semibold">{view.title}</h2>
      <div className="flex flex-wrap gap-2 text-xs">
        <span>{operationalDetector(view.detectorSource, view.detectorName)}</span>
        <Pill tone="accent">{view.state.priorityBand ?? "Unassigned"} / {view.state.operationalPriority ?? "—"}</Pill>
        <Pill>{routeLabel(view.state.handlingRoute)}</Pill>
        <span>Review Disposition: <strong>{reviewLabel(view)}</strong></span>
      </div>
    </header>
    <div role="tablist" aria-label="Operational alert sections" className="flex shrink-0 overflow-x-auto whitespace-nowrap border-b border-border bg-surface px-2">
      {tabs.map(name => <button key={name} id={"ops-tab-" + name} role="tab" aria-selected={tab === name} aria-controls="ops-alert-panel"
        onClick={() => setTab(name)} className={`border-b-2 px-3 py-2 text-xs ${tab === name ? "border-primary text-text" : "border-transparent text-muted hover:text-text"}`}>{name}</button>)}
    </div>
    <div id="ops-alert-panel" role="tabpanel" aria-label={tab} className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
      {(tab === "Overview" || tab === "Evidence") && <>
        {view.classification && <p className="text-sm capitalize">{view.classification.status === "informational_policy_signal" ? "Classification" : "Attack Category"}: <strong>{attackLabel(view.classification.attackCategory)}</strong></p>}
        {evidence.status === "loading" && <LoadingState label="Loading canonical evidence…" />}
        {evidence.status === "error" && <ErrorState error={evidence.error} onRetry={evidence.reload} />}
        {evidence.status === "success" && <OperationalEvidence alert={evidence.data} summaryOnly={tab === "Overview"} />}
      </>}
      {/* Keep this mounted across tabs so draft reasons, retry IDs and success remain stable. */}
      <div hidden={tab !== "Overview"} className="space-y-4">
        <SystemRouting view={view} />
        <RoutingDetail initial={view} refresh={refresh} canRecover compact onChanged={onChanged} />
      </div>
      {tab === "Context & Review" && <SelectiveReviewPanel key={view.stateVersion} alertRef={view.operationalAlertRef} onReview={onReview} />}
      {tab === "Triage Memory" && <AlertMemoryPanel key={view.stateVersion} view={view} />}
      {tab === "History & Notes" && <section className="space-y-3" aria-label="Operational decision history">
        <h3 className="label-mono">Latest routing decision</h3>
        {view.latestDecision ? <>
          <p className="capitalize">{view.latestDecision.action.replaceAll("_", " ")} · {view.latestDecision.decisionSource === "system_policy" ? "System Policy" : `Actor #${view.latestDecision.actorId}`}</p>
          <p className="whitespace-pre-wrap break-words text-sm">{view.latestDecision.reason}</p>
          <p className="text-xs text-muted">{view.latestDecision.createdAt}</p>
        </> : <p className="text-sm text-muted">No routing decision recorded.</p>}
        {view.caseRef ? <Link className="text-accent underline" to={"/analyst/tier2-cases/" + view.caseRef}>Open case notes and timeline</Link>
          : <p className="text-sm text-muted">Investigation notes and the full case timeline become available in the Tier 2 Case after escalation.</p>}
        <p className="text-xs text-muted">Legacy scoring/feedback history remains separate in Historical tools.</p>
      </section>}
      {tab === "Technical" && <section className="space-y-3" aria-label="Operational technical snapshots">
        <h3 className="label-mono">Read-only snapshots</h3>
        <details><summary className="cursor-pointer">Operational state / latest routing audit</summary><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(view, null, 2)}</pre></details>
        <details><summary className="cursor-pointer">Immutable canonical detector snapshot</summary><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{evidence.status === "success" ? JSON.stringify(evidence.data, null, 2) : "Evidence not available"}</pre></details>
      </section>}
    </div>
  </section>;
}

export function OperationalWorkstationPage() {
  const [search, setSearch] = useSearchParams();
  const requested = search.get("alertRef");
  const parsed = Number(search.get("offset") ?? 0);
  const offset = Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0;
  const filter = search.get("q") ?? "";
  const activeView = queueViews.find(view => view.key === search.get("view")) ?? queueViews[0];
  const attackCategory = attackCategories.find(([key]) => key === search.get("attackCategory"))?.[0];
  // Only one supported ranking. Missing/unknown URL values safely use this default.
  const sort = "priority_desc" as const;
  const [overrides, setOverrides] = useState<Record<string, View>>({});
  const summary = useApi(signal => unwrap(api.GET("/api/v2/alerts/summary", { signal })), []);
  const queue = useApi(signal => unwrap(api.GET("/api/v2/alerts", { params: { query: { limit: 50, offset, ...activeView.query, attackCategory, q: filter || undefined, sort } }, signal })), [offset, activeView.key, attackCategory, filter, sort]);
  const linked = useApi(async signal => requested ? unwrap(api.GET("/api/v2/alerts/{alertRef}/triage-state", { params: { path: { alertRef: requested } }, signal })) : null, [requested]);
  const items = queue.status === "success" ? queue.data.items.map(item => overrides[item.operationalAlertRef] ?? item) : [];
  const visible = items;
  const [lastCurrent, setLastCurrent] = useState<View>();
  const selected = requested ?? visible[0]?.operationalAlertRef ??
    (queue.status === "loading" || (lastCurrent && overrides[lastCurrent.operationalAlertRef]) ? lastCurrent?.operationalAlertRef : undefined);
  const fresh = selected ? overrides[selected] ?? items.find(item => item.operationalAlertRef === selected)
    ?? (linked.status === "success" && linked.data?.operationalAlertRef === selected ? linked.data : undefined) : undefined;
  const current = fresh ?? (lastCurrent?.operationalAlertRef === selected ? lastCurrent : undefined);
  useEffect(() => { if (fresh) setLastCurrent(fresh); }, [fresh]);
  function reviewChanged(review: Schemas["ReviewView"]) {
    if (!current || current.operationalAlertRef !== review.operationalAlertRef || current.effectiveReview?.version === review.version) return;
    changed({ ...current, effectiveReview: reviewProjection(review) });
  }
  function select(ref: string) { setSearch(previous => { const next = new URLSearchParams(previous); next.set("alertRef", ref); return next; }, { replace: true }); }
  function page(nextOffset: number) { setSearch(previous => { const next = new URLSearchParams(previous); next.set("offset", String(nextOffset)); next.delete("alertRef"); return next; }); }
  function setFilter(key: string, value: string, replace = false) {
    setOverrides({});
    setSearch(previous => { const next = new URLSearchParams(previous); if (value) next.set(key, value); else next.delete(key);
      next.set("sort", sort); next.delete("offset"); next.delete("alertRef"); return next; }, { replace, flushSync: true });
  }
  function chooseView(view: QueueView) { setFilter("view", view); }
  function refresh() { setOverrides({}); queue.reload(); linked.reload(); summary.reload(); }
  function changed(updated: View) { select(updated.operationalAlertRef); setOverrides(previous => ({ ...previous, [updated.operationalAlertRef]: updated })); queue.reload(); summary.reload(); }
  const refreshRef = useRef(refresh); refreshRef.current = refresh;
  useEffect(() => { const timer = setInterval(() => refreshRef.current(), 15000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    function key(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || (event.target instanceof HTMLElement && (event.target.isContentEditable || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)))) return;
      if (event.key === "/") { event.preventDefault(); document.getElementById("ops-search")?.focus(); }
      if ((event.key === "j" || event.key === "k") && visible.length) {
        const index = visible.findIndex(item => item.operationalAlertRef === selected);
        const next = visible[Math.max(0, Math.min(visible.length - 1, index + (event.key === "j" ? 1 : -1)))];
        if (next) { event.preventDefault(); select(next.operationalAlertRef); }
      }
    }
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, [visible, selected, setSearch]);
  return <div className="operational-workstation flex h-full min-h-0 flex-col">
    <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border bg-bg px-4 py-2">
      <h1 className="text-sm font-semibold">Analyst Workstation</h1>
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="hidden text-dim md:inline">j / k select · / search</span>
        <button className={button} onClick={refresh}>Refresh operational queue</button>
        <details className="relative"><summary className="cursor-pointer text-muted">Advanced / Historical</summary><div className="absolute right-0 z-20 mt-2 w-56 space-y-2 rounded-sm border border-border bg-surface p-3">
          <Link className="block text-accent underline" to="/analyst/workstation">Legacy Flow Workstation</Link>
          <Link className="block text-accent underline" to="/analyst/queue">Historical Alert Queue</Link>
          <Link className="block text-accent underline" to="/analyst/feedback-impact">Historical Feedback Impact</Link>
          <Link className="block text-accent underline" to="/analyst/investigations">Historical Investigations</Link>
          <Link className="block text-accent underline" to="/analyst/overview">Historical Overview</Link>
        </div></details>
      </div>
    </header>
    <OperationalKpis data={summary.status === "success" ? summary.data : undefined} onView={chooseView} />
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
          <p className="text-[10px] text-muted">Operational Priority ↓ · newest first on ties</p>
        </div>
        <div id="operational-queue-panel" role="tabpanel" aria-labelledby={"queue-view-" + activeView.key} className="min-h-0 flex-1 overflow-y-auto">
          {queue.status === "loading" && <p role="status" className="p-3 text-xs">Loading operational alerts…</p>}
          {queue.status === "error" && <ErrorState error={queue.error} onRetry={queue.reload} />}
          {queue.status === "success" && visible.length === 0 && <p className="p-4 text-sm text-muted">No operational alerts match this view.</p>}
          <ul aria-label="Operational alerts">{visible.map(item => <li key={item.operationalAlertRef}>
            <button aria-pressed={selected === item.operationalAlertRef} onClick={() => select(item.operationalAlertRef)}
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
      {current ? <AlertWorkspace key={current.operationalAlertRef} view={current} onChanged={changed} refresh={refresh} onReview={reviewChanged} />
        : <section aria-label="Operational alert workspace" className="p-5 text-sm text-muted">{linked.status === "error" ? <ErrorState error={linked.error} onRetry={linked.reload} /> : "Select an operational alert."}</section>}
      {current && <Assistance key={"assistance-" + current.operationalAlertRef} view={current} onReview={reviewChanged} />}
    </div>
  </div>;
}
