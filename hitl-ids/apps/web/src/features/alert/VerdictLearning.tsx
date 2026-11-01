import { useEffect,useRef,useState } from "react";
import { Link } from "react-router";
import { api,unwrap,type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { verdictLabels } from "./AnalystVerdict";

const button="rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";
export function VerdictLearning({view,onVerdict,onContributed}:{view:Schemas["RoutingView"];onVerdict?:()=>void;onContributed?:()=>void}) {
  const alertRef=view.operationalAlertRef;
  const verdict=useApi(signal=>unwrap(api.GET("/api/v2/alerts/{alertRef}/verdict",{params:{path:{alertRef}},signal})),[alertRef,view.stateVersion]);
  const contribution=useApi(signal=>unwrap(api.GET("/api/v2/alerts/{alertRef}/triage-memory/verdict-state",{params:{path:{alertRef}},signal})),[alertRef]);
  const matches=useApi(signal=>unwrap(api.GET("/api/v2/alerts/{alertRef}/triage-memory/matches",{params:{path:{alertRef},query:{limit:50,offset:0}},signal})),[alertRef]);
  const [scope,setScope]=useState<"exact"|"narrow">("narrow");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const pending=useRef<{key:string;id:string}|null>(null);
  const refreshRef=useRef(()=>{});refreshRef.current=()=>{verdict.reload();contribution.reload();matches.reload();};
  useEffect(()=>{const timer=setInterval(()=>refreshRef.current(),15000);return()=>clearInterval(timer);},[]);
  async function contribute(){
    if(busy||verdict.status!=="success"||!verdict.data.latest)return;
    const fields={verdictRef:verdict.data.latest.verdictRef,expectedStateVersion:verdict.data.sourceStateVersion,scope};
    const key=JSON.stringify(fields);if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};
    setBusy(true);setError("");
    try {await unwrap(api.POST("/api/v2/alerts/{alertRef}/triage-memory/from-verdict",{params:{path:{alertRef}},body:{...fields,requestId:pending.current.id}}));pending.current=null;refreshRef.current();onContributed?.();}
    catch(cause){setError(cause instanceof Error?cause.message:"Contribution could not be confirmed.");}finally{setBusy(false);}
  }
  const current=verdict.status==="success"?verdict.data.latest:null;
  const status=contribution.status==="success"?contribution.data:null;
  const consistent=!!status&&status.latestVerdictRef===current?.verdictRef;
  return <section aria-label="Human Learning" className="min-w-0 space-y-4">
    <h2 className="label-mono">Human Learning</h2>
    <p className="text-sm text-muted">The Verdict is the human conclusion. Scope controls how narrowly this evidence may support future alerts. Canonical decisions automatically create Exact evidence. Active guidance requires independent support and the safety policy.</p>
    {(verdict.status==="loading"||contribution.status==="loading")&&<p role="status">Loading Verdict learning state…</p>}
    {verdict.status==="error"&&<p role="alert">{verdict.error.message}</p>}
    {contribution.status==="error"&&<p role="alert">{contribution.error.message}</p>}
    {view.state.handlingRoute==="tier2_case"?<p>Tier 2 learning uses Investigation Finding. No Tier 1 Verdict is required.</p>:
      verdict.status==="success"&&!current?<><p>Record an Analyst Verdict to automatically capture Exact learning evidence.</p><button className={button} onClick={onVerdict}>Open Analyst Verdict</button></>:null}
    {current&&<>
      <p>Analyst Verdict: <strong>{verdictLabels[current.outcome]}</strong></p>
      <p className="whitespace-pre-wrap break-words text-sm">Verdict reason: {current.reason}</p>
      <p className="text-xs text-muted">Verdict author: {current.actorName} · Revision {current.revision}</p>
      {status?.contributionStatus==="superseded"&&<p role="status" className="text-warn">{view.state.handlingRoute==="tier2_case"?"Previous Verdict evidence superseded by expert investigation. Use Human Learning in the Tier 2 Case.":"Previous Verdict evidence superseded. Only the latest eligible canonical judgment is reusable."}</p>}
      {status?.contributionStatus==="contributed"&&consistent&&<p role="status">{status.decisionSource==="system_policy"?"Automatically recorded as Exact evidence":"Contributed · Scope: "+status.scope}</p>}
      {status?.memory&&<div className="space-y-1 text-sm">
        <p>Support: {status.memory.supportCount} / {status.memory.lesson.configuration.minimumSupport} · Conflicts: {status.memory.conflictCount}</p>
        <p>Status: {status.memory.status.replaceAll("_"," ")}</p>
        {status.memory.decision?.decisionSource==="system_policy"&&<p>Auto-activated by System Policy · {status.memory.decision.policyVersion}</p>}
        {status.memory.validFrom&&<p>Valid from: {status.memory.validFrom}</p>}
        {status.memory.expiresAt&&<p>Valid until: {status.memory.expiresAt}</p>}
      </div>}
      {status?.lessonRef&&<Link className="block text-accent underline" to={"/analyst/triage-memory?lessonRef="+status.lessonRef}>Open linked Memory lesson</Link>}
      {verdict.status==="success"&&verdict.data.canRecord&&consistent&&status?.scope!=="narrow"&&<div className="space-y-2">
        <label htmlFor="verdict-learning-scope" className="block text-sm">Optional broader learning scope</label>
        <select id="verdict-learning-scope" value={scope} disabled={busy} onChange={e=>setScope(e.target.value as typeof scope)} className="w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm"><option value="narrow">Narrow — explicit broader scope</option></select>
        <button className={button} disabled={busy} onClick={()=>void contribute()}>Expand Learning Scope to Narrow</button>
      </div>}
    </>}
    {error&&<p role="alert">{error}</p>}
    <section aria-label="Related Memory evidence" className="space-y-3 border-t border-border pt-3">
      <h3 className="label-mono">Related Memory lessons</h3>
      {matches.status==="error"&&<p role="alert">{matches.error.message}</p>}
      {matches.status==="success"&&matches.data.items.map(match=><article key={match.memory.lesson.lessonRef} className="space-y-1 border-b border-border pb-3 text-sm">
        <p className="capitalize">{match.memory.lesson.outcome.replaceAll("_"," ")} · {match.memory.status.replaceAll("_"," ")}</p>
        <p>Support: {match.memory.supportCount} · Conflicts: {match.memory.conflictCount}</p>
        <p>Active guidance: {match.guidanceActive?"Yes":"No"}</p>
        <Link className="text-accent underline" to={"/analyst/triage-memory?lessonRef="+match.memory.lesson.lessonRef}>Inspect lesson and evidence history</Link>
      </article>)}
    </section>
    <button className={button} disabled={busy} onClick={()=>refreshRef.current()}>Refresh learning</button>
  </section>;
}
