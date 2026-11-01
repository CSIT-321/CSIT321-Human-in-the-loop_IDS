import { VerdictLearning } from "../../features/alert/VerdictLearning";
import { finalCategories } from "./InvestigationConclusion";
import { useRef,useState } from "react";
import { Link,useSearchParams } from "react-router";
import { api,unwrap,type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { PageHeader,Pill } from "../../components/ui";
import { useSession } from "../../session/SessionContext";

type View=Schemas["MemoryView"];
const button="rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";
const input="w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm";
const pretty=(value:string)=>value.replaceAll("_"," ");
const prefix=(role?:string)=>role==="system_admin"?"/admin":role==="evaluator"?"/evaluator":"/analyst";
const warning="Memory guidance only — Human review still required.";

function Pagination({offset,total,onChange}:{offset:number;total:number;onChange:(n:number)=>void}) {
  return <div className="flex flex-wrap items-center gap-3 text-sm">
    <button className={button} disabled={offset===0} onClick={()=>onChange(Math.max(0,offset-50))}>Previous memory records</button>
    <span>{total} records</span>
    <button className={button} disabled={offset+50>=total} onClick={()=>onChange(offset+50)}>Next memory records</button>
  </div>;
}

export function MemorySummary({view}:{view:View}) {
  return <div className="min-w-0 space-y-3">
    <h3 className="text-base font-semibold capitalize">{pretty(view.lesson.outcome)}</h3>
    <Pill tone={view.status==="active"?"ok":view.status==="conflict_review"?"warn":"muted"}>{pretty(view.status)}</Pill>
    <p className="whitespace-pre-wrap break-words text-sm">{view.lesson.humanReason}</p>
    <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
      <div><dt className="text-muted">Scope</dt><dd>{view.lesson.scope}</dd></div>
      <div><dt className="text-muted">Support</dt><dd>{view.supportCount}</dd></div>
      <div><dt className="text-muted">Conflicts</dt><dd>{view.conflictCount}</dd></div>
      <div><dt className="text-muted">Agreement</dt><dd>{(view.agreementRatio*100).toFixed(1)}%</dd></div>
      <div><dt className="text-muted">Created by</dt><dd>{view.lesson.decisionSource==="system_policy"?"System Policy":`Actor #${view.lesson.createdByActorId}`}</dd></div>
      <div><dt className="text-muted">Created at</dt><dd className="break-all">{view.lesson.createdAt}</dd></div>
      <div><dt className="text-muted">Expires at</dt><dd className="break-all">{view.expiresAt??"Not assigned"}</dd></div>
      <div><dt className="text-muted">Last support</dt><dd className="break-all">{view.lastSupportedAt}</dd></div>
      <div><dt className="text-muted">Last conflict</dt><dd className="break-all">{view.lastConflictAt??"None"}</dd></div>
    </dl>
  </div>;
}

function MemoryDetail({view,canWrite,onChange}:{view:View;canWrite:boolean;onChange:()=>void}) {
  const {session}=useSession();
  const [reason,setReason]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [offset,setOffset]=useState(0);
  const pending=useRef<{key:string;id:string}|null>(null);
  const ref=view.lesson.lessonRef;
  const history=useApi(signal=>unwrap(api.GET("/api/v2/triage-memory/{lessonRef}/events",{
    params:{path:{lessonRef:ref},query:{limit:50,offset}},signal,
  })),[ref,view.revision,offset]);
  async function decide(action:"activate"|"reject") {
    if(busy||!reason.trim()) return;
    const key=JSON.stringify([action,reason.trim(),view.revision]);
    if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};
    setBusy(true);setError("");
    const params={path:{lessonRef:ref}};
    const body={requestId:pending.current.id,expectedRevision:view.revision,reason:reason.trim()};
    try {
      if(action==="activate")await unwrap(api.POST("/api/v2/triage-memory/{lessonRef}/activate",{params,body}));
      else await unwrap(api.POST("/api/v2/triage-memory/{lessonRef}/reject",{params,body}));
      setReason("");pending.current=null;onChange();
    } catch(cause){setError(cause instanceof Error?cause.message:"Memory decision could not be confirmed.");}
    finally{setBusy(false);}
  }
  return <section className="min-w-0 space-y-5" aria-label="Triage lesson detail">
    <MemorySummary view={view}/>
    <div className="flex flex-wrap gap-4 text-sm">
      <Link className="text-accent underline" to={prefix(session?.role)+"/v2-triage?alertRef="+view.lesson.sourceOperationalAlertRef}>Source alert</Link>
      {view.lesson.sourceCaseRef&&<Link className="text-accent underline" to={prefix(session?.role)+"/tier2-cases/"+view.lesson.sourceCaseRef}>Source case</Link>}
    </div>
    <p className="break-words text-sm">Scope fields: {view.lesson.scopeFields.join(", ")}</p>
    <details><summary className="cursor-pointer text-sm">Context snapshot</summary><pre className="overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(view.lesson.contextSnapshot,null,2)}</pre></details>
    <details><summary className="cursor-pointer text-sm">Activation policy</summary><pre className="overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(view.lesson.configuration,null,2)}</pre></details>
    {view.decision&&<div className="space-y-1 border-t border-border pt-3 text-sm">
      <p>{view.decision.decisionSource==="system_policy"?`Auto-activated by System Policy · ${view.decision.policyVersion}`:`${view.decision.action==="activate"?"Activated":"Rejected"} by actor #${view.decision.actorId}`}</p>
      <p className="break-all">{view.decision.createdAt}</p><p className="whitespace-pre-wrap break-words">{view.decision.reason}</p>
    </div>}
    {canWrite&&!view.decision&&view.status!=="expired"&&<div className="space-y-2 border-t border-border pt-3">
      <label htmlFor="memory-approval-reason" className="block text-sm">Memory activation or rejection reason</label>
      <textarea id="memory-approval-reason" className={input} rows={3} maxLength={4000} value={reason} disabled={busy} onChange={e=>setReason(e.target.value)}/>
      <div className="flex flex-wrap gap-2">
        <button className={button} disabled={busy||!reason.trim()||view.status!=="eligible_for_activation"} onClick={()=>void decide("activate")}>Activate Lesson</button>
        <button className={button} disabled={busy||!reason.trim()} onClick={()=>void decide("reject")}>Reject Lesson</button>
      </div>
    </div>}
    {error&&<p role="alert" className="text-danger">{error}</p>}
    <section className="space-y-3 border-t border-border pt-4" aria-label="Memory evidence and audit">
      <h2 className="text-base font-semibold">Memory Evidence and Activation History</h2>
      {history.status==="loading"&&<p role="status">Loading memory history...</p>}
      {history.status==="error"&&<p role="alert">{history.error.message}</p>}
      {history.status==="success"&&<>
        {history.data.items.map(event=><article key={event.id} className="min-w-0 space-y-2 border-b border-border py-3 text-sm">
          <p className="break-all text-xs text-muted">{event.eventType} / {event.decisionSource==="system_policy"?"System Policy":`Actor #${event.actorId}`} / {event.createdAt}</p>
          <p className="whitespace-pre-wrap break-words">{event.reason}</p>
          {event.evidence?.sourceConclusion&&<div className="min-w-0 space-y-1 border-l-2 border-primary pl-3 text-xs [overflow-wrap:anywhere]">
            <p>Source: Tier 2 Investigation Conclusion</p>
            <p>Finding: {pretty(event.evidence.sourceConclusion.finding)}</p>
            <p>Human Final Attack Classification: {event.evidence.sourceConclusion.finalAttackCategory?finalCategories[event.evidence.sourceConclusion.finalAttackCategory]:"Not applicable / unresolved"}</p>
            <p className="whitespace-pre-wrap">Investigation reason: {event.evidence.humanReason}</p>
            <p>Conclusion Author: {event.evidence.conclusionAuthorName} / #{event.evidence.sourceConclusion.actorId}</p>
            <p>Memory Contributor: {event.evidence.decisionSource==="system_policy"?"Automatic System Policy":`${event.evidence.contributionActorName} / #${event.evidence.actorId}`}</p>
            <p>Conclusion event #{event.evidence.sourceConclusion.eventId} · Case revision {event.evidence.sourceConclusion.caseRevision}</p>
            <p>Scope: {event.evidence.contributionScope}</p>
            <Link className="text-accent underline" to={`${prefix(session?.role)}/tier2-cases/${event.evidence.sourceCaseRef}`}>Source Case</Link>
            <p>{event.evidenceCurrent?"Current human evidence":"Superseded human evidence — excluded from effective support"}</p>
          </div>}
          {event.evidence&&!event.evidence.sourceConclusion&&!event.evidence.sourceVerdictRef&&<p className="text-xs">Source: Historical compatibility evidence</p>}
          {event.evidence?.sourceVerdictRef&&<div className="space-y-1 border-l-2 border-primary pl-3 text-xs">
            <p className="capitalize">Source Human Verdict: {pretty(event.evidence.outcome)}</p>
            <p className="break-all">Verdict Reference: {event.evidence.sourceVerdictRef} · Revision {event.evidence.sourceVerdictRevision}</p>
            <p>Verdict Author: {event.evidence.verdictAuthorName} / #{event.evidence.verdictAuthorId}</p>
            <p>Memory Contribution: {event.evidence.decisionSource==="system_policy"?"Automatic System Policy":`Actor #${event.evidence.actorId}`} · Scope: {event.lessonSnapshot.lesson.scope}</p>
            <p>{event.evidenceCurrent?"Current human evidence":"Superseded human evidence — excluded from effective support"}</p>
          </div>}
          <p className="text-xs text-muted">{event.evidence?"Memory Evidence History":"Memory Activation History"}</p>
          {event.evidence&&<><p>{pretty(event.evidence.outcome)} / {event.evidence.relation}</p>
            <Link className="text-accent underline" to={prefix(session?.role)+"/v2-triage?alertRef="+event.evidence.sourceOperationalAlertRef}>{event.evidence.sourceConclusion?"Source Alert":"Evidence alert"}</Link></>}
          <details><summary className="cursor-pointer">Immutable event snapshot</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(event,null,2)}</pre></details>
        </article>)}
        <Pagination offset={offset} total={history.data.page.total} onChange={setOffset}/>
      </>}
      <button className={button} onClick={history.reload}>Refresh memory history</button>
    </section>
  </section>;
}

