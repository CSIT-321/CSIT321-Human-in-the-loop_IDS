import { screen,waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe,expect,it } from "vitest";
import { renderApp,stubFetch,jsonResponse } from "../../test/renderApp";
import type { Schemas } from "../../api/client";

const ref="fe130e6f-af86-4fc6-89f2-bc76b6cad68b";
const session={username:"g.ang",displayName:"Analyst",role:"security_analyst" as const,token:"test"};
const empty={items:[],page:{total:0,limit:50,offset:0,returned:0}};
const view: Schemas["MemoryView"]={
  lesson:{decisionSource:"analyst",policyVersion:null,lessonRef:ref,outcome:"expected_activity",humanReason:"Authorised internal vulnerability scanner",scope:"exact",scopeFields:["sourceIp","detectorSource"],
    sourceOperationalAlertRef:ref,sourceCaseRef:null,createdByActorId:1,createdAt:"2026-10-31T00:00:00Z",
    contextSnapshot:{detectorSource:"suricata",detectionTitle:"SSH scan",detectionCategory:"SSH Scan",sourceIp:"10.0.0.50",destinationIp:"10.0.0.20",sourcePort:44444,destinationPort:22,protocol:"TCP",assetCriticality:null,assetIdentifier:null,knownScannerIdentity:null,authorisedActivityType:null,scheduleWindow:null,analystDefinedTag:null},
    configuration:{version:"triage-memory-v1",minimumSupport:3,minimumAgreementRatio:0.67,maximumConflicts:0,defaultValidityDays:30,exactRequiredFields:[],narrowRequiredFields:[]}},
  status:"eligible_for_activation",revision:3,supportCount:3,conflictCount:0,agreementRatio:1,validFrom:null,expiresAt:"2026-11-30T00:00:00Z",lastSupportedAt:"2026-10-31T00:00:00Z",lastConflictAt:null,decision:null,
};

describe("Triage memory",()=>{
  it("distinguishes expert author/contributor, source Case and superseded evidence",async()=>{
    const evidence={sourceKind:"tier2_conclusion",sourceConclusion:{eventId:9,finding:"confirmed_malicious",finalAttackCategory:"web_attack",actorId:1,caseRevision:3},
      conclusionAuthorName:"Expert",contributionActorName:"Contributor",actorId:2,contributionScope:"exact",sourceCaseRef:ref,sourceOperationalAlertRef:ref,outcome:"confirmed_malicious",relation:"conflict",humanReason:"Canonical expert reason"};
    stubFetch(req=>jsonResponse(req.url.includes("/events")?{...empty,items:[{id:4,eventType:"V2_TRIAGE_MEMORY_EXPERT_SUPERSEDED",actorId:2,createdAt:"2026-11-01T00:00:00Z",reason:"Expert correction",evidence,evidenceCurrent:false,lessonSnapshot:view}]}:view));
    renderApp("/analyst/triage-memory?lessonRef="+ref,{session});
    expect(await screen.findByText("Source: Tier 2 Investigation Conclusion")).toBeVisible();
    expect(screen.getByText("Conclusion Author: Expert / #1")).toBeVisible();
    expect(screen.getByText("Memory Contributor: Contributor / #2")).toBeVisible();
    expect(screen.getByText("Human Final Attack Classification: Web Attack")).toBeVisible();
    expect(screen.getByText("Investigation reason: Canonical expert reason")).toBeVisible();
    expect(screen.getByRole("link",{name:"Source Alert"})).toHaveAttribute("href","/analyst/v2-triage?alertRef="+ref);
    expect(screen.getByText("Superseded human evidence — excluded from effective support")).toBeVisible();
    expect(screen.getByRole("link",{name:"Source Case"})).toHaveAttribute("href","/analyst/tier2-cases/"+ref);
  });
  it("lists historical knowledge and keeps guidance advisory",async()=>{
    stubFetch(()=>jsonResponse({...empty,items:[view],page:{...empty.page,total:1}}));
    renderApp("/analyst/triage-memory",{session});
    expect(await screen.findByText("Authorised internal vulnerability scanner")).toBeInTheDocument();
    expect(screen.getByText("Memory guidance only — Human review still required.")).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument();
    expect(screen.getByRole("link",{name:"Review lesson"})).toHaveAttribute("href",expect.stringContaining(ref));
  });

  it("requires a reason and retains idempotency identity on stale activation",async()=>{
    const bodies:unknown[]=[];
    stubFetch(async req=>{
      if(req.method==="POST"){bodies.push(await req.json());return jsonResponse({error:{code:"MEMORY_CONFLICT",message:"Lesson changed; refresh"}},409);}
      return jsonResponse(req.url.includes("/events")?empty:view);
    });
    renderApp("/analyst/triage-memory?lessonRef="+ref,{session});
    const activate=await screen.findByRole("button",{name:"Activate Lesson"});
    expect(activate).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Memory activation or rejection reason"),"Reviewed three source alerts");
    await userEvent.click(activate);
    expect(await screen.findByRole("alert")).toHaveTextContent("Lesson changed");
    await userEvent.click(activate);
    await waitFor(()=>expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual(bodies[0]);
    expect(bodies[0]).toMatchObject({expectedRevision:3,reason:"Reviewed three source alerts"});
    expect(bodies[0]).not.toHaveProperty("actorId");
  });

  it("does not offer activation below the threshold",async()=>{
    stubFetch(req=>jsonResponse(req.url.includes("/events")?empty:{...view,status:"candidate",supportCount:1,revision:1}));
    renderApp("/analyst/triage-memory?lessonRef="+ref,{session});
    await userEvent.type(await screen.findByLabelText("Memory activation or rejection reason"),"Too few supporting alerts");
    expect(screen.getByRole("button",{name:"Activate Lesson"})).toBeDisabled();
    expect(screen.getByRole("button",{name:"Reject Lesson"})).toBeEnabled();
  });

  it("keeps evaluator history read-only",async()=>{
    stubFetch(req=>jsonResponse(req.url.includes("/events")?empty:view));
    renderApp("/evaluator/triage-memory?lessonRef="+ref,{session:{...session,role:"evaluator"}});
    await screen.findByText("Authorised internal vulnerability scanner");
    expect(screen.queryByLabelText("Memory activation or rejection reason")).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Activate Lesson"})).not.toBeInTheDocument();
  });

  it.each(["active","conflict_review","expired","rejected"] as const)("preserves immutable %s history without activation controls",async status=>{
    stubFetch(req=>jsonResponse(req.url.includes("/events")?empty:{...view,status,decision:status==="expired"?null:{action:"activate",actorId:1,reason:"Recorded human approval",createdAt:"2026-10-31T00:00:00Z"}}));
    renderApp("/analyst/triage-memory?lessonRef="+ref,{session});
    expect(await screen.findByText(status.replaceAll("_"," "),{exact:true})).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Activate Lesson"})).not.toBeInTheDocument();
  });

  it("handles empty and failure states distinctly",async()=>{
    stubFetch(()=>jsonResponse(empty));
    const first=renderApp("/analyst/triage-memory",{session});
    expect(await screen.findByText("No triage lessons.")).toBeInTheDocument();
    first.unmount();
    stubFetch(()=>jsonResponse({error:{code:"OFFLINE",message:"Memory database unavailable"}},503));
    renderApp("/analyst/triage-memory",{session});
    expect(await screen.findByRole("alert")).toHaveTextContent("Memory database unavailable");
    expect(screen.queryByText("No triage lessons.")).not.toBeInTheDocument();
  });
});
