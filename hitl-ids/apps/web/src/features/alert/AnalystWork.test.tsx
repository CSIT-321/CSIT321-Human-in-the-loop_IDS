import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {describe,it,expect,vi} from 'vitest';
import {stubFetch,jsonResponse} from '../../test/renderApp';
import {AnalystWorkPanel} from './AnalystWork';
import type {Schemas} from '../../api/client';

const work:Schemas['WorkView']={status:'available',revision:0,canClaim:true,canMutate:false,isOwner:false,explanation:'Available — select Start Review to request ownership.',claimedAt:null,finishedAt:null,finishedByActorId:null,finishedByName:null,ownerActorId:null,ownerName:null,roundRef:null,verdictRef:null,verdictOutcome:null};
describe('explicit shared analyst claim',()=>{
 it('viewing never claims; Start Review submits the revision and refreshes',async()=>{
  const bodies:unknown[]=[];const changed=vi.fn();
  stubFetch(async r=>{bodies.push(await r.json());return jsonResponse({outcome:'claimed'});});
  render(<AnalystWorkPanel alertRef="alert" work={work} onChanged={changed} onConflict={vi.fn()}/>);
  expect(bodies).toHaveLength(0);
  await userEvent.click(screen.getByRole('button',{name:'Start Review'}));
  await waitFor(()=>expect(changed).toHaveBeenCalledOnce());
  expect(bodies).toEqual([{requestId:expect.any(String),expectedRevision:0}]);
 });
 it('controlled contention requests reselect, without reporting ownership',async()=>{
  const changed=vi.fn(),conflict=vi.fn();
  stubFetch(()=>jsonResponse({error:{code:'CLAIM_CONTENTION',message:'Multiple analysts selected this alert. Select again.'}},409));
  render(<AnalystWorkPanel alertRef="alert" work={work} onChanged={changed} onConflict={conflict}/>);
  await userEvent.click(screen.getByRole('button',{name:'Start Review'}));
  await waitFor(()=>expect(conflict).toHaveBeenCalledWith('Multiple analysts selected this alert. Select again.'));
  expect(changed).not.toHaveBeenCalled();
 });
 it('uncertain network retries reuse exactly the same request identity',async()=>{
  const bodies:unknown[]=[];const changed=vi.fn();
  stubFetch(async r=>{bodies.push(await r.json());return bodies.length===1?jsonResponse({error:{code:'UNAVAILABLE',message:'Retry connection'}},503):jsonResponse({outcome:'claimed'});});
  render(<AnalystWorkPanel alertRef="alert" work={work} onChanged={changed} onConflict={vi.fn()}/>);
  await userEvent.click(screen.getByRole('button',{name:'Start Review'}));await screen.findByRole('alert');
  await userEvent.click(screen.getByRole('button',{name:'Start Review'}));
  await waitFor(()=>expect(changed).toHaveBeenCalledOnce());expect(bodies[0]).toEqual(bodies[1]);
 });
 it('non-owner and completed views have no claim controls and retain provenance',()=>{
  const mounted=render(<AnalystWorkPanel alertRef="alert" work={{...work,status:'in_review',canClaim:false,ownerName:'Alice'}} onChanged={vi.fn()} onConflict={vi.fn()}/>);
  expect(screen.getByText('In Review — Alice')).toBeVisible();expect(screen.queryByRole('button')).toBeNull();
  mounted.rerender(<AnalystWorkPanel alertRef="alert" work={{...work,status:'completed',canClaim:false,finishedByName:'Alice',finishedAt:'2026-11-02T00:00:00Z',verdictOutcome:'expected_activity'}} onChanged={vi.fn()} onConflict={vi.fn()}/>);
  expect(screen.getByText('Completed — Reviewed by Alice')).toBeVisible();expect(screen.getByText('Verdict: expected activity')).toBeVisible();expect(screen.queryByRole('button')).toBeNull();
 });
});
