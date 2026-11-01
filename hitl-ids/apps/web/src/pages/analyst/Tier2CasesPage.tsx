import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { PageHeader, Pill } from "../../components/ui";
import { useSession } from "../../session/SessionContext";
import { ResponseRecommendations } from "./ResponseRecommendations";
import { InvestigationAssistance } from "./InvestigationAssistance";

const button = "rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";
const input = "w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm";
type Case = Schemas["CaseView"];
type Tab = "note" | "finding" | "link" | "timeline";
const prefixFor = (role?: string) => role === "system_admin" ? "/admin" : role === "evaluator" ? "/evaluator" : "/analyst";

export function CreateCasePanel({ alert }: { alert: Schemas["RoutingView"] }) {
  const { session } = useSession();
  const navigate = useNavigate();
  const [title, setTitle] = useState(alert.title);
  const [handoff, setHandoff] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<{ key: string; id: string } | null>(null);
  if (!session || session.role === "evaluator") return null;
  async function create() {
    if (busy || !title.trim() || !handoff.trim() || !reason.trim()) return;
    const key = JSON.stringify([title.trim(), handoff.trim(), reason.trim(), alert.stateVersion]);
    if (pending.current?.key !== key) pending.current = { key, id: crypto.randomUUID() };
    setBusy(true); setError("");
    try {
      const result = await unwrap(api.POST("/api/v2/alerts/{alertRef}/tier2/case", {
        params: { path: { alertRef: alert.operationalAlertRef } }, body: {
          requestId: pending.current.id, expectedStateVersion: alert.stateVersion, title: title.trim(),
          tier1HandoffSummary: handoff.trim(), reason: reason.trim(),
        },
      }));
      navigate(prefixFor(session?.role) + "/tier2-cases/" + result.case.caseRef);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Case creation could not be confirmed."); }
    finally { setBusy(false); }
  }
  return <section className="space-y-3 border-t border-border pt-4" aria-label="Create Tier 2 case">
    <h3 className="text-sm font-semibold">Tier 2 Case Creation</h3>
    <label htmlFor="case-title" className="block text-sm">Case title</label>
    <input id="case-title" className={input} maxLength={200} value={title} disabled={busy} onChange={e => setTitle(e.target.value)} />
    <label htmlFor="case-handoff" className="block text-sm">Tier 1 handoff summary</label>
    <textarea id="case-handoff" className={input} rows={3} maxLength={4000} value={handoff} disabled={busy} onChange={e => setHandoff(e.target.value)} />
    <label htmlFor="case-reason" className="block text-sm">Case creation reason</label>
    <textarea id="case-reason" className={input} rows={2} maxLength={4000} value={reason} disabled={busy} onChange={e => setReason(e.target.value)} />
    <button className={button} disabled={busy || !title.trim() || !handoff.trim() || !reason.trim()} onClick={() => void create()}>Create Tier 2 Case</button>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
  </section>;
}

export function Tier2CasesPage() {
  const { session } = useSession();
  const [offset, setOffset] = useState(0);
  const cases = useApi(signal => unwrap(api.GET("/api/v2/tier2/cases", { params: { query: { limit: 50, offset } }, signal })), [offset]);
  return <div className="min-w-0 space-y-5 p-4 sm:p-6">
    <PageHeader title="Tier 2 Cases" />
    {cases.status === "loading" && <p role="status">Loading cases...</p>}
    {cases.status === "error" && <div><p role="alert">{cases.error.message}</p><button className={button} onClick={cases.reload}>Retry</button></div>}
    {cases.status === "success" && <>
      {cases.data.items.length === 0 ? <p>No Tier 2 cases.</p> : <div className="overflow-x-auto">
        <table className="w-full text-left text-sm" aria-label="Tier 2 cases">
          <thead><tr>{["Case ID", "Title", "Priority", "Status", "Owner", "Created", "Primary Alert"].map(x => <th className="border-b border-border p-2" key={x}>{x}</th>)}</tr></thead>
          <tbody>{cases.data.items.map(item => <tr key={item.caseRef}>
            <td className="border-b border-border p-2"><Link className="text-accent underline" title={item.caseRef} to={prefixFor(session?.role) + "/tier2-cases/" + item.caseRef}>{item.caseRef.slice(0, 8)}</Link></td>
            <td className="min-w-48 border-b border-border p-2">{item.title}</td>
            <td className="border-b border-border p-2">{item.snapshot.triage.priorityBand ?? "Unassigned"} / {item.snapshot.triage.operationalPriority ?? "Not assigned"}</td>
            <td className="border-b border-border p-2">{item.status}</td><td className="border-b border-border p-2">{item.ownerActorId == null ? "Unassigned" : `Actor #${item.ownerActorId}`}</td>
            <td className="border-b border-border p-2">{item.createdAt}</td>
            <td className="border-b border-border p-2"><Link className="text-accent underline" to={prefixFor(session?.role) + "/v2-triage?alertRef=" + item.primaryOperationalAlertRef}>{item.primaryOperationalAlertRef.slice(0, 8)}</Link></td>
          </tr>)}</tbody>
        </table>
      </div>}
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
  const { session } = useSession();
  const [current, setCurrent] = useState(initial);
  const [tab, setTab] = useState<Tab>("note");
  const [offset, setOffset] = useState(0);
  const [reason, setReason] = useState("");
  const [linkedRef, setLinkedRef] = useState("");
  const [finding, setFinding] = useState<Schemas["FindingRequest"]["finding"]>("inconclusive");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const pending = useRef<{ key: string; id: string } | null>(null);
  const canWrite = session?.role === "security_analyst" || session?.role === "system_admin";
  const events = useApi(signal => unwrap(api.GET("/api/v2/tier2/cases/{caseRef}/events", {
    params: { path: { caseRef: current.caseRef }, query: { limit: 50, offset, ...(tab === "timeline" ? {} : { action: tab }) } }, signal,
  })), [current.caseRef, current.revision, tab, offset]);
  async function act(action: "note" | "finding" | "link" | "start") {
    if (busy || !reason.trim() || (action === "link" && !linkedRef.trim())) return;
    const key = JSON.stringify([action, reason.trim(), linkedRef.trim(), finding, current.revision]);
    if (pending.current?.key !== key) pending.current = { key, id: crypto.randomUUID() };
    const body = { requestId: pending.current.id, reason: reason.trim(), expectedRevision: current.revision };
    const params = { path: { caseRef: current.caseRef } };
    setBusy(true); setError(""); setMessage("");
    try {
      const result = action === "link" ? await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/alerts", { params, body: { ...body, operationalAlertRef: linkedRef.trim() } }))
        : action === "finding" ? await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/findings", { params, body: { ...body, finding } }))
        : action === "start" ? await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/start-investigation", { params, body }))
        : await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/notes", { params, body }));
      setCurrent(result.case); setOffset(0); setReason(""); setLinkedRef(""); pending.current = null;
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
      <Pill tone="accent">{current.status}</Pill>
      <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <div><dt className="text-muted">Owner</dt><dd>{current.ownerActorId == null ? "Unassigned" : `Actor #${current.ownerActorId}`}</dd></div>
        <div><dt className="text-muted">Creation Source</dt><dd>{current.decisionSource === "system_policy" ? "System Policy" : `Analyst #${current.createdByActorId}`}</dd></div>
        <div><dt className="text-muted">Created</dt><dd>{current.createdAt}</dd></div>
        <div><dt className="text-muted">Operational Priority at Creation</dt><dd>{snapshot.triage.priorityBand ?? "Unassigned"} / {snapshot.triage.operationalPriority ?? "Not assigned"}</dd></div>
        <div><dt className="text-muted">Policy at Creation</dt><dd>{snapshot.triage.triagePolicyVersion ?? "Not applied"}</dd></div>
      </dl>
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
    <section className="space-y-2 border-t border-border pt-4" aria-label="Detector evidence">
      <h2 className="text-base font-semibold">Detector Evidence</h2>
      <p className="text-sm">Detector: {detector.detectorName} ({detector.detectorSource})</p>
      <p className="text-sm">Native Severity: {detector.nativeSeverity ?? "Not provided"}</p>
      <p className="text-sm">Confidence: {detector.detectorConfidence === null ? "Not provided" : detector.detectorConfidence}</p>
      <p className="break-words text-sm">{detector.detectionTitle} / {detector.detectionCategory ?? "Not provided"}</p>
      <p className="break-all text-sm">Source: {detector.sourceIp} / Port: {detector.sourcePort ?? "Not provided"}</p>
      <p className="break-all text-sm">Destination: {detector.destinationIp} / Port: {detector.destinationPort ?? "Not provided"}</p>
      <Link className="inline-block text-sm text-accent underline" to={prefixFor(session?.role) + "/v2-triage?alertRef=" + current.primaryOperationalAlertRef}>Primary alert</Link>
      <details><summary className="cursor-pointer text-sm">Immutable detector snapshot</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all p-2 text-xs">{JSON.stringify(detector.detectorEvidence,null,2)}</pre></details>
    </section>
    <section className="space-y-4 border-t border-border pt-4">
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Case investigation">
        {([["note","Investigation Notes"],["finding","Findings"],["link","Linked Alerts"],["timeline","Audit Timeline"]] as const).map(([value,label]) =>
          <button role="tab" aria-selected={tab === value} disabled={busy} className={button} key={value}
            onClick={() => { setTab(value); setOffset(0); setReason(""); setError(""); setMessage(""); }}>{label}</button>)}
      </div>
      {events.status === "loading" && <p role="status">Loading case history...</p>}
      {events.status === "error" && <div><p role="alert">{events.error.message}</p><button className={button} onClick={events.reload}>Retry</button></div>}
      {events.status === "success" && <div role="tabpanel" className="space-y-3">
        {events.data.items.length === 0 && <p className="text-sm">No records yet.</p>}
        {events.data.items.map(event => <article key={event.id} className="space-y-1 border-b border-border py-3">
          <p className="text-xs text-muted">{event.eventType} / {event.decisionSource === "system_policy" ? "System Policy" : `actor #${event.actorId}`} / {event.createdAt}</p>
          {event.finding && <Pill tone="warn">{event.finding.replaceAll("_"," ")}</Pill>}
          <p className="whitespace-pre-wrap break-words text-sm">{event.reason}</p>
          {event.linkedAlertRef && <Link className="break-all text-sm text-accent underline" to={prefixFor(session?.role) + "/v2-triage?alertRef=" + event.linkedAlertRef}>{event.linkedAlertRef}</Link>}
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
        {tab === "finding" && <><label htmlFor="case-finding" className="block text-sm">Finding</label><select id="case-finding" value={finding} disabled={busy} onChange={e => setFinding(e.target.value as typeof finding)} className={input}>
          <option value="inconclusive">Inconclusive</option><option value="suspicious">Suspicious</option><option value="confirmed_malicious">Confirmed malicious</option><option value="expected_activity">Expected activity</option>
        </select></>}
        <label htmlFor="investigation-note" className="block text-sm">{tab === "note" ? "Investigation note" : "Decision reason"}</label>
        <textarea id="investigation-note" rows={3} maxLength={4000} value={reason} disabled={busy} onChange={e => setReason(e.target.value)} className={input} />
        <button className={button} disabled={busy || !reason.trim() || (tab === "link" && !linkedRef.trim())} onClick={() => void act(tab === "timeline" ? "start" : tab)}>
          {tab === "note" ? "Add investigation note" : tab === "finding" ? "Record finding" : tab === "link" ? "Link alert" : "Start investigation"}
        </button>
      </div>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {message && <p role="status" className="text-sm text-ok">{message}</p>}
      <button className={button} disabled={busy} onClick={refresh}>Refresh case</button>
    </section>
    <ResponseRecommendations key={current.caseRef} current={current} canWrite={canWrite} />
  </div>;
}
