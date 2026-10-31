import {render,screen} from "@testing-library/react";
import {describe,it,expect} from "vitest";
import {TrustedContextPanel} from "./TrustedContextPanel";
import type {Schemas} from "../../api/client";

const base:Schemas["ResolvedTrustedContext"]={
  operationalAlertRef:"00000000-0000-4000-8000-000000000001",evaluatedAt:"2026-10-31T00:00:00Z",
  resolverVersion:"context-resolver-v1",complete:false,context:{assetCriticality:null,knownMaliciousIndicator:null,
    responseRequired:null,confirmedMalicious:null,evidenceConflict:null,repeatedCampaign:null,
    correlatedAlertCount:null,analystEscalated:null,unresolvedByTier1:null},fields:[],
};
const field:Schemas["ResolvedField"]={contextKey:"knownMaliciousIndicator",value:false,status:"trusted",facts:[],
  availableAt:"2026-10-31T00:00:00Z",expiresAt:"2026-10-31T04:00:00Z",explanation:"Explicit scoped negative fact"};

describe("Trusted Context",()=>{
  it("does not render absent provenance as safe",()=>{
    render(<TrustedContextPanel/>);
    expect(screen.getByText("Fact provenance unavailable. Safety context is unknown.")).toBeInTheDocument();
  });
  it("distinguishes explicit false from unknown",()=>{
    render(<TrustedContextPanel context={{...base,fields:[field,{...field,contextKey:"responseRequired",value:null,status:"unknown"}]}}/>);
    expect(screen.getByText("false",{exact:true})).toBeInTheDocument();
    expect(screen.getByText("Unknown",{exact:true})).toBeInTheDocument();
    expect(screen.getByText("Effect: Must Review")).toBeInTheDocument();
  });
  it.each(["expired","conflict","not_applicable"] as const)("shows %s as blocking without mutation controls",status=>{
    render(<TrustedContextPanel context={{...base,fields:[{...field,value:null,status}]}}/>);
    expect(screen.getByText("Effect: Must Review")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
