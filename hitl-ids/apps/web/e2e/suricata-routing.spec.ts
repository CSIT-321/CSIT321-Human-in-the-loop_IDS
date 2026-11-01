import { expect, test } from "@playwright/test";

test("correlated Suricata: routine, multiple signatures, automatic expert/critical cases and manual override", async ({ page }) => {
  const errors: string[] = [];
  const writes: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (request.method() === "POST") writes.push(new URL(request.url()).pathname); });
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  const queue = page.getByRole("list", { name: "Operational alerts" });
  await expect(queue.getByRole("button")).toHaveCount(6);
  const select = async (text: string) => {
    await queue.getByRole("button").filter({ hasText: text }).click();
    await expect(page.getByRole("heading", { name: "System Routing", exact: true })).toBeVisible();
  };
  // A: known, routine detection with alert + flow + SSH.
  await select("SYNTHETIC Possible SSH brute force");
  await expect(page.getByRole("region", { name: "System Routing", exact: true })).toContainText("Routine Review");
  await expect(page.getByText("brute force", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Manual Escalation / Override" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve Tier 2" })).toHaveCount(0);
  await expect(page.getByText(/Human routing decision|Tier 2 Recommended/)).toHaveCount(0);
  await page.getByRole("tab", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Flow / Session Evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Application Evidence" })).toBeVisible();
  await expect(page.getByText(/OpenSSH_9.6/).first()).toBeVisible();
  await expect(page.getByText("Unavailable — no validated feature bridge")).toBeVisible();
  // B: two signatures, one detection; severity 1 alone remains routine.
  await select("SYNTHETIC SSH brute force");
  await expect(page.getByRole("region", { name: "System Routing", exact: true })).toContainText("Routine Review");
  await page.getByRole("tab", { name: "Evidence", exact: true }).click();
  const signatures = page.getByRole("table", { name: "Related Suricata signatures" });
  await expect(signatures.getByRole("row")).toHaveCount(3);
  await expect(signatures).toContainText("SYNTHETIC SSH password guessing");
  await expect(signatures).toContainText("SYNTHETIC SSH brute force");
  const multiRef = new URL(page.url()).searchParams.get("alertRef")!;
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["dark", "light"]) {
      await page.evaluate(theme => document.documentElement.setAttribute("data-theme", theme), theme);
      await expect(signatures).toBeVisible();
      await signatures.scrollIntoViewIfNeeded();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `test-results/suricata-evidence-${width}-${theme}.png`, fullPage: true });
      await page.getByRole("tab", { name: "Overview", exact: true }).click();
      await expect(page.getByRole("heading", { name: "System Routing", exact: true })).toBeVisible();
      await page.getByRole("region", { name: "System Routing", exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `test-results/suricata-routing-${width}-${theme}.png`, fullPage: true });
      await page.getByRole("tab", { name: "Evidence", exact: true }).click();
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  // C/D: real cases exist without any escalation/approval POST.
  for (const [title, routeClass] of [["SYNTHETIC Unresolved encrypted protocol pattern", "Expert Review Required"], ["SYNTHETIC SQL injection attempt", "Critical Escalation"]]) {
    await select(title);
    await expect(page.getByRole("region", { name: "System Routing", exact: true })).toContainText(routeClass);
    if (routeClass === "Expert Review Required") await expect(page.getByRole("tabpanel", { name: "Overview" }).getByText("Unknown / Needs Expert", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve Tier 2" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Escalate to Tier 2" })).toHaveCount(0);
    const alertUrl = page.url();
    await page.getByRole("link", { name: "Open Tier 2 Case", exact: true }).click();
    await expect(page.getByRole("region", { name: "Case summary" })).toContainText("Unassigned");
    await expect(page.getByRole("region", { name: "Case summary" })).toContainText("System Policy");
    await expect(page.getByRole("heading", { name: "System Routing at Creation" })).toBeVisible();
    await page.getByRole("tab", { name: "Audit Timeline" }).click();
    await expect(page.getByRole("tabpanel")).toContainText("V2_TIER2_CASE_CREATED / System Policy");
    await expect(page.getByRole("tabpanel")).not.toContainText("actor #");
    await page.goto(alertUrl);
  }
  expect(writes.filter(path => path.includes("/tier2/"))).toEqual([]);
  // E: authenticated manual override remains a single compound command.
  await select("SYNTHETIC Port scan manual override fixture");
  await page.getByLabel("Decision reason").fill("SYNTHETIC analyst override after inspecting correlated evidence");
  const response = page.waitForResponse(response => response.url().endsWith("/tier2/escalate-case") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Escalate to Tier 2", exact: true }).click();
  const result = await (await response).json();
  expect(result.case.decisionSource).toBe("analyst");
  expect(result.case.createdByActorId).toBeGreaterThan(0);
  expect(result.audit.decisionSource).toBe("analyst");
  expect(result.view.state.handlingRoute).toBe("tier2_case");
  await expect(page.getByRole("heading", { name: "Escalated to Tier 2" })).toBeVisible();
  await expect(page.getByRole("region", { name: "System Routing", exact: true })).toContainText("Manual Escalation / Override");
  await expect(page.getByRole("region", { name: "System Routing", exact: true })).toContainText("Initial system route: Tier 1 (Routine Review)");
  await expect(page.getByText(/Tier 2 Candidate|Create Tier 2 Case/)).toHaveCount(0);
  await page.getByRole("tab", { name: "History & Notes" }).click();
  await expect(page.getByRole("region", { name: "Operational decision history" })).toContainText("Actor #");
  await page.goto("/analyst/v2-triage?alertRef=" + multiRef);
  await expect(page.getByRole("heading", { name: "Analyst Workstation", exact: true })).toBeVisible();
  await select("Legacy Flow Detector");
  await page.getByRole("tab", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Historical XGBoost Evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Historical Signature Evidence" })).toBeVisible();
  expect(writes.filter(path => path.includes("/tier2/"))).toHaveLength(1);
  expect(writes.some(path => /collection|prospective|protocol/.test(path))).toBe(false);
  expect(errors).toEqual([]);
});
