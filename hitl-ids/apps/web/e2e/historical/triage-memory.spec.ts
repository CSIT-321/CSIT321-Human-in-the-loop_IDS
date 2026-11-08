import { expect,test } from "@playwright/test";

test("three human reviews, activation, future guidance and contradiction without automation",async({page})=>{
  const errors:string[]=[];
  page.on("pageerror",error=>errors.push(error.message));
  page.on("console",message=>{if(message.type()==="error")errors.push(message.text());});
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password",{exact:true}).fill("analyst-demo");
  await page.getByRole("button",{name:"Sign in"}).click();
  await page.getByRole("link",{name:"Analyst Workstation"}).click();
  const options=page.getByRole("list",{name:"Operational alerts"}).getByRole("button").filter({hasText:"DEMO SSH scan"});
  await expect(options).toHaveCount(5);
  const refs:string[]=[];
  for(let index=0;index<await options.count();index++){
    await options.nth(index).click();
    refs.push(new URL(page.url()).searchParams.get("alertRef")!);
  }
  for(const ref of refs.slice(0,3)){
    await page.goto("/analyst/operations?alertRef="+ref);
    await page.getByRole("tab",{name:"Triage Memory",exact:true}).click();
    await page.getByLabel("Human memory outcome").selectOption("expected_activity");
    await page.getByLabel("Human memory reason").fill("Authorised internal vulnerability scanner");
    await page.getByRole("button",{name:"Record Human Memory Review"}).click();
    await expect(page.getByText("Human review recorded.",{exact:false})).toBeVisible();
  }
  await page.getByRole("link",{name:"Open recorded lesson"}).click();
  const detail=page.getByRole("region",{name:"Triage lesson detail"});
  await expect(detail.getByText("eligible for activation",{exact:true})).toBeVisible();
  await expect(detail.getByRole("button",{name:"Activate Lesson"})).toBeDisabled();
  await page.getByLabel("Memory activation or rejection reason").fill("Three independent alerts agree; narrow operational context reviewed");
  await page.getByRole("button",{name:"Activate Lesson"}).click();
  await expect(detail.getByText("active",{exact:true})).toBeVisible();
  await expect(detail.getByRole("button",{name:"Activate Lesson"})).toHaveCount(0);
  await page.goto("/analyst/v2-triage?alertRef="+refs[3]);
  await page.getByRole("tab",{name:"Triage Memory",exact:true}).click();
  const memory=page.getByRole("region",{name:"Historical Triage Memory",exact:true});
  await expect(memory.getByText("Match: High",{exact:true})).toBeVisible();
  await expect(memory.getByText("Active guidance: Yes",{exact:true})).toBeVisible();
  await expect(memory.getByText("Authorised internal vulnerability scanner",{exact:true})).toBeVisible();
  await expect(memory.getByText("Memory guidance only — Human review still required.",{exact:true})).toBeVisible();
  const routing=page.getByRole("region",{name:"Operational alert workspace",exact:true});
  await expect(routing.getByText("tier1 review",{exact:true})).toBeVisible();
  await expect(routing.getByText("P1 / 85",{exact:true})).toBeVisible();
  await expect(routing.getByText("Review Required: Yes",{exact:true})).toBeVisible();
  await memory.evaluate(el=>el.scrollIntoView({block:"start"}));
  await page.screenshot({path:"test-results/triage-memory-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await memory.evaluate(el=>el.scrollIntoView({block:"start"}));
  await page.screenshot({path:"test-results/triage-memory-mobile.png",fullPage:true});
  expect(await page.locator("main").evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await page.goto("/analyst/v2-triage?alertRef="+refs[4]);
  await page.getByRole("tab",{name:"Triage Memory",exact:true}).click();
  await page.getByLabel("Human memory outcome").selectOption("confirmed_malicious");
  await page.getByLabel("Human memory reason").fill("Contradictory investigation evidence requires memory review");
  await page.getByRole("button",{name:"Record Human Memory Review"}).click();
  await expect(memory.getByText("conflict review",{exact:true})).toBeVisible();
  await expect(memory.getByText("Active guidance: No",{exact:true})).toBeVisible();
  await expect(routing.getByText("tier1 review",{exact:true})).toBeVisible();
  await expect(routing.getByText("P1 / 85",{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});
