import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter} from "react-router";
import {describe,it,expect} from "vitest";
import {stubFetch,jsonResponse} from "../../test/renderApp";
import type {Schemas} from "../../api/client";
import {ConclusionLearning} from "./ConclusionLearning";

const ref="fe130e6f-af86-4fc6-89f2-bc76b6cad68b";
const current={caseRef:ref,revision:3} as Schemas["CaseView"];
const state={latestConclusion:{eventId:9,finding:"confirmed_malicious",finalAttackCategory:"web_attack",reason:"Canonical expert reason"},
  eligible:true,contributionStatus:"not_contributed",scope:null,lessonRef:null,memory:null,previousExpertEvidenceSuperseded:false,tier1EvidenceSuperseded:true};
function show(canWrite=true){render(<MemoryRouter><ConclusionLearning current={current} canWrite={canWrite} prefix="/analyst"/></MemoryRouter>);}
describe("Expert Human Learning",()=>{
  it("contributes only identity, scope and expected revision without asking for canonical facts again",async()=>{
    const bodies:Record<string,unknown>[]=[];
    stubFetch(async r=>{
      if(r.method==="POST"){bodies.push(await r.json() as Record<string,unknown>);return jsonResponse({});}
      return jsonResponse(bodies.length?{...state,contributionStatus:"contributed",scope:"narrow",lessonRef:ref,memory:{status:"candidate",supportCount:1,conflictCount:0}}:state);
    });show();
    expect(await screen.findByText("Reason: Canonical expert reason")).toBeVisible();
    expect(screen.getByText("Previous Tier 1 learning evidence: Superseded by expert investigation conclusion.")).toBeVisible();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Learning Scope"),"narrow");
    await userEvent.click(screen.getByRole("button",{name:"Expand Expert Learning Scope to Narrow"}));
    expect(await screen.findByText("Contribution: Contributed · Scope: narrow")).toBeVisible();
    expect(Object.keys(bodies[0]!).sort()).toEqual(["conclusionEventId","expectedCaseRevision","requestId","scope"]);
    expect(bodies[0]).toMatchObject({conclusionEventId:9,expectedCaseRevision:3,scope:"narrow"});
    expect(screen.getByRole("link",{name:"Open linked Memory lesson"})).toHaveAttribute("href","/analyst/triage-memory?lessonRef="+ref);
    expect(screen.queryByRole("button",{name:"Expand Expert Learning Scope to Narrow"})).not.toBeInTheDocument();
  });
  it("keeps exact retry identity on conflict",async()=>{
    const bodies:unknown[]=[];stubFetch(async r=>{if(r.method==="POST"){bodies.push(await r.json());return jsonResponse({error:{code:"MEMORY_CONFLICT",message:"Refresh expert conclusion"}},409);}return jsonResponse(state);});show();
    const button=await screen.findByRole("button",{name:"Expand Expert Learning Scope to Narrow"});
    await userEvent.click(button);await screen.findByText("Refresh expert conclusion");await userEvent.click(button);
    await waitFor(()=>expect(bodies).toHaveLength(2));expect(bodies[0]).toEqual(bodies[1]);
  });
  it("explains Inconclusive and supersession without offering contribution",async()=>{
    stubFetch(()=>jsonResponse({...state,latestConclusion:{...state.latestConclusion,finding:"inconclusive",finalAttackCategory:null},eligible:false,previousExpertEvidenceSuperseded:true}));show();
    expect(await screen.findByText(/Not eligible for reusable Memory evidence/)).toBeVisible();
    expect(screen.getByText(/Previous expert learning evidence: Superseded/)).toBeVisible();
    expect(screen.queryByLabelText("Learning Scope")).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Expand Expert Learning Scope to Narrow"})).not.toBeInTheDocument();
  });
  it("shows automatic expert evidence and preserves explicit Narrow expansion",async()=>{
    stubFetch(()=>jsonResponse({...state,contributionStatus:"contributed",scope:"exact",decisionSource:"system_policy",lessonRef:ref,
      memory:{status:"active",supportCount:3,conflictCount:0,decision:{decisionSource:"system_policy",policyVersion:"safe-memory-auto-activation-v1"},validFrom:"2026-11-01T00:00:00Z",expiresAt:"2026-12-01T00:00:00Z"}}));show();
    expect(await screen.findByText('Contribution: Automatically recorded as Exact evidence')).toBeVisible();
    expect(screen.getByText(/Auto-activated by System Policy/)).toBeVisible();
    expect(screen.getByText('Valid until: 2026-12-01T00:00:00Z')).toBeVisible();
    expect(screen.getByRole('button',{name:'Expand Expert Learning Scope to Narrow'})).toBeVisible();
  });
  it("keeps evaluator learning read-only",async()=>{
    stubFetch(()=>jsonResponse(state));show(false);await screen.findByText("Reason: Canonical expert reason");
    expect(screen.queryByRole("button",{name:"Expand Expert Learning Scope to Narrow"})).not.toBeInTheDocument();
  });
});
