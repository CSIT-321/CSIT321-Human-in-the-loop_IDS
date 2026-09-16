import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const CAPTURE_DIR = process.env.THEME_CAPTURE_DIR;

async function chooseTheme(page: Page, theme: "light" | "dark") {
  await page.evaluate((next) => {
    window.localStorage.setItem("hitl-ids-theme", next);
  }, theme);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

async function signIn(page: Page, username: string, password: string, home: string) {
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(new RegExp(`${home}$`));
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

test("the selected theme survives a browser reload", async ({ page }) => {
  await page.goto("/login");
  await page.evaluate(() => window.localStorage.removeItem("hitl-ids-theme"));
  await page.reload();

  const initial = await page.locator("html").getAttribute("data-theme");
  const next = initial === "dark" ? "light" : "dark";
  await page.getByRole("button", { name: `Switch to ${next} theme` }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", next);

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", next);
  await expect(page.getByRole("button", { name: `Switch to ${initial} theme` })).toBeVisible();
});

test("capture light and dark role views", async ({ page }) => {
  test.skip(CAPTURE_DIR === undefined, "set THEME_CAPTURE_DIR to capture the theme review");
  const output = resolve(CAPTURE_DIR!);
  mkdirSync(output, { recursive: true });

  await page.goto("/login");
  await chooseTheme(page, "light");
  await page.screenshot({ path: `${output}/login-light.png`, fullPage: true, animations: "disabled" });
  await chooseTheme(page, "dark");
  await page.screenshot({ path: `${output}/login-dark.png`, fullPage: true, animations: "disabled" });

  await chooseTheme(page, "light");
  await signIn(page, "g.ang", "analyst-demo", "/analyst/workstation");
  await expect(page.getByRole("heading", { level: 1, name: "Workstation" })).toBeVisible();
  await expect(page.getByText("Loading...")).toHaveCount(0);
  await page.screenshot({ path: `${output}/workstation-light.png`, fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ path: `${output}/workstation-dark.png`, fullPage: true, animations: "disabled" });

  await signOut(page);
  await chooseTheme(page, "light");
  await signIn(page, "admin", "admin-demo", "/admin/status");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Guardrails" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Guardrails" })).toBeVisible();
  await page.screenshot({ path: `${output}/guardrails-light.png`, fullPage: true, animations: "disabled" });

  await signOut(page);
  await chooseTheme(page, "dark");
  await signIn(page, "evaluator", "evaluator-demo", "/evaluator/scenarios");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Detection Metrics" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Detection metrics" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Per class" })).toBeVisible();
  await page.screenshot({ path: `${output}/evaluator-metrics-dark.png`, fullPage: true, animations: "disabled" });
});
