import { expect, test, type Page } from "@playwright/test";

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.locator("main").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
}

test("original console, persisted preferences and responsive deep links", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workstation", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Alert queue", exact: true })).toBeVisible();
  await expect(page.getByText("Legacy Flow Detector", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/refinement-workstation-dark.png" });

  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["dark", "light"]) {
      const toggle = page.getByRole("button", { name: "Light theme", exact: true });
      if (await toggle.getAttribute("aria-pressed") !== String(theme === "light")) await toggle.click();
      await page.goto("/analyst/dashboard");
      await expect(page.getByRole("heading", { name: "Legacy Detector Composition" })).toBeVisible();
      await noOverflow(page);
      await page.screenshot({ path: `test-results/refinement-dashboard-${width}-${theme}.png` });
      const collapse = page.getByRole("button", { name: "Collapse sidebar" });
      await collapse.focus(); await page.keyboard.press("Enter");
      await page.reload();
      await expect(page.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
      await expect(toggle).toHaveAttribute("aria-pressed", String(theme === "light"));
      await page.screenshot({ path: `test-results/refinement-collapsed-${width}-${theme}.png` });
      for (const [label, route] of [["Incoming Alerts", "/analyst/external-admission"], ["Analyst Workspace", "/analyst/v2-triage"]]) {
        const link = page.getByRole("link", { name: label, exact: true });
        await link.scrollIntoViewIfNeeded(); await link.click();
        await expect(page).toHaveURL(new RegExp(route + "$"));
        await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();
        await noOverflow(page);
        await page.screenshot({ path: `test-results/refinement-${label.replaceAll(" ", "-")}-${width}-${theme}.png` });
      }
      for (const route of ["/analyst/queue", "/analyst/selective-review"]) {
        await page.goto(route);
        await expect(page.getByRole("table").first()).toBeVisible();
        await noOverflow(page);
      }
      await page.goto("/analyst/workstation");
      await expect(page.getByRole("tab", { name: "Overview", exact: true })).toBeVisible();
      await noOverflow(page);
      await page.getByRole("tab", { name: "History", exact: true }).scrollIntoViewIfNeeded();
      await page.getByRole("tab", { name: "History", exact: true }).click();
      await page.screenshot({ path: `test-results/refinement-workstation-${width}-${theme}.png` });
      await page.getByRole("button", { name: "Expand sidebar" }).click();
    }
  }
  expect(errors).toEqual([]);
});

test("canonical detector fixtures do not inherit historical flow evidence", async ({ page }) => {
  // Presentation fixtures only: no new detector or backend route is introduced.
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  const fullPage = page.getByRole("link", { name: "Open full page" });
  await expect(fullPage).toBeVisible();
  const url = (await fullPage.getAttribute("href"))!;
  let source = "suricata";
  let shap = false;
  await page.route("**/api/alerts/" + url.split("/").at(-1), async route => {
    const response = await route.fetch();
    const detail = await response.json();
    detail.detector = { ...detail.detector, detectorSource: source,
      detectorName: source === "suricata" ? "Suricata" : "XGBoost", detectorVersion: "synthetic-v1",
      detectorSeverity: 2, detectionTitle: "SYNTHETIC detector presentation fixture",
      confidence: source === "suricata" ? null : .82, structuredEvidence: { mlPredictedClass: "Port Scan" } };
    detail.ml = { ...detail.ml, predictedClass: "Port Scan", probability: .82, modelVersion: "synthetic-v1",
      topSupporting: shap ? detail.ml.topSupporting : [], topOpposing: [] };
    await route.fulfill({ response, json: detail });
  });
  for (const theme of ["dark", "light"]) {
    for (source of ["suricata", "xgboost"]) {
      await page.goto(url);
      const toggle = page.getByRole("button", { name: "Light theme" });
      if (await toggle.getAttribute("aria-pressed") !== String(theme === "light")) await toggle.click();
      const provenance = page.getByRole("region", { name: "Detector provenance" });
      await expect(provenance.getByText(source === "suricata" ? "Suricata" : "XGBoost", { exact: true })).toBeVisible();
      await expect(page.getByText("Combined explanation", { exact: true })).toHaveCount(0);
      await expect(page.getByText(/Contributions are TreeSHAP/)).toHaveCount(0);
      if (source === "suricata") {
        await expect(provenance.getByText("Not provided", { exact: true })).toBeVisible();
        await expect(page.getByText("Model prediction", { exact: true })).toHaveCount(0);
      } else {
        await expect(provenance.getByText("Port Scan", { exact: true })).toBeVisible();
        await expect(provenance).toContainText("82");
      }
      await page.screenshot({ path: `test-results/refinement-${source}-${theme}.png` });
      await noOverflow(page);
    }
  }
  source = "xgboost"; shap = true;
  await page.goto(url);
  await expect(page.getByText(/Contributions are TreeSHAP/)).toBeVisible();
  await page.screenshot({ path: "test-results/refinement-xgboost-shap.png" });
});
