import { expect, test, type Page } from "@playwright/test";

async function login(page: Page, user: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Alert Triage" }).click();
  await expect(page.getByRole("heading", { name: "Alert Triage" })).toBeVisible();
}

test("real authenticated routing, approval and rejection", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await login(page, "g.ang", "analyst-demo");
  await page.getByLabel("Decision reason").fill("Admitted after evidence review");
  await page.getByRole("button", { name: "Admit to Tier 1" }).click();
  await expect(page.getByRole("status")).toContainText("recorded");
  await expect(page.getByText("NO", { exact: true })).toBeVisible();
  await page.getByLabel("Decision reason").fill("Manual escalation for deeper review");
  await page.getByRole("button", { name: "Manual Escalate" }).click();
  await expect(page.getByText("tier2 candidate", { exact: true })).toBeVisible();
  await page.getByLabel("Operational alert").selectOption({ index: 1 });
  await expect(page.getByText("YES", { exact: true })).toBeVisible();
  await expect(page.getByText("tier1 review", { exact: true })).toBeVisible();
  await page.locator('main').evaluate(element => { element.scrollTop = 0; });
  await page.screenshot({ path: "test-results/routing-recommendation-desktop.png", fullPage: true });
  await page.getByLabel("Decision reason").fill("Approve policy recommendation");
  await page.getByRole("button", { name: "Approve Tier 2" }).click();
  await expect(page.getByText("assessment", { exact: true })).toBeVisible();
  await page.getByLabel("Operational alert").selectOption({ index: 2 });
  await page.getByLabel("Decision reason").fill("Continue Tier 1 evidence gathering");
  await page.getByRole("button", { name: "Keep in Tier 1" }).click();
  await expect(page.getByRole("region", { name: "Latest routing decision" })).toContainText("Continue Tier 1");
  await expect(page.getByText("YES", { exact: true })).toBeVisible();
  await expect(page.getByText("tier1 review", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('main').evaluate(element => { element.scrollTop = 0; });
  await page.screenshot({ path: "test-results/routing-mobile.png", fullPage: true });
  expect(await page.locator('main').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  await page.getByRole('button', { name: 'Manual Escalate' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/routing-mobile-actions.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("evaluator can inspect but cannot route", async ({ page }) => {
  await login(page, "evaluator", "evaluator-demo");
  await expect(page.getByLabel("Operational alert")).toBeVisible();
  await expect(page.getByLabel("Decision reason")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Manual Escalate" })).toHaveCount(0);
});

test("analyst workflow orientation starts in triage and keeps legacy analysis optional", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/v2-triage$/);
  await expect(page.getByRole("heading", { name: "Alert Triage", exact: true })).toBeVisible();
  const navigation = page.getByRole("navigation", { name: "Main" });
  await expect(navigation.getByRole("link")).toHaveText([
    "Incoming Alerts", "Alert Triage", "Tier 2 Cases", "Triage Memory", "Selective Review",
    "Overview", "Dashboard", "Alert Queue", "Investigations", "Feedback Impact", "Legacy Flow Workstation",
  ]);
  await navigation.getByRole("link", { name: "Incoming Alerts", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Incoming Alerts", exact: true })).toBeVisible();
  await navigation.getByRole("link", { name: "Legacy Flow Workstation", exact: true }).click();
  await expect(page).toHaveURL(/\/analyst\/workstation$/);
  await expect(page.getByRole("heading", { name: "Legacy Flow Workstation", exact: true })).toBeVisible();
  await expect(page.getByText(/Historical recorded-flow analysis using the legacy Signature\/XGBoost pipeline/)).toBeVisible();
  await page.getByRole("tab", { name: /^Verdict/ }).click();
  await expect(page.getByRole("radio", { name: /Escalation Recommended/ })).toBeVisible();
  await page.screenshot({ path: "test-results/workflow-clarity-legacy.png" });
  await page.getByRole("link", { name: "Open Alert Triage", exact: true }).click();
  await expect(page).toHaveURL(/\/analyst\/v2-triage$/);
  await navigation.getByRole("link", { name: "Tier 2 Cases", exact: true }).click();
  await expect(page).toHaveURL(/\/analyst\/tier2-cases$/);
});
