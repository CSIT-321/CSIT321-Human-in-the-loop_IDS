import { useEffect,useRef,useState } from "react";
import { Link } from "react-router";
import { api,unwrap,type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { PageHeader,Pill } from "../../components/ui";
import { useSession } from "../../session/SessionContext";
import { TrustedContextPanel } from "./TrustedContextPanel";
import {CollectionRunsPanel,CollectionDecisionPanel,ContextCollectionForm} from "./CollectionPanel";

type View=Schemas["ReviewView"];
type Disposition=View["disposition"];
const labels:Record<Disposition,string>={must_review:"Must Review",recommended_review:"Recommended Review",no_immediate_review:"No Immediate Review"};
const button="rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";
const prefix=(role?:string)=>role==="system_admin"?"/admin":role==="evaluator"?"/evaluator":"/analyst";
const warning="No Immediate Review is an automation decision, not a human verdict.";

export function ReviewSummary({view}:{view:View}) {
  const {session}=useSession();
  const snap=view.lastDecision?.snapshot??view.policyEvaluation;
  const memory=snap.inputs.matches.find(match=>match.memory.lesson.lessonRef===snap.result.matchedLessonRef);
  return <div className="min-w-0 space-y-3">
    <h3 className="text-sm font-semibold">Review Disposition</h3>
    <Pill tone={view.disposition==="no_immediate_review"?"ok":view.disposition==="recommended_review"?"warn":"accent"}>{labels[view.disposition]}</Pill>
    <p className="break-words text-sm">{view.explanation}</p>
    {view.recalled&&<p className="text-sm text-warn">Prior deferral recalled</p>}
    <ul className="space-y-1 break-words text-xs text-muted">{view.reasonCodes.map(code=><li key={code}>{code}</li>)}</ul>
    <p className="text-sm">Policy: {view.policyEvaluation.result.policyVersion}</p>
    <p className="text-sm">Operational priority: {view.priority??"Not assigned"}</p>
    {memory&&<section className="space-y-2 border-t border-border pt-3" aria-label="Decision memory snapshot">
      <h4 className="text-sm font-semibold">Decision Memory Snapshot</h4>
      <p className="text-sm capitalize">{memory.memory.lesson.outcome.replaceAll("_"," ")}</p>
      <p className="break-words text-sm">{memory.memory.lesson.humanReason}</p>
      <p className="text-sm">Support: {memory.memory.supportCount} / Conflicts: {memory.memory.conflictCount} / Match: {memory.strength}</p>
      <Link className="text-sm text-accent underline" to={prefix(session?.role)+"/triage-memory?lessonRef="+memory.memory.lesson.lessonRef}>Inspect memory lesson</Link>
    </section>}
    <TrustedContextPanel context={view.policyEvaluation.contextProvenance}/>
    <details><summary className="cursor-pointer text-sm">Current safety evidence</summary><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(view.policyEvaluation,null,2)}</pre></details>
  </div>;
}

