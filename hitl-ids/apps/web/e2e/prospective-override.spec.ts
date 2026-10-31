import {expect,test,type Page} from "@playwright/test";

async function login(page:Page,user:string,password:string){
  await page.goto('/login');await page.getByLabel('Username').fill(user);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Sign in'}).click();
}

test('human overrides survive expired and closed collection runs without changing their ledger',async({page,browser},testInfo)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await login(page,'g.ang','analyst-demo');
  await page.getByRole('link',{name:'Analyst Workspace',exact:true}).click();
  const options=page.locator('#v2-alert option').filter({hasText:'DEMO selective SSH scan'});
  await expect(options).toHaveCount(6);
  const refs=await options.evaluateAll(nodes=>nodes.map(node=>(node as HTMLOptionElement).value));
  for(const ref of refs.slice(0,3)){
    await page.getByLabel('Operational alert',{exact:true}).selectOption(ref);
    await page.getByLabel('Human memory outcome').selectOption('expected_activity');
    await page.getByLabel('Human memory reason').fill('Explicit safe synthetic history for override regression');
    await page.getByRole('button',{name:'Record Human Memory Review'}).click();
    await expect(page.getByRole('link',{name:'Open recorded lesson'})).toBeVisible();
  }
  await page.getByRole('link',{name:'Open recorded lesson'}).click();
  await page.getByLabel('Memory activation or rejection reason').fill('Three independent synthetic reviews agree');
  await page.getByRole('button',{name:'Activate Lesson'}).click();
  await expect(page.getByRole('region',{name:'Triage lesson detail'}).getByText('active',{exact:true})).toBeVisible();
  const section=page.getByRole('region',{name:'Selective Human Review',exact:true});
  const eligible:string[]=[];
  for(const ref of refs.slice(3)){
    await page.goto('/analyst/v2-triage?alertRef='+ref);
    await expect(section.getByText('Must Review',{exact:true})).toBeVisible();
    const current=JSON.parse((await section.locator('details pre').textContent())!);
    if(current.result.disposition==='no_immediate_review')eligible.push(ref);
  }
  expect(eligible.length).toBeGreaterThanOrEqual(2);
  const adminContext=await browser.newContext();const admin=await adminContext.newPage();
  await login(admin,'admin','admin-demo');
  await admin.getByRole('link',{name:'Selective Review',exact:true}).click();
  await admin.getByText('Advanced / Research & Evaluation',{exact:true}).click();
  await admin.getByRole('button',{name:'Collection Runs',exact:true}).click();
  const start=Date.now()+10000,end=start+20000,cutoff=end+20000;
  await admin.getByLabel('Protocol version',{exact:true}).fill('synthetic-override-boundaries');
  await admin.getByLabel('Readiness PASS review reference').fill('SYNTHETIC disposable regression only, not study authorization');
  await admin.getByLabel('Holdout start').fill(new Date(start).toISOString());
  await admin.getByLabel('Holdout end').fill(new Date(end).toISOString());
  await admin.getByLabel('Outcome cutoff').fill(new Date(cutoff).toISOString());
  const createdResponse=admin.waitForResponse(r=>r.url().endsWith('/collection/runs')&&r.request().method()==='POST');
  await admin.getByRole('button',{name:'Create Draft Run'}).click();
  const created=await (await createdResponse).json();
  const run=admin.getByRole('article',{name:'synthetic-override-boundaries'});
  await run.getByRole('button',{name:'Open Run',exact:true}).click();
  await expect(run.getByText('Status: open',{exact:true})).toBeVisible();
  await expect.poll(()=>Date.now(),{timeout:15000}).toBeGreaterThan(start);
  async function select(ref:string){
    await page.goto('/analyst/v2-triage?alertRef='+ref);
    await page.getByText('Advanced / Research & Evaluation',{exact:true}).click();
    await page.getByRole('button',{name:'Prospective Collection',exact:true}).click();
    await page.getByLabel('Collection run',{exact:true}).selectOption(created.runRef);
    await expect(page.getByText(/Protocol: synthetic-override-boundaries/)).toBeVisible();
  }
  for(const ref of eligible.slice(0,2)){
    await select(ref);
    await page.getByLabel('Review policy or override reason').fill('Record synthetic deferral during the actual decision window');
    await page.getByRole('button',{name:'Evaluate Review Policy',exact:true}).click();
    await expect(section.getByText('No Immediate Review',{exact:true})).toBeVisible();
    await expect(page.getByText('Persisted disposition: no_immediate_review',{exact:true})).toBeVisible();
  }
  async function archive(){
    const response=admin.waitForResponse(r=>r.url().endsWith('/'+created.runRef+'/export'));
    await run.getByRole('button',{name:'Inspect Export',exact:true}).click();return (await response).json();
  }
  const ledger=(a:any)=>({run:a.run,decisions:a.decisions,observations:a.observations,runEvents:a.runEvents});
  await expect.poll(()=>Date.now(),{timeout:30000}).toBeGreaterThan(end);
  const expiredBefore=await archive();
  async function override(ref:string,reason:string,notice:string){
    await select(ref);
    await expect(section.getByText('No Immediate Review',{exact:true})).toBeVisible();
    await page.getByLabel('Review policy or override reason').fill(reason);
    await page.getByRole('button',{name:'Require Human Review',exact:true}).click();
    await expect(page.getByText('Human review required',{exact:true})).toBeVisible();
    await expect(page.getByText(notice,{exact:true})).toBeVisible();
    await page.reload();
    await expect(section.getByText('Must Review',{exact:true})).toBeVisible();
    await expect(page.getByText('Human review required',{exact:true})).toBeVisible();
    await expect(page.getByText(notice,{exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Review decision history',exact:true}).click();
    await expect(page.getByRole('region',{name:'Review audit history'}).getByText(reason,{exact:true})).toBeVisible();
  }
  await override(eligible[0],'Human override after holdout end','Not recorded in selected collection run because the holdout window has ended.');
  const expiredAfter=await archive();expect(ledger(expiredAfter)).toEqual(ledger(expiredBefore));
  expect(expiredAfter.reviewEvents.some((e:any)=>e.alertRef===eligible[0]&&e.action==='require_review')).toBe(true);
  await expect.poll(()=>Date.now(),{timeout:30000}).toBeGreaterThan(cutoff);
  await admin.getByRole('button',{name:'Refresh Runs',exact:true}).click();
  await expect(run.getByText('Recorded decisions: 2')).toBeVisible();
  await run.getByRole('button',{name:'Close Run',exact:true}).click();
  await expect(run.getByText('Status: closed',{exact:true})).toBeVisible();
  const closedBefore=await archive();
  await override(eligible[1],'Human override after run closure','Not recorded in selected collection run because the run is closed.');
  const closedAfter=await archive();expect(ledger(closedAfter)).toEqual(ledger(closedBefore));
  expect(closedAfter.reviewEvents.some((e:any)=>e.alertRef===eligible[1]&&e.action==='require_review')).toBe(true);
  await page.getByText('Human review required',{exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('override-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await page.getByText('Human review required',{exact:true}).scrollIntoViewIfNeeded();
  expect(await page.locator('main').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await expect(page.getByText('Not recorded in selected collection run because the run is closed.',{exact:true})).toBeVisible();
  await page.screenshot({path:testInfo.outputPath('override-mobile.png')});
  expect(errors).toEqual([]);await adminContext.close();
});
