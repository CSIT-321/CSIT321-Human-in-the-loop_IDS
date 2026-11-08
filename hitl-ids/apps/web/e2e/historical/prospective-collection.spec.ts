import {expect,test,type Page} from "@playwright/test";
import {spawnSync} from "node:child_process";
import path from "node:path";

async function login(page:Page,user:string,password:string){
  await page.goto('/login');await page.getByLabel('Username').fill(user);
  await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in'}).click();
}

test('authenticated UI collection uses actual decisions and survives post-window history',async({page,browser},testInfo)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await login(page,'g.ang','analyst-demo');
  await page.getByRole('link',{name:'Incoming Alerts'}).click();
  const option=page.locator('#external-alert option').filter({hasText:'SYNTHETIC prospective collection'});
  await expect(option).toHaveCount(1);
  await page.getByLabel('Staged alert').selectOption((await option.getAttribute('value'))!);
  await page.getByLabel('Eligibility decision').selectOption('accepted');
  await page.getByLabel('Decision reason').fill('Synthetic disposable fixture identity verified');
  await page.getByRole('button',{name:'Record eligibility review'}).click();
  await expect(page.getByRole('status')).toContainText('Eligibility decision recorded');
  await page.getByLabel('Decision reason').fill('Human-authorized synthetic operational admission');
  await page.getByRole('button',{name:'Admit to HITL Workflow'}).click();
  await expect(page.getByRole('status')).toContainText('Operational admission completed');
  await page.getByRole('link',{name:'Open Alert Triage'}).click();
  await page.getByRole('button',{name:'Add Trusted Context',exact:true}).click();
  const form=page.getByRole('region',{name:'Collect structured safety context'});
  await form.getByLabel('Asset Criticality',{exact:true}).selectOption('low');
  await form.getByLabel('Correlated Alert Count',{exact:true}).fill('1');
  for(const label of ['Known Malicious Indicator','Response Required','Confirmed Malicious','Evidence Conflict','Repeated Campaign','Analyst Escalated','Unresolved By Tier1']){
    await form.getByLabel(label,{exact:true}).selectOption('false');
  }
  await form.getByLabel('Structured assessment reason').fill('Explicit safe synthetic context, independently assessed after admission');
  await form.getByRole('button',{name:'Record Safety Assessment'}).click();
  await expect(page.getByRole('region',{name:'Trusted Context / Safety Evidence'}).getByText('Status: trusted',{exact:true})).toHaveCount(9);
    await page.getByText('Advanced / Research & Evaluation',{exact:true}).click();
  await page.getByRole('button',{name:'Prospective Collection',exact:true}).click();
  const adminContext=await browser.newContext();const admin=await adminContext.newPage();
  await login(admin,'admin','admin-demo');await admin.getByRole('link',{name:'Selective Review',exact:true}).click();
  await admin.getByText('Advanced / Research & Evaluation',{exact:true}).click();
  await admin.getByRole('button',{name:'Collection Runs',exact:true}).click();
  const start=Date.now()+12000,end=start+25000,cutoff=end+12000;
  await admin.getByLabel('Protocol version',{exact:true}).fill('synthetic-browser-prospective-v2');
  await admin.getByLabel('Readiness PASS review reference').fill('SYNTHETIC automated exercise only; not registered production collection');
  await admin.getByLabel('Holdout start').fill(new Date(start).toISOString());
  await admin.getByLabel('Holdout end').fill(new Date(end).toISOString());
  await admin.getByLabel('Outcome cutoff').fill(new Date(cutoff).toISOString());
  const creation=admin.waitForResponse(r=>r.url().endsWith('/api/v2/collection/runs')&&r.request().method()==='POST');
  await admin.getByRole('button',{name:'Create Draft Run'}).click();const created=await (await creation).json();
  const run=admin.getByRole('article',{name:'synthetic-browser-prospective-v2'});
  await run.getByRole('button',{name:'Open Run',exact:true}).click();await expect(run.getByText('Status: open',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Refresh Collection',exact:true}).click();
  await page.getByLabel('Collection run',{exact:true}).selectOption(created.runRef);
  await expect(page.getByText(/Protocol: synthetic-browser-prospective-v2/)).toBeVisible();
  await expect.poll(()=>Date.now(),{timeout:20000}).toBeGreaterThan(start);
  await page.getByLabel('Review policy or override reason').fill('Record actual prospective decision with post-occurrence context');
  const before=Date.now();
  const response=page.waitForResponse(r=>r.url().endsWith('/selective-review/evaluate')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Evaluate Review Policy',exact:true}).click();
  expect((await response).status()).toBe(200);const after=Date.now();
  const collected=page.getByRole('region',{name:'Prospective decision collection'});
  await expect(collected.getByText('Persisted disposition: must_review',{exact:true})).toBeVisible();
  await expect(collected.getByText('Outcome: Pending',{exact:true})).toBeVisible();
  await page.getByLabel('Human memory outcome').selectOption('expected_activity');
  await page.getByLabel('Human memory reason').fill('Later human investigation completed for synthetic fixture');
  await page.getByRole('button',{name:'Record Human Memory Review'}).click();
  await expect(page.getByRole('link',{name:'Open recorded lesson'})).toBeVisible();
  await page.getByRole('button',{name:'Refresh Collection',exact:true}).click();
  await expect(collected.getByText('Outcome: Completed',{exact:true})).toBeVisible();
  await collected.getByLabel('Analyst review seconds').fill('8');await collected.getByLabel('Total task seconds').fill('15');
  await collected.getByLabel('Task observation notes').fill('Proxy/student analyst synthetic timed task');
  await collected.getByRole('button',{name:'Record Task Observation'}).click();
  await expect(collected.getByLabel('Task observation notes')).toHaveValue('');
  await collected.evaluate(e=>e.scrollIntoView({block:'start'}));
  await page.screenshot({path:testInfo.outputPath('prospective-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await collected.evaluate(e=>e.scrollIntoView({block:'start'}));
  await page.screenshot({path:testInfo.outputPath('prospective-mobile.png'),fullPage:true});
  expect(await page.locator('main').evaluate(e=>e.scrollWidth<=e.clientWidth)).toBe(true);
  await expect.poll(()=>Date.now(),{timeout:60000,intervals:[500,1000]}).toBeGreaterThan(cutoff);
  await admin.getByRole('button',{name:'Refresh Runs',exact:true}).click();
  await expect(run.getByText('Recorded decisions: 1')).toBeVisible();
  await run.getByRole('button',{name:'Close Run',exact:true}).click();await expect(run.getByText('Status: closed',{exact:true})).toBeVisible();
  const exportResponse=admin.waitForResponse(r=>r.url().endsWith('/export'));
  await run.getByRole('button',{name:'Inspect Export',exact:true}).click();const archive=await (await exportResponse).json();
  expect(archive.decisions).toHaveLength(1);const decision=archive.decisions[0];
  expect(Date.parse(decision.decisionAt)).toBeGreaterThanOrEqual(before);expect(Date.parse(decision.decisionAt)).toBeLessThanOrEqual(after);
  expect(Date.parse(decision.alertOccurredAt)).toBeLessThan(Date.parse(decision.operationalAdmittedAt));
  expect(Date.parse(decision.reviewEligibleAt)).toBeLessThanOrEqual(Date.parse(decision.decisionAt));
  expect(archive.outcomes.some((o:{alertRef:string;availableAt:string})=>o.alertRef===decision.operationalAlertRef&&Date.parse(o.availableAt)>Date.parse(decision.decisionAt))).toBe(true);
  const reportResponse=admin.waitForResponse(r=>r.url().endsWith('/report'));
  await run.getByRole('button',{name:'Evaluate Recorded Collection',exact:true}).click();const report=(await (await reportResponse).json()).payload;
  expect(report.evaluationMode).toBe('prospective_recorded');expect(report.eligibleAlerts).toBe(1);expect(report.outcomeCompleteness).toBe(1);
  expect(report.decisions[0].decisionAt).toBe(decision.decisionAt.replace('Z','+00:00'));
  expect(report.workload.measuredAnalystTimeReduction).toBeNull();
  const evaluate=(input:unknown)=>{
    const result=spawnSync(process.env.HITL_PYTHON??'python',['-B','-c','import sys; from packages.evaluation.prospective_recorded import RecordedArchive,evaluate_recorded; from packages.detection.prospective_collection import canonical; print(canonical(evaluate_recorded(RecordedArchive.model_validate_json(sys.stdin.read()))))'],{cwd:path.resolve('../..'),input:JSON.stringify(input),encoding:'utf8'});
    expect(result.status,result.stderr).toBe(0);return result.stdout;
  };
  const frozen=evaluate(archive);
  const future=structuredClone(archive),at=new Date().toISOString();
  const fact={...future.unrelatedHistory.contextFacts[0],factRef:crypto.randomUUID(),id:null,sourceType:'synthetic_fixture',createdByActorId:null,
    sourceSnapshot:{synthetic:true},observedAt:at,availableAt:at,recordedAt:at,validFrom:at,expiresAt:new Date(Date.now()+3600000).toISOString(),
    freshnessPolicy:{...future.unrelatedHistory.contextFacts[0].freshnessPolicy,version:'future-v2'}};
  future.unrelatedHistory.contextFacts.push(fact);
  future.unrelatedHistory.policies=[{effectiveAt:at,availableAt:at,configuration:{...archive.run.protocol.selectivePolicy,version:'future-v2'}}];
  expect(evaluate(future)).toBe(frozen);
  expect(errors).toEqual([]);await adminContext.close();
});
