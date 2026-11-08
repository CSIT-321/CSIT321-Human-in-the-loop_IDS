import { useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { PageHeader, Pill } from "../../components/ui";
import { OperationalEvidence, isFlow } from "../../features/alert/OperationalEvidence";
import { FlowScorePanel } from "../../features/alert/FlowScorePanel";
import { useSession } from "../../session/SessionContext";
import { ResponseRecommendations } from "./ResponseRecommendations";
import { InvestigationAssistance } from "./InvestigationAssistance";
import { ConclusionDetails, finalCategories, systemCategoryLabel, type FinalCategory } from "./InvestigationConclusion";
import { ConclusionLearning } from "./ConclusionLearning";
import { CaseResolution, ResolutionDetails } from "./CaseResolution";
import { useActorName } from "../../session/ActorNames";

const button = "rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";
const input = "w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm";
type Case = Schemas["CaseView"];
type Tab = "note" | "finding" | "link" | "timeline";
const prefixFor = (role?: string) => role === "system_admin" ? "/admin" : role === "evaluator" ? "/evaluator" : "/analyst";
const caseAssignment = (ownerActorId: number | null, actorName: (id: number) => string) => ownerActorId == null ? "Unassigned / Collaborative" : `Assigned to ${actorName(ownerActorId)}`;

export function Tier2CasesPage() {
  const actorName = useActorName();
  const { session } = useSession();
  const [offset, setOffset] = useState(0);
  // D1: server-side filters. Default = active work (open + investigating); "all" sends no status.
  const [status, setStatus] = useState<"active" | "open" | "investigating" | "resolved" | "all">("active");
  const [owner, setOwner] = useState<"any" | "me" | "unassigned">("any");
  const cases = useApi(signal => unwrap(api.GET("/api/v2/tier2/cases", { params: { query: {
    limit: 50, offset, ...(status === "all" ? {} : { status }), ...(owner === "any" ? {} : { owner }) } }, signal })), [offset, status, owner]);
  return <div className="min-w-0 space-y-5 p-4 sm:p-6">
    <PageHeader title="Tier 2 Cases" />
    <div className="flex flex-wrap items-end gap-3 text-sm">
      <label className="block">Status<select className={input + " block"} aria-label="Status" value={status}
        onChange={e => { setStatus(e.target.value as typeof status); setOffset(0); }}>
        <option value="active">Active (open + investigating)</option><option value="open">Open</option>
        <option value="investigating">Investigating</option><option value="resolved">Resolved</option><option value="all">All</option>
      </select></label>
      <label className="block">Owner<select className={input + " block"} aria-label="Owner" value={owner}
        onChange={e => { setOwner(e.target.value as typeof owner); setOffset(0); }}>
        <option value="any">Anyone</option><option value="me">Mine</option><option value="unassigned">Unassigned</option>
      </select></label>
    </div>
    {cases.status === "loading" && <p role="status">Loading cases...</p>}
    {cases.status === "error" && <div><p role="alert">{cases.error.message}</p><button className={button} onClick={cases.reload}>Retry</button></div>}
    {cases.status === "success" && <>
      {cases.data.items.length === 0 ? <p>No Tier 2 cases.</p> : <div className="overflow-x-auto">
        <table className="w-full text-left text-sm" aria-label="Tier 2 cases">
          <thead><tr>{["Case ID", "Title", "Priority", "Status", "Escalated by", "Case Assignment", "Created", "Primary Alert"].map(x => <th className="border-b border-border p-2" key={x}>{x}</th>)}</tr></thead>
          <tbody>{cases.data.items.map(item => <tr key={item.caseRef}>
            <td className="border-b border-border p-2"><Link className="text-accent underline" title={item.caseRef} to={prefixFor(session?.role) + "/tier2-cases/" + item.caseRef}>{item.caseRef.slice(0, 8)}</Link></td>
            <td className="min-w-48 border-b border-border p-2">{item.title}</td>
            <td className="border-b border-border p-2">{item.snapshot.triage.priorityBand ?? "Unassigned"} / {item.snapshot.triage.operationalPriority ?? "Not assigned"}</td>
            <td className="border-b border-border p-2">{item.status === "resolved" ? "Resolved" : item.status}</td>
            <td className="min-w-48 border-b border-border p-2">
              <span className="block font-semibold">{item.decisionSource === "system_policy" ? "Rule" : actorName(item.createdByActorId)}</span>
              <span className="block text-xs text-muted">{item.snapshot.escalationReason}</span></td>
            <td className="border-b border-border p-2">{caseAssignment(item.ownerActorId, actorName)}</td>
            <td className="border-b border-border p-2">{item.createdAt}</td>
            <td className="border-b border-border p-2"><Link className="text-accent underline" to={(session?.role === "security_analyst" ? "/analyst/operations" : prefixFor(session?.role) + "/v2-triage") + "?alertRef=" + item.primaryOperationalAlertRef}>{item.primaryOperationalAlertRef.slice(0, 8)}</Link></td>
          </tr>)}</tbody>
        </table>
      </div>}
      <p className="text-xs text-muted">Tier 2 V1 supports collaborative investigation; it does not implement automatic case assignment or workload balancing.</p>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <button className={button} disabled={offset === 0} onClick={() => setOffset(Math.max(0,offset-50))}>Previous</button>
        <span>{cases.data.page.total} cases</span>
        <button className={button} disabled={offset+50 >= cases.data.page.total} onClick={() => setOffset(offset+50)}>Next</button>
      </div>
    </>}
  </div>;
}

export function Tier2CaseDetailPage() {
  const { caseRef = "" } = useParams();
  const { session } = useSession();
  const resource = useApi(signal => unwrap(api.GET("/api/v2/tier2/cases/{caseRef}", { params: { path: { caseRef } }, signal })), [caseRef]);
  return <div className="min-w-0 space-y-5 p-4 sm:p-6">
    <Link className="text-sm text-accent underline" to={prefixFor(session?.role) + "/tier2-cases"}>All Tier 2 cases</Link>
    {resource.status === "loading" && <p role="status">Loading case...</p>}
    {resource.status === "error" && <div><p role="alert">{resource.error.message}</p><button className={button} onClick={resource.reload}>Retry</button></div>}
    {resource.status === "success" && <CaseInvestigation key={resource.data.caseRef + ":" + resource.data.revision} initial={resource.data} refresh={resource.reload} />}
  </div>;
}

export function CaseInvestigation({ initial, refresh }: { initial: Case; refresh: () => void }) {
  const actorName = useActorName();
  const { session } = useSession();
  const [current, setCurrent] = useState(initial);
  const [responseVersion,setResponseVersion] = useState(0);
  const [tab, setTab] = useState<Tab>("note");
  const [offset, setOffset] = useState(0);
  const [reason, setReason] = useState("");
  const [linkedRef, setLinkedRef] = useState("");
  const [finding, setFinding] = useState<Schemas["InvestigationConclusionRequest"]["finding"]>("inconclusive");
  const [finalCategory, setFinalCategory] = useState<FinalCategory | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const pending = useRef<{ key: string; id: string } | null>(null);
  const canWrite = current.status !== "resolved" && (session?.role === "security_analyst" || session?.role === "system_admin");
  const events = useApi(signal => unwrap(api.GET("/api/v2/tier2/cases/{caseRef}/events", {
    params: { path: { caseRef: current.caseRef }, query: { limit: 50, offset, ...(tab === "timeline" ? {} : { action: tab }) } }, signal,
  })), [current.caseRef, current.revision, tab, offset]);
  async function act(action: "note" | "finding" | "link" | "start") {
    if (busy || !reason.trim() || (action === "link" && !linkedRef.trim()) || (action === "finding" && finding === "confirmed_malicious" && !finalCategory)) return;
    const key = JSON.stringify([action, reason.trim(), linkedRef.trim(), finding, finalCategory, current.revision]);
    if (pending.current?.key !== key) pending.current = { key, id: crypto.randomUUID() };
    const body = { requestId: pending.current.id, reason: reason.trim(), expectedRevision: current.revision };
    const params = { path: { caseRef: current.caseRef } };
    setBusy(true); setError(""); setMessage("");
    try {
      const result = action === "link" ? await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/alerts", { params, body: { ...body, operationalAlertRef: linkedRef.trim() } }))
        : action === "finding" ? await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/conclusions", { params, body: { ...body, finding, finalAttackCategory: finding === "expected_activity" ? null : finalCategory || null } }))
        : action === "start" ? await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/start-investigation", { params, body }))
        : await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/notes", { params, body }));
      setCurrent(result.case); setOffset(0); setReason(""); setLinkedRef(""); setFinalCategory(""); pending.current = null;
      setMessage("Investigation decision recorded.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Decision could not be confirmed."); }
    finally { setBusy(false); }
  }
  const snapshot = current.snapshot;
  const detector = snapshot.detector;
  return <div className="min-w-0 space-y-5 break-words">
    <PageHeader title={current.title} />
    <section className="space-y-3" aria-label="Case summary">
      <p className="break-all font-mono text-xs">{current.caseRef}</p>
      <Pill tone="accent">{current.status === "resolved" ? "Resolved" : current.status}</Pill>
      {current.status === "resolved" && <p className="text-sm">Investigation closed. Evidence, history and human learning provenance remain available.</p>}
      <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <div><dt className="text-muted">Case Assignment</dt><dd>{caseAssignment(current.ownerActorId, actorName)}</dd></div>
        <div><dt className="text-muted">Creation Source</dt><dd>{current.decisionSource === "system_policy" ? "System Policy" : actorName(current.createdByActorId)}</dd></div>
        <div><dt className="text-muted">Created</dt><dd>{current.createdAt}</dd></div>
        <div><dt className="text-muted">Operational Priority at Creation</dt><dd>{snapshot.triage.priorityBand ?? "Unassigned"} / {snapshot.triage.operationalPriority ?? "Not assigned"}</dd></div>
        <div><dt className="text-muted">Policy at Creation</dt><dd>{snapshot.triage.triagePolicyVersion ?? "Not applied"}</dd></div>
      </dl>
      <p className="text-xs text-muted">Tier 2 V1 supports collaborative investigation; it does not implement automatic case assignment or workload balancing.</p>
      <p className="text-sm">System Attack Classification: {systemCategoryLabel(current.systemAttackClassification)}</p>
      {current.latestConclusion && <section aria-label="Latest Human Investigation Conclusion" className="space-y-2 border-t border-border pt-3">
        <h2 className="text-base font-semibold">Latest Human Investigation Conclusion</h2>
        <ConclusionDetails conclusion={current.latestConclusion} />
      </section>}
    </section>
    <InvestigationAssistance caseRef={current.caseRef} revision={current.revision} prefix={prefixFor(session?.role)}
      onSelect={canWrite ? ref => {
        setTab("link"); setOffset(0); setLinkedRef(ref); setReason(""); setError(""); setMessage("Review the selected alert and enter a reason before linking.");
        window.setTimeout(() => document.getElementById("linked-alert")?.scrollIntoView({ block: "center", behavior: "smooth" }), 0);
      } : undefined} />
    <section className="space-y-2 border-t border-border pt-4" aria-label="Tier 1 handoff">
      <h2 className="text-base font-semibold">{current.decisionSource === "system_policy" ? "System Routing at Creation" : "Tier 1 Handoff"}</h2>
      <p className="whitespace-pre-wrap break-words text-sm">{snapshot.tier1HandoffSummary}</p>
      <p className="break-words text-sm">Escalation: {snapshot.escalationReason}</p>
      <p className="text-xs text-muted">{snapshot.routingDecision.eventType} by {snapshot.routingDecision.decisionSource === "system_policy" ? "System Policy" : `actor #${snapshot.routingDecision.actorId}`}</p>
      <ul className="space-y-1 text-sm">{snapshot.triage.tier2RecommendationReasons.map((text,i) => <li key={i}>{text}</li>)}</ul>
    </section>
    <section className="space-y-3 border-t border-border pt-4" aria-label="Primary Alert Evidence">
      <h2 className="text-base font-semibold">Primary Alert Evidence</h2>
      <p className="break-all font-mono text-xs">{current.primaryOperationalAlertRef}</p>
      <p className="text-xs text-muted">Immutable detector evidence captured when this Case was created.</p>
      <OperationalEvidence alert={detector} />
      <Link className="inline-block text-sm text-accent underline" to={(session?.role === "security_analyst" ? "/analyst/operations" : prefixFor(session?.role) + "/v2-triage") + "?alertRef=" + current.primaryOperationalAlertRef}>Primary alert</Link>
    </section>
    {/* D2: a flow alert's live score, verdict history and family, read only (the C5 panel). */}
    {isFlow(detector) && <section className="space-y-3 border-t border-border pt-4">
      <h2 className="text-base font-semibold">Flow & Score (live)</h2>
      <FlowScorePanel alertRef={current.primaryOperationalAlertRef} />
    </section>}
    <section className="space-y-4 border-t border-border pt-4">
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Case investigation">
        {([["note","Investigation Notes"],["finding","Investigation Conclusion"],["link","Linked Alerts"],["timeline","Audit Timeline"]] as const).map(([value,label]) =>
          <button role="tab" aria-selected={tab === value} disabled={busy} className={button} key={value}
            onClick={() => { setTab(value); setOffset(0); setReason(""); setError(""); setMessage(""); }}>{label}</button>)}
      </div>
      {events.status === "loading" && <p role="status">Loading case history...</p>}
      {events.status === "error" && <div><p role="alert">{events.error.message}</p><button className={button} onClick={events.reload}>Retry</button></div>}
      {events.status === "success" && <div role="tabpanel" className="space-y-3">
        {events.data.items.length === 0 && <p className="text-sm">No records yet.</p>}
        {events.data.items.map(event => <article key={event.id} className="space-y-1 border-b border-border py-3">
          <p className="text-xs text-muted">{event.eventType} / {event.decisionSource === "system_policy" ? "System Policy" : `actor #${event.actorId}`} / {event.createdAt}</p>
          {event.resolution && <ResolutionDetails resolution={event.resolution} />}
          {event.conclusion ? <><h3 className="font-semibold">{event.conclusion.recordKind === "legacy_finding" ? "Historical Finding" : "Investigation Conclusion"}</h3>
            <ConclusionDetails conclusion={event.conclusion} />
            <p className="text-xs text-muted">System classification recorded with conclusion: {systemCategoryLabel(event.conclusion.systemClassification)}</p></> : <>
            {event.finding && <Pill tone="warn">{event.finding.replaceAll("_"," ")}</Pill>}
            <p className="whitespace-pre-wrap break-words text-sm">{event.reason}</p></>}
          {event.linkedAlertRef && <Link className="break-all text-sm text-accent underline" to={(session?.role === "security_analyst" ? "/analyst/operations" : prefixFor(session?.role) + "/v2-triage") + "?alertRef=" + event.linkedAlertRef}>{event.linkedAlertRef}</Link>}
          {tab === "timeline" && <details><summary className="cursor-pointer text-xs">State change</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({ before: event.beforeState, after: event.afterState },null,2)}</pre></details>}
        </article>)}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <button className={button} disabled={offset === 0} onClick={() => setOffset(Math.max(0,offset-50))}>Previous</button>
          <span>{events.data.page.total} records</span>
          <button className={button} disabled={offset+50 >= events.data.page.total} onClick={() => setOffset(offset+50)}>Next</button>
        </div>
      </div>}
      {canWrite && (tab !== "timeline" || current.status === "open") && <div className="space-y-3">
        {tab === "link" && <><label htmlFor="linked-alert" className="block text-sm">Operational alert UUID</label><input id="linked-alert" value={linkedRef} disabled={busy} onChange={e => setLinkedRef(e.target.value)} className={input} /></>}
        {tab === "finding" && <>
          <p className="text-sm">System Attack Classification: {systemCategoryLabel(current.systemAttackClassification)}</p>
          <label htmlFor="case-finding" className="block text-sm">Human Investigation Finding</label><select id="case-finding" value={finding} disabled={busy} onChange={e => { setFinding(e.target.value as typeof finding); if (e.target.value === "expected_activity") setFinalCategory(""); }} className={input}>
          <option value="inconclusive">Inconclusive</option><option value="suspicious">Suspicious</option><option value="confirmed_malicious">Confirmed malicious</option><option value="expected_activity">Expected activity</option>
        </select>
          <label htmlFor="final-category" className="block text-sm">Human Final Attack Classification</label>
          <select id="final-category" className={input} disabled={busy || finding === "expected_activity"} required={finding === "confirmed_malicious"}
            value={finalCategory} onChange={e => setFinalCategory(e.target.value as FinalCategory | "")}>
            <option value="">{finding === "expected_activity" ? "Not applicable" : "Unresolved / select category"}</option>
            {Object.entries(finalCategories).map(([value,label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <p className="text-xs text-muted">{finding === "confirmed_malicious" ? "Required. Explicitly select a concrete category; use Other Known Attack if needed and explain the evidence." : finding === "expected_activity" ? "Not applicable to Expected Activity." : "Optional when the attack type remains uncertain."} The system classification is preserved.</p>
        </>}
        <label htmlFor="investigation-note" className="block text-sm">{tab === "note" ? "Investigation note" : tab === "finding" ? "Investigation Reason" : "Decision reason"}</label>
        <textarea id="investigation-note" rows={3} maxLength={4000} value={reason} disabled={busy} onChange={e => setReason(e.target.value)} className={input} />
        <button className={button} disabled={busy || !reason.trim() || (tab === "link" && !linkedRef.trim()) || (tab === "finding" && finding === "confirmed_malicious" && !finalCategory)} onClick={() => void act(tab === "timeline" ? "start" : tab)}>
          {tab === "note" ? "Add investigation note" : tab === "finding" ? "Record Investigation Conclusion" : tab === "link" ? "Link alert" : "Start investigation"}
        </button>
      </div>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {message && <p role="status" className="text-sm text-ok">{message}</p>}
      <button className={button} disabled={busy} onClick={refresh}>Refresh case</button>
    </section>
    <ConclusionLearning current={current} canWrite={canWrite} prefix={prefixFor(session?.role)} />
    <ResponseRecommendations key={current.caseRef} current={current} canWrite={canWrite} onChange={()=>setResponseVersion(value=>value+1)} />
    <CaseResolution current={current} canWrite={canWrite} responseVersion={responseVersion} onResolved={setCurrent} />
  </div>;
}
