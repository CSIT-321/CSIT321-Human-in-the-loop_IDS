import { expect, test } from "@playwright/test";

test("real case assistance: Unknown, human investigation, related link, approved plan, Critical and Verdict handoff", async ({ page }) => {
  test.setTimeout(180_000);
  const errors: string[] = [];
  const writes: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (request.method() === "POST") writes.push(new URL(request.url()).pathname); });
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  const workspace = page.getByRole("region", { name: "Operational alert workspace", exact: true });
  async function select(title: string) {
    await page.goto("/analyst/operations");
    await page.getByLabel("Search operational alerts", { exact: true }).fill(title);
    const row = page.getByRole("list", { name: "Operational alerts" }).getByRole("button").first();
    await expect(row).toContainText(title); await row.click();
    await expect(workspace.getByRole("heading", { name: title, exact: true })).toBeVisible();
  }
  const assistance = page.getByRole("region", { name: "Investigation Assistance", exact: true });
  const brief = assistance.getByRole("region", { name: "Investigation Brief", exact: true });
  const related = assistance.getByRole("region", { name: "Potentially Related Alerts", exact: true });
  const steps = assistance.getByRole("region", { name: "Suggested Investigation Steps", exact: true });
  await select("SYNTHETIC Unresolved suspicious network activity 0");
  const beforeInspection = writes.length;
  await workspace.getByRole("link", { name: "Open Tier 2 Case", exact: true }).click();
  await expect(brief).toContainText("At Case Creation");
  await expect(brief).toContainText("EXPERT_REVIEW_REQUIRED");
  await expect(brief).toContainText("Unknown / Needs Expert");
  await expect(brief).toContainText("Not recorded / not required for automatic Tier 2 routing");
  await expect(related).toContainText("Same source IP");
  await expect(steps).toContainText("none of these steps has been executed");
  expect(writes.length).toBe(beforeInspection);
  await expect(page.getByRole("region", { name: "Case summary", exact: true })).toContainText("open");
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["dark", "light"]) {
      if (await page.locator("html").getAttribute("data-theme") !== theme)
        await page.getByRole("button", { name: "Light theme", exact: true }).click();
      await brief.scrollIntoViewIfNeeded();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      for (const region of [brief, related, steps]) {
        expect(await region.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
        await region.scrollIntoViewIfNeeded();
        await expect(region.getByRole("heading").first()).toBeVisible();
        await page.screenshot({ path: `test-results/assistance-${width}-${theme}-${await region.getAttribute("aria-label")}.png` });
      }
      await page.getByLabel("Investigation note", { exact: true }).scrollIntoViewIfNeeded();
      await expect(page.getByLabel("Investigation note", { exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await brief.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `test-results/assistance-${width}-${theme}.png`, fullPage: true });
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("tab", { name: "Audit Timeline", exact: true }).click();
  await page.getByLabel("Decision reason", { exact: true }).fill("SYNTHETIC human starts investigation after reviewing brief");
  await page.getByRole("button", { name: "Start investigation", exact: true }).click();
  await expect(brief).toContainText("Status: investigating");
  await page.getByRole("tab", { name: "Investigation Notes", exact: true }).click();
  await page.getByLabel("Investigation note", { exact: true }).fill("SYNTHETIC reviewed signatures and documented missing HTTP evidence");
  await page.getByRole("button", { name: "Add investigation note", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toContainText("SYNTHETIC reviewed signatures");
  // Select a suggestion, then supply a human reason through the existing linking command.
  const first = related.getByRole("article").first();
  const relatedHref = await first.getByRole("link").getAttribute("href");
  const linkRef = new URL(relatedHref!, "http://localhost").searchParams.get("alertRef")!;
  const beforeSelect = writes.length;
  await first.getByRole("button", { name: "Review link to Case" }).click();
  await expect(page.getByLabel("Operational alert UUID")).toHaveValue(linkRef);
  await expect(page.getByRole("button", { name: "Link alert", exact: true })).toBeDisabled();
  expect(writes.length).toBe(beforeSelect);
  await page.getByLabel("Decision reason", { exact: true }).fill("SYNTHETIC reviewed shared endpoints and event proximity");
  await page.getByRole("button", { name: "Link alert", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toContainText("V2_TIER2_ALERT_LINKED");
  await expect(page.getByRole("tabpanel").getByRole("link", { name: linkRef })).toBeVisible();
  await expect(related.locator(`a[href="${relatedHref}"]`)).toHaveCount(0);
  await page.getByRole("tab", { name: "Investigation Conclusion", exact: true }).click();
  await page.getByLabel("Human Investigation Finding", { exact: true }).selectOption("confirmed_malicious");
  await page.getByLabel("Investigation Reason", { exact: true }).fill("SYNTHETIC human corroborated malicious activity; assistance did not decide");
  await page.getByLabel("Human Final Attack Classification", {exact:true}).selectOption("web_attack");
  await page.getByRole("button", { name: "Record Investigation Conclusion", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toContainText("SYNTHETIC human corroborated");
  const responses = page.getByRole("region", { name: "Response Recommendations", exact: true });
  await responses.getByLabel("Proposal reason").fill("SYNTHETIC propose containment plan after human Finding");
  await responses.getByRole("button", { name: "Generate recommendation", exact: true }).click();
  const card = responses.getByRole("article", { name: "Block Source IP", exact: true });
  await expect(card).toContainText("Pending Human Approval");
  await card.getByLabel("Approval or rejection reason").fill("SYNTHETIC authorize plan only; do not execute");
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(card).toContainText("Approved - Not Executed");
  await expect(card).toContainText("V2_RESPONSE_APPROVED");
  await select("SYNTHETIC critical SQL injection");
  await workspace.getByRole("link", { name: "Open Tier 2 Case", exact: true }).click();
  await expect(brief).toContainText("CRITICAL_ESCALATION");
  await expect(brief).toContainText("web_attack");
  await brief.getByText("Current trusted context and provenance", { exact: true }).click();
  await expect(brief).toContainText("synthetic:critical-asset");
  await select("SYNTHETIC Known routine brute force");
  const verdict = workspace.getByRole("region", { name: "Analyst Verdict", exact: true });
  await verdict.getByLabel("Verdict outcome").selectOption("suspicious");
  await verdict.getByLabel("Verdict reason").fill("SYNTHETIC suspicious authentication requires deeper review");
  await verdict.getByRole("button", { name: "Record Verdict", exact: true }).click();
  await expect(verdict).toContainText("Current Verdict: Suspicious");
  await workspace.getByLabel("Decision reason", { exact: true }).fill("SYNTHETIC manual escalation after Suspicious Verdict");
  await workspace.getByRole("button", { name: "Escalate to Tier 2", exact: true }).click();
  await workspace.getByRole("link", { name: "Open Tier 2 Case", exact: true }).click();
  await expect(brief).toContainText("Manual analyst escalation");
  await expect(brief).toContainText("Current Tier 1 Verdict: suspicious");
  await expect(brief).toContainText("SYNTHETIC suspicious authentication requires deeper review");
  await expect(brief).toContainText("ROUTINE_REVIEW");
  expect(errors).toEqual([]);
  expect(writes.some(path => /execute|collection/.test(path))).toBe(false);
});
