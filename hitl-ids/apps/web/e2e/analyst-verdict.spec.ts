import { expect,test } from "@playwright/test";

test("Tier 1 Verdict: human conclusion, correction/history, separate escalation and automatic Expert case",async({page})=>{
  await page.goto("/login");await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password",{exact:true}).fill("analyst-demo");await page.getByRole("button",{name:"Sign in"}).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  const detail=page.getByRole("region",{name:"Operational alert workspace"});
  async function select(title:string){
    await page.getByLabel("Search operational alerts",{exact:true}).fill(title);
    const row=page.getByRole("list",{name:"Operational alerts"}).getByRole("button").first();await expect(row).toContainText(title);await row.click();
    await detail.getByRole("tab",{name:"Overview",exact:true}).click();await expect(detail.getByRole("heading",{name:title,exact:true})).toBeVisible();
  }
  const panel=detail.getByRole("region",{name:"Analyst Verdict",exact:true});
  async function verdict(outcome:string,reason:string,correct=false){
    await panel.getByLabel("Verdict outcome").selectOption(outcome);await panel.getByLabel("Verdict reason").fill(reason);
    await panel.getByRole("button",{name:correct?"Correct Verdict":"Record Verdict",exact:true}).click();
    await expect(panel.getByText(reason,{exact:true})).toBeVisible();
  }
  await select("SYNTHETIC Known routine brute force");
  await expect(panel).toContainText("Current Verdict: Not recorded");
  await verdict("suspicious","SYNTHETIC suspicious human conclusion");
  await expect(panel).toContainText("Current Verdict: Suspicious");
  await expect(detail.getByRole("region",{name:"System Routing",exact:true})).toContainText("Routine Review");
  await detail.getByLabel("Decision reason").fill("SYNTHETIC explicit manual escalation after verdict");
  await detail.getByRole("button",{name:"Escalate to Tier 2",exact:true}).click();
  await expect(detail.getByRole("link",{name:"Open Tier 2 Case",exact:true})).toBeVisible();
  await expect(panel).toContainText("Current Verdict: Suspicious");
  await select("SYNTHETIC DDoS detected");
  await verdict("suspicious","SYNTHETIC initial DDoS assessment");
  await verdict("false_positive","SYNTHETIC corrected false positive",true);
  await expect(detail).toContainText(/Attack Category: ddos/i);
  await expect(detail.getByRole("region",{name:"System Routing",exact:true})).toContainText("Routine Review");
  await detail.getByRole("tab",{name:"History & Notes",exact:true}).click();
  const history=detail.getByRole("region",{name:"Analyst Verdict History"});
  await expect(history).toContainText("SYNTHETIC initial DDoS assessment");await expect(history).toContainText("SYNTHETIC corrected false positive");
  await select("Informational notice: software version");
  await verdict("expected_activity","SYNTHETIC approved notification human conclusion");
  await expect(detail).toContainText("Classification: Informational / Policy Signal");
  for(const width of [1440,1024,390]){
    await page.setViewportSize({width,height:900});
    for(const theme of ["dark","light"]){
      if(await page.locator("html").getAttribute("data-theme")!==theme)await page.getByRole("button",{name:"Light theme",exact:true}).click();
      await panel.scrollIntoViewIfNeeded();await expect(panel.getByLabel("Verdict reason")).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await page.screenshot({path:`test-results/verdict-${width}-${theme}.png`,fullPage:true});
    }
  }
  await page.setViewportSize({width:1440,height:900});
  await select("SYNTHETIC DDoS conflicting evidence");
  await expect(detail).toContainText("Expert Review Required");await expect(panel).toContainText("Current Verdict: Not recorded");
  await expect(panel.getByLabel("Verdict reason")).toHaveCount(0);
  await detail.getByRole("link",{name:"Open Tier 2 Case",exact:true}).click();
  await expect(page.getByRole("region",{name:"Case summary"})).toContainText("System Policy");
});
