import {expect,test,type Page,type Locator} from '@playwright/test';
import {writeFileSync} from 'node:fs';

test('three analysts share work, arbitrate contention, complete and escalate through the real API',async({browser},info)=>{
 test.setTimeout(240000);
 const contexts=await Promise.all([1,2,3,4].map(()=>browser.newContext({baseURL:`http://127.0.0.1:${process.env.HITL_WORK_WEB_PORT??'5202'}`,viewport:{width:1440,height:900}})));
 const [a,b,c,e]=await Promise.all(contexts.map(context=>context.newPage()));
 const tokens=new Map<Page,string>(),errors:string[]=[];
 for(const p of [a,b,c,e]){
  p.on('pageerror',err=>errors.push(err.message));
  p.on('request',r=>{if(r.headers().authorization)tokens.set(p,r.headers().authorization);});
 }
 const get=async(p:Page,path:string)=>{const r=await p.request.get(path,{headers:{Authorization:tokens.get(p)??''}});expect(r.ok(),await r.text()).toBe(true);return r.json();};
 const harness=`http://127.0.0.1:${process.env.HITL_WORK_API_PORT??'8032'}/__work`;
 const refs=await get(a,harness+'/manifest');
 const panel=(p:Page)=>p.getByRole('region',{name:'Human work status',exact:true});
 const workspace=(p:Page)=>p.getByRole('region',{name:'Operational alert workspace',exact:true});
 async function open(p:Page,n:string){await p.goto('/analyst/operations?alertRef='+refs[n]);await expect(workspace(p)).toContainText(refs[n]);await expect(panel(p)).toBeVisible();}
 async function login(p:Page,name:string){
  await p.goto('/login');await p.getByLabel('Username').fill(name);await p.getByLabel('Password',{exact:true}).fill('work-demo');await p.getByRole('button',{name:'Sign in'}).click();await expect(p).not.toHaveURL(/\/login$/);
 }
 const row=(p:Page,n:string)=>p.getByRole('list',{name:'Operational alerts'}).locator(`button[data-alert-ref="${refs[n]}"]`);
 async function claim(p:Page,n:string){await row(p,n).click();await expect(panel(p)).toContainText('Your Access: Owner');}
 async function smoke(p:Page,label:string,control:Locator){
  await expect(p.getByRole('button',{name:/^Total Alerts \d/})).toBeAttached();
  for(const theme of ['light','dark'])for(const width of [1440,1024,390]){
   await p.evaluate(t=>document.documentElement.dataset.theme=t,theme);await p.setViewportSize({width,height:900});
   await control.scrollIntoViewIfNeeded();await expect(control).toBeVisible();
   expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
   await p.screenshot({path:info.outputPath(`${label}-${theme}-${width}.png`)});
  }
  await p.setViewportSize({width:1440,height:900});
 }
 await Promise.all([login(a,'alice'),login(b,'bob'),login(c,'carol'),login(e,'observer')]);
 const before=await get(a,harness+'/proof');
 await Promise.all([open(a,'1'),open(b,'1'),open(c,'1')]);
 await smoke(a,'available',panel(a));
 expect((await get(a,harness+'/proof')).digest).toBe(before.digest);
 await claim(a,'1');await a.reload();await expect(panel(a)).toContainText('Your Access: Owner');
 for(const p of [b,c]){
  await p.getByRole('button',{name:'Refresh operational queue'}).click();await expect(panel(p)).toContainText('Owner: Alice');
  await expect(panel(p)).toContainText('Your Access: Viewer');
  expect(await workspace(p).getByRole('button',{name:'Escalate to Tier 2',exact:true}).count()).toBe(0);
  await workspace(p).getByRole('tab',{name:'Analyst Verdict',exact:true}).click();expect(await workspace(p).getByLabel('Verdict reason').count()).toBe(0);
 }
 await smoke(b,'in-review-other-owner',panel(b));
 // Stage both real browser requests before releasing them together to the server.
 await Promise.all([open(a,'2'),open(b,'2')]);
 let arrived=0;let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
 for(const p of [a,b])await p.route('**/work/claim',async route=>{if(++arrived===2)release();await gate;await route.continue();});
 const responses=[a,b].map(p=>p.waitForResponse(r=>r.url().endsWith('/work/claim')&&r.request().method()==='POST'));
 await Promise.all([a,b].map(p=>row(p,'2').click()));
 const raced=await Promise.all(responses);const raceBodies=await Promise.all(raced.map(r=>r.json()));
 writeFileSync(info.outputPath('race-debug.json'),JSON.stringify({requests:raced.map(r=>({url:r.url(),body:r.request().postDataJSON()})),raceBodies,proof:await get(a,harness+'/proof')},null,2));
 expect(raced.map(r=>r.status())).toEqual([409,409]);expect(raceBodies[0].error.detail.roundRef).toBe(raceBodies[1].error.detail.roundRef);
 for(const p of [a,b]){await p.unroute('**/work/claim');await expect(p.getByRole('alert')).toContainText('Claim Conflict');await expect(workspace(p)).toContainText('Select an operational alert.');}
 const contested=await get(a,harness+'/proof');
 expect(contested.rounds.find((r:any)=>r.status==='contended').owner_actor_id).toBeNull();
 await smoke(a,'claim-conflict',a.getByRole('alert'));
 await open(b,'2');await claim(b,'2');
 const late=await a.request.post(`/api/v2/alerts/${refs['2']}/work/claim`,{headers:{Authorization:tokens.get(a)!},data:{requestId:crypto.randomUUID(),expectedRevision:2}});
 expect(late.status()).toBe(409);expect((await get(b,`/api/v2/alerts/${refs['2']}/work`)).ownerName).toBe('Bob');
 await open(c,'3');await claim(c,'3');
 await workspace(c).getByRole('tab',{name:'Analyst Verdict',exact:true}).click();
 await workspace(c).getByLabel('Verdict outcome').selectOption('expected_activity');await workspace(c).getByLabel('Verdict reason').fill('SYNTHETIC authorized activity independently reviewed by Carol');
 await workspace(c).getByRole('button',{name:'Record Verdict',exact:true}).click();await expect(panel(c)).toContainText('Completed — Reviewed by Carol');
 expect((await get(c,'/api/v2/alerts?workScope=active')).items.some((r:any)=>r.operationalAlertRef===refs['3'])).toBe(false);
 await c.getByRole('tab',{name:/^Completed /}).click();await expect(c.getByRole('list',{name:'Operational alerts'})).toContainText('Completed — Reviewed by Carol');
 await open(c,'3');await smoke(c,'completed-history',panel(c));
 // Explicit correction retains completed status and revises the existing vote.
 await workspace(c).getByRole('tab',{name:'Analyst Verdict',exact:true}).click();
 await workspace(c).getByLabel('Verdict outcome').selectOption('false_positive');await workspace(c).getByLabel('Verdict reason').fill('SYNTHETIC explicit historical correction');
 await workspace(c).getByRole('button',{name:'Correct Verdict',exact:true}).click();await expect(panel(c)).toContainText('false positive');
 await open(a,'4');await claim(a,'4');await workspace(a).getByLabel('Decision reason',{exact:true}).fill('SYNTHETIC analyst requests expert investigation');
 await workspace(a).getByRole('button',{name:'Escalate to Tier 2',exact:true}).click();await expect(panel(a)).toContainText('Escalated — Alice');
 await expect(workspace(a).getByRole('link',{name:'Open Tier 2 Case',exact:true})).toBeVisible();
 await open(c,'6');const beforeUnknown=(await get(c,harness+'/proof')).intents.length;await row(c,'6').click();expect((await get(c,harness+'/proof')).intents).toHaveLength(beforeUnknown);await expect(workspace(c).getByRole('link',{name:'Open Tier 2 Case',exact:true})).toBeVisible();
 const denied=await e.request.post(`/api/v2/alerts/${refs['5']}/work/claim`,{headers:{Authorization:tokens.get(e)!},data:{requestId:crypto.randomUUID(),expectedRevision:0}});expect(denied.status()).toBe(403);
 const proof=await get(a,harness+'/proof');expect(proof.collectionRuns).toBe(0);expect(proof.foreignKeys).toBe(0);expect(proof.verdicts).toBe(2);expect(proof.memoryEvidence).toBe(2);expect(proof.cases).toBe(2);expect(errors).toEqual([]);
 writeFileSync(info.outputPath('multi-user-proof.json'),JSON.stringify({refs,raceBodies,contested,final:proof},null,2));
 await Promise.all(contexts.map(context=>context.close()));
});