export function TriageMemoryPage() {
  const {session}=useSession();
  const [search,setSearch]=useSearchParams();
  const ref=search.get("lessonRef");
  const [offset,setOffset]=useState(0);
  const resource=useApi(async signal=>{
    if(ref){const view=await unwrap(api.GET("/api/v2/triage-memory/{lessonRef}",{params:{path:{lessonRef:ref}},signal}));return {items:[view],page:{total:1}};}
    return unwrap(api.GET("/api/v2/triage-memory",{params:{query:{limit:50,offset}},signal}));
  },[ref,offset]);
  const canWrite=session?.role==="security_analyst"||session?.role==="system_admin";
  return <div className="min-w-0 space-y-5 p-4 sm:p-6">
    <PageHeader title="Triage Memory"/>
    <p className="text-sm font-semibold text-warn">{warning}</p>
    {ref&&<button className={button} onClick={()=>setSearch({})}>All memory lessons</button>}
    {resource.status==="loading"&&<p role="status">Loading triage memory...</p>}
    {resource.status==="error"&&<p role="alert">{resource.error.message}</p>}
    {resource.status==="success"&&<>
      {resource.data.items.length===0&&<p>No triage lessons.</p>}
      {ref&&resource.data.items[0]?<MemoryDetail key={ref} view={resource.data.items[0]} canWrite={canWrite} onChange={resource.reload}/>:
        <><div className="space-y-5">{resource.data.items.map(view=><article key={view.lesson.lessonRef} className="min-w-0 space-y-3 border-b border-border pb-5">
          <MemorySummary view={view}/><Link className="text-sm text-accent underline" to={"?lessonRef="+view.lesson.lessonRef}>Review lesson</Link>
        </article>)}</div><Pagination offset={offset} total={resource.data.page.total} onChange={setOffset}/></>}
    </>}
    <button className={button} onClick={resource.reload}>Refresh memory</button>
  </div>;
}

