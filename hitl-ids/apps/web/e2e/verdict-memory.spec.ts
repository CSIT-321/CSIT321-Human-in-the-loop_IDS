import { expect,test } from "@playwright/test";

test("canonical learning: automatic Exact contribution, independent support, correction, conflicts and Tier 2 boundary",async({page})=>{
  await page.goto("/login");await page.getByLabel("Username").fill("g.ang");await page.getByLabel("Password",{exact:true}).fill("analyst-demo");await page.getByRole("button",{name:"Sign in"}).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  const detail=page.getByRole("region",{name:"Operational alert workspace"});
  const learning=detail.getByRole("region",{name:"Human Learning"});
  const panel=detail.getByRole("region",{name:"Analyst Verdict",exact:true});
  const firstUrls:string[]=[];
  for(let index=0;index<3;index++){
    await page.getByLabel("Search operational alerts",{exact:true}).fill("canonical learning");
    const rows=page.getByRole("list",{name:"Operational alerts"}).getByRole("button");await expect(rows).toHaveCount(4);await rows.nth(index).click();
    firstUrls.push(page.url());
    await detail.getByRole("tab",{name:"Triage Memory",exact:true}).click();
    await expect(learning).toContainText("Record an Analyst Verdict to automatically capture Exact learning evidence.");
    await learning.getByRole("button",{name:"Open Analyst Verdict",exact:true}).click();
    await panel.getByLabel("Verdict outcome").selectOption("expected_activity");await panel.getByLabel("Verdict reason").fill(`SYNTHETIC authorized scan assessment ${index+1}`);
    await panel.getByRole("button",{name:"Record Verdict",exact:true}).click();
    await panel.getByRole("button",{name:"Use in Triage Memory",exact:true}).click();
    await expect(learning.getByLabel("Human memory outcome")).toHaveCount(0);await expect(learning.getByLabel("Human memory reason")).toHaveCount(0);
    await expect(learning).toContainText("Automatically recorded as Exact evidence");await expect(learning).toContainText(`Support: ${index+1} · Conflicts: 0`);
  }
  await learning.getByRole("link",{name:"Open linked Memory lesson",exact:true}).click();
  await expect(page.getByText("active",{exact:true})).toBeVisible();
  await expect(page.getByText("Verdict Author:",{exact:false}).first()).toBeVisible();
  await page.goto(firstUrls[0]!);await detail.getByRole("tab",{name:"Analyst Verdict",exact:true}).click();
  await panel.getByLabel("Verdict outcome").selectOption("confirmed_malicious");await panel.getByLabel("Verdict reason").fill("SYNTHETIC corrected human conclusion");
  await panel.getByRole("button",{name:"Correct Verdict",exact:true}).click();
  await panel.getByRole("button",{name:"Use in Triage Memory",exact:true}).click();
  await expect(learning).toContainText("Automatically recorded as Exact evidence");
  await expect(learning).toContainText("Support: 2 · Conflicts: 1");await expect(learning).toContainText("Active guidance: No");
  const rail=page.getByRole("complementary",{name:"Context and assistance"});
  await expect(rail).toContainText("Support: 2 · Conflicts: 1");
  await expect(rail).not.toContainText("Active guidance: Yes");
  await expect(page.getByRole("button",{name:"Total Alerts 72",exact:true})).toBeVisible();
  for(const width of [1440,1024,390]){
    await page.setViewportSize({width,height:900});
    for(const theme of ["dark","light"]){
      if(await page.locator("html").getAttribute("data-theme")!==theme)await page.getByRole("button",{name:"Light theme",exact:true}).click();
      await learning.getByLabel("Optional broader learning scope").scrollIntoViewIfNeeded();await expect(learning.getByLabel("Optional broader learning scope")).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await page.screenshot({path:`test-results/verdict-memory-${width}-${theme}.png`,fullPage:true});
    }
  }
  await page.setViewportSize({width:1440,height:900});
  await expect(learning).toContainText("Support: 2 · Conflicts: 1");await expect(learning).toContainText("conflict review");
  await page.getByRole("list",{name:"Operational alerts"}).getByRole("button").nth(3).click();
  await detail.getByRole("tab",{name:"Analyst Verdict",exact:true}).click();
  await panel.getByLabel("Verdict outcome").selectOption("confirmed_malicious");await panel.getByLabel("Verdict reason").fill("SYNTHETIC independent conflicting alert");
  await panel.getByRole("button",{name:"Record Verdict",exact:true}).click();await panel.getByRole("button",{name:"Use in Triage Memory",exact:true}).click();
  await expect(learning).toContainText("Support: 2 · Conflicts: 2");
  await page.getByLabel("Search operational alerts",{exact:true}).fill("DDoS conflicting evidence");
  const unknown=page.getByRole("list",{name:"Operational alerts"}).getByRole("button").first();await expect(unknown).toContainText("DDoS conflicting evidence");await unknown.click();
  await detail.getByRole("tab",{name:"Triage Memory",exact:true}).click();await expect(learning).toContainText("No Tier 1 Verdict is required");
  await expect(learning.getByRole("button",{name:"Expand Learning Scope to Narrow",exact:true})).toHaveCount(0);
});
