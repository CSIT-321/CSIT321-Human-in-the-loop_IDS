import {useRef,useState} from 'react';
import {api,unwrap,ApiError,type Schemas} from '../../api/client';

export function workLabel(work: Schemas['WorkView']) {
  if(work.status==='in_review') return work.isOwner?'In Review — You':`In Review — ${work.ownerName}`;
  if(work.status==='completed') return `Completed — Reviewed by ${work.finishedByName}`;
  if(work.status==='escalated') return `Escalated — ${work.finishedByName}`;
  return work.status==='available'?'Available':'No active Tier 1 work';
}

export function AnalystWorkPanel({alertRef,work,onChanged,onConflict}:{alertRef:string;work:Schemas['WorkView'];onChanged:()=>void;onConflict:(message:string)=>void}) {
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const pending=useRef<Schemas['ClaimCommand']|null>(null);
  async function start(){
    if(busy||!work.canClaim)return;
    pending.current??={requestId:crypto.randomUUID(),expectedRevision:work.revision};
    setBusy(true);setError('');
    try{
      await unwrap(api.POST('/api/v2/alerts/{alertRef}/work/claim',{params:{path:{alertRef}},body:pending.current}));
      pending.current=null;onChanged();
    }catch(cause){
      const message=cause instanceof Error?cause.message:'Claim could not be confirmed. Retry the same request.';
      if(cause instanceof ApiError&&cause.status===409&&cause.code!=='WORK_RETRY'){
        pending.current=null;onConflict(message);
      }else setError(message);
    }finally{setBusy(false);}
  }
  return <section aria-label="Human work status" className="min-w-0 space-y-2 rounded-sm border border-border p-3 text-xs">
    <p>Work Status: <strong>{workLabel(work)}</strong></p>
    <p className="break-words text-muted">{work.explanation}</p>
    {work.finishedAt&&<p>Finished at: {work.finishedAt}</p>}
    {work.verdictOutcome&&<p className="capitalize">Verdict: {work.verdictOutcome.replaceAll('_',' ')}</p>}
    {work.canClaim&&<button disabled={busy} className="rounded-sm border border-border px-3 py-2 disabled:opacity-50" onClick={()=>void start()}>{busy?'Claiming…':'Start Review'}</button>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