export function AlertMemoryPanel({view,onVerdict,onContributed}:{view:Schemas["RoutingView"];onVerdict?:()=>void;onContributed?:()=>void}) {
  return view.systemRouting ? <VerdictLearning view={view} onVerdict={onVerdict} onContributed={onContributed}/> : <LegacyAlertMemoryPanel view={view}/>;
}

function LegacyAlertMemoryPanel({view}:{view:Schemas["RoutingView"]}) {
  const {session}=useSession();
  const [outcome,setOutcome]=useState<Schemas["MemoryReviewRequest"]["outcome"]>("suspicious");
  const [scope,setScope]=useState<"exact"|"narrow">("exact");
  const [reason,setReason]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [lessonRef,setLessonRef]=useState("");
  const [offset,setOffset]=useState(0);
  const pending=useRef<{key:string;id:string}|null>(null);
  const canWrite=(session?.role==="security_analyst"||session?.role==="system_admin")&&["tier1_review","tier2_candidate","tier2_case"].includes(view.state.handlingRoute);
  const resource=useApi(signal=>unwrap(api.GET("/api/v2/alerts/{alertRef}/triage-memory/matches",{
    params:{path:{alertRef:view.operationalAlertRef},query:{limit:50,offset}},signal,
  })),[view.operationalAlertRef,offset]);
  async function review(){
    if(busy||!reason.trim())return;
    const key=JSON.stringify([outcome,scope,reason.trim(),view.stateVersion]);
    if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};
    setBusy(true);setError("");
    try{
      const result=await unwrap(api.POST("/api/v2/alerts/{alertRef}/triage-memory/candidate",{
        params:{path:{alertRef:view.operationalAlertRef}},body:{requestId:pending.current.id,expectedStateVersion:view.stateVersion,outcome,scope,reason:reason.trim()},
      }));
      setLessonRef(result.memory.lesson.lessonRef);setReason("");pending.current=null;resource.reload();
    }catch(cause){setError(cause instanceof Error?cause.message:"Human memory review could not be confirmed.");}
    finally{setBusy(false);}
  }
  return <section aria-label="Historical Triage Memory" className="min-w-0 space-y-4 border-t border-border pt-5">
    <h2 className="text-base font-semibold">Historical Triage Memory Match</h2>
    <p className="text-sm font-semibold text-warn">{warning}</p>
    {resource.status==="loading"&&<p role="status">Looking up historical lessons...</p>}
    {resource.status==="error"&&<p role="alert">{resource.error.message}</p>}
    {resource.status==="success"&&<>
      {resource.data.items.length===0&&<p className="text-sm">No related triage memory.</p>}
      {resource.data.items.map(match=><article key={match.memory.lesson.lessonRef} className="min-w-0 space-y-3 border-b border-border pb-4">
        <MemorySummary view={match.memory}/>
        <p className="text-sm">Match: {match.strength==="high"?"High":"Partial"}</p>
        <p className="text-sm">Active guidance: {match.guidanceActive?"Yes":"No"}</p>
        <p className="break-words text-xs">Matched: {match.matchedFields.join(", ")||"None"}</p>
        <p className="break-words text-xs">Mismatched: {match.mismatchedFields.join(", ")||"None"}</p>
        <p className="break-words text-xs">Unavailable: {match.unavailableFields.join(", ")||"None"}</p>
        <Link className="text-sm text-accent underline" to={prefix(session?.role)+"/triage-memory?lessonRef="+match.memory.lesson.lessonRef}>Review lesson</Link>
      </article>)}
      <Pagination offset={offset} total={resource.data.page.total} onChange={setOffset}/>
    </>}
    {canWrite&&<div className="space-y-3 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Historical / Legacy Human Memory Review</h3>
      <label htmlFor="memory-outcome" className="block text-sm">Human memory outcome</label>
      <select id="memory-outcome" className={input} disabled={busy} value={outcome} onChange={e=>setOutcome(e.target.value as typeof outcome)}>
        <option value="suspicious">Suspicious</option><option value="expected_activity">Expected Activity</option><option value="false_positive">False Positive</option><option value="confirmed_malicious">Confirmed Malicious</option>
      </select>
      <label htmlFor="memory-scope" className="block text-sm">Memory scope</label>
      <select id="memory-scope" className={input} disabled={busy} value={scope} onChange={e=>setScope(e.target.value as typeof scope)}><option value="exact">Exact</option><option value="narrow">Narrow</option></select>
      <label htmlFor="memory-human-reason" className="block text-sm">Human memory reason</label>
      <textarea id="memory-human-reason" className={input} rows={3} maxLength={4000} disabled={busy} value={reason} onChange={e=>setReason(e.target.value)}/>
      <button className={button} disabled={busy||!reason.trim()} onClick={()=>void review()}>Record Human Memory Review</button>
    </div>}
    {error&&<p role="alert" className="text-danger">{error}</p>}
    {lessonRef&&<p role="status" className="text-sm">Human review recorded. <Link className="text-accent underline" to={prefix(session?.role)+"/triage-memory?lessonRef="+lessonRef}>Open recorded lesson</Link></p>}
    <button className={button} onClick={resource.reload}>Refresh historical memory</button>
  </section>;
}
