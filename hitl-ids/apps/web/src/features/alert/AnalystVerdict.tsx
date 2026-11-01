import { useRef, useState } from "react";
import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";

export const verdictLabels = { confirmed_malicious: "Confirmed Malicious", suspicious: "Suspicious", expected_activity: "Expected Activity", false_positive: "False Positive" };
const button="rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";

function VerdictRecord({ verdict }: { verdict: Schemas["AnalystVerdict"] }) {
  return <article className="min-w-0 space-y-2 border-l-2 border-primary pl-3">
    <p className="font-semibold">{verdictLabels[verdict.outcome]}</p>
    <p className="text-xs text-muted">Recorded by: {verdict.actorName} · {verdict.createdAt} · Revision {verdict.revision}</p>
    <p className="whitespace-pre-wrap break-words text-sm">{verdict.reason}</p>
    {verdict.supersedesRef && <p className="break-all text-xs text-muted">Supersedes: {verdict.supersedesRef}</p>}
  </article>;
}

export function AnalystVerdictPanel({ alertRef, stateVersion }: { alertRef: string; stateVersion: string }) {
  const resource=useApi(signal=>unwrap(api.GET("/api/v2/alerts/{alertRef}/verdict",{params:{path:{alertRef}},signal})),[alertRef,stateVersion]);
  const [outcome,setOutcome]=useState<keyof typeof verdictLabels>("suspicious");
  const [reason,setReason]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const pending=useRef<{key:string;id:string}|null>(null);
  async function save() {
    if(busy||!reason.trim()||resource.status!=="success"||!resource.data.canRecord)return;
    const fields={outcome,reason:reason.trim(),expectedRevision:resource.data.revision,expectedStateVersion:resource.data.sourceStateVersion};
    const key=JSON.stringify(fields);if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};
    setBusy(true);setError("");
    try {await unwrap(api.POST("/api/v2/alerts/{alertRef}/verdict",{params:{path:{alertRef}},body:{...fields,requestId:pending.current.id}}));
      pending.current=null;setReason("");resource.reload();
    }catch(cause){setError(cause instanceof Error?cause.message:"Verdict could not be confirmed.");}finally{setBusy(false);}
  }
  return <section aria-label="Analyst Verdict" className="min-w-0 space-y-3 border-t border-border pt-4">
    <h2 className="label-mono">Analyst Verdict</h2>
    <p className="text-xs text-muted">An authenticated human conclusion, separate from system classification and routing. Recording a verdict does not escalate this alert.</p>
    {resource.status==="loading"&&<p role="status">Loading Analyst Verdict…</p>}
    {resource.status==="error"&&<p role="alert">{resource.error.message}</p>}
    {resource.status==="success"&&<>
      <p className="text-sm">Current Verdict: <strong>{resource.data.latest?verdictLabels[resource.data.latest.outcome]:"Not recorded"}</strong></p>
      {resource.data.latest&&<VerdictRecord verdict={resource.data.latest}/>}
      {!resource.data.canRecord&&<p className="text-xs text-muted">Tier 1 Verdict is available to authorized analysts in Tier 1 review. Tier 2 uses Investigation Finding; no Tier 1 Verdict is required.</p>}
      {resource.data.canRecord&&<fieldset disabled={busy} className="min-w-0 space-y-3">
        <legend className="text-sm">{resource.data.latest?"Correct Verdict":"Record Verdict"}</legend>
        <label className="block text-sm" htmlFor="analyst-verdict-outcome">Verdict outcome</label>
        <select id="analyst-verdict-outcome" value={outcome} onChange={e=>setOutcome(e.target.value as keyof typeof verdictLabels)} className="w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm">
          {Object.entries(verdictLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}
        </select>
        <label htmlFor="analyst-verdict-reason" className="block text-sm">Verdict reason</label>
        <textarea id="analyst-verdict-reason" required maxLength={4000} rows={3} value={reason} onChange={e=>setReason(e.target.value)} className="w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm"/>
        <button className={button} disabled={busy||!reason.trim()} onClick={()=>void save()}>{resource.data.latest?"Correct Verdict":"Record Verdict"}</button>
      </fieldset>}
    </>}
    {error&&<p role="alert">{error}</p>}
    <button className={button} disabled={busy} onClick={resource.reload}>Refresh Verdict</button>
  </section>;
}

export function AnalystVerdictHistory({alertRef}:{alertRef:string}) {
  const [offset,setOffset]=useState(0);
  const resource=useApi(signal=>unwrap(api.GET("/api/v2/alerts/{alertRef}/verdict-history",{params:{path:{alertRef},query:{limit:50,offset}},signal})),[alertRef,offset]);
  return <section aria-label="Analyst Verdict History" className="space-y-3 border-t border-border pt-4">
    <h3 className="label-mono">Analyst Verdict History</h3>
    {resource.status==="loading"&&<p role="status">Loading verdict history…</p>}
    {resource.status==="error"&&<p role="alert">{resource.error.message}</p>}
    {resource.status==="success"&&<>
      <p className="text-xs text-muted">Newest first; revision {resource.data.items[0]?.revision??0} on this page. Earlier revisions remain human evidence.</p>
      {resource.data.total===0&&<p>Not recorded</p>}
      {resource.data.items.map((verdict,index)=><div key={verdict.verdictRef} className="space-y-2">
        <p className="text-xs text-muted">{offset===0&&index===0?"Latest verdict":"Superseded verdict"}</p>
        <VerdictRecord verdict={verdict}/>
      </div>)}
      <div className="flex flex-wrap gap-2"><button className={button} disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous verdicts</button>
        <button className={button} disabled={offset+50>=resource.data.total} onClick={()=>setOffset(offset+50)}>Next verdicts</button></div>
    </>}
  </section>;
}
