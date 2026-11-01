import { expect, test } from "@playwright/test";

test("whole-dataset operational workload, filters, priority, pagination, URL and responsive panes", async ({ page }) => {
  const errors: string[] = [], writes: string[] = [], queueRequests: URL[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => {
    const url = new URL(request.url());
    if (request.method() !== "GET" && url.pathname.startsWith("/api/")) writes.push(url.pathname);
    if (url.pathname === "/api/v2/alerts") queueRequests.push(url);
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  const initialQueue = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v2/alerts" && response.status() === 200);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  const workload = page.getByRole("region", { name: "Operational workload" });
  for (const name of ["Critical 54", "Tier 2 54", "Expert Review 2", "Needs Review 64", "No Immediate Review 2", "Tier 1 9", "Total Alerts 66"])
    await expect(workload.getByRole("button", { name, exact: true })).toBeVisible();
  await expect(workload.getByRole("link", { name: "Open Tier 2 Cases 54", exact: true })).toBeVisible();
  const queue = page.getByRole("list", { name: "Operational alerts" });
  const queueRegion = page.getByRole("region", { name: "Operational alert queue", exact: true });
  const views = page.getByRole("tablist", { name: "Operational queue views" });
  const scores = () => queue.locator('[aria-label^="Operational Priority:"]');
  await expect(queue.getByRole("button")).toHaveCount(50);
  await expect(queueRegion).toContainText("1–50 of 66");
  await expect(scores().first()).toHaveAttribute("aria-label", "Operational Priority: 95");
  expect(await scores().first().locator("span").first().evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(28);
  // The server response order is what the UI renders; all pages are globally ranked.
  const initialRows = (await (await initialQueue).json()).items;
  expect(initialRows.map((row: { state: { operationalPriority: number } }) => row.state.operationalPriority)).toEqual(Array(50).fill(95));
  expect(initialRows[0].title).toBe("SYNTHETIC Critical SQL injection 52");
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(true);
  await page.screenshot({ path: "test-results/queue-all-1440-dark.png", fullPage: true });
  await page.getByRole("button", { name: "Next alerts" }).click();
  await expect(queueRegion).toContainText("51–66 of 66");
  expect(await scores().evaluateAll(elements => elements.map(element => {
    const value = element.getAttribute("aria-label")!.split(": ")[1]; return value === "Unassigned" ? null : Number(value);
  }))).toEqual([95,95,85,85,65,65,40,40,40,40,40,40,40,20,20,null]);
  await views.getByRole("tab", { name: "Tier 2 54", exact: true }).click();
  await expect(queueRegion).toContainText("1–50 of 54");
  await expect(queue.getByRole("button")).toHaveCount(50);
  expect(await queue.getByRole("button").allTextContents()).toEqual(expect.arrayContaining([expect.stringContaining("Tier 2")]));
  expect((await queue.getByRole("button").allTextContents()).every(text => text.includes("Tier 2"))).toBe(true);
  await page.screenshot({ path: "test-results/queue-tier2.png", fullPage: true });
  await page.getByRole("button", { name: "Next alerts" }).click();
  await expect(queueRegion).toContainText("51–54 of 54");
  await expect(queue.getByRole("button")).toHaveCount(4);
  expect((await queue.getByRole("button").allTextContents()).every(text => text.includes("Tier 2"))).toBe(true);
  const values = (await scores().evaluateAll(elements => elements.map(element => Number(element.getAttribute("aria-label")!.split(": ")[1]))));
  expect(values).toEqual([95,95,65,65]);
  await views.getByRole("tab", { name: "Expert Review 2", exact: true }).click();
  await expect(queueRegion).toContainText("1–2 of 2");
  await expect(queue.getByRole("button")).toHaveCount(2);
  expect((await queue.getByRole("button").allTextContents()).every(text => text.includes("EXPERT") && text.includes("Unknown / Needs Expert"))).toBe(true);
  await page.screenshot({ path: "test-results/queue-expert.png", fullPage: true });
  await views.getByRole("tab", { name: "Tier 1 9", exact: true }).click();
  await expect(queueRegion).toContainText("1–9 of 9");
  await expect(queue.getByRole("button")).toHaveCount(9);
  expect((await queue.getByRole("button").allTextContents()).every(text => text.includes("Tier 1") && text.includes("Routine Review"))).toBe(true);
  expect(await scores().evaluateAll(elements => elements.map(element => Number(element.getAttribute("aria-label")!.split(": ")[1])))).toEqual([85,85,40,40,40,40,40,40,40]);
  await views.getByRole("tab", { name: "Needs Review 64", exact: true }).click();
  await expect(queueRegion).toContainText("1–50 of 64");
  expect((await queue.getByRole("button").allTextContents()).every(text => text.includes("Review Required: Yes"))).toBe(true);
  await views.getByRole("tab", { name: "No Immediate Review 2", exact: true }).click();
  await expect(queue.getByRole("button")).toHaveCount(2);
  await expect(queueRegion).toContainText("1–2 of 2");
  expect((await queue.getByRole("button").allTextContents()).every(text => text.includes("No Immediate Review") && text.includes("Review Required: No"))).toBe(true);
  await views.getByRole("tab", { name: "All 66", exact: true }).click();
  await page.getByLabel("Attack Type").selectOption("web_attack");
  await expect(queueRegion).toContainText("1–50 of 52");
  expect((await queue.getByRole("button").allTextContents()).every(text => text.includes("Web Attack"))).toBe(true);
  await queue.getByRole("button").first().click();
  await expect(page).toHaveURL(/alertRef=/);
  const saved = page.url();
  await page.reload();
  await expect(page).toHaveURL(saved);
  await expect(page.getByLabel("Attack Type")).toHaveValue("web_attack");
  await expect(views.getByRole("tab", { name: "All 66", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(queueRegion).toContainText("1–50 of 52");
  await expect(queue.getByRole("button").first()).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("complementary", { name: "Context and assistance" })).toBeVisible();
  await expect(page.getByRole("region", { name: "System Routing", exact: true })).toContainText("Critical Escalation");
  await page.screenshot({ path: "test-results/queue-attack-filter.png", fullPage: true });
  await page.getByRole("tab", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("table", { name: "Related Suricata signatures" })).toBeVisible();
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("link", { name: "Open Tier 2 Case", exact: true })).toBeVisible();
  // Search is also server-side and reaches the unassigned row beyond the first 50.
  await page.getByLabel("Attack Type").selectOption("");
  await page.getByLabel("Search operational alerts", { exact: true }).fill("historical compatibility");
  await expect(queueRegion).toContainText("1–1 of 1");
  await expect(scores().first()).toHaveAttribute("aria-label", "Operational Priority: Unassigned");
  await page.getByLabel("Search operational alerts", { exact: true }).fill("");
  await expect(queueRegion).toContainText("1–50 of 66");
  for (const width of [1440,1024,390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["dark","light"]) {
      if (await page.locator("html").getAttribute("data-theme") !== theme) await page.getByRole("button", { name: "Light theme", exact: true }).click();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(workload).toBeVisible();
      await expect(scores().first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `test-results/queue-all-${width}-${theme}.png`, fullPage: true });
    }
  }
  expect(queueRequests.some(url => url.searchParams.get("handlingRoute") === "tier2_case" && url.searchParams.get("offset") === "50")).toBe(true);
  expect(queueRequests.some(url => url.searchParams.get("routeClass") === "EXPERT_REVIEW_REQUIRED")).toBe(true);
  expect(queueRequests.some(url => url.searchParams.get("attackCategory") === "web_attack")).toBe(true);
  expect(queueRequests.every(url => url.searchParams.get("sort") === "priority_desc")).toBe(true);
  await expect(views.getByRole("tab", { name: /Rule \+ Model|Model Only|Rule Only|Not Flagged|Tier 2 Candidate/ })).toHaveCount(0);
  await expect(workload.getByText(/Verdicts|False Positives/i)).toHaveCount(0);
  expect(writes).toEqual(["/api/auth/login"]);
  expect(errors).toEqual([]);
});
