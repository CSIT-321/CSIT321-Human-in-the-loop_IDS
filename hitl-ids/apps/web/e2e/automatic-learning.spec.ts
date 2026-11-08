import {expect,test} from "@playwright/test";

test("canonical UI judgments automatically learn, activate, reduce review, and withdraw on conflict",async({page},info)=>{
 test.setTimeout(120000);
 let authorization="";const writes:string[]=[];const errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{authorization=r.headers().authorization??authorization;if(r.method()==='POST')writes.push(new URL(r.url()).pathname);});
 await page.goto('/login');await page.getByLabel('Username').fill('g.ang');await page.getByLabel('Password',{exact:true}).fill('analyst-demo');await page.getByRole('button',{name:'Sign in'}).click();
 await expect(page).toHaveURL(/\/analyst\/operations$/);
 // Take the token from the stored session (set at sign-in). Copying it from the first signed-in request raced:
 // the URL can change before any API request is sent, so get() ran with an empty token and got 401.
 authorization='Bearer '+await page.evaluate(()=>JSON.parse(sessionStorage.getItem('hitl-ids.session.v1')??'{}').token);
 expect(authorization).not.toBe('Bearer undefined');
 const get=async(path:string)=>(await page.request.get(path,{headers:{Authorization:authorization}})).json();
 const all=await get('/api/v2/alerts?limit=200&q=automatic%20learning');const refs=all.items.map((a:{operationalAlertRef:string})=>a.operationalAlertRef);
 expect(refs).toHaveLength(6);
 const detail=page.getByRole('region',{name:'Operational alert workspace',exact:true});
 async function open(ref:string){await page.goto('/analyst/operations?view=all&q='+ref+'&alertRef='+ref);await expect(detail).toBeVisible();}
 // A Tier 1 Verdict needs the analyst to own the alert (claim rule, 24d43c5); a row click claims it, as in final-golden-path.
 async function claim(ref:string){await page.getByRole('list',{name:'Operational alerts'}).locator(`button[data-alert-ref="${ref}"]`).click();await expect(detail.getByRole('region',{name:'Human work status'})).toContainText('Your Access: Owner');}
 async function judgment(ref:string,outcome:string){
  await open(ref);await claim(ref);await detail.getByRole('tab',{name:'Analyst Verdict',exact:true}).click();
  const panel=detail.getByRole('region',{name:'Analyst Verdict',exact:true});
  await panel.getByLabel('Verdict outcome').selectOption(outcome);await panel.getByLabel('Verdict reason').fill('SYNTHETIC browser human judgment '+outcome);
  await panel.getByRole('button',{name:'Record Verdict',exact:true}).click();await expect(panel).toContainText('Revision 1');
 }
 for(let i=0;i<3;i++){
  await judgment(refs[i], 'expected_activity');
  const state=await get(`/api/v2/alerts/${refs[i]}/triage-memory/verdict-state`);
  expect(state.decisionSource).toBe('system_policy');expect(state.memory.supportCount).toBe(i+1);expect(state.memory.status).toBe(i===2?'active':'candidate');
 }
 const state=await get(`/api/v2/alerts/${refs[2]}/triage-memory/verdict-state`);
 expect(state.memory.decision.actorId).toBeNull();expect(state.memory.decision.policyVersion).toBe('safe-memory-auto-activation-v1');
 expect(Date.parse(state.memory.expiresAt)-Date.parse(state.memory.validFrom)).toBe(30*86400000);
 async function evaluate(ref:string){
  await open(ref);await detail.getByRole('tab',{name:'Context & Review',exact:true}).click();
  const panel=page.getByRole('region',{name:'Selective Human Review',exact:true});
  await panel.getByLabel('Review policy or override reason').fill('SYNTHETIC evaluate independent safety gate');
  await panel.getByRole('button',{name:'Evaluate Review Policy'}).click();
  await expect.poll(async()=>(await get(`/api/v2/alerts/${ref}/selective-review`)).lastDecision).not.toBeNull();
 }
 await evaluate(refs[3]);expect((await get(`/api/v2/alerts/${refs[3]}/selective-review`)).disposition).toBe('no_immediate_review');
 await page.goto('/analyst/triage-memory?lessonRef='+state.lessonRef);
 await expect(page.getByText(/Auto-activated by System Policy/)).toBeVisible();
 for(const theme of ['light','dark'])for(const width of [1440,1024,390]){
  await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);await page.setViewportSize({width,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.screenshot({path:info.outputPath(`memory-${theme}-${width}.png`),fullPage:true});
 }
 await judgment(refs[4],'confirmed_malicious');
 const withdrawn=await get(`/api/v2/alerts/${refs[0]}/triage-memory/verdict-state`);
 expect(withdrawn.memory.status).toBe('conflict_review');expect(withdrawn.memory.conflictCount).toBe(1);
 expect((await get(`/api/v2/alerts/${refs[3]}/selective-review`)).disposition).toBe('must_review');
 await evaluate(refs[5]);expect((await get(`/api/v2/alerts/${refs[5]}/selective-review`)).disposition).toBe('must_review');
 const expiredAlerts=await get('/api/v2/alerts?limit=200&q=expired%20learning');
 let expiredLesson="";let futureExpired="";
 for(const alert of expiredAlerts.items){
  const s=await get(`/api/v2/alerts/${alert.operationalAlertRef}/triage-memory/verdict-state`);
  if(s.memory){expect(s.memory.status).toBe('expired');expiredLesson=s.lessonRef;}
  else futureExpired=alert.operationalAlertRef;
 }
 expect(expiredLesson).not.toBe('');expect(futureExpired).not.toBe('');
 await page.goto('/analyst/triage-memory?lessonRef='+expiredLesson);
 await expect(page.getByText('expired',{exact:true})).toBeVisible();
 await evaluate(futureExpired);expect((await get(`/api/v2/alerts/${futureExpired}/selective-review`)).disposition).toBe('must_review');
 expect(writes.filter(p=>/from-verdict|from-conclusion|\/activate|\/collection/.test(p))).toEqual([]);
 expect(errors).toEqual([]);
});
