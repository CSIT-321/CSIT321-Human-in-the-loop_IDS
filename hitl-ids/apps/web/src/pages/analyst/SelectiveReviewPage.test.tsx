import {screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe,expect,it} from "vitest";
import {renderApp,stubFetch,jsonResponse} from "../../test/renderApp";

const ref="fe130e6f-af86-4fc6-89f2-bc76b6cad68b";
const session={username:"g.ang",displayName:"Analyst",role:"security_analyst" as const,token:"test"};
const empty={items:[],page:{total:0,limit:50,offset:0,returned:0}};
const routing={operationalAlertRef:ref,title:"Selective demo",detectorName:"Suricata",stateVersion:"a".repeat(64),reviewReasons:[],latestDecision:null,allowedActions:[],
  state:{operationalPriority:85,priorityBand:"P1",reviewRequired:true,handlingRoute:"tier1_review",workflowStage:"triage",tier2Recommended:false,tier2RecommendationReasons:[]}};
const view={operationalAlertRef:ref,title:"Selective demo",version:"b".repeat(64),disposition:"no_immediate_review",reasonCodes:["VALIDATED_MEMORY_AND_CONTEXT"],explanation:"All safety gates passed",priority:85,route:"tier1_review",humanOverride:false,eligibleAlert:true,recalled:false,lastDecision:null,
  policyEvaluation:{inputs:{matches:[]},result:{policyVersion:"selective-review-v1",matchedLessonRef:null}}};
function reads(req:Request){
  if(req.url.includes("/triage-state"))return jsonResponse(routing);
  if(req.url.includes("/matches")||req.url.includes("/events"))return jsonResponse(empty);
  return jsonResponse(view);
}

