import { render,screen,waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe,expect,it,vi } from "vitest";
import { ResponseRecommendationCard,ResponseRecommendations } from "./ResponseRecommendations";
import { stubFetch,jsonResponse } from "../../test/renderApp";
import type { Schemas } from "../../api/client";

const ref="fe130e6f-af86-4fc6-89f2-bc76b6cad68b";
const proposal: Schemas["ResponseProposal"]={
  recommendationRef:ref,caseRef:ref,proposedByActorId:1,proposalSource:"system_policy",
  recommendationType:"block_source_ip",targetType:"ip",targetValue:"203.0.113.20",rationale:"Confirmed malicious with source evidence",
  proposalReason:"Reviewed supporting evidence",caseRevision:2,policyVersion:"response-policy-v1",
  evidenceSnapshot:{caseRef:ref,caseRevision:2,finding:{eventId:2,finding:"confirmed_malicious",actorId:1,reason:"Corroborated source",createdAt:"2026-10-31T00:00:00Z"},targetBasis:"primary_source_ip",targetAlert:null,linkEventId:null},
  eventType:"V2_RESPONSE_RECOMMENDED",createdAt:"2026-10-31T00:00:00Z",
};
const pending: Schemas["ResponseView"]={proposal,status:"pending",revision:1,decision:null,executionStatus:"not_executed"};
const current={caseRef:ref,revision:2,snapshot:{detector:{sourceIp:"203.0.113.20"}}} as Schemas["CaseView"];
const empty={items:[],caseRevision:2,page:{limit:50,offset:0,total:0,returned:0}};

describe("Response authorization boundary",()=>{
  it("requires a reason, binds revisions, and retains retry identity after conflict",async()=>{
    const bodies:unknown[]=[];
    stubFetch(async req=>{bodies.push(await req.json());return jsonResponse({error:{code:"RESPONSE_CONFLICT",message:"Refresh case evidence"}},409);});
    render(<ResponseRecommendationCard view={pending} caseRevision={2} canWrite onChange={vi.fn()} />);
    expect(screen.getByRole("button",{name:"Approve"})).toBeDisabled();
    expect(screen.getByRole("button",{name:"Reject"})).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Approval or rejection reason"),"Target verified");
    await userEvent.click(screen.getByRole("button",{name:"Approve"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh case evidence");
    await userEvent.click(screen.getByRole("button",{name:"Approve"}));
    await waitFor(()=>expect(bodies).toHaveLength(2));
    expect(bodies[0]).toEqual(bodies[1]);
    expect(bodies[0]).toMatchObject({expectedCaseRevision:2,expectedRevision:1,reason:"Target verified"});
    expect(bodies[0]).not.toHaveProperty("actorId");
  });

  it("blocks stale approval while allowing explicit rejection",async()=>{
    render(<ResponseRecommendationCard view={pending} caseRevision={3} canWrite onChange={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Approval or rejection reason"),"Evidence superseded");
    expect(screen.getByText("Stale case evidence snapshot")).toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Approve"})).toBeDisabled();
    expect(screen.getByRole("button",{name:"Reject"})).toBeEnabled();
  });

  it.each(["approved","rejected"] as const)("renders immutable %s decision history without mutation controls",status=>{
    const view: Schemas["ResponseView"]={...pending,status,revision:2,decision:{actorId:3,decision:status,reason:"Human decision reason",eventType:"V2_RESPONSE_"+status.toUpperCase(),createdAt:"2026-10-31T01:00:00Z",proposalSnapshot:proposal}};
    render(<ResponseRecommendationCard view={view} caseRevision={2} canWrite onChange={vi.fn()} />);
    expect(screen.getByText(status==="approved"?"Approved - Not Executed":"Rejected")).toBeInTheDocument();
    expect(screen.getByText("Human decision reason")).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Approve"})).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Approval or rejection reason")).not.toBeInTheDocument();
  });

  it("keeps evaluator read-only and shows the execution warning",async()=>{
    stubFetch(()=>jsonResponse({...empty,items:[pending]}));
    render(<ResponseRecommendations current={current} canWrite={false} />);
    expect(await screen.findByText("Pending Human Approval")).toBeInTheDocument();
    expect(screen.getByText("APPROVAL DOES NOT EXECUTE THE ACTION.")).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Approve"})).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Proposal source")).not.toBeInTheDocument();
  });

  it("offers explicit manual source-IP proposals but disables unavailable identity targets",async()=>{
    const bodies:unknown[]=[];
    stubFetch(async req=>{
      if(req.method==="POST") {bodies.push(await req.json());return jsonResponse({response:pending,replayed:false});}
      return jsonResponse(empty);
    });
    render(<ResponseRecommendations current={current} canWrite />);
    expect(await screen.findByRole("button",{name:"Generate recommendation"})).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Proposal source"),"analyst");
    await userEvent.selectOptions(screen.getByLabelText("Recommendation type"),"block_source_ip");
    expect(screen.getByRole("option",{name:/Isolate Host/})).toBeDisabled();
    expect(screen.getByRole("option",{name:/Disable Account/})).toBeDisabled();
    expect(screen.getByLabelText("Target value")).toHaveValue("203.0.113.20");
    await userEvent.type(screen.getByLabelText("Proposal reason"),"Manual corroboration");
    await userEvent.click(screen.getByRole("button",{name:"Create manual recommendation"}));
    await waitFor(()=>expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({recommendationType:"block_source_ip",targetType:"ip",targetValue:"203.0.113.20",reason:"Manual corroboration",expectedCaseRevision:2});
    expect(await screen.findByText("Recommendation recorded; pending human approval.")).toBeInTheDocument();
  });

  it("does not show a false empty success after a failed read",async()=>{
    stubFetch(()=>jsonResponse({error:{code:"OFFLINE",message:"Response ledger unavailable"}},503));
    render(<ResponseRecommendations current={current} canWrite />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Response ledger unavailable");
    expect(screen.queryByText("No response recommendations.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Generate recommendation"})).not.toBeInTheDocument();
  });
});
