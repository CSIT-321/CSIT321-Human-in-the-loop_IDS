import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe,it,expect,vi} from "vitest";
import {stubFetch,jsonResponse} from "../../test/renderApp";
import type {Schemas} from "../../api/client";
import {CaseResolution} from "./CaseResolution";

const ref="fe130e6f-af86-4fc6-89f2-bc76b6cad68b";
const conclusion={eventId:9,caseRef:ref,finding:"confirmed_malicious",finalAttackCategory:"web_attack",actorId:1,
 reason:"Canonical investigation reason",createdAt:"2026-11-01T00:00:00Z",caseRevision:3,requestId:ref,
 systemClassification:null,supersedesEventId:null,recordKind:"investigation_conclusion"} as Schemas["InvestigationConclusion"];
const current={caseRef:ref,revision:3,status:"investigating",latestConclusion:conclusion} as Schemas["CaseView"];
const empty={items:[],page:{total:0,limit:200,offset:0,returned:0},caseRevision:3};
const resolution={eventId:10,caseRef:ref,actorId:1,actorName:"Analyst",reason:"Investigation complete; plan approved without execution",createdAt:"2026-11-02T00:00:00Z",previousStatus:"investigating",newStatus:"resolved",caseRevision:4,requestId:ref,conclusion,
 responses:[{recommendationRef:ref,recommendationType:"block_source_ip",proposalCaseRevision:3,approvalStatus:"approved",decisionActorId:1,decisionAt:"2026-11-01T00:10:00Z",executionStatus:"not_executed"}]} as Schemas["CaseResolution"];

describe("Case Resolution",()=>{
 it("requires a conclusion and reason, submits only lifecycle fields and displays server result",async()=>{
  const onResolved=vi.fn();const bodies:Record<string,unknown>[]=[];
  stubFetch(async r=>{if(r.method==="POST"){bodies.push(await r.json() as Record<string,unknown>);return jsonResponse({case:{...current,status:"resolved",revision:4,resolution},eventId:10,replayed:false});}return jsonResponse(empty);});
  render(<CaseResolution current={current} canWrite responseVersion={0} onResolved={onResolved}/>);
  const button=await screen.findByRole("button",{name:"Resolve Case"});expect(button).toBeDisabled();
  expect(screen.getByText("Latest Finding: confirmed malicious")).toBeVisible();
  await userEvent.type(screen.getByLabelText("Resolution Reason"),resolution.reason);
  await userEvent.click(button);await waitFor(()=>expect(onResolved).toHaveBeenCalledOnce());
  expect(bodies[0]).toMatchObject({expectedRevision:3,reason:resolution.reason});
  expect(Object.keys(bodies[0]!).sort()).toEqual(["expectedRevision","reason","requestId"]);
 });
 it("blocks missing conclusions and pending human response decisions",async()=>{
  stubFetch(()=>jsonResponse({...empty,items:[{status:"pending",proposal:{recommendationRef:ref,recommendationType:"block_source_ip"}}]}));
  render(<CaseResolution current={{...current,latestConclusion:null}} canWrite responseVersion={0} onResolved={vi.fn()}/>);
  expect(await screen.findByText(/Complete human approval or rejection/)).toBeVisible();
  expect(screen.getByText("Record an Investigation Conclusion before resolving this Case.")).toBeVisible();
  await userEvent.type(screen.getByLabelText("Resolution Reason"),"Complete investigation");
  expect(screen.getByRole("button",{name:"Resolve Case"})).toBeDisabled();
 });
 it("keeps exact retry identity on conflicts and refreshes response state after decisions",async()=>{
  const bodies:unknown[]=[];let pending=true;
  stubFetch(async r=>{if(r.method==="POST"){bodies.push(await r.json());return jsonResponse({error:{code:"CASE_CONFLICT",message:"Refresh Case revision"}},409);}return jsonResponse({...empty,items:[{status:pending?"pending":"approved",proposal:{recommendationRef:ref,recommendationType:"block_source_ip"}}]});});
  const view=render(<CaseResolution current={current} canWrite responseVersion={0} onResolved={vi.fn()}/>);
  await screen.findByText(/Pending Human Approval/);pending=false;
  view.rerender(<CaseResolution current={current} canWrite responseVersion={1} onResolved={vi.fn()}/>);
  await screen.findByText(/Approved - Not Executed/);
  await userEvent.type(screen.getByLabelText("Resolution Reason"),"Complete investigation");
  await userEvent.click(screen.getByRole("button",{name:"Resolve Case"}));await screen.findByText("Refresh Case revision");
  await userEvent.click(screen.getByRole("button",{name:"Resolve Case"}));await waitFor(()=>expect(bodies).toHaveLength(2));
  expect(bodies[0]).toEqual(bodies[1]);
 });
 it("shows immutable resolved details without mutation controls for all readers",async()=>{
  stubFetch(()=>jsonResponse(empty));render(<CaseResolution current={{...current,status:"resolved",resolution}} canWrite={false} responseVersion={0} onResolved={vi.fn()}/>);
  expect(await screen.findByText("Resolved by: Analyst / #1")).toBeVisible();
  expect(screen.getByText(/Approved - Not Executed/)).toBeVisible();
  expect(screen.getByText("Resolution reason: "+resolution.reason)).toBeVisible();
  expect(screen.queryByRole("button",{name:"Resolve Case"})).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Resolution Reason")).not.toBeInTheDocument();
 });
});
