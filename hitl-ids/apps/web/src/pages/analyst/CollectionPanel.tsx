import {useEffect,useRef,useState} from "react";
import {api,unwrap,type Schemas} from "../../api/client";
import {useApi} from "../../api/useApi";
import {useSession} from "../../session/SessionContext";

type Run=Schemas["RunView"];
const control="w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm";
const button="rounded-sm border border-border px-3 py-2 text-sm disabled:opacity-50";
const message=(e:unknown)=>e instanceof Error?e.message:"Collection request failed";
const keys=["assetCriticality","knownMaliciousIndicator","responseRequired","confirmedMalicious","evidenceConflict","repeatedCampaign","correlatedAlertCount","analystEscalated","unresolvedByTier1"] as const;
const label=(key:string)=>key.replace(/([A-Z])/g," $1").replace(/^./,s=>s.toUpperCase());

export function ContextCollectionForm({alertRef,onSaved}:{alertRef:string;onSaved:()=>void}) {
  const [values,setValues]=useState<Record<string,string>>({});
  const [reason,setReason]=useState("");
  const [observed,setObserved]=useState(()=>new Date().toISOString());
  const [expiry,setExpiry]=useState(()=>new Date(Date.now()+3600000).toISOString());
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const pending=useRef<{key:string;id:string;revision:number}|null>(null);
  async function save(){
    setBusy(true);setError("");
    try{
      for(const key of keys){
        if(!(key in values))continue;
        const page=await unwrap(api.GET("/api/v2/context/facts",{params:{query:{limit:1,offset:0}}}));
        const raw=values[key]??"";
        const value=raw===""?null:key==="assetCriticality"?raw:key==="correlatedAlertCount"?Number(raw):raw==="true";
        const body={subjectType:"operational_alert" as const,subjectValue:alertRef,contextKey:key,value,
          observedAt:observed,validFrom:observed,expiresAt:expiry,reason:reason.trim(),sourceReference:"structured-ui-assessment",expectedRevision:page.revision};
        const identity=JSON.stringify({...body,expectedRevision:undefined});
        if(pending.current?.key!==identity)pending.current={key:identity,id:crypto.randomUUID(),revision:page.revision};
        await unwrap(api.POST("/api/v2/context/facts",{body:{...body,expectedRevision:pending.current.revision,requestId:pending.current.id}}));
        pending.current=null;
        setValues(current=>{const remaining={...current};delete remaining[key];return remaining;});
      }
      setValues({});setReason("");onSaved();
    }catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <section aria-label="Collect structured safety context" className="space-y-3 border-t border-border pt-3">
    <div className="grid min-w-0 gap-3 sm:grid-cols-2">{keys.map(key=><label key={key} className="min-w-0 text-sm">{label(key)}
      {key==="correlatedAlertCount"?<input aria-label={label(key)} className={control} type="number" min={0} step={1} value={values[key]??""} onChange={e=>setValues({...values,[key]:e.target.value})}/>:
      <select aria-label={label(key)} className={control} value={values[key]??"unassessed"} onChange={e=>setValues({...values,[key]:e.target.value})}>
        <option value="unassessed" disabled>Not assessed</option><option value="">Unknown</option>{(key==="assetCriticality"?["low","medium","high","critical"]:["false","true"]).map(v=><option key={v} value={v}>{v}</option>)}
      </select>}</label>)}</div>
    <label className="block text-sm">Observed at<input className={control} value={observed} onChange={e=>setObserved(e.target.value)}/></label>
    <label className="block text-sm">Context expires at<input className={control} value={expiry} onChange={e=>setExpiry(e.target.value)}/></label>
    <label className="block text-sm">Structured assessment reason<textarea className={control} value={reason} onChange={e=>setReason(e.target.value)} maxLength={4000}/></label>
    <button className={button} disabled={busy||!reason.trim()||Object.keys(values).length===0} onClick={()=>void save()}>Record Safety Assessment</button>
    {error&&<p role="alert">{error}</p>}
  </section>;
}

export function CollectionDecisionPanel({alertRef,runRef,onSelect,onRun,refreshKey}:{alertRef:string;runRef:string;onSelect:(s:string)=>void;onRun:(run:Run|null)=>void;refreshKey:string}){
  const {session}=useSession();const canWrite=session?.role!=="evaluator";
  const runs=useApi(signal=>unwrap(api.GET("/api/v2/collection/runs",{signal})),[refreshKey]);
  const archive=useApi(async signal=>runRef?unwrap(api.GET("/api/v2/collection/runs/{runRef}/export",{params:{path:{runRef}},signal})):null,[runRef,refreshKey]);
  const [reviewSeconds,setReviewSeconds]=useState("");const [taskSeconds,setTaskSeconds]=useState("");const [notes,setNotes]=useState("");
  const [errors,setErrors]=useState(0);const [rework,setRework]=useState(0);const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const pending=useRef<{key:string;id:string}|null>(null);
  const run=archive.status==="success"?archive.data?.run:null;
  useEffect(()=>onRun(run??null),[run,onRun]);
  const recorded=archive.status==="success"?archive.data?.decisions.filter(d=>d.operationalAlertRef===alertRef).at(-1):undefined;
  const later=recorded&&archive.status==="success"?archive.data?.outcomes.filter(o=>o.alertRef===alertRef&&new Date(o.availableAt)>new Date(recorded.decisionAt)):[];
  async function observe(){
    if(!run)return;setBusy(true);setError("");
    const body={expectedRevision:run.revision,operationalAlertRef:alertRef,analystReviewSeconds:reviewSeconds===""?null:Number(reviewSeconds),totalTaskSeconds:taskSeconds===""?null:Number(taskSeconds),errors,rework,notes};
    const key=JSON.stringify(body);if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};
    try{await unwrap(api.POST("/api/v2/collection/runs/{runRef}/observations",{params:{path:{runRef}},body:{...body,requestId:pending.current.id}}));pending.current=null;setNotes("");archive.reload();}
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <section aria-label="Prospective decision collection" className="space-y-3 border-t border-border pt-3">
    <label className="block text-sm">Collection run<select aria-label="Collection run" className={control} value={runRef} onChange={e=>onSelect(e.target.value)}><option value="">No collection run</option>{runs.status==="success"&&runs.data.items.map(r=><option key={r.runRef} value={r.runRef}>{r.protocol.registration.protocolVersion} / {r.status} / {r.runRef}</option>)}</select></label>
    {runs.status==="error"&&<p role="alert">{runs.error.message}</p>}
    {archive.status==="error"&&<p role="alert">{archive.error.message}</p>}
    {run&&<p className="break-all text-sm">Protocol: {run.protocol.registration.protocolVersion} / Collection: {run.status} / {run.protocol.registration.evidenceBasis}</p>}
    {recorded&&<div className="space-y-1 break-words text-sm">
      <p>Persisted disposition: {recorded.snapshot.result.disposition}</p><p>Decision timestamp: {recorded.decisionAt}</p>
      <p>Alert occurrence: {recorded.alertOccurredAt}</p><p>Operational admission: {recorded.operationalAdmittedAt}</p><p>Review eligibility: {recorded.reviewEligibleAt}</p>
      <p>Recorded policy: {recorded.snapshot.policyConfigSnapshot.version}</p><p>Recorded context: {recorded.snapshot.contextProvenance?.complete?"Complete":"Incomplete"}</p>
      <p>Outcome: {later?.some(o=>o.outcome!=="inconclusive")?"Completed":"Pending"}</p>
      {canWrite&&run?.status==="open"&&<div className="space-y-2">
        <label className="block">Analyst review seconds<input className={control} type="number" min={0} value={reviewSeconds} onChange={e=>setReviewSeconds(e.target.value)}/></label>
        <label className="block">Total task seconds<input className={control} type="number" min={0} value={taskSeconds} onChange={e=>setTaskSeconds(e.target.value)}/></label>
        <label className="block">Errors<input className={control} type="number" min={0} value={errors} onChange={e=>setErrors(Number(e.target.value))}/></label>
        <label className="block">Rework<input className={control} type="number" min={0} value={rework} onChange={e=>setRework(Number(e.target.value))}/></label>
        <label className="block">Task observation notes<textarea className={control} value={notes} onChange={e=>setNotes(e.target.value)}/></label>
        <button className={button} disabled={busy||!notes.trim()} onClick={()=>void observe()}>Record Task Observation</button>
      </div>}
    </div>}
    {error&&<p role="alert">{error}</p>}
    <button className={button} onClick={()=>{runs.reload();archive.reload();}}>Refresh Collection</button>
  </section>;
}

export function CollectionRunsPanel(){
  const {session}=useSession();const admin=session?.role==="system_admin";
  const [open,setOpen]=useState(false);
  return <section className="space-y-3 border-t border-border pt-4" aria-label="Prospective collection runs">
    <button className={button} aria-expanded={open} onClick={()=>setOpen(!open)}>Collection Runs</button>
    {open&&<CollectionRunManager admin={admin}/>}
  </section>;
}

function CollectionRunManager({admin}:{admin:boolean}){
  const runs=useApi(signal=>unwrap(api.GET("/api/v2/collection/runs",{signal})),[]);
  const [version,setVersion]=useState("prospective-context-protocol-v2-draft");const [basis,setBasis]=useState<"synthetic/demo"|"historical-inputs-unverified">("synthetic/demo");
  const [participant,setParticipant]=useState<"professional_analyst"|"proxy_student_analyst">("proxy_student_analyst");
  const [start,setStart]=useState("");const [end,setEnd]=useState("");const [cutoff,setCutoff]=useState("");const [approval,setApproval]=useState("");
  const [error,setError]=useState("");const [busy,setBusy]=useState(false);const [document,setDocument]=useState<unknown>(null);
  const pending=useRef<{key:string;id:string}|null>(null);
  function requestId(key:string){if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};return pending.current.id;}
  async function create(){
    setBusy(true);setError("");
    const body={protocolVersion:version,evidenceBasis:basis,participantClass:participant,holdoutStart:start||null,holdoutEnd:end||null,outcomeCutoff:cutoff||null,readinessReviewReference:approval||null,minimumEligibleAlerts:100,minimumOutcomeCompleteness:.95};
    try{await unwrap(api.POST("/api/v2/collection/runs",{body:{...body,requestId:requestId(JSON.stringify(body))}}));pending.current=null;runs.reload();}
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  async function command(run:Run,action:"open"|"close"|"evaluated"|"export"|"report"){
    setBusy(true);setError("");
    const params={path:{runRef:run.runRef}};
    const body={requestId:requestId(JSON.stringify([run.runRef,run.revision,action])),expectedRevision:run.revision};
    try{
      if(action==="export")setDocument(await unwrap(api.GET("/api/v2/collection/runs/{runRef}/export",{params})));
      else if(action==="report")setDocument((await unwrap(api.GET("/api/v2/collection/runs/{runRef}/report",{params}))).payload);
      else if(action==="open")await unwrap(api.POST("/api/v2/collection/runs/{runRef}/open",{params,body}));
      else if(action==="close")await unwrap(api.POST("/api/v2/collection/runs/{runRef}/close",{params,body}));
      else await unwrap(api.POST("/api/v2/collection/runs/{runRef}/evaluated",{params,body}));
      pending.current=null;runs.reload();
    }catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <div className="min-w-0 space-y-4">
    {admin&&<div className="grid min-w-0 gap-3 sm:grid-cols-2">
      <label className="text-sm">Protocol version<input className={control} value={version} onChange={e=>setVersion(e.target.value)}/></label>
      <label className="text-sm">Evidence basis<select className={control} value={basis} onChange={e=>setBasis(e.target.value as typeof basis)}><option value="synthetic/demo">Synthetic/demo</option><option value="historical-inputs-unverified">Historical inputs, unverified</option></select></label>
      <label className="text-sm">Participant classification<select className={control} value={participant} onChange={e=>setParticipant(e.target.value as typeof participant)}><option value="proxy_student_analyst">Proxy/student analyst</option><option value="professional_analyst">Professional analyst</option></select></label>
      <label className="text-sm">Readiness PASS review reference<input className={control} value={approval} onChange={e=>setApproval(e.target.value)}/></label>
      <label className="text-sm">Holdout start<input className={control} value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label className="text-sm">Holdout end<input className={control} value={end} onChange={e=>setEnd(e.target.value)}/></label>
      <label className="text-sm">Outcome cutoff<input className={control} value={cutoff} onChange={e=>setCutoff(e.target.value)}/></label>
      <button className={button} disabled={busy||!version.trim()} onClick={()=>void create()}>Create Draft Run</button>
    </div>}
    {runs.status==="error"&&<p role="alert">{runs.error.message}</p>}
    {runs.status==="success"&&runs.data.items.map(run=><article key={run.runRef} aria-label={run.protocol.registration.protocolVersion} className="space-y-2 border-b border-border pb-3 text-sm">
      <h3 className="font-semibold">{run.protocol.registration.protocolVersion}</h3><p>Status: {run.status}</p>
      <p className="break-all">Run: {run.runRef}</p><p>Recorded decisions: {run.decisionCount}</p><p>Participants: {run.protocol.registration.participantClass}</p>
      <p className="break-all">Commit: {run.protocol.codeCommitSha}</p><p className="break-all">Protocol hash: {run.protocolHash}</p>
      <p>Start: {run.protocol.registration.holdoutStart??"Unset"}</p><p>End: {run.protocol.registration.holdoutEnd??"Unset"}</p><p>Outcome cutoff: {run.protocol.registration.outcomeCutoff??"Unset"}</p>
      <div className="flex flex-wrap gap-2">
        {admin&&run.status==="draft"&&<button className={button} disabled={busy} onClick={()=>void command(run,"open")}>Open Run</button>}
        {admin&&run.status==="open"&&<button className={button} disabled={busy} onClick={()=>void command(run,"close")}>Close Run</button>}
        <button className={button} disabled={busy} onClick={()=>void command(run,"export")}>Inspect Export</button>
        <button className={button} disabled={busy||!["closed","evaluated"].includes(run.status)} onClick={()=>void command(run,"report")}>Evaluate Recorded Collection</button>
        {admin&&run.status==="closed"&&<button className={button} disabled={busy} onClick={()=>void command(run,"evaluated")}>Record Evaluation Receipt</button>}
      </div>
    </article>)}
    {error&&<p role="alert">{error}</p>}
    {document!==null&&<section aria-label="Collection document"><a className="text-accent underline" download="prospective-collection.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(document,null,2))}>Download JSON</a><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(document,null,2)}</pre></section>}
    <button className={button} disabled={busy} onClick={runs.reload}>Refresh Runs</button>
  </div>;
}
