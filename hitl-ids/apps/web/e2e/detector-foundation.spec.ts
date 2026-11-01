import { expect, test, type Page } from "@playwright/test";

async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("analyst sees provenance and retains investigation workflow", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await login(page, "g.ang", "analyst-demo");
  await expect(page).toHaveURL(/\/analyst\/v2-triage/);
  await page.getByRole("link", { name: "Legacy Flow Workstation", exact: true }).click();
  await expect(page.getByRole("region", { name: "Detector provenance" })).toBeVisible();
  await expect(page.getByText("Legacy Flow Detector", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: /^Verdict/ }).click();
  await expect(page.getByRole("button", { name: "Record verdict" })).toBeVisible();
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await page.screenshot({ path: "test-results/detector-analyst.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("admin IP reports remain available", async ({ page }) => {
  await login(page, "admin", "admin-demo");
  await expect(page).toHaveURL(/\/admin\/status/);
  await page.goto("/admin/reports/ip");
  await expect(page.getByRole("heading", { name: "IP Security Reports", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "All Source IPs", exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "All source IPs" })).toBeVisible();
  await page.getByRole("button", { name: /^View report for/ }).first().click();
  await expect(page.getByRole("article", { name: "Generated IP security report" })).toBeVisible();
  await page.screenshot({ path: "test-results/detector-admin.png", fullPage: true });
});

test("evaluator retains scenario and metric navigation", async ({ page }) => {
  await login(page, "evaluator", "evaluator-demo");
  await expect(page).toHaveURL(/\/evaluator\/scenarios/);
  await expect(page.getByRole("heading", { name: "Evaluation scenarios", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open run", exact: false })).toBeVisible();
  await page.goto("/evaluator/metrics");
  await expect(page.getByRole("heading", { name: "Detection Metrics", exact: true })).toBeVisible();
  await expect(page.getByText("Score saturation", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/detector-evaluator.png", fullPage: true });
});
