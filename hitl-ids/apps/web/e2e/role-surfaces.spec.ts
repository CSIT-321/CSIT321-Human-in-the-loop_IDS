import { expect, test, type Page } from "@playwright/test";

// The two still-valid checks kept from the retired detector-foundation.spec.ts (moved to e2e/historical/).
// Admin IP reports: the 2026-11 admin home is /admin/overview (was /admin/status).

async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("admin IP security reports open from the current admin home", async ({ page }) => {
  await login(page, "admin", "admin-demo");
  await expect(page).toHaveURL(/\/admin\/overview/);
  await page.goto("/admin/reports/ip");
  await expect(page.getByRole("heading", { name: "IP Security Reports", exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "All source IPs" })).toBeVisible();
  await page.getByRole("button", { name: /^View report for/ }).first().click();
  await expect(page.getByRole("article", { name: "Generated IP security report" })).toBeVisible();
});

test("evaluator keeps scenario and metric navigation", async ({ page }) => {
  await login(page, "evaluator", "evaluator-demo");
  await expect(page).toHaveURL(/\/evaluator\/scenarios/);
  await expect(page.getByRole("heading", { name: "Evaluation scenarios", exact: true })).toBeVisible();
  await page.goto("/evaluator/metrics");
  await expect(page.getByRole("heading", { name: "Detection Metrics", exact: true })).toBeVisible();
});
