import {expect,test} from "@playwright/test";

test("expert learning: automatic Unknown, Tier 1 replacement, Inconclusive, corrections and active-guidance safety",async({page})=>{
 test.setTimeout(180_000);const errors:string[]=[];const writes:string[]=[];
 page.on("pageerror",e=>errors.push(e.message));page.on("request",r=>{if(r.method()==="POST")writes.push(new URL(r.url()).pathname);});
 await page.goto("/login");await page.getByLabel("Username").fill("g.ang");await page.getByLabel("Password",{exact:true}).fill("analyst-demo");await page.getByRole("button",{name:"Sign in"}).click();
 await expect(page).toHaveURL(/\/analyst\/operations$/);
 const workspace=page.getByRole("region",{name:"Operational alert workspace",exact:true});
 const learning=page.getByRole("region",{name:"Expert Human Learning",exact:true});
 async function select(title:string,index=0){
  await page.goto("/analyst/operations");await page.getByLabel("Search operational alerts",{exact:true}).fill(title);
  const rows=page.getByRole("list",{name:"Operational alerts"}).getByRole("button");await expect(rows.first()).toContainText(title);
  await (index<0?rows.last():rows.nth(index)).click();await expect(workspace).toContainText(title);
 }
 async function openCase(){await workspace.getByRole("link",{name:"Open Tier 2 Case",exact:true}).click();await expect(learning).toBeVisible();}
 async function conclude(finding:string,category:string,reason:string){
  await page.getByRole("tab",{name:"Investigation Conclusion",exact:true}).click();
  await page.getByLabel("Human Investigation Finding",{exact:true}).selectOption(finding);
  if(category)await page.getByLabel("Human Final Attack Classification",{exact:true}).selectOption(category);
  await page.getByLabel("Investigation Reason",{exact:true}).fill(reason);
  await page.getByRole("button",{name:"Record Investigation Conclusion",exact:true}).click();
  await expect(learning).toContainText(`Reason: ${reason}`);
 }
 async function contribute(){
  await expect(learning).toContainText("Contribution: Automatically recorded as Exact evidence");
 }
 async function escalate(){
  await workspace.getByRole("tab",{name:"Overview",exact:true}).click();
  await workspace.getByLabel("Decision reason",{exact:true}).fill("SYNTHETIC expert escalation after learning review");
  await workspace.getByRole("button",{name:"Escalate to Tier 2",exact:true}).click();await openCase();
 }
 async function tier1Learn(index:number){
  await select("SYNTHETIC expert learning brute force",index);
  const verdict=workspace.getByRole("region",{name:"Analyst Verdict",exact:true});
  await verdict.getByLabel("Verdict outcome").selectOption("expected_activity");
  await verdict.getByLabel("Verdict reason").fill(`SYNTHETIC Tier 1 expected activity ${index}`);
  await verdict.getByRole("button",{name:"Record Verdict",exact:true}).click();
  await verdict.getByRole("button",{name:"Use in Triage Memory",exact:true}).click();
  const human=workspace.getByRole("region",{name:"Human Learning",exact:true});
  await expect(human).toContainText("Automatically recorded as Exact evidence");await escalate();
 }
 // E: existing active guidance loses a distinct source before a replacement is contributed.
 await select("SYNTHETIC selective SSH scan",-1);
 await expect(page.getByRole("button",{name:"No Immediate Review 3",exact:true})).toBeVisible();
 await workspace.getByRole("tab",{name:"Triage Memory",exact:true}).click();
 const human=workspace.getByRole("region",{name:"Human Learning",exact:true});
 await expect(human).toContainText("Automatically recorded as Exact evidence");
 await expect(human).toContainText("Support: 3 · Conflicts: 0");await escalate();
 await conclude("inconclusive","","SYNTHETIC expert withdraws stale active lesson support");
 await page.goto("/analyst/operations");await expect(page.getByRole("button",{name:"No Immediate Review 0",exact:true})).toBeVisible();
 await select("SYNTHETIC selective SSH scan",0);await workspace.getByRole("tab",{name:"Triage Memory",exact:true}).click();
 await expect(human).toContainText("Support: 2 · Conflicts: 0");await expect(human).toContainText("Active guidance: No");

 // A: no Tier 1 Verdict needed; Exact evidence is automatic.
 await select("SYNTHETIC Unresolved suspicious network activity 0");await openCase();
 await conclude("confirmed_malicious","web_attack","SYNTHETIC expert reusable Web Attack evidence");
 await expect(learning).toContainText("Contribution: Automatically recorded as Exact evidence");
 expect(writes.filter(p=>p.endsWith("from-conclusion"))).toHaveLength(0);
 for(const width of [1440,1024,390]){
  await page.setViewportSize({width,height:900});
  for(const theme of ["dark","light"]){
   if(await page.locator("html").getAttribute("data-theme")!==theme)await page.getByRole("button",{name:"Light theme",exact:true}).click();
   await learning.getByLabel("Learning Scope").scrollIntoViewIfNeeded();
   await expect(learning.getByRole("button",{name:"Expand Expert Learning Scope to Narrow",exact:true})).toBeVisible();
   expect(await learning.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.screenshot({path:`test-results/expert-learning-${width}-${theme}.png`});
  }
 }
 await page.setViewportSize({width:1440,height:900});await contribute();
 await expect(learning).toContainText("Memory Status: candidate · Support: 1 · Conflicts: 0");
 const firstCase=page.url();await learning.getByRole("link",{name:"Open linked Memory lesson",exact:true}).click();
 const history=page.getByRole("region",{name:"Memory evidence and audit",exact:true});
 await expect(history).toContainText("Source: Tier 2 Investigation Conclusion");
 await expect(history).toContainText("Human Final Attack Classification: Web Attack");
 await expect(history).toContainText("Conclusion Author:");await expect(history).toContainText("Memory Contributor:");
 await history.getByRole("link",{name:"Source Case",exact:true}).click();await expect(page).toHaveURL(firstCase);
 // B: expert replaces this alert's Tier 1 vote with the automatic expert contribution.
 await tier1Learn(0);
 await conclude("confirmed_malicious","infiltration","SYNTHETIC expert overrides earlier Tier 1 reuse");
 await expect(learning).toContainText("Previous Tier 1 learning evidence: Superseded by expert investigation conclusion.");
 await expect(learning).toContainText("Contribution: Automatically recorded as Exact evidence");await contribute();
 await learning.getByRole("link",{name:"Open linked Memory lesson",exact:true}).click();
 await expect(history).toContainText("V2_TRIAGE_MEMORY_EXPERT_SUPERSEDED");
 await expect(history).toContainText("Superseded human evidence — excluded from effective support");
 await expect(history).toContainText("Current human evidence");
 // C: Inconclusive also withdraws Tier 1 evidence; no expert contribution is offered.
 await tier1Learn(1);await conclude("inconclusive","","SYNTHETIC expert cannot support reusable outcome");
 await expect(learning).toContainText("Not eligible for reusable Memory evidence");
 await expect(learning).toContainText("Previous Tier 1 learning evidence: Superseded");
 await expect(learning.getByRole("button",{name:"Expand Expert Learning Scope to Narrow",exact:true})).toHaveCount(0);
 // D: correcting an expert conclusion immediately supersedes its previous evidence.
 await select("SYNTHETIC Unresolved suspicious network activity 1");await openCase();
 await conclude("suspicious","web_attack","SYNTHETIC first expert conclusion");await contribute();
 await conclude("confirmed_malicious","infiltration","SYNTHETIC corrected expert conclusion");
 await expect(learning).toContainText("Previous expert learning evidence: Superseded");
 await expect(learning).toContainText("Support: 0");await contribute();await expect(learning).toContainText("Conflicts: 1");
 expect(errors).toEqual([]);expect(writes.some(p=>/execute|collection|\/responses\//.test(p))).toBe(false);
});
