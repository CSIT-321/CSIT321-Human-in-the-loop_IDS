import { useRef,useState } from "react";
import { api,unwrap,type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { Pill } from "../../components/ui";

type View = Schemas["ResponseView"];
type Kind = Schemas["ManualResponseRequest"]["recommendationType"];
const labels: Record<Kind,string> = {
  block_source_ip:"Block Source IP",isolate_host:"Isolate Host",disable_account:"Disable Account",
  notify_security_team:"Notify Security Team",monitor:"Monitor",further_investigation:"Further Investigation",
};
const button = "rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";
const input = "w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm";

export function ResponseRecommendationCard({ view,caseRevision,canWrite,onChange }: {
  view:View;caseRevision:number;canWrite:boolean;onChange:()=>void;
}) {
  const [reason,setReason] = useState("");
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const pending = useRef<{ key:string;id:string } | null>(null);
  const proposal = view.proposal;
  const stale = proposal.caseRevision !== caseRevision;
  async function decide(action:"approve"|"reject") {
    if (busy || !reason.trim()) return;
    const key=JSON.stringify([action,reason.trim(),caseRevision,view.revision]);
    if (pending.current?.key !== key) pending.current={key,id:crypto.randomUUID()};
    setBusy(true);setError("");
    try {
      const params={path:{caseRef:proposal.caseRef,recommendationRef:proposal.recommendationRef}};
      const body={requestId:pending.current.id,reason:reason.trim(),expectedCaseRevision:caseRevision,expectedRevision:view.revision};
      if (action==="approve") await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/responses/{recommendationRef}/approve",{params,body}));
      else await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/responses/{recommendationRef}/reject",{params,body}));
      onChange();
    } catch(cause) { setError(cause instanceof Error ? cause.message : "Decision could not be confirmed."); }
    finally { setBusy(false); }
  }
  return <article className="min-w-0 space-y-3 rounded-sm border border-border p-4" aria-label={labels[proposal.recommendationType]}>
    <h3 className="text-base font-semibold">{labels[proposal.recommendationType]}</h3>
    <Pill tone={view.status==="approved" ? "ok" : view.status==="rejected" ? "muted" : "warn"}>
      {view.status==="approved" ? "Approved - Not Executed" : view.status==="rejected" ? "Rejected" : "Pending Human Approval"}
    </Pill>
    <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
      <div><dt className="text-muted">Target</dt><dd className="break-all">{proposal.targetType}: {proposal.targetValue}</dd></div>
      <div><dt className="text-muted">Proposal Source</dt><dd>{proposal.proposalSource==="system_policy" ? "System Policy" : "Analyst"}</dd></div>
      <div><dt className="text-muted">Proposed By</dt><dd>Actor #{proposal.proposedByActorId}</dd></div>
      <div><dt className="text-muted">Created</dt><dd>{proposal.createdAt}</dd></div>
    </dl>
    <p className="whitespace-pre-wrap break-words text-sm">{proposal.rationale}</p>
    <p className="whitespace-pre-wrap break-words text-sm">Proposal reason: {proposal.proposalReason}</p>
    <p className="text-xs text-muted">Finding: {proposal.evidenceSnapshot.finding?.finding.replaceAll("_"," ") ?? "No Tier 2 finding"}</p>
    {proposal.evidenceSnapshot.finding && <p className="break-words text-sm">{proposal.evidenceSnapshot.finding.reason}</p>}
    {proposal.policyVersion && <p className="text-xs text-muted">Policy: {proposal.policyVersion}</p>}
    <p className="break-all text-xs text-dim">{proposal.eventType} / {proposal.recommendationRef}</p>
    {view.decision && <section className="space-y-1 border-t border-border pt-3" aria-label="Human response decision">
      <p className="text-sm">{view.status==="approved" ? "Approved" : "Rejected"} by actor #{view.decision.actorId}</p>
      <p className="text-xs text-muted">{view.decision.createdAt}</p>
      <p className="break-words whitespace-pre-wrap text-sm">{view.decision.reason}</p>
      <p className="text-xs text-dim">{view.decision.eventType}</p>
    </section>}
    {view.status==="pending" && stale && <p className="text-sm text-warn">Stale case evidence snapshot</p>}
    {canWrite && view.status==="pending" && <div className="space-y-2 border-t border-border pt-3">
      <label className="block text-sm" htmlFor={"response-decision-"+proposal.recommendationRef}>Approval or rejection reason</label>
      <textarea id={"response-decision-"+proposal.recommendationRef} rows={2} maxLength={4000} disabled={busy}
        value={reason} onChange={e=>setReason(e.target.value)} className={input} />
      <div className="flex flex-wrap gap-2">
        <button className={button} disabled={busy || !reason.trim() || stale} onClick={()=>void decide("approve")}>Approve</button>
        <button className={button} disabled={busy || !reason.trim()} onClick={()=>void decide("reject")}>Reject</button>
      </div>
    </div>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
  </article>;
}

export function ResponseRecommendations({ current,canWrite,onChange }: { current:Schemas["CaseView"];canWrite:boolean;onChange?:()=>void }) {
  const [offset,setOffset]=useState(0);
  const [mode,setMode]=useState<"system_policy"|"analyst">("system_policy");
  const [kind,setKind]=useState<Kind>("further_investigation");
  const [targetType,setTargetType]=useState<Schemas["ManualResponseRequest"]["targetType"]>("case");
  const [target,setTarget]=useState(current.caseRef);
  const [reason,setReason]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const pending=useRef<{key:string;id:string}|null>(null);
  const responses=useApi(signal=>unwrap(api.GET("/api/v2/tier2/cases/{caseRef}/responses",{
    params:{path:{caseRef:current.caseRef},query:{limit:50,offset}},signal,
  })),[current.caseRef,current.revision,offset]);
  function chooseKind(value:Kind) {
    setKind(value);
    setTargetType(value==="block_source_ip" ? "ip" : "case");
    setTarget(value==="block_source_ip" ? current.snapshot.detector.sourceIp : current.caseRef);
  }
  async function propose() {
    if (busy || !reason.trim() || responses.status!=="success" || (mode==="analyst" && !target.trim())) return;
    const revision=responses.data.caseRevision;
    const key=JSON.stringify([mode,kind,targetType,target.trim(),reason.trim(),revision]);
    if(pending.current?.key!==key) pending.current={key,id:crypto.randomUUID()};
    const params={path:{caseRef:current.caseRef}};
    const body={requestId:pending.current.id,expectedCaseRevision:revision,reason:reason.trim()};
    setBusy(true);setError("");setMessage("");
    try {
      if(mode==="analyst") await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/responses/manual",{
        params,body:{...body,recommendationType:kind,targetType,targetValue:target.trim()},
      }));
      else await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/responses/recommend",{params,body}));
      pending.current=null;setReason("");setOffset(0);responses.reload();onChange?.();setMessage("Recommendation recorded; pending human approval.");
    } catch(cause) { setError(cause instanceof Error ? cause.message : "Proposal could not be confirmed."); }
    finally {setBusy(false);}
  }
  return <section className="min-w-0 space-y-4 border-t border-border pt-5" aria-label="Response Recommendations">
    <h2 className="text-base font-semibold">Response Recommendations</h2>
    <p className="text-sm font-semibold text-warn">APPROVAL DOES NOT EXECUTE THE ACTION.</p>
    {responses.status==="loading" && <p role="status">Loading response plans...</p>}
    {responses.status==="error" && <div><p role="alert">{responses.error.message}</p><button className={button} onClick={responses.reload}>Retry</button></div>}
    {responses.status==="success" && <>
      {responses.data.items.length===0 && <p className="text-sm">No response recommendations.</p>}
      {responses.data.items.map(view=><ResponseRecommendationCard key={view.proposal.recommendationRef+":"+view.revision}
        view={view} caseRevision={responses.data.caseRevision} canWrite={canWrite}
        onChange={()=>{responses.reload();onChange?.();setMessage("Human decision recorded. No action executed.");}} />)}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button className={button} disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous responses</button>
        <span>{responses.data.page.total} recommendations</span>
        <button className={button} disabled={offset+50>=responses.data.page.total} onClick={()=>setOffset(offset+50)}>Next responses</button>
      </div>
      {canWrite && <div className="space-y-3">
        <label htmlFor="proposal-source" className="block text-sm">Proposal source</label>
        <select id="proposal-source" value={mode} disabled={busy} onChange={e=>setMode(e.target.value as typeof mode)} className={input}>
          <option value="system_policy">System policy</option><option value="analyst">Analyst proposal</option>
        </select>
        {mode==="analyst" && <>
          <label htmlFor="response-type" className="block text-sm">Recommendation type</label>
          <select id="response-type" value={kind} disabled={busy} onChange={e=>chooseKind(e.target.value as Kind)} className={input}>
            {Object.entries(labels).map(([value,label])=><option key={value} value={value} disabled={value==="isolate_host" || value==="disable_account"}>{label}{value==="isolate_host" || value==="disable_account" ? " (target evidence unavailable)" : ""}</option>)}
          </select>
          <label htmlFor="response-target-type" className="block text-sm">Target type</label>
          <select id="response-target-type" value={targetType} disabled={busy} onChange={e=>setTargetType(e.target.value as typeof targetType)} className={input}>
            {kind==="block_source_ip" ? <option value="ip">IP</option> : <><option value="case">Case</option>{kind==="monitor" && <option value="operational_alert">Operational alert</option>}</>}
          </select>
          <label htmlFor="response-target" className="block text-sm">Target value</label>
          <input id="response-target" value={target} maxLength={500} disabled={busy} onChange={e=>setTarget(e.target.value)} className={input} />
        </>}
        <label htmlFor="proposal-reason" className="block text-sm">Proposal reason</label>
        <textarea id="proposal-reason" rows={3} maxLength={4000} value={reason} disabled={busy} onChange={e=>setReason(e.target.value)} className={input} />
        <button className={button} disabled={busy || !reason.trim() || (mode==="analyst" && !target.trim())} onClick={()=>void propose()}>
          {mode==="system_policy" ? "Generate recommendation" : "Create manual recommendation"}
        </button>
      </div>}
    </>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {message && <p role="status" className="text-sm text-ok">{message}</p>}
    <button className={button} disabled={busy} onClick={responses.reload}>Refresh responses</button>
  </section>;
}
