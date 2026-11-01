import { expect,test } from "@playwright/test";

test("human conclusions: Unknown resolution, known correction, append-only history and Expected Activity",async({page})=>{
  test.setTimeout(180_000);
  const errors:string[]=[];const writes:string[]=[];
  page.on("pageerror",e=>errors.push(e.message));
  page.on("request",r=>{if(r.method()==="POST")writes.push(new URL(r.url()).pathname);});
  await page.goto("/login");await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password",{exact:true}).fill("analyst-demo");await page.getByRole("button",{name:"Sign in"}).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  const workspace=page.getByRole("region",{name:"Operational alert workspace",exact:true});
  const summary=page.getByRole("region",{name:"Case summary",exact:true});
  const latest=page.getByRole("region",{name:"Latest Human Investigation Conclusion",exact:true});
  const brief=page.getByRole("region",{name:"Investigation Brief",exact:true});
  const responses=page.getByRole("region",{name:"Response Recommendations",exact:true});
  async function select(title:string){
    await page.goto("/analyst/operations");await page.getByLabel("Search operational alerts",{exact:true}).fill(title);
    const row=page.getByRole("list",{name:"Operational alerts"}).getByRole("button").first();await expect(row).toContainText(title);await row.click();
    await expect(workspace.getByRole("heading",{name:title,exact:true})).toBeVisible();
  }
  async function record(finding:string,category:string,reason:string){
    await page.getByRole("tab",{name:"Investigation Conclusion",exact:true}).click();
    await page.getByLabel("Human Investigation Finding",{exact:true}).selectOption(finding);
    if(category)await page.getByLabel("Human Final Attack Classification",{exact:true}).selectOption(category);
    await page.getByLabel("Investigation Reason",{exact:true}).fill(reason);
    await page.getByRole("button",{name:"Record Investigation Conclusion",exact:true}).click();
    await expect(latest).toContainText(reason);
  }
  async function propose(reason:string){
    await responses.getByLabel("Proposal reason").fill(reason);
    await responses.getByRole("button",{name:"Generate recommendation",exact:true}).click();
    await expect(responses.getByText(`Proposal reason: ${reason}`,{exact:true})).toBeVisible();
  }
  // A: Unknown stays immutable; a human explicitly selects Web Attack after investigation.
  await select("SYNTHETIC Unresolved suspicious network activity 1");
  await workspace.getByRole("link",{name:"Open Tier 2 Case",exact:true}).click();
  await expect(brief).toContainText("Unknown / Needs Expert");
  await page.getByRole("tab",{name:"Audit Timeline",exact:true}).click();
  await page.getByLabel("Decision reason",{exact:true}).fill("SYNTHETIC expert begins evidence investigation");
  await page.getByRole("button",{name:"Start investigation",exact:true}).click();
  await expect(summary).toContainText("investigating");
  await page.getByRole("tab",{name:"Investigation Conclusion",exact:true}).click();
  await page.getByLabel("Human Investigation Finding",{exact:true}).selectOption("confirmed_malicious");
  await page.getByLabel("Investigation Reason",{exact:true}).fill("SYNTHETIC expert corroborated a web attack");
  await expect(page.getByLabel("Human Final Attack Classification",{exact:true})).toHaveValue("");
  await expect(page.getByRole("button",{name:"Record Investigation Conclusion",exact:true})).toBeDisabled();
  await expect(page.getByLabel("Human Final Attack Classification").locator('option[value="unknown_needs_expert"]')).toHaveCount(0);
  for(const width of [1440,1024,390]){
    await page.setViewportSize({width,height:900});
    for(const theme of ["dark","light"]){
      if(await page.locator("html").getAttribute("data-theme")!==theme)await page.getByRole("button",{name:"Light theme",exact:true}).click();
      await page.getByLabel("Human Final Attack Classification",{exact:true}).scrollIntoViewIfNeeded();
      await expect(page.getByLabel("Human Final Attack Classification",{exact:true})).toBeVisible();
      await expect(page.getByRole("button",{name:"Record Investigation Conclusion",exact:true})).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await page.screenshot({path:`test-results/reclassification-${width}-${theme}.png`});
    }
  }
  await page.setViewportSize({width:1440,height:900});
  await record("confirmed_malicious","web_attack","SYNTHETIC expert corroborated a web attack");
  await expect(summary).toContainText("System Attack Classification: Unknown / Needs Expert");
  await expect(latest).toContainText("Human Final Attack Classification: Web Attack");
  await expect(summary).toContainText("investigating");
  await expect(brief).toContainText("unknown_needs_expert");
  await propose("SYNTHETIC plan based on human Finding");
  const block=responses.getByRole("article",{name:"Block Source IP",exact:true});
  await block.getByLabel("Approval or rejection reason").fill("SYNTHETIC human approval of plan only");
  await block.getByRole("button",{name:"Approve",exact:true}).click();
  await expect(block).toContainText("Approved - Not Executed");
  // B/D: known Brute Force may differ from both first and corrected human conclusions.
  await select("SYNTHETIC reclassification known brute force");
  const verdict=workspace.getByRole("region",{name:"Analyst Verdict",exact:true});
  await verdict.getByLabel("Verdict outcome").selectOption("suspicious");
  await verdict.getByLabel("Verdict reason").fill("SYNTHETIC original Tier 1 suspicion");
  await verdict.getByRole("button",{name:"Record Verdict",exact:true}).click();
  await expect(verdict).toContainText("Current Verdict: Suspicious");
  await workspace.getByLabel("Decision reason",{exact:true}).fill("SYNTHETIC expert review needed");
  await workspace.getByRole("button",{name:"Escalate to Tier 2",exact:true}).click();
  await workspace.getByRole("link",{name:"Open Tier 2 Case",exact:true}).click();
  await record("suspicious","web_attack","SYNTHETIC initial expert assessment");
  await expect(summary).toContainText("System Attack Classification: Brute Force");
  await propose("SYNTHETIC monitor suspicious evidence");
  await expect(responses.getByRole("article",{name:"Monitor",exact:true})).toBeVisible();
  await expect(responses.getByRole("article",{name:"Block Source IP",exact:true})).toHaveCount(0);
  await record("confirmed_malicious","infiltration","SYNTHETIC corrected expert conclusion after deeper evidence");
  await expect(latest).toContainText("Human Final Attack Classification: Infiltration");
  await expect(latest).toContainText("Supersedes event");
  await expect(summary).toContainText("System Attack Classification: Brute Force");
  await expect(page.getByRole("tabpanel")).toContainText("SYNTHETIC initial expert assessment");
  await expect(page.getByRole("tabpanel")).toContainText("Human Final Attack Classification: Web Attack");
  await page.getByRole("tab",{name:"Audit Timeline",exact:true}).click();
  await expect(page.getByRole("tabpanel")).toContainText("Human Final Attack Classification: Infiltration");
  await expect(page.getByRole("tabpanel")).toContainText("Human Final Attack Classification: Web Attack");
  await expect(brief).toContainText("Current Tier 1 Verdict: suspicious");
  await expect(brief).toContainText("SYNTHETIC original Tier 1 suspicion");
  await propose("SYNTHETIC updated response after corrected Finding");
  await expect(responses.getByRole("article",{name:"Block Source IP",exact:true})).toBeVisible();
  // C: Expected Activity has no final attack category and produces non-containment guidance.
  await select("SYNTHETIC Unresolved suspicious network activity 2");
  await workspace.getByRole("link",{name:"Open Tier 2 Case",exact:true}).click();
  await page.getByRole("tab",{name:"Investigation Conclusion",exact:true}).click();
  await page.getByLabel("Human Investigation Finding",{exact:true}).selectOption("expected_activity");
  await expect(page.getByLabel("Human Final Attack Classification",{exact:true})).toBeDisabled();
  await record("expected_activity","","SYNTHETIC authorized expected activity");
  await expect(latest).toContainText("Human Final Attack Classification: Not applicable");
  await expect(summary).toContainText("System Attack Classification: Unknown / Needs Expert");
  await propose("SYNTHETIC monitor expected activity");
  await expect(responses.getByRole("article",{name:"Monitor",exact:true})).toBeVisible();
  await expect(responses.getByRole("article",{name:"Block Source IP",exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);
  expect(writes.some(path=>/execute|collection|memory/.test(path))).toBe(false);
});