describe("Selective Human Review",()=>{
  it("separates automation from verdict and preserves displayed priority",async()=>{
    stubFetch(reads);renderApp("/analyst/v2-triage?alertRef="+ref,{session});
    expect(await screen.findByText("No Immediate Review",{exact:true})).toBeInTheDocument();
    expect(screen.getByText("No Immediate Review is an automation decision, not a human verdict.")).toBeInTheDocument();
    expect(screen.getByText("Operational priority: 85")).toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Require Human Review"})).toBeDisabled();
  });

  it("binds override to reason and revision and retains retry identity",async()=>{
    const bodies:unknown[]=[];
    stubFetch(async req=>{if(req.method==="POST"){bodies.push(await req.json());return jsonResponse({error:{code:"REVIEW_CONFLICT",message:"Evidence changed; refresh"}},409);}return reads(req);});
    renderApp("/analyst/v2-triage?alertRef="+ref,{session});
    await userEvent.type(await screen.findByLabelText("Review policy or override reason"),"Analyst requires investigation");
    await userEvent.click(screen.getByRole("button",{name:"Require Human Review"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Evidence changed");
    await userEvent.click(screen.getByRole("button",{name:"Require Human Review"}));
    await waitFor(()=>expect(bodies).toHaveLength(2));
    expect(bodies[0]).toEqual(bodies[1]);
    expect(bodies[0]).toMatchObject({expectedVersion:view.version,reason:"Analyst requires investigation"});
    expect(bodies[0]).not.toHaveProperty("context");expect(bodies[0]).not.toHaveProperty("actorId");
  });

  it("evaluator reads policy but cannot mutate",async()=>{
    stubFetch(reads);renderApp("/evaluator/v2-triage?alertRef="+ref,{session:{...session,role:"evaluator"}});
    await screen.findByText("No Immediate Review",{exact:true});
    expect(screen.queryByLabelText("Review policy or override reason")).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Require Human Review"})).not.toBeInTheDocument();
  });

  it("allows human override with a closed collection and explains skipped recording",async()=>{
    const runRef="00000000-0000-4000-8000-000000000002";
    const run={runRef,status:"closed",revision:3,protocol:{registration:{protocolVersion:"closed-demo",evidenceBasis:"synthetic/demo"}}};
    let overridden=false;const bodies:unknown[]=[];
    stubFetch(async req=>{
      if(req.method==="POST"){bodies.push(await req.json());overridden=true;return jsonResponse({});}
      if(req.url.includes("/collection/runs")&&req.url.endsWith("/export"))return jsonResponse({run,decisions:[],outcomes:[]});
      if(req.url.endsWith("/collection/runs"))return jsonResponse({items:[run]});
      if(req.url.endsWith("/selective-review")&&overridden)return jsonResponse({...view,disposition:"must_review",humanOverride:true,
        lastDecision:{action:"require_review",snapshot:view.policyEvaluation,collectionRecording:{runRef,status:"not_recorded",reason:"the run is closed"}}});
      return reads(req);
    });
    renderApp("/analyst/v2-triage?alertRef="+ref,{session});
    await screen.findByText("No Immediate Review",{exact:true});
    await userEvent.click(screen.getByRole("button",{name:"Prospective Collection"}));
    await screen.findByRole("option",{name:/closed-demo/});
    await userEvent.selectOptions(screen.getByLabelText("Collection run"),runRef);
    await screen.findByText(/Protocol: closed-demo/);
    await userEvent.type(screen.getByLabelText("Review policy or override reason"),"Safety review after collection closure");
    expect(screen.getByRole("button",{name:"Evaluate Review Policy"})).toBeDisabled();
    await userEvent.click(screen.getByRole("button",{name:"Require Human Review"}));
    expect(await screen.findByText("Human review required",{exact:true})).toBeVisible();
    expect(screen.getByText("Not recorded in selected collection run because the run is closed.")).toBeVisible();
    expect(bodies[0]).toMatchObject({collectionRunRef:runRef,expectedRunRevision:3});
  });

  it("shows recall and does not offer repeat override",async()=>{
    stubFetch(req=>req.url.endsWith("/selective-review")?jsonResponse({...view,disposition:"must_review",recalled:true,humanOverride:true,reasonCodes:["HUMAN_REVIEW_OVERRIDE"]}):reads(req));
    renderApp("/analyst/v2-triage?alertRef="+ref,{session});
    expect(await screen.findByText("Prior deferral recalled")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Review policy or override reason"),"Repeat");
    expect(screen.getByRole("button",{name:"Require Human Review"})).toBeDisabled();
  });

  it("filters deferred alerts without hiding the queue and displays metrics",async()=>{
    const seen=stubFetch(req=>req.url.includes("/metrics")?jsonResponse({totalAlerts:6,eligibleAlerts:6,mustReviewCount:5,recommendedReviewCount:0,noImmediateReviewCount:1,immediateReviewReductionRate:1/6,unsafeSuppressionCount:0,conflictTriggeredRecallCount:0,sampledOverrideCount:0,dataBasis:"Fixture data only"}):jsonResponse({...empty,items:[view],page:{...empty.page,total:1}}));
    renderApp("/analyst/selective-review",{session});
    expect(await screen.findByText("16.7%")).toBeInTheDocument();
    expect(screen.getByText("Fixture data only")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab",{name:"No Immediate Review"}));
    await waitFor(()=>expect(seen.some(req=>req.url.includes("disposition=no_immediate_review"))).toBe(true));
    expect(await screen.findByRole("link",{name:"Selective demo"})).toHaveAttribute("href",expect.stringContaining(ref));
  });

  it("reports unavailable policy instead of a safe disposition",async()=>{
    stubFetch(req=>req.url.endsWith("/selective-review")?jsonResponse({error:{code:"OFFLINE",message:"Review policy unavailable"}},503):reads(req));
    renderApp("/analyst/v2-triage?alertRef="+ref,{session});
    expect(await screen.findByRole("alert")).toHaveTextContent("Review policy unavailable");
    expect(screen.queryByText("No Immediate Review",{exact:true})).not.toBeInTheDocument();
  });
});
