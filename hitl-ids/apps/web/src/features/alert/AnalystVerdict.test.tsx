import { render,screen,within,waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe,it,expect } from "vitest";
import { stubFetch,jsonResponse } from "../../test/renderApp";
import { AnalystVerdictPanel,AnalystVerdictHistory } from "./AnalystVerdict";

const ref="00000000-0000-4000-8000-000000000001";
const initial={operationalAlertRef:ref,sourceStateVersion:"a".repeat(64),revision:0,canRecord:true,latest:null};
describe("canonical Analyst Verdict",()=>{
  it("requires reason, saves a human conclusion, corrects with a new revision and displays both historical events",async()=>{
    let current:Record<string,unknown>={...initial};const history:Record<string,unknown>[]=[];const bodies:Record<string,unknown>[]=[];
    stubFetch(async request=>{
      if(request.method==="POST") {
        const body=await request.json();bodies.push(body);
        const verdict={verdictRef:crypto.randomUUID(),operationalAlertRef:ref,revision:history.length+1,
          actorName:"Reviewer",actorId:1,outcome:body.outcome,reason:body.reason,createdAt:"2026-11-01T12:00:00Z",supersedesRef:history[0]?.verdictRef??null};
        history.unshift(verdict);current={...initial,revision:history.length,latest:verdict};return jsonResponse({verdict,replayed:false});
      }
      return jsonResponse(request.url.includes("verdict-history")?{items:history,total:history.length,limit:50,offset:0}:current);
    });
    const panel=render(<AnalystVerdictPanel alertRef={ref} stateVersion="a"/>);
    expect(await screen.findByText("Not recorded",{exact:true})).toBeVisible();
    expect(screen.getByRole("button",{name:/^Record Verdict$/})).toBeDisabled();
    expect(screen.getAllByRole("option").map(option=>option.textContent)).toEqual(["Confirmed Malicious","Suspicious","Expected Activity","False Positive"]);
    await userEvent.type(screen.getByLabelText("Verdict reason"),"Initial evidence assessment");
    await userEvent.click(screen.getByRole("button",{name:/^Record Verdict$/}));
    expect(await screen.findByText("Recorded by: Reviewer",{exact:false})).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText("Verdict outcome"),"false_positive");
    await userEvent.type(screen.getByLabelText("Verdict reason"),"Correction after checking context");
    await userEvent.click(screen.getByRole("button",{name:/^Correct Verdict$/}));
    await waitFor(()=>expect(bodies).toHaveLength(2));
    expect(bodies[0]).toMatchObject({expectedRevision:0,outcome:"suspicious"});
    expect(bodies[1]).toMatchObject({expectedRevision:1,outcome:"false_positive"});
    expect(bodies[1]!.requestId).not.toBe(bodies[0]!.requestId);
    panel.unmount();render(<AnalystVerdictHistory alertRef={ref}/>);
    const region=screen.getByRole("region",{name:"Analyst Verdict History"});
    expect(await within(region).findByText("False Positive",{exact:true})).toBeVisible();
    expect(within(region).getByText("Suspicious",{exact:true})).toBeVisible();
    expect(within(region).getByText("Initial evidence assessment")).toBeVisible();
  });
  it("retains exact retry identity after network uncertainty and displays conflict feedback",async()=>{
    const bodies:unknown[]=[];
    stubFetch(async request=>{
      if(request.method==="POST"){bodies.push(await request.json());return jsonResponse({error:{code:"VERDICT_CONFLICT",message:"Refresh before recording"}},409);}
      return jsonResponse(initial);
    });
    render(<AnalystVerdictPanel alertRef={ref} stateVersion="a"/>);
    await userEvent.type(await screen.findByLabelText("Verdict reason"),"Human assessment");
    for(let i=0;i<2;i++){await userEvent.click(screen.getByRole("button",{name:/^Record Verdict$/}));await screen.findByRole("alert");}
    expect(bodies).toHaveLength(2);expect(bodies[0]).toEqual(bodies[1]);
  });
  it("shows auto Tier 2 as requiring no Tier 1 verdict and exposes no editing controls",async()=>{
    stubFetch(()=>jsonResponse({...initial,canRecord:false}));
    render(<AnalystVerdictPanel alertRef={ref} stateVersion="a"/>);
    expect(await screen.findByText(/no Tier 1 Verdict is required/)).toBeVisible();
    expect(screen.queryByLabelText("Verdict reason")).toBeNull();
    expect(screen.getByText("Not recorded",{exact:true})).toBeVisible();
  });
});
