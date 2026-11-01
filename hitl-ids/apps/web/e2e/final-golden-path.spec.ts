import {expect,test,type Locator} from '@playwright/test';
import {writeFileSync} from 'node:fs';

test('FINAL coherent Golden Path: staged correlated EVE → human learning → safe review → investigation → resolution',async({page},info)=>{
 test.setTimeout(300000);page.setDefaultTimeout(15000);
 let authorization='';const writes:string[]=[];const errors:string[]=[];const evidence:Record<string,any>={};
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(r.url().includes('/api/'))authorization=r.headers().authorization??authorization;if(r.method()==='POST')writes.push(new URL(r.url()).pathname);});
 const get=async(path:string)=>{const r=await page.request.get(path,{headers:{Authorization:authorization}});expect(r.ok(),await r.text()).toBe(true);return r.json();};
 const post=async(path:string,data:unknown,status=200)=>{const r=await page.request.post(path,{headers:{Authorization:authorization},data});expect(r.status(),await r.text()).toBe(status);return r.json();};
 const harness='http://127.0.0.1:8030/__golden';
 const manifest=await get(harness+'/manifest');const refs:Record<string,string>={};
 const workspace=page.getByRole('region',{name:'Operational alert workspace',exact:true});
 const rail=page.getByRole('complementary',{name:'Context and assistance'});
 const workload=page.getByRole('region',{name:'Operational workload'});
 const verdict=workspace.getByRole('region',{name:'Analyst Verdict',exact:true});
 const expert=page.getByRole('region',{name:'Expert Human Learning',exact:true});
 const summary=page.getByRole('region',{name:'Case summary',exact:true});
 const resolution=page.getByRole('region',{name:'Case Resolution',exact:true});
 const responses=page.getByRole('region',{name:'Response Recommendations',exact:true});
 async function login(user='g.ang',password='analyst-demo'){
  await page.goto('/login');await page.getByLabel('Username').fill(user);await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in'}).click();await expect(page).not.toHaveURL(/\/login$/);
 }
 async function open(name:string){await page.goto('/analyst/operations?alertRef='+refs[name]);await expect(workspace).toContainText(refs[name]);}
 async function smoke(label:string,control:Locator){
  for(const theme of ['light','dark'])for(const width of [1440,1024,390]){
   await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);await page.setViewportSize({width,height:900});
   await control.scrollIntoViewIfNeeded();await expect(control).toBeVisible();await expect(control).toBeEnabled();
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
   await page.screenshot({path:info.outputPath(`${label}-${theme}-${width}.png`)});
  }
  await page.setViewportSize({width:1440,height:900});
 }
 async function admit(name:string){
  console.log('Golden intake',name);
  await page.goto('/analyst/external-admission');
  await page.getByLabel('Staged alert').selectOption(String(manifest[name].inboxId));
  await page.getByLabel('Eligibility decision').selectOption('accepted');await page.getByLabel('Decision reason').fill('SYNTHETIC Golden source and correlation checked');
  await page.getByRole('button',{name:'Record eligibility review'}).click();await expect(page.getByRole('status')).toContainText('Eligibility decision recorded');
  await page.getByLabel('Decision reason').fill('SYNTHETIC Golden operational intake');await page.getByRole('button',{name:'Admit to HITL Workflow'}).click();
  await expect(page.getByRole('status')).toContainText('Operational admission completed');await page.getByRole('link',{name:'Open Analyst Workstation'}).click();
  refs[name]=new URL(page.url()).searchParams.get('alertRef')!;expect(refs[name]).toBeTruthy();
  await post(`${harness}/context/${refs[name]}`,{});
  const state=await get(`/api/v2/alerts/${refs[name]}/triage-state`);evidence[name]={...manifest[name],alertRef:refs[name],admission:state};return state;
 }
 const learning=(name:string)=>get(`/api/v2/alerts/${refs[name]}/triage-memory/verdict-state`);
 const review=(name:string)=>get(`/api/v2/alerts/${refs[name]}/selective-review`);
 async function judge(name:string,outcome='expected_activity',correction=false){
  console.log('Golden judgment',name,outcome);
  await open(name);await workspace.getByRole('tab',{name:'Analyst Verdict',exact:true}).click();
  await verdict.getByLabel('Verdict outcome').selectOption(outcome);await verdict.getByLabel('Verdict reason').fill('SYNTHETIC Golden '+name+' '+outcome);
  if(name==='A'&&!correction)await smoke('verdict',verdict.getByRole('button',{name:'Record Verdict',exact:true}));
  const result=page.waitForResponse(r=>r.url().endsWith('/verdict')&&r.request().method()==='POST');
  await verdict.getByRole('button',{name:correction?'Correct Verdict':'Record Verdict',exact:true}).click();
  const response=await result;const saved=await response.json();evidence[name].verdictRequest=response.request().postDataJSON();evidence[name].verdict=saved.verdict;
  const state=await learning(name);evidence[name].learning=state;
  expect(state.decisionSource).toBe('system_policy');expect(saved.verdict.actorId).toBeGreaterThan(0);
  expect((await review(name)).policyEvaluation.inputs.canonicalVerdict.verdictRef).toBe(saved.verdict.verdictRef);
  return state;
 }
 async function evaluate(name:string,expected:string){
  await open(name);await workspace.getByRole('tab',{name:'Context & Review',exact:true}).click();
  const panel=workspace.getByRole('region',{name:'Selective Human Review',exact:true});
  await panel.getByLabel('Review policy or override reason').fill('SYNTHETIC Golden independent current safety check');
  const result=page.waitForResponse(r=>r.url().endsWith('/selective-review/evaluate')&&r.request().method()==='POST');
  if(name==='D'&&expected==='no_immediate_review')await smoke('review-policy',panel.getByRole('button',{name:'Evaluate Review Policy'}));
  await panel.getByRole('button',{name:'Evaluate Review Policy'}).click();expect((await result).ok()).toBe(true);
  const state=await review(name);expect(state.disposition).toBe(expected);evidence[name].review=state;return state;
 }
 async function escalate(name:string){
  await open(name);await workspace.getByRole('tab',{name:'Overview',exact:true}).click();
  await workspace.getByLabel('Decision reason',{exact:true}).fill('SYNTHETIC Golden request expert investigation');
  const escalated=page.waitForResponse(r=>r.url().endsWith('/tier2/escalate-case')&&r.request().method()==='POST');
  await workspace.getByRole('button',{name:'Escalate to Tier 2',exact:true}).click();expect((await escalated).ok()).toBe(true);
  const routed=await get(`/api/v2/alerts/${refs[name]}/triage-state`);expect(routed.latestDecision.decisionSource).toBe('analyst');expect(routed.latestDecision.actorId).toBeGreaterThan(0);evidence[name].manualEscalation=routed.latestDecision;
  await workspace.getByRole('link',{name:'Open Tier 2 Case',exact:true}).click();return new URL(page.url()).pathname.split('/').at(-1)!;
 }
 async function conclude(finding:string,category:string){
  await page.getByRole('tab',{name:'Investigation Conclusion',exact:true}).click();await page.getByLabel('Human Investigation Finding',{exact:true}).selectOption(finding);
  if(category)await page.getByLabel('Human Final Attack Classification',{exact:true}).selectOption(category);
  await page.getByLabel('Investigation Reason',{exact:true}).fill('SYNTHETIC Golden expert '+finding);
  const r=page.waitForResponse(r=>r.url().endsWith('/conclusions')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Record Investigation Conclusion',exact:true}).click();return (await (await r).json()).case;
 }
 await login();
 // A/B: actual UI intake and correlated evidence, then three independent judgments.
 for(const name of ['A','B','C']){
  const admitted=await admit(name);expect(admitted.state.handlingRoute).toBe('tier1_review');expect(admitted.classification.attackCategory).toBe('brute_force');
  const detector=await get(`/api/v2/alerts/${refs[name]}/evidence`);evidence[name].detector=detector;
  const bundle=detector.detectorEvidence.structuredEvidence.suricataBundle;expect(bundle.relatedSignatures).toHaveLength(2);expect(bundle.records).toHaveLength(4);expect(bundle.sensorId).toBe('golden-sensor');expect(bundle.captureScope).toBe(manifest[name].captureScope);expect(String(bundle.flowId)).toBe(String(manifest[name].flowId));
  expect(detector.detectorEvidence.confidence).toBeNull();expect(JSON.stringify(detector.detectorEvidence)).not.toMatch(/treeShap|mlPredictedClass|groundTruth/);
  const learned=await judge(name);expect(learned.memory.supportCount).toBe(['A','B','C'].indexOf(name)+1);expect(learned.memory.status).toBe(name==='C'?'active':'candidate');
  const unchanged=await get(`/api/v2/alerts/${refs[name]}/triage-state`);expect(unchanged.classification).toEqual(admitted.classification);expect(unchanged.state).toEqual(admitted.state);
 }
 const active=(await learning('C')).memory;const lessonRef=active.lesson.lessonRef;evidence.autoActive=active;
 expect(active.decision.actorId).toBeNull();expect(active.decision.decisionSource).toBe('system_policy');expect(active.decision.policyVersion).toBe('safe-memory-auto-activation-v1');
 expect(Date.parse(active.expiresAt)-Date.parse(active.validFrom)).toBe(30*86400000);
 // C/D/E: admit future D only after activation; check every operational surface.
 await admit('D');await evaluate('D','no_immediate_review');
 await expect(workspace).toContainText('Review Disposition: No Immediate Review');await expect(rail).toContainText('Review Required: No');
 await expect(workload.getByRole('button',{name:'No Immediate Review 1',exact:true})).toBeVisible();
 await workload.getByRole('button',{name:'No Immediate Review 1',exact:true}).click();await expect(page.getByRole('list',{name:'Operational alerts'}).getByRole('button')).toHaveCount(1);
 expect((await get('/api/v2/alerts?reviewDisposition=no_immediate_review')).items.map((a:any)=>a.operationalAlertRef)).toEqual([refs.D]);
 expect((await get(`/api/v2/alerts/${refs.D}/verdict`)).latest).toBeNull();
 await page.goto('/analyst/selective-review');await page.getByRole('tab',{name:'No Immediate Review',exact:true}).click();await expect(page.getByRole('row')).toHaveCount(2);
 await judge('D','confirmed_malicious');await expect(workspace).toContainText('Review Disposition: Human Review Required');await expect(rail).toContainText('Review Required: Yes');
 await expect(workload.getByRole('button',{name:'No Immediate Review 0',exact:true})).toBeVisible();
 expect((await review('D')).disposition).toBe('must_review');expect((await get('/api/v2/selective-review/metrics')).unsafeSuppressionCount).toBe(1);
 const conflict=(await learning('A')).memory;expect(conflict.status).toBe('conflict_review');expect(conflict.conflictCount).toBe(1);expect(conflict.decision).toEqual(active.decision);expect(Date.now()).toBeLessThan(Date.parse(active.expiresAt));evidence.conflict=conflict;
 await admit('E');await evaluate('E','must_review');
 // F: correction, replay and explicit Narrow must never add a second alert vote.
 await judge('A','confirmed_malicious',true);const corrected=(await learning('A')).memory;expect(corrected.supportCount).toBe(2);expect(corrected.conflictCount).toBe(2);
 expect((await post(`/api/v2/alerts/${refs.A}/verdict`,evidence.A.verdictRequest)).replayed).toBe(true);
 const vh=await get(`/api/v2/alerts/${refs.A}/verdict-history`);expect(vh.items.map((v:any)=>v.revision)).toEqual([2,1]);
 await workspace.getByRole('tab',{name:'Triage Memory',exact:true}).click();const narrowResponse=page.waitForResponse(r=>r.url().endsWith('/from-verdict')&&r.request().method()==='POST');await workspace.getByRole('button',{name:'Expand Learning Scope to Narrow',exact:true}).click();expect((await narrowResponse).ok()).toBe(true);expect((await learning('A')).decisionSource).toBe('analyst');
 expect((await get(`/api/v2/triage-memory/${lessonRef}`)).conflictCount).toBe(2);await page.reload();expect((await get(`/api/v2/triage-memory/${lessonRef}`)).supportCount).toBe(2);
 // G/H/I/K/L: genuinely Unknown source → automatic Case → real investigation → approval → resolve.
 const unknown=await admit('U');expect(unknown.classification.attackCategory).toBe('unknown_needs_expert');expect(unknown.state.handlingRoute).toBe('tier2_case');
 expect(unknown.latestDecision.decisionSource).toBe('system_policy');expect(unknown.latestDecision.actorId).toBeNull();
 await workspace.getByRole('link',{name:'Open Tier 2 Case',exact:true}).click();const caseRef=new URL(page.url()).pathname.split('/').at(-1)!;
 const initial=await get(`/api/v2/tier2/cases/${caseRef}`);expect(initial.createdByActorId).toBeNull();expect(initial.ownerActorId).toBeNull();evidence.unknownCase=initial;
 for(const name of ['Investigation Brief','Potentially Related Alerts','Suggested Investigation Steps'])await expect(page.getByRole('region',{name,exact:true})).toBeVisible();
 await page.getByRole('tab',{name:'Audit Timeline',exact:true}).click();await page.getByLabel('Decision reason',{exact:true}).fill('SYNTHETIC Golden start expert investigation');await page.getByRole('button',{name:'Start investigation',exact:true}).click();
 await page.getByRole('tab',{name:'Investigation Conclusion',exact:true}).click();await page.getByLabel('Human Investigation Finding',{exact:true}).selectOption('confirmed_malicious');await page.getByLabel('Human Final Attack Classification',{exact:true}).selectOption('web_attack');await page.getByLabel('Investigation Reason',{exact:true}).fill('SYNTHETIC Golden investigated web attack');
 await smoke('expert-conclusion',page.getByRole('button',{name:'Record Investigation Conclusion',exact:true}));
 const investigated=await conclude('confirmed_malicious','web_attack');expect(investigated.systemAttackClassification.attackCategory).toBe('unknown_needs_expert');expect(investigated.latestConclusion.finalAttackCategory).toBe('web_attack');
 const expertState=await get(`/api/v2/tier2/cases/${caseRef}/triage-memory/conclusion-state`);expect(expertState.decisionSource).toBe('system_policy');expect(expertState.memory.supportCount).toBe(1);expect(expertState.memory.decision).toBeNull();evidence.expertLearning=expertState;
 await responses.getByLabel('Proposal reason').fill('SYNTHETIC Golden recommendation only');await responses.getByRole('button',{name:'Generate recommendation',exact:true}).click();
 const block=responses.getByRole('article',{name:'Block Source IP',exact:true});await block.getByLabel('Approval or rejection reason').fill('SYNTHETIC Golden human approves plan, no execution');await smoke('response-approval',block.getByRole('button',{name:'Approve',exact:true}));await block.getByRole('button',{name:'Approve',exact:true}).click();await expect(block).toContainText('Approved - Not Executed');
 await resolution.getByLabel('Resolution Reason').fill('SYNTHETIC Golden investigation complete, response plan approved not executed');await smoke('case-resolution',resolution.getByRole('button',{name:'Resolve Case',exact:true}));
 const closedResponse=page.waitForResponse(r=>r.url().endsWith('/resolve')&&r.request().method()==='POST');await resolution.getByRole('button',{name:'Resolve Case',exact:true}).click();const closed=(await (await closedResponse).json()).case;evidence.resolvedCase=closed;
 await expect(summary.getByText('Resolved',{exact:true})).toBeVisible();expect(closed.resolution.actorId).toBeGreaterThan(0);expect(closed.resolution.responses[0].executionStatus).toBe('not_executed');
 const command={requestId:crypto.randomUUID(),expectedRevision:closed.revision,reason:'SYNTHETIC terminal guard check'};
 for(const [suffix,extra] of [['notes',{}],['start-investigation',{}],['alerts',{operationalAlertRef:refs.A}],['conclusions',{finding:'suspicious',finalAttackCategory:null}],['responses/recommend',{expectedCaseRevision:closed.revision}] ] as const){
  const body=suffix==='responses/recommend'?{requestId:crypto.randomUUID(),reason:command.reason,...extra}:{...command,requestId:crypto.randomUUID(),...extra};await post(`/api/v2/tier2/cases/${caseRef}/${suffix}`,body,409);
 }
 await page.getByRole('tab',{name:'Audit Timeline',exact:true}).click();await expect(page.getByRole('tabpanel')).toContainText('V2_TIER2_CASE_RESOLVED');await expect(expert).toContainText('Automatically recorded as Exact evidence');
 // J and authority: a second benign lesson loses a source to Inconclusive, then expert malicious authority.
 for(const name of ['I1','I2','I3']){await admit(name);await judge(name);}
 const authorityLesson=(await learning('I1')).lessonRef;const incRef=await escalate('I1');await conclude('inconclusive','');
 const inc=await get(`/api/v2/tier2/cases/${incRef}/triage-memory/conclusion-state`);expect(inc.eligible).toBe(false);expect(inc.contributionStatus).toBe('not_contributed');expect((await get(`/api/v2/triage-memory/${authorityLesson}`)).supportCount).toBe(2);evidence.inconclusive=inc;
 const supersedingRef=await escalate('I2');await conclude('confirmed_malicious','web_attack');
 const votes=(await get(harness+'/proof')).votes;expect(votes[authorityLesson].filter((v:any)=>v.alertRef===refs.I1)).toHaveLength(0);expect(votes[authorityLesson].filter((v:any)=>v.alertRef===refs.I2)).toHaveLength(1);expect(votes[authorityLesson].find((v:any)=>v.alertRef===refs.I2).sourceKind).toBe('tier2_conclusion');evidence.authorityVotes=votes;
 // Evaluator reads the same final product but every operational mutation remains forbidden.
 await page.getByRole('button',{name:'Sign out',exact:true}).click();await login('evaluator','evaluator-demo');
 await page.goto('/evaluator/tier2-cases/'+caseRef);await expect(summary).toContainText('Resolved');
 const av=await get(`/api/v2/alerts/${refs.A}/verdict`);expect(av.canRecord).toBe(false);
 const authBefore=await get(harness+'/proof');
 const attempts=[
  [`/api/v2/alerts/${refs.A}/verdict`,{...evidence.A.verdictRequest,requestId:crypto.randomUUID()}],
  [`/api/v2/alerts/${refs.A}/triage-memory/from-verdict`,{requestId:crypto.randomUUID(),verdictRef:av.latest.verdictRef,expectedStateVersion:av.sourceStateVersion,scope:'narrow'}],
  [`/api/v2/tier2/cases/${caseRef}/notes`,command],
  [`/api/v2/tier2/cases/${caseRef}/resolve`,command],
  [`/api/v2/tier2/cases/${caseRef}/responses/${closed.resolution.responses[0].recommendationRef}/approve`,{requestId:crypto.randomUUID(),expectedCaseRevision:closed.revision,expectedRevision:1,reason:'SYNTHETIC forbidden evaluator decision'}]
 ] as const;
 for(const [path,body] of attempts)await post(path,body,403);
 expect((await get(harness+'/proof')).digest).toBe(authBefore.digest);evidence.evaluatorDenied=attempts.map(([path])=>path);
 await page.getByRole('button',{name:'Sign out',exact:true}).click();await login();
 // M: one uninterrupted clock-controlled aging story, with fresh trusted context at each date.
 for(const name of ['T1','T2','T3']){await admit(name);await judge(name);}
 const timed=(await learning('T1')).memory;evidence.initialAging=timed;
 await admit('T5');await evaluate('T5','no_immediate_review');
 for(const changes of [{known_malicious_indicator:true},{evidence_conflict:true},{repeated_campaign:true},{asset_criticality:'critical'}]){
  await post(`${harness}/context/${refs.T5}`,{changes});await evaluate('T5','must_review');
 }
 await post(`${harness}/clock`,{at:new Date(Date.parse(timed.validFrom)+15*86400000).toISOString()});
 await evaluate('T5','must_review'); // previous facts are stale; active Memory alone is insufficient.
 await admit('T4');await evaluate('T4','no_immediate_review');await workspace.getByLabel('Review policy or override reason').fill('SYNTHETIC Golden human requires review');await workspace.getByRole('button',{name:'Require Human Review',exact:true}).click();await expect.poll(async()=>(await review('T4')).humanOverride).toBe(true);expect((await review('T4')).disposition).toBe('must_review');await judge('T4');const day15=(await learning('T1')).memory;expect(day15.supportCount).toBe(4);expect(day15.expiresAt).toBe(timed.expiresAt);evidence.day15=day15;
 await post(`${harness}/context/${refs.T5}`,{});await evaluate('T5','no_immediate_review');
 await post(`${harness}/clock`,{at:timed.expiresAt});await post(`${harness}/context/${refs.T5}`,{});await evaluate('T5','must_review');
 const expired=(await learning('T1')).memory;expect(expired.status).toBe('expired');expect(expired.expiresAt).toBe(timed.expiresAt);evidence.expired=expired;
 await page.goto('/analyst/triage-memory?lessonRef='+timed.lesson.lessonRef);await expect(page.getByText('expired',{exact:true})).toBeVisible();
 await judge('T5');const postExpiry=(await learning('T5')).memory;expect(postExpiry.lesson.lessonRef).toBe(timed.lesson.lessonRef);expect(postExpiry.status).toBe('expired');expect(postExpiry.expiresAt).toBe(timed.expiresAt);evidence.postExpiry=postExpiry;
 // Inspection must never mutate any table, even when deriving expiry.
 const before=await get(harness+'/proof');
 for(const path of ['/api/v2/alerts','/api/v2/alerts/summary','/api/v2/selective-review','/api/v2/selective-review/metrics','/api/v2/triage-memory',`/api/v2/tier2/cases/${caseRef}`,`/api/v2/tier2/cases/${caseRef}/events`,`/api/v2/tier2/cases/${caseRef}/responses`,`/api/v2/alerts/${refs.T5}/triage-memory/matches`])await get(path);
 const after=await get(harness+'/proof');expect(after.digest).toBe(before.digest);expect(after.collectionRuns).toBe(0);expect(after.foreignKeys).toBe(0);evidence.finalProof=after;evidence.finalMetrics=await get('/api/v2/selective-review/metrics');
 const queue=(await get('/api/v2/alerts?limit=200')).items;const sorted=[...queue].sort((a:any,b:any)=>(b.state.operationalPriority??-1)-(a.state.operationalPriority??-1)||b.detectionSummary.occurredAt.localeCompare(a.detectionSummary.occurredAt)||a.operationalAlertRef.localeCompare(b.operationalAlertRef));expect(queue).toEqual(sorted);evidence.queueOrder=queue.map((a:any)=>({alertRef:a.operationalAlertRef,priority:a.state.operationalPriority,occurredAt:a.detectionSummary.occurredAt}));
 for(const current of Object.values(after.votes) as any[][])expect(new Set(current.map(v=>v.alertRef)).size).toBe(current.length);
 expect(writes.some(p=>/\/activate|from-conclusion|execute|collection/.test(p))).toBe(false);
 expect(writes.filter(p=>p.endsWith('/from-verdict'))).toHaveLength(1);expect(errors).toEqual([]);
 evidence.refs=refs;evidence.supersedingCaseRef=supersedingRef;evidence.consoleErrors=errors;evidence.productWrites=writes.filter(p=>p.startsWith('/api/'));
 writeFileSync(info.outputPath('golden-path-evidence.json'),JSON.stringify(evidence,null,2));
});
