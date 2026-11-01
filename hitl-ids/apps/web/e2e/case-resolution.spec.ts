import {expect,test} from "@playwright/test";

test("final Case lifecycle: investigated malicious case, approved plan, learning, explicit resolve and readable terminal history",async({page})=>{
 test.setTimeout(180_000);const errors:string[]=[];const writes:string[]=[];let authorization="";
 page.on("pageerror",e=>errors.push(e.message));page.on("request",r=>{
  if(r.url().includes("/api/v2/"))authorization=r.headers()["authorization"]??authorization;
  if(r.method()==="POST")writes.push(new URL(r.url()).pathname);
 });
 await page.goto("/login");await page.getByLabel("Username").fill("g.ang");await page.getByLabel("Password",{exact:true}).fill("analyst-demo");await page.getByRole("button",{name:"Sign in"}).click();
 await expect(page).toHaveURL(/\/analyst\/operations$/);
 const workspace=page.getByRole("region",{name:"Operational alert workspace",exact:true});
 const summary=page.getByRole("region",{name:"Case summary",exact:true});
 const resolution=page.getByRole("region",{name:"Case Resolution",exact:true});
 const learning=page.getByRole("region",{name:"Expert Human Learning",exact:true});
 const responses=page.getByRole("region",{name:"Response Recommendations",exact:true});
 async function select(title:string){
  await page.goto("/analyst/operations");await page.getByLabel("Search operational alerts",{exact:true}).fill(title);
  const row=page.getByRole("list",{name:"Operational alerts"}).getByRole("button").first();await expect(row).toContainText(title);await row.click();
  await workspace.getByRole("link",{name:"Open Tier 2 Case",exact:true}).click();
  await expect(resolution).toBeVisible();
 }
 async function conclude(finding:string,category:string){
  await page.getByRole("tab",{name:"Investigation Conclusion",exact:true}).click();
  await page.getByLabel("Human Investigation Finding",{exact:true}).selectOption(finding);
  if(category)await page.getByLabel("Human Final Attack Classification",{exact:true}).selectOption(category);
  await page.getByLabel("Investigation Reason",{exact:true}).fill("SYNTHETIC expert investigation outcome: "+finding);
  await page.getByRole("button",{name:"Record Investigation Conclusion",exact:true}).click();
  await expect(resolution).toContainText("Latest Finding: "+finding.replaceAll("_"," "));
 }
 // A: no conclusion cannot resolve; start, note and evidence stay auditable.
 await select("SYNTHETIC Unresolved suspicious network activity 0");
 await expect(resolution.getByRole("button",{name:"Resolve Case",exact:true})).toBeDisabled();
 await page.getByRole("tab",{name:"Audit Timeline",exact:true}).click();
 await page.getByLabel("Decision reason",{exact:true}).fill("SYNTHETIC begin expert investigation");
 await page.getByRole("button",{name:"Start investigation",exact:true}).click();await expect(summary).toContainText("investigating");
 await page.getByRole("tab",{name:"Investigation Notes",exact:true}).click();
 await page.getByLabel("Investigation note",{exact:true}).fill("SYNTHETIC retained investigation note");
 await page.getByRole("button",{name:"Add investigation note",exact:true}).click();
 await expect(page.getByRole("tabpanel")).toContainText("SYNTHETIC retained investigation note");
 await page.getByRole("region",{name:"Potentially Related Alerts",exact:true}).getByRole("button",{name:"Review link to Case",exact:true}).first().click();
 await page.getByLabel("Decision reason",{exact:true}).fill("SYNTHETIC related evidence reviewed");
 await page.getByRole("button",{name:"Link alert",exact:true}).click();await expect(page.getByRole("tabpanel")).toContainText("V2_TIER2_ALERT_LINKED");
 await conclude("confirmed_malicious","web_attack");
 await expect(summary).toContainText("System Attack Classification: Unknown / Needs Expert");
 await responses.getByLabel("Proposal reason").fill("SYNTHETIC propose plan without execution");
 await responses.getByRole("button",{name:"Generate recommendation",exact:true}).click();
 await expect(resolution).toContainText("Pending Human Approval");
 await resolution.getByLabel("Resolution Reason").fill("SYNTHETIC investigation complete; approved plan not executed");
 await expect(resolution.getByRole("button",{name:"Resolve Case",exact:true})).toBeDisabled();
 const block=responses.getByRole("article",{name:"Block Source IP",exact:true});
 await block.getByLabel("Approval or rejection reason").fill("SYNTHETIC approve plan only, not execution");
 await block.getByRole("button",{name:"Approve",exact:true}).click();
 await expect(resolution).toContainText("Approved - Not Executed");
 await expect(learning).toContainText("Contribution: Automatically recorded as Exact evidence");
 const memoryHref=await learning.getByRole("link",{name:"Open linked Memory lesson",exact:true}).getAttribute("href");
 const caseUrl=page.url();
 await expect(summary).toContainText("investigating"); // neither response approval nor learning closes the Case
 for(const width of [1440,1024,390]){
  await page.setViewportSize({width,height:900});
  for(const theme of ["dark","light"]){
   if(await page.locator("html").getAttribute("data-theme")!==theme)await page.getByRole("button",{name:"Light theme",exact:true}).click();
   await resolution.getByLabel("Resolution Reason").scrollIntoViewIfNeeded();
   await expect(resolution.getByRole("button",{name:"Resolve Case",exact:true})).toBeVisible();
   expect(await resolution.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.screenshot({path:`test-results/resolution-${width}-${theme}.png`});
  }
 }
 await page.setViewportSize({width:1440,height:900});
 const result=page.waitForResponse(r=>r.url().endsWith("/resolve")&&r.request().method()==="POST");
 await resolution.getByRole("button",{name:"Resolve Case",exact:true}).click();const closed=(await (await result).json()).case;
 await expect(summary.getByText("Resolved",{exact:true})).toBeVisible();
 await expect(resolution).toContainText("Resolved by: Glenn Ang");await expect(resolution).toContainText("Approved - Not Executed");
 await expect(resolution.getByLabel("Resolution Reason")).toHaveCount(0);
 await expect(learning).toContainText("Contribution: Automatically recorded as Exact evidence");
 await expect(page.getByRole("region",{name:"Investigation Brief",exact:true})).toContainText("unknown_needs_expert");
 // C: UI is read-only, server also rejects new investigation attempts.
 for(const tab of ["Investigation Notes","Investigation Conclusion","Linked Alerts","Audit Timeline"]){
  await page.getByRole("tab",{name:tab,exact:true}).click();
  await expect(page.getByRole("button",{name:/^(Add investigation note|Record Investigation Conclusion|Link alert|Start investigation)$/})).toHaveCount(0);
 }
 await expect(page.getByRole("tabpanel")).toContainText("V2_TIER2_CASE_RESOLVED");
 await expect(page.getByRole("tabpanel")).toContainText("Case Resolved");
 await expect(page.getByRole("tabpanel")).toContainText("SYNTHETIC retained investigation note");
 await expect(page.getByRole("tabpanel")).toContainText("V2_TIER2_ALERT_LINKED");
 await expect(responses.getByLabel("Proposal reason")).toHaveCount(0);
 await expect(block).toContainText("Approved - Not Executed");
 const attempt=await page.request.post(`/api/v2/tier2/cases/${closed.caseRef}/notes`,{headers:{Authorization:authorization},data:{requestId:crypto.randomUUID(),expectedRevision:closed.revision,reason:"SYNTHETIC forbidden after closure"}});
 expect(attempt.status()).toBe(409);
 await page.goto(memoryHref!);await expect(page.getByRole("region",{name:"Memory evidence and audit",exact:true})).toContainText("Current human evidence");
 await page.goto(caseUrl);await expect(summary).toContainText("Resolved");
 await page.getByRole("link",{name:"All Tier 2 cases",exact:true}).click();
 await expect(page.getByRole("row").filter({hasText:"SYNTHETIC Unresolved suspicious network activity 0"})).toContainText("Resolved");
 // B: Expected Activity can resolve without inventing a containment recommendation.
 await select("SYNTHETIC Unresolved suspicious network activity 1");await conclude("expected_activity","");
 await expect(resolution).toContainText("Response: None recorded");
 await resolution.getByLabel("Resolution Reason").fill("SYNTHETIC authorized expected activity; no containment required");
 await resolution.getByRole("button",{name:"Resolve Case",exact:true}).click();
 await expect(summary).toContainText("Resolved");await expect(resolution).toContainText("Not applicable");
 expect(errors).toEqual([]);expect(writes.some(p=>/execute|collection/.test(p))).toBe(false);
});