export function SelectiveReviewPanel({alertRef}:{alertRef:string}) {
  const {session}=useSession();
  const [reason,setReason]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [offset,setOffset]=useState(0);
  const [historyOpen,setHistoryOpen]=useState(false);
  const [contextOpen,setContextOpen]=useState(false);
  const [collectionOpen,setCollectionOpen]=useState(false);
  const [runRef,setRunRef]=useState("");
  const [run,setRun]=useState<Schemas["RunView"]|null>(null);
  const pending=useRef<{key:string;id:string}|null>(null);
  const resource=useApi(signal=>unwrap(api.GET("/api/v2/alerts/{alertRef}/selective-review",{params:{path:{alertRef}},signal})),[alertRef]);
  const history=useApi(async signal=>historyOpen?unwrap(api.GET("/api/v2/alerts/{alertRef}/selective-review/events",{params:{path:{alertRef},query:{limit:50,offset}},signal})):null,[alertRef,historyOpen,offset,resource.status==="success"?resource.data.version:""]);
  const reload=resource.reload;
  useEffect(()=>{if(busy)return;const timer=setInterval(reload,15000);return()=>clearInterval(timer);},[reload,busy]);
  const canWrite=session?.role==="security_analyst"||session?.role==="system_admin";
  async function act(action:"apply"|"require_review") {
    if(busy||!reason.trim()||resource.status!=="success")return;
    if(action==="apply"&&runRef&&(!run||run.status!=="open"))return;
    const key=JSON.stringify([action,reason.trim(),resource.data.version,runRef,run?.revision]);
    if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};
    setBusy(true);setError("");
    const params={path:{alertRef}};
    const body={requestId:pending.current.id,expectedVersion:resource.data.version,reason:reason.trim(),
      collectionRunRef:runRef||null,expectedRunRevision:runRef?(run?.revision??1):null};
    try {
      if(action==="apply")await unwrap(api.POST("/api/v2/alerts/{alertRef}/selective-review/evaluate",{params,body}));
      else await unwrap(api.POST("/api/v2/alerts/{alertRef}/selective-review/require-human",{params,body}));
      pending.current=null;setReason("");reload();
    }catch(cause){setError(cause instanceof Error?cause.message:"Review decision could not be confirmed.");}
    finally{setBusy(false);}
  }
  return <section aria-label="Selective Human Review" className="min-w-0 space-y-4 border-t border-border pt-5">
    <h2 className="text-base font-semibold">Selective Human Review</h2>
    <p className="text-sm font-semibold text-warn">{warning}</p>
    <button className={button} aria-expanded={collectionOpen} onClick={()=>setCollectionOpen(!collectionOpen)}>Prospective Collection</button>
    {collectionOpen&&<CollectionDecisionPanel alertRef={alertRef} runRef={runRef} onSelect={setRunRef} onRun={setRun} refreshKey={resource.status==="success"?resource.data.version:""}/>}
    {canWrite&&<button className={button} aria-expanded={contextOpen} onClick={()=>setContextOpen(!contextOpen)}>Add Trusted Context</button>}
    {canWrite&&contextOpen&&<ContextCollectionForm key={alertRef} alertRef={alertRef} onSaved={()=>{setContextOpen(false);reload();}}/>}
    {resource.status==="loading"&&<p role="status">Checking current safety evidence...</p>}
    {resource.status==="error"&&<p role="alert">{resource.error.message}</p>}
    {resource.status==="success"&&<>
      <ReviewSummary view={resource.data}/>
      {resource.data.humanOverride&&<p role="status" className="text-sm">Human review required</p>}
      {resource.data.lastDecision?.collectionRecording?.status==="not_recorded"&&<p role="status" className="text-sm">
        Not recorded in selected collection run because {resource.data.lastDecision.collectionRecording.reason}.
      </p>}
      {canWrite&&<div className="space-y-2">
        <label htmlFor="selective-reason" className="block text-sm">Review policy or override reason</label>
        <textarea id="selective-reason" rows={3} maxLength={4000} disabled={busy} value={reason} onChange={e=>setReason(e.target.value)} className="w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm"/>
        <div className="flex flex-wrap gap-2">
          <button className={button} disabled={busy||!reason.trim()||Boolean(runRef&&(!run||run.status!=="open"))} onClick={()=>void act("apply")}>Evaluate Review Policy</button>
          <button className={button} disabled={busy||!reason.trim()||!resource.data.eligibleAlert||resource.data.humanOverride} onClick={()=>void act("require_review")}>Require Human Review</button>
        </div>
      </div>}
    </>}
    {error&&<p role="alert" className="text-danger">{error}</p>}
    <div className="flex flex-wrap gap-2">
      <button className={button} disabled={busy} onClick={reload}>Refresh review disposition</button>
      <button className={button} aria-expanded={historyOpen} onClick={()=>setHistoryOpen(!historyOpen)}>Review decision history</button>
    </div>
    {historyOpen&&history.status==="error"&&<p role="alert">{history.error.message}</p>}
    {historyOpen&&history.status==="success"&&history.data&&<section className="space-y-3" aria-label="Review audit history">
      {history.data.items.length===0&&<p className="text-sm">No recorded review decisions.</p>}
      {history.data.items.map(event=><article key={event.id} className="min-w-0 space-y-2 border-b border-border py-3 text-sm">
        <p className="break-all text-xs text-muted">{event.eventType} / Actor #{event.actorId} / {event.createdAt}</p>
        <p>{labels[event.snapshot.result.disposition]}</p><p className="whitespace-pre-wrap break-words">{event.reason}</p>
        <details><summary className="cursor-pointer">Immutable decision snapshot</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(event.snapshot,null,2)}</pre></details>
      </article>)}
      <div className="flex gap-2"><button className={button} disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous decisions</button>
      <button className={button} disabled={offset+50>=history.data.page.total} onClick={()=>setOffset(offset+50)}>Next decisions</button></div>
    </section>}
  </section>;
}

