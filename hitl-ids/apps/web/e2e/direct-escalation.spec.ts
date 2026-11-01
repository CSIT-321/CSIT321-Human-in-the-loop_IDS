import { expect, test, type Page } from "@playwright/test";

async function admitNext(page: Page) {
  await page.getByRole("link", { name: "Incoming Alerts", exact: true }).click();
  const staged = page.locator("#external-alert option").filter({ hasText: "(staged)" }).first();
  await page.getByLabel("Staged alert").selectOption((await staged.getAttribute("value"))!);
  await page.getByLabel("Eligibility decision").selectOption("accepted");
  await page.getByLabel("Decision reason").fill("SYNTHETIC direct escalation: canonical source verified");
  await page.getByRole("button", { name: "Record eligibility review" }).click();
  await expect(page.getByRole("status")).toContainText("Eligibility decision recorded");
  await page.getByLabel("Decision reason").fill("SYNTHETIC direct escalation: admit for Tier 1 triage");
  await page.getByRole("button", { name: "Admit to HITL Workflow" }).click();
  await expect(page.getByRole("status")).toContainText("Operational admission completed");
  await page.getByRole("link", { name: "Open Alert Triage" }).click();
  await expect(page.getByText("tier1 review", { exact: true })).toBeVisible();
}

test("one escalation creates a case, stays on the alert, and supports both result actions", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/v2-triage$/);
  await expect(page.getByRole("heading", { name: "Alert Triage", exact: true })).toBeVisible();
  const navigation = page.getByRole("navigation", { name: "Main" }).getByRole("link");
  await expect(navigation.nth(0)).toHaveText("Incoming Alerts");
  await expect(navigation.nth(1)).toHaveText("Alert Triage");
  await expect(navigation.nth(2)).toHaveText("Tier 2 Cases");
  await expect(navigation.last()).toHaveText("Legacy Flow Workstation");
  const cases: string[] = [];
  for (let index = 0; index < 2; index++) {
    await admitNext(page);
    const url = page.url();
    const reason = `SYNTHETIC direct escalation ${index}: unresolved source evidence`;
    await page.getByLabel("Decision reason").fill(reason);
    const resultPromise = page.waitForResponse(response => response.url().endsWith("/tier2/escalate-case") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Escalate to Tier 2", exact: true }).click();
    const result = await (await resultPromise).json();
    cases.push(result.case.caseRef);
    await expect(page.getByRole("heading", { name: "Escalated to Tier 2", exact: true })).toBeVisible();
    await expect(page.getByText("Tier 2 Case created successfully.", { exact: true })).toBeVisible();
    await expect(page.getByText("Case: " + result.case.caseRef, { exact: true })).toBeVisible();
    await expect(page).toHaveURL(url);
    await expect(page.getByText(/tier.?2 candidate|assessment/i)).toHaveCount(0);
    await expect(page.getByLabel("Case title")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Create Tier 2 Case", exact: true })).toHaveCount(0);
    if (index === 1) {
      await page.getByRole("button", { name: "Continue Reviewing", exact: true }).click();
      await expect(page).toHaveURL(url);
      await expect(page.getByRole("status", { name: "Tier 2 escalation result" })).toHaveCount(0);
      await page.reload();
    }
    const open = page.getByRole("link", { name: "Open Tier 2 Case", exact: true });
    await expect(open).toHaveAttribute("href", "/analyst/tier2-cases/" + result.case.caseRef);
    await open.click();
    await expect(page).toHaveURL(new RegExp("/tier2-cases/" + result.case.caseRef + "$"));
    await expect(page.getByRole("heading", { name: result.case.title, exact: true })).toBeVisible();
    await expect(page.getByText(reason, { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Confidence: Not provided", { exact: true })).toBeVisible();
    expect(result.case.snapshot.escalationReason).toBe(reason);
    expect(result.case.snapshot.tier1HandoffSummary).toContain(reason);
  }
  await page.getByRole("link", { name: "Tier 2 Cases", exact: true }).click();
  for (const ref of cases) await expect(page.getByRole("link", { name: ref.slice(0, 8), exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/direct-created-cases.png" });
  expect(errors).toEqual([]);
});
