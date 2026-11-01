import { render,screen,waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import userEvent from "@testing-library/user-event";
import { describe,it,expect,vi } from "vitest";
import { jsonResponse,stubFetch } from "../../test/renderApp";
import type { Schemas } from "../../api/client";
import { VerdictLearning } from "./VerdictLearning";

const ref="00000000-0000-4000-8000-000000000001",vref="00000000-0000-4000-8000-000000000002";
const view={operationalAlertRef:ref,stateVersion:"a".repeat(64),state:{handlingRoute:"tier1_review"}} as Schemas["RoutingView"];
const latest={verdictRef:vref,outcome:"expected_activity",reason:"Canonical authorized scan reason",actorName:"Verdict Author",revision:1};
const empty={items:[],page:{total:0,returned:0,limit:50,offset:0}};
function mount(onVerdict=()=>{}){return render(<MemoryRouter><VerdictLearning view={view} onVerdict={onVerdict}/></MemoryRouter>);}
describe("Verdict-based human learning",()=>{
  it("guides missing-Verdict users to the canonical editor instead of requesting another outcome",async()=>{
    const open=vi.fn();stubFetch(req=>jsonResponse(req.url.endsWith('/verdict')?{latest:null,canRecord:true}:req.url.includes('verdict-state')?{latestVerdictRef:null,contributionStatus:'not_contributed',lessonRef:null}:empty));
    mount(open);await userEvent.click(await screen.findByRole('button',{name:'Open Analyst Verdict'}));
    expect(open).toHaveBeenCalledOnce();expect(screen.queryByLabelText('Human memory outcome')).toBeNull();
    expect(screen.queryByRole('button',{name:'Expand Learning Scope to Narrow'})).toBeNull();
  });
  it("contributes only the Verdict reference, workflow version and explicit scope",async()=>{
    let contributed=false;let body:Record<string,unknown>|undefined;
    stubFetch(async req=>{
      if(req.method==='POST'){body=await req.json();contributed=true;return jsonResponse({});}
      if(req.url.endsWith('/verdict'))return jsonResponse({latest,canRecord:true,sourceStateVersion:view.stateVersion});
      if(req.url.includes('verdict-state'))return jsonResponse({latestVerdictRef:vref,contributionStatus:contributed?'contributed':'not_contributed',scope:contributed?'narrow':null,lessonRef:null});
      return jsonResponse(empty);
    });
    mount();expect(await screen.findByText('Verdict reason: '+latest.reason)).toBeVisible();
    await userEvent.selectOptions(await screen.findByLabelText('Optional broader learning scope'),'narrow');
    await userEvent.click(screen.getByRole('button',{name:'Expand Learning Scope to Narrow'}));
    expect(await screen.findByText('Contributed · Scope: narrow')).toBeVisible();
    expect(body).toMatchObject({verdictRef:vref,scope:'narrow',expectedStateVersion:view.stateVersion});
    expect(body).not.toHaveProperty('outcome');expect(body).not.toHaveProperty('reason');expect(body).not.toHaveProperty('actorId');
    expect(screen.queryByLabelText('Human memory reason')).toBeNull();
  });
  it("shows superseded evidence and preserves retry identity after a failed contribution",async()=>{
    const bodies:unknown[]=[];stubFetch(async req=>{
      if(req.method==='POST'){bodies.push(await req.json());return jsonResponse({error:{code:'MEMORY_CONFLICT',message:'Refresh current Verdict'}},409);}
      if(req.url.endsWith('/verdict'))return jsonResponse({latest:{...latest,revision:2},canRecord:true,sourceStateVersion:view.stateVersion});
      if(req.url.includes('verdict-state'))return jsonResponse({latestVerdictRef:vref,contributionStatus:'superseded',scope:'exact',lessonRef:ref});
      return jsonResponse(empty);
    });
    mount();expect(await screen.findByText(/Previous Verdict evidence superseded/)).toBeVisible();
    const action=await screen.findByRole('button',{name:'Expand Learning Scope to Narrow'});
    await userEvent.click(action);await screen.findByRole('alert');await userEvent.click(action);
    await waitFor(()=>expect(bodies).toHaveLength(2));expect(bodies[1]).toEqual(bodies[0]);
  });
  it("shows automatic exact learning, policy activation and fixed validity without manual Exact actions",async()=>{
    stubFetch(req=>jsonResponse(req.url.endsWith('/verdict')?{latest,canRecord:true}:req.url.includes('verdict-state')?{
      latestVerdictRef:vref,contributionStatus:'contributed',scope:'exact',lessonRef:ref,decisionSource:'system_policy',
      memory:{supportCount:3,conflictCount:0,status:'active',lesson:{configuration:{minimumSupport:3}},decision:{decisionSource:'system_policy',policyVersion:'safe-memory-auto-activation-v1'},validFrom:'2026-11-01T00:00:00Z',expiresAt:'2026-12-01T00:00:00Z'}
    }:empty));mount();
    expect(await screen.findByText('Automatically recorded as Exact evidence')).toBeVisible();
    expect(screen.getByText('Support: 3 / 3 · Conflicts: 0')).toBeVisible();
    expect(screen.getByText(/Auto-activated by System Policy/)).toBeVisible();
    expect(screen.getByText('Valid until: 2026-12-01T00:00:00Z')).toBeVisible();
    expect(screen.getByRole('button',{name:'Expand Learning Scope to Narrow'})).toBeVisible();
    expect(screen.queryByRole('button',{name:/Activate|Use Verdict as/})).toBeNull();
  });
  it("keeps evaluator contributions read-only",async()=>{
    stubFetch(req=>jsonResponse(req.url.endsWith('/verdict')?{latest,canRecord:false}:req.url.includes('verdict-state')?{latestVerdictRef:vref,contributionStatus:'not_contributed',lessonRef:null}:empty));
    mount();await screen.findByText('Verdict reason: '+latest.reason);
    expect(screen.queryByRole('button',{name:'Expand Learning Scope to Narrow'})).toBeNull();
  });
});
