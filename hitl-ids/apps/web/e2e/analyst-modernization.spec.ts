import { expect, test } from "@playwright/test";

test("modernized analyst workflow, preferences, themes and responsive evidence", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/analyst\/dashboard$/);
  await expect(page.getByText("Needs Human Review", {exact:true})).toBeVisible();
  await page.screenshot({path:"test-results/modern-dark-dashboard.png"});
  await page.getByRole("button",{name:"Collapse sidebar",exact:true}).click();
  await page.reload(); await expect(page.getByRole("button",{name:"Expand sidebar",exact:true})).toBeVisible();
  await expect(page.getByText("Needs Human Review",{exact:true})).toBeVisible();
  await page.screenshot({path:"test-results/modern-collapsed-dashboard.png"});
  await page.getByRole("button",{name:"Switch to Light theme"}).click();await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme","light");
  await expect(page.getByText("Needs Human Review",{exact:true})).toBeVisible();
  await page.screenshot({path:"test-results/modern-light-dashboard.png"});
  await page.getByRole("button",{name:"Expand sidebar",exact:true}).click();
  await page.getByRole("button",{name:"Switch to Dark theme"}).click();
  await page.getByRole("link", { name: "Incoming Alerts", exact: true }).click();
  await expect(page.getByLabel("Staged alert")).toBeVisible();
  await page.screenshot({path:"test-results/modern-incoming.png"});
  const option = page.locator("#external-alert option").filter({ hasText: "(staged)" }).first();
  await expect(option).toHaveCount(1);
  await page.getByLabel("Staged alert").selectOption((await option.getAttribute("value"))!);
  await page.getByLabel("Eligibility decision").selectOption("accepted");
  await page.getByLabel("Decision reason").fill("Source and canonical evidence verified");
  await page.getByRole("button", { name: "Record eligibility review" }).click();
  await expect(page.getByRole("status")).toContainText("Eligibility decision recorded");
  await page.getByLabel("Decision reason").fill("Admit for operational review");
  await page.getByRole("button", { name: "Admit to HITL Workflow" }).click();
  await expect(page.getByRole("status")).toContainText("Operational admission completed");
  await page.getByRole("link", { name: "Open in Analyst Workspace" }).click();
  await expect(page.getByText("tier1 review", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create Tier 2 Case", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"Evidence & Safety",exact:true})).toBeVisible();
  await expect(page.getByRole("region",{name:"Detector provenance"})).toContainText("Suricata");
  await expect(page.getByRole("region",{name:"Detector provenance"})).toContainText("Not provided");
  await page.screenshot({path:"test-results/modern-suricata-workspace.png"});
  for (const width of [1024,390]) {
    await page.setViewportSize({width,height:844});
    expect(await page.locator("main").evaluate(e=>e.scrollWidth<=e.clientWidth)).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  await page.screenshot({path:"test-results/modern-mobile-workspace.png"});
  await page.getByRole("button",{name:"Switch to Light theme"}).click();await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme","light");
  await page.screenshot({path:"test-results/modern-light-mobile.png"});
  await page.getByRole("button",{name:"Navigation"}).click();await page.getByRole("link",{name:"Analyst Workspace",exact:true}).click();
  await page.goBack();
  await page.setViewportSize({width:1440,height:900});
  await page.getByRole("button",{name:"Switch to Dark theme"}).click();
  await page.getByLabel("Decision reason").fill("Unresolved source-host investigation");
  await page.getByRole("button", { name: "Manual Escalate" }).click();
  await expect(page.getByText("tier2 candidate", { exact: true })).toBeVisible();
  await expect(page.getByText("A formal Tier 2 Case has not been created yet.")).toBeVisible();
  await page.screenshot({path:"test-results/modern-tier2-candidate.png"});
  await page.getByLabel("Case title").fill("Suricata source-host investigation");
  await page.getByLabel("Tier 1 handoff summary").fill("Review source host and related destination activity");
  await page.getByLabel("Case creation reason").fill("Formal investigation requires an owner");
  await page.getByRole("button", { name: "Create Tier 2 Case", exact: true }).click();
  await expect(page).toHaveURL(/tier2-cases\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: "Suricata source-host investigation" })).toBeVisible();
  await expect(page.getByText("No response recommendations.", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Audit Timeline" }).click();
  await page.getByLabel("Decision reason").fill("Begin deeper analysis");
  await page.getByRole("button", { name: "Start investigation" }).click();
  await expect(page.getByText("investigating", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Investigation Notes" }).click();
  await page.getByLabel("Investigation note").fill("Affected account identified; additional host requires review.");
  await page.getByRole("button", { name: "Add investigation note" }).click();
  await expect(page.getByRole("tabpanel")).toContainText("Affected account identified");
  await page.getByRole("tab", { name: "Findings" }).click();
  await page.getByLabel("Finding", { exact: true }).selectOption("suspicious");
  await page.getByLabel("Decision reason").fill("Suspicious activity needs corroboration; no response authorized.");
  await page.getByRole("button", { name: "Record finding" }).click();
  await expect(page.getByRole("tabpanel")).toContainText("Suspicious activity needs corroboration");
  await page.locator("main").evaluate(element => { element.scrollTop = 0; });
  await page.screenshot({ path: "test-results/tier2-case-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("main").evaluate(element => { element.scrollTop = 0; });
  await page.screenshot({ path: "test-results/tier2-case-mobile.png", fullPage: true });
  expect(await page.locator("main").evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  await page.getByRole("button", { name: "Record finding" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/tier2-case-mobile-investigation.png", fullPage: true });
  await page.getByRole("link", { name: "Primary alert", exact: true }).click();
  await expect(page.getByText("tier2 case", { exact: true })).toBeVisible();
  await expect(page.getByText("investigation", { exact: true })).toBeVisible();
  await page.goto("/analyst/v2-triage"); await expect(page.getByRole("heading",{name:"Analyst Workspace",exact:true})).toBeVisible();
  await page.goto("/analyst/external-admission"); await expect(page.getByRole("heading",{name:"Incoming Alerts",exact:true})).toBeVisible();
  await page.setViewportSize({width:1440,height:900});
  await page.goto("/analyst/workstation");
  await expect(page.getByText("Legacy detector evidence — Signature + XGBoost. Historical compatibility evidence.")).toBeVisible();
  await page.screenshot({path:"test-results/modern-legacy.png"});
  expect(errors).toEqual([]);
});


test("light and dark responsive operations retain keyboard controls and contained tables", async ({page}) => {
  await page.goto("/login"); await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password",{exact:true}).fill("analyst-demo");
  await page.getByRole("button",{name:"Sign in"}).click(); await expect(page).toHaveURL(/analyst\/dashboard$/);
  const toggle=page.getByRole("button",{name:"Collapse sidebar",exact:true});
  await toggle.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("button",{name:"Expand sidebar",exact:true})).toBeFocused();
  for (const theme of ["dark","light"]) {
    if(theme === "light") await page.getByRole("button",{name:"Switch to Light theme"}).click();
    for (const width of [1440,1024,390]) {
      await page.setViewportSize({width,height:900});
      for (const route of ["dashboard","inbox","workspace","tier2-cases","triage-memory","selective-review","analytics","legacy-analytics"]) {
        await page.goto("/analyst/"+route); await expect(page.locator("main h1")).toBeVisible();
        await expect(page.locator("main").getByRole("status")).toHaveCount(0);
        expect(await page.locator("main").evaluate(e=>e.scrollWidth<=e.clientWidth)).toBe(true);
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
        if(route === "dashboard" && width < 1440) await page.screenshot({path:`test-results/modern-${theme}-dashboard-${width}.png`});
      }
    }
  }
});
