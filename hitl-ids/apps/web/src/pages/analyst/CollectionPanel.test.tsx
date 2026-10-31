import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe,it,expect,vi} from "vitest";
import {ContextCollectionForm} from "./CollectionPanel";
import {stubFetch,jsonResponse,renderApp} from "../../test/renderApp";

describe('prospective context collection',()=>{
  it('submits only explicit fields and never submits source or server timestamps',async()=>{
    const bodies:Record<string,unknown>[]=[];
    stubFetch(async req=>{if(req.method==='POST'){bodies.push(await req.json());return jsonResponse({});}return jsonResponse({revision:4});});
    const saved=vi.fn();render(<ContextCollectionForm alertRef="00000000-0000-4000-8000-000000000001" onSaved={saved}/>);
    expect(screen.getByLabelText('Known Malicious Indicator',{exact:true})).toHaveValue('unassessed');
    await userEvent.selectOptions(screen.getByLabelText('Known Malicious Indicator',{exact:true}),'false');
    await userEvent.type(screen.getByLabelText('Structured assessment reason'),'Explicit assessment');
    await userEvent.click(screen.getByRole('button',{name:'Record Safety Assessment'}));
    await waitFor(()=>expect(saved).toHaveBeenCalledOnce());expect(bodies).toHaveLength(1);
    expect(bodies[0]).toMatchObject({value:false,contextKey:'knownMaliciousIndicator',expectedRevision:4});
    for(const field of ['availableAt','recordedAt','actorId','sourceType','sourceSnapshot'])expect(bodies[0]).not.toHaveProperty(field);
  });
  it('keeps the original request revision and identity on uncertain retry',async()=>{
    const bodies:unknown[]=[];let revision=1;
    stubFetch(async req=>{if(req.method==='POST'){bodies.push(await req.json());revision=2;return jsonResponse({error:{code:'UNAVAILABLE',message:'Result uncertain'}},503);}return jsonResponse({revision});});
    render(<ContextCollectionForm alertRef="00000000-0000-4000-8000-000000000001" onSaved={()=>{}}/>);
    await userEvent.selectOptions(screen.getByLabelText('Known Malicious Indicator',{exact:true}),'false');
    await userEvent.type(screen.getByLabelText('Structured assessment reason'),'Explicit assessment');
    await userEvent.click(screen.getByRole('button',{name:'Record Safety Assessment'}));await screen.findByText('Result uncertain');
    await userEvent.click(screen.getByRole('button',{name:'Record Safety Assessment'}));
    await waitFor(()=>expect(bodies).toHaveLength(2));expect(bodies[0]).toEqual(bodies[1]);
  });
  it('keeps evaluator collection management read-only',async()=>{
    stubFetch(req=>req.url.includes('/collection/runs')?jsonResponse({items:[]}):req.url.includes('/metrics')?jsonResponse({totalAlerts:0,eligibleAlerts:0,mustReviewCount:0,recommendedReviewCount:0,noImmediateReviewCount:0,immediateReviewReductionRate:0}):jsonResponse({items:[],page:{total:0}}));
    renderApp('/evaluator/selective-review',{session:{username:'evaluator',displayName:'Evaluator',role:'evaluator',token:'test'}});
    await userEvent.click(screen.getByText('Advanced / Research & Evaluation'));
    await userEvent.click(screen.getByRole('button',{name:'Collection Runs'}));
    expect(screen.queryByRole('button',{name:'Create Draft Run'})).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Holdout start')).not.toBeInTheDocument();
  });
});
