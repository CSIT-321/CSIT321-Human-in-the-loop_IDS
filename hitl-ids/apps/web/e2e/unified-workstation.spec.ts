import { expect, test } from "@playwright/test";

test("one operational workstation: evidence, context, direct cases, compatibility and responsive themes", async ({ page }) => {
  const errors: string[] = [];
  const writes: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (request.method() === "POST") writes.push(new URL(request.url()).pathname); });
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link")).toHaveText(["Analyst Workstation", "Tier 2 Cases", "Triage Memory", "Selective Review", "Dashboard", "Incoming Alerts"]);
  const queue = page.getByRole("list", { name: "Operational alerts" });
  await expect(queue.getByRole("button").first()).toBeVisible();
  await queue.getByRole("button").filter({ hasText: "SYNTHETIC unified-workstation journey" }).first().click();
  const selected = new URL(page.url()).searchParams.get("alertRef")!;
  await page.getByRole("tab", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Suricata Rule Evidence" })).toBeVisible();
  await expect(page.getByText("Confidence", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Detector provenance" })).toContainText("Not provided");
  await expect(page.getByText(/TreeSHAP|Historical Signature Evidence|Historical XGBoost/)).toHaveCount(0);
  await expect(page.getByRole("complementary", { name: "Context and assistance" })).toContainText("Related Triage Memory");
  await expect(page.getByRole("complementary", { name: "Context and assistance" })).toContainText("Review Disposition / Trusted Context");
  await page.getByRole("tab", { name: "Context & Review" }).click();
  await expect(page.getByRole("heading", { name: "Selective Human Review" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Trusted Context / Safety Evidence", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Triage Memory", exact: true }).click();
  await expect(page.getByText("Guidance only — human review still required.").first()).toBeVisible();
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  // The staged alert is deliberately unassigned; Tier 1 admission stays a distinct human action.
  await page.getByLabel("Decision reason").fill("SYNTHETIC: admit source for analyst review");
  await page.getByRole("button", { name: "Admit to Tier 1" }).click();
  await expect(page.getByRole("button", { name: "Escalate to Tier 2", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/unified-desktop-dark.png" });
  const caseRefs: string[] = [];
  for (let index = 0; index < 2; index++) {
    if (index === 1) {
      await queue.getByRole("button").filter({ hasText: "SYNTHETIC unified-workstation journey" }).nth(1).click();
    }
    await page.getByLabel("Decision reason").fill(`SYNTHETIC: deeper Tier 2 investigation ${index}`);
    const response = page.waitForResponse(response => response.url().endsWith("/tier2/escalate-case") && response.request().method() === "POST");
    const before = page.url();
    await page.getByRole("button", { name: "Escalate to Tier 2", exact: true }).click();
    const result = await (await response).json();
    caseRefs.push(result.case.caseRef);
    expect(result.view.state.handlingRoute).toBe("tier2_case");
    await expect(page.getByRole("heading", { name: "Escalated to Tier 2", exact: true })).toBeVisible();
    await expect(page).toHaveURL(before);
    await expect(page.getByText(/Tier 2 Candidate|Create Tier 2 Case/)).toHaveCount(0);
    await expect(page.getByLabel("Case title")).toHaveCount(0);
    await page.screenshot({ path: `test-results/unified-direct-success-${index}.png` });
    if (index === 0) {
      await page.getByRole("button", { name: "Continue Reviewing", exact: true }).click();
      await expect(page).toHaveURL(before);
      await expect(queue.getByRole("button").first()).toBeEnabled();
    } else {
      await page.getByRole("link", { name: "Open Tier 2 Case", exact: true }).click();
      await expect(page).toHaveURL(new RegExp("/tier2-cases/" + result.case.caseRef + "$"));
      await expect(page.getByRole("tab", { name: "Findings" })).toBeVisible();
      await expect(page.getByRole("region", { name: "Response Recommendations" })).toBeVisible();
    }
  }
  await page.goto("/analyst/v2-triage?alertRef=" + selected);
  await expect(page.getByRole("heading", { name: "Analyst Workstation", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Tier 2 Case", exact: true })).toHaveAttribute("href", "/analyst/tier2-cases/" + caseRefs[0]);
  await page.reload();
  await expect(page.getByRole("link", { name: "Open Tier 2 Case", exact: true })).toBeVisible();
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["dark", "light"]) {
      await page.evaluate(theme => document.documentElement.setAttribute("data-theme", theme), theme);
      await page.getByRole("tab", { name: "Evidence", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Suricata Rule Evidence" })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `test-results/unified-suricata-${width}-${theme}.png`, fullPage: true });
      if (width === 390) {
        await page.locator(".ops-detail").evaluate(element => element.scrollIntoView({ block: "start" }));
        await page.screenshot({ path: `test-results/unified-mobile-evidence-${theme}.png` });
        await page.locator(".ops-context").evaluate(element => element.scrollIntoView({ block: "start" }));
        await page.screenshot({ path: `test-results/unified-mobile-context-${theme}.png` });
      }
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await queue.getByRole("button").filter({ hasText: "Legacy Flow Detector" }).click();
  await page.getByRole("tab", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Historical XGBoost Evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Historical Signature Evidence" })).toBeVisible();
  await page.screenshot({ path: "test-results/unified-legacy-canonical.png" });
  await page.goto("/analyst/workstation");
  await expect(page.getByRole("heading", { name: "Legacy Flow Workstation", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Analyst Workstation" })).toHaveAttribute("href", "/analyst/operations");
  expect(writes.filter(path => path.includes("/tier2/"))).toEqual([`/api/v2/alerts/${selected}/tier2/escalate-case`, expect.stringMatching(/\/tier2\/escalate-case$/)]);
  expect(errors).toEqual([]);
});

test("XGBoost canonical presentation fixture renders supplied attributions", async ({ page }) => {
  // Pure ML is a presentation fixture, not a new detector/admission implementation.
  // The main operational journey above uses the real backend without request interception.
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  await page.route("**/api/v2/alerts?*", async route => {
    const response = await route.fetch();
    const queue = await response.json();
    queue.items[0] = { ...queue.items[0], detectorSource: "xgboost", detectorName: "XGBoost", title: "SYNTHETIC XGBoost: PortScan" };
    await route.fulfill({ response, json: queue });
  });
  await page.route("**/api/v2/alerts/*/evidence", async route => {
    const response = await route.fetch();
    const alert = await response.json();
    alert.detectorEvidence = { ...alert.detectorEvidence, detectorSource: "xgboost", detectorName: "XGBoost", detectorVersion: "SYNTHETIC-model-v1", confidence: 0.91,
      structuredEvidence: { mlPredictedClass: "PortScan", treeShap: { topSupportingFeatures: [{ featureName: "Flow Duration", featureValue: 10, shapContribution: 0.42 }] } } };
    await route.fulfill({ response, json: alert });
  });
  await page.reload();
  await page.getByRole("tab", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Model Evidence", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "TreeSHAP evidence" })).toContainText("Flow Duration");
  await expect(page.getByRole("heading", { name: "Historical Signature Evidence" })).toHaveCount(0);
  await page.screenshot({ path: "test-results/unified-xgboost-presentation.png" });
});