export function SelectiveReviewPage() {
  const {session}=useSession();
  const [filter,setFilter]=useState<Disposition|undefined>();
  const [offset,setOffset]=useState(0);
  const resource=useApi(signal=>unwrap(api.GET("/api/v2/selective-review",{params:{query:{disposition:filter,limit:50,offset}},signal})),[filter,offset]);
  const metrics=useApi(signal=>unwrap(api.GET("/api/v2/selective-review/metrics",{signal})),[]);
  const reload=resource.reload;const reloadMetrics=metrics.reload;
  useEffect(()=>{const timer=setInterval(()=>{reload();reloadMetrics();},15000);return()=>clearInterval(timer);},[reload,reloadMetrics]);
  return <div className="min-w-0 space-y-5 p-4 sm:p-6">
    <PageHeader title="Selective Human Review"/>
    <CollectionRunsPanel/>
    <p className="text-sm font-semibold text-warn">{warning}</p>
    {metrics.status==="success"&&<section className="space-y-3" aria-label="Review workload metrics">
      <dl className="grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
        {[["Total alerts",metrics.data.totalAlerts],["Eligible Tier 1 alerts",metrics.data.eligibleAlerts],["Must Review",metrics.data.mustReviewCount],["Recommended Review",metrics.data.recommendedReviewCount],
          ["No Immediate Review",metrics.data.noImmediateReviewCount],["Review-volume reduction",(metrics.data.immediateReviewReductionRate*100).toFixed(1)+"%"],
          ["Later contradictory outcomes",metrics.data.unsafeSuppressionCount],["Conflict-triggered recalls",metrics.data.conflictTriggeredRecallCount],["Audit samples",metrics.data.sampledOverrideCount]].map(([name,value])=><div key={name}><dt className="text-muted">{name}</dt><dd>{value}</dd></div>)}
      </dl><p className="text-xs text-muted">{metrics.data.dataBasis}</p>
    </section>}
    {metrics.status==="error"&&<p role="alert">{metrics.error.message}</p>}
    <div role="tablist" aria-label="Review disposition filters" className="flex flex-wrap gap-2">
      <button role="tab" aria-selected={!filter} className={button} onClick={()=>{setFilter(undefined);setOffset(0);}}>All</button>
      {(Object.keys(labels) as Disposition[]).map(value=><button key={value} role="tab" aria-selected={filter===value} className={button} onClick={()=>{setFilter(value);setOffset(0);}}>{labels[value]}</button>)}
    </div>
    {resource.status==="loading"&&<p role="status">Loading review queue...</p>}
    {resource.status==="error"&&<p role="alert">{resource.error.message}</p>}
    {resource.status==="success"&&<>
      {resource.data.items.length===0?<p>No alerts in this review view.</p>:<div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead><tr>{["Alert","Review disposition","Priority","Workflow route"].map(name=><th key={name} className="border-b border-border p-2">{name}</th>)}</tr></thead>
        <tbody>{resource.data.items.map(view=><tr key={view.operationalAlertRef}>
          <td className="min-w-48 border-b border-border p-2"><Link className="text-accent underline" to={prefix(session?.role)+"/v2-triage?alertRef="+view.operationalAlertRef}>{view.title}</Link></td>
          <td className="border-b border-border p-2">{labels[view.disposition]}</td><td className="border-b border-border p-2">{view.priority??"Not assigned"}</td><td className="border-b border-border p-2">{view.route.replaceAll("_"," ")}</td>
        </tr>)}</tbody>
      </table></div>}
      <div className="flex gap-2"><button className={button} disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous alerts</button>
      <button className={button} disabled={offset+50>=resource.data.page.total} onClick={()=>setOffset(offset+50)}>Next alerts</button></div>
    </>}
    <button className={button} onClick={()=>{reload();reloadMetrics();}}>Refresh review queue</button>
  </div>;
}
