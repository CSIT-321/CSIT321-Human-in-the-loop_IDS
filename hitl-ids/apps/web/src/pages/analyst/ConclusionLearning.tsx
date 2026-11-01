import { useRef,useState } from "react";
import { Link } from "react-router";
import { api,unwrap,type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { finalCategories } from "./InvestigationConclusion";

const button="rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";
export function ConclusionLearning({current,canWrite,prefix}:{current:Schemas["CaseView"];canWrite:boolean;prefix:string}) {
  const [scope,setScope]=useState<"exact"|"narrow">("exact");
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const pending=useRef<{key:string;id:string}|null>(null);
  const state=useApi(signal=>unwrap(api.GET("/api/v2/tier2/cases/{caseRef}/triage-memory/conclusion-state",{
    params:{path:{caseRef:current.caseRef}},signal,
  })),[current.caseRef,current.revision]);
  async function contribute(){
    if(busy||state.status!=="success"||!state.data.eligible||!state.data.latestConclusion)return;
    const event=state.data.latestConclusion;
    const key=JSON.stringify([current.caseRef,current.revision,event.eventId,scope]);
    if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};
    setBusy(true);setError("");
    try {
      await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/triage-memory/from-conclusion",{
        params:{path:{caseRef:current.caseRef}},body:{requestId:pending.current.id,expectedCaseRevision:current.revision,conclusionEventId:event.eventId,scope},
      }));
      pending.current=null;state.reload();
    } catch(cause){setError(cause instanceof Error?cause.message:"Expert contribution could not be confirmed.");}
    finally{setBusy(false);}
  }
  return <section aria-label="Expert Human Learning" className="min-w-0 space-y-3 border-t border-border pt-4 text-sm [overflow-wrap:anywhere]">
    <h2 className="text-base font-semibold">Human Learning</h2>
    {state.status==="loading"&&<p role="status">Loading expert learning state...</p>}
    {state.status==="error"&&<><p role="alert">{state.error.message}</p><button className={button} onClick={state.reload}>Retry expert learning</button></>}
    {state.status==="success"&&<>
      {!state.data.latestConclusion?<p>Record an Investigation Conclusion before contributing expert learning evidence.</p>:<>
        <p className="capitalize">Latest Expert Conclusion: {state.data.latestConclusion.finding.replaceAll("_"," ")}</p>
        <p>Human Final Attack Classification: {state.data.latestConclusion.finalAttackCategory?finalCategories[state.data.latestConclusion.finalAttackCategory]:state.data.latestConclusion.finding==="expected_activity"?"Not applicable":"Unresolved / not recorded"}</p>
        <p className="whitespace-pre-wrap">Reason: {state.data.latestConclusion.reason}</p>
        {!state.data.eligible&&<p>Not eligible for reusable Memory evidence. {state.data.latestConclusion.recordKind==="legacy_finding"?"Historical Findings require a current Investigation Conclusion.":"Inconclusive investigation outcomes are not reused as confirmed human learning."}</p>}
        {state.data.tier1EvidenceSuperseded&&<p>Previous Tier 1 learning evidence: Superseded by expert investigation conclusion.</p>}
        {state.data.previousExpertEvidenceSuperseded&&<p>Previous expert learning evidence: Superseded — historical only.</p>}
        <p>Contribution: {state.data.contributionStatus==="contributed"?`Contributed · Scope: ${state.data.scope}`:state.data.contributionStatus==="superseded"?"Previous contribution superseded":"Not contributed"}</p>
        {state.data.memory&&<div className="space-y-1">
          <p>Memory Status: {state.data.memory.status.replaceAll("_"," ")} · Support: {state.data.memory.supportCount} · Conflicts: {state.data.memory.conflictCount}</p>
          <Link className="text-accent underline" to={`${prefix}/triage-memory?lessonRef=${state.data.lessonRef}`}>Open linked Memory lesson</Link>
        </div>}
        {canWrite&&state.data.eligible&&state.data.contributionStatus!=="contributed"&&<div className="space-y-2">
          <p className="text-xs text-muted">Expert conclusion is the human outcome. Scope controls how narrowly this evidence may support future alerts. One alert contributes at most one current human learning vote.</p>
          <label className="block" htmlFor="expert-learning-scope">Learning Scope</label>
          <select id="expert-learning-scope" className="w-full min-w-0 rounded-sm border border-border bg-surface p-2" value={scope} disabled={busy} onChange={e=>setScope(e.target.value as typeof scope)}><option value="exact">Exact</option><option value="narrow">Narrow</option></select>
          <button className={button} disabled={busy} onClick={()=>void contribute()}>Use Expert Conclusion as Triage Memory Evidence</button>
        </div>}
      </>}
    </>}
    {error&&<p role="alert" className="text-danger">{error}</p>}
  </section>;
}
