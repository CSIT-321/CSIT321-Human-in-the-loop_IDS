import {useRef,useState} from "react";
import {api,unwrap,type Schemas} from "../../api/client";
import {useApi} from "../../api/useApi";
import {finalCategories} from "./InvestigationConclusion";

const button="rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";
const approval=(status:string)=>status==="approved"?"Approved - Not Executed":status==="rejected"?"Rejected":"Pending Human Approval";
export function ResolutionDetails({resolution}:{resolution:Schemas["CaseResolution"]}){
 return <div className="min-w-0 space-y-2 text-sm [overflow-wrap:anywhere]">
  <p className="font-semibold">Case Resolved · {resolution.previousStatus} → Resolved</p>
  <p>Resolved by: {resolution.actorName} / #{resolution.actorId}</p>
  <p>Resolved at: {resolution.createdAt}</p><p className="whitespace-pre-wrap">Resolution reason: {resolution.reason}</p>
  <p>Conclusion event #{resolution.conclusion.eventId} · Case revision {resolution.caseRevision}</p>
  <p>Latest Finding at resolution: {resolution.conclusion.finding.replaceAll("_"," ")}</p>
  <p>Human Final Attack Classification: {resolution.conclusion.finalAttackCategory?finalCategories[resolution.conclusion.finalAttackCategory]:resolution.conclusion.finding==="expected_activity"?"Not applicable":"Unresolved / not recorded"}</p>
  {resolution.responses.length===0?<p>Response at resolution: None recorded.</p>:resolution.responses.map(response=><p key={response.recommendationRef}>
   Response: {response.recommendationType.replaceAll("_"," ")} · {approval(response.approvalStatus)} · {response.recommendationRef} · Proposal Case revision {response.proposalCaseRevision}
  </p>)}
 </div>;
}

export function CaseResolution({current,canWrite,responseVersion,onResolved}:{current:Schemas["CaseView"];canWrite:boolean;responseVersion:number;onResolved:(value:Schemas["CaseView"])=>void}){
 const [reason,setReason]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
 const pending=useRef<{key:string;id:string}|null>(null);
 const responses=useApi(async signal=>{
  const items:Schemas["ResponseView"][]=[];
  if(current.status==="resolved")return items;
  let offset=0;
  for(;;){
   const page=await unwrap(api.GET("/api/v2/tier2/cases/{caseRef}/responses",{params:{path:{caseRef:current.caseRef},query:{limit:200,offset}},signal}));
   items.push(...page.items);offset+=page.items.length;
   if(offset>=page.page.total||page.items.length===0)return items;
  }
 },[current.caseRef,current.revision,current.status,responseVersion]);
 async function resolve(){
  if(busy||!reason.trim()||!current.latestConclusion||responses.status!=="success"||responses.data.some(r=>r.status==="pending"))return;
  const key=JSON.stringify([current.caseRef,current.revision,reason.trim()]);
  if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};
  setBusy(true);setError("");
  try{
   const result=await unwrap(api.POST("/api/v2/tier2/cases/{caseRef}/resolve",{params:{path:{caseRef:current.caseRef}},
    body:{requestId:pending.current.id,expectedRevision:current.revision,reason:reason.trim()}}));
   pending.current=null;setReason("");onResolved(result.case);
  }catch(cause){setError(cause instanceof Error?cause.message:"Resolution could not be confirmed.");}finally{setBusy(false);}
 }
 return <section aria-label="Case Resolution" className="min-w-0 space-y-3 border-t border-border pt-4 text-sm [overflow-wrap:anywhere]">
  <h2 className="text-base font-semibold">Case Resolution</h2>
  <p className="text-xs text-muted">Resolution closes the investigation. It does not execute a response or withdraw current learning evidence.</p>
  {current.status==="resolved"&&current.resolution?<ResolutionDetails resolution={current.resolution}/>:<>
   {current.latestConclusion?<>
    <p>Latest Finding: {current.latestConclusion.finding.replaceAll("_"," ")}</p>
    <p>Human Final Attack Classification: {current.latestConclusion.finalAttackCategory?finalCategories[current.latestConclusion.finalAttackCategory]:current.latestConclusion.finding==="expected_activity"?"Not applicable":"Unresolved / not recorded"}</p>
   </>:<p>Record an Investigation Conclusion before resolving this Case.</p>}
   {responses.status==="loading"&&<p role="status">Checking response approval status...</p>}
   {responses.status==="error"&&<><p role="alert">{responses.error.message}</p><button className={button} onClick={responses.reload}>Retry resolution status</button></>}
   {responses.status==="success"&&<>
    {responses.data.length===0?<p>Response: None recorded. A response recommendation is not required to resolve.</p>:responses.data.map(r=><p key={r.proposal.recommendationRef}>Response: {r.proposal.recommendationType.replaceAll("_"," ")} · {approval(r.status)}</p>)}
    {responses.data.some(r=>r.status==="pending")&&<p className="text-warn">Complete human approval or rejection of all pending response recommendations before resolving. Execution is not required.</p>}
   </>}
   {canWrite&&<div className="space-y-2">
    <label className="block" htmlFor="case-resolution-reason">Resolution Reason</label>
    <textarea id="case-resolution-reason" rows={3} maxLength={4000} className="w-full min-w-0 rounded-sm border border-border bg-surface p-2" value={reason} disabled={busy} onChange={e=>setReason(e.target.value)}/>
    <button className={button} disabled={busy||!reason.trim()||!current.latestConclusion||responses.status!=="success"||responses.data.some(r=>r.status==="pending")} onClick={()=>void resolve()}>Resolve Case</button>
   </div>}
   <button className={button} disabled={busy} onClick={responses.reload}>Refresh resolution status</button>
  </>}
  {error&&<p role="alert" className="text-danger">{error}</p>}
 </section>;
}
