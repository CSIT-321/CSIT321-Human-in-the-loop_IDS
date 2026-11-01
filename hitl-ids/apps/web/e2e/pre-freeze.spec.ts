import { expect, test } from "@playwright/test";

test("F1–F7 real operational journey, capture isolation and responsive semantics", async ({ page }) => {
  const errors: string[] = []; let authorization = "";
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (request.url().includes("/api/v2/alerts")) authorization = request.headers()["authorization"] ?? authorization; });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  const workload = page.getByRole("region", { name: "Operational workload" });
  const queue = page.getByRole("list", { name: "Operational alerts" });
  const detail = page.getByRole("region", { name: "Operational alert workspace" });
  const rail = page.getByRole("complementary", { name: "Context and assistance" });
  const views = page.getByRole("tablist", { name: "Operational queue views" });
  await expect(workload.getByRole("button", { name: "Total Alerts 68", exact: true })).toBeVisible();
  await expect(workload.getByRole("button", { name: "No Immediate Review 3", exact: true })).toBeVisible();
  await expect(workload.getByRole("button", { name: "Needs Review 65", exact: true })).toBeVisible();
  async function search(text: string) {
    await views.getByRole("tab", { name: /^All / }).click();
    await page.getByLabel("Search operational alerts", { exact: true }).fill(text);
    await expect(queue.getByRole("button").first()).toContainText(text);
    await queue.getByRole("button").first().click();
    await detail.getByRole("tab", { name: "Overview", exact: true }).click();
  }
  // A: high native priority alone remains routine Tier 1.
  await search("Known routine brute force");
  await expect(detail).toContainText("brute force");
  await expect(detail.getByRole("region", { name: "System Routing", exact: true })).toContainText("Routine Review");
  await expect(detail).toContainText("Human Review Required");
  // H: the old public command cannot strand this current alert in Candidate.
  const ref = new URL(page.url()).searchParams.get("alertRef")!;
  const before = await (await page.request.get(`/api/v2/alerts/${ref}/triage-state`, { headers: { authorization } })).json();
  const old = await page.request.post(`/api/v2/alerts/${ref}/tier2/escalate`, { headers: { authorization }, data: {
    requestId: crypto.randomUUID(), expectedStateVersion: before.stateVersion, reason: "SYNTHETIC browser compatibility regression",
  } });
  expect(old.status()).toBe(409);
  const after = await (await page.request.get(`/api/v2/alerts/${ref}/triage-state`, { headers: { authorization } })).json();
  expect(after.state).toEqual(before.state); expect(after.caseRef).toBeNull();
  // G: the normal UI command creates a formal case with analyst attribution.
  await detail.getByLabel("Decision reason").fill("SYNTHETIC manual investigation override");
  await detail.getByRole("button", { name: "Escalate to Tier 2", exact: true }).click();
  await expect(detail.getByRole("status", { name: "Tier 2 escalation result" })).toContainText("Tier 2 Case created successfully");
  await expect(detail).toContainText("Analyst — manual override");
  // B: real memory/context decisions, then real human recall, update every surface.
  await page.getByLabel("Search operational alerts", { exact: true }).fill("");
  await views.getByRole("tab", { name: "No Immediate Review 3", exact: true }).click();
  await expect(queue.getByRole("button")).toHaveCount(3);
  await queue.getByRole("button").first().click();
  await expect(detail).toContainText("No Immediate Review");
  await expect(rail).toContainText("Review Required: No");
  await detail.getByRole("tab", { name: "Context & Review", exact: true }).click();
  const panel = detail.getByRole("region", { name: "Selective Human Review" });
  await expect(panel.getByText("No Immediate Review", { exact: true })).toBeVisible();
  await panel.getByLabel("Review policy or override reason").fill("SYNTHETIC human recall");
  await panel.getByRole("button", { name: "Require Human Review", exact: true }).click();
  await expect(workload.getByRole("button", { name: "No Immediate Review 2", exact: true })).toBeVisible();
  await expect(workload.getByRole("button", { name: "Needs Review 66", exact: true })).toBeVisible();
  await expect(queue.getByRole("button")).toHaveCount(2);
  await expect(panel.getByText("Human Review Required", { exact: true })).toBeVisible();
  await expect(rail).toContainText("Review Required: Yes");
  // C: 53 explicit notices retain informational status without Expert cases.
  await search("Informational notice");
  await expect(queue.getByRole("button")).toHaveCount(50);
  await expect(page.getByRole("region", { name: "Operational alert queue", exact: true })).toContainText("1–50 of 53");
  await expect(detail).toContainText("Informational / Policy Signal");
  await expect(detail.getByRole("region", { name: "System Routing", exact: true })).toContainText("Routine Review");
  await expect(detail.getByRole("link", { name: "Open Tier 2 Case", exact: true })).toHaveCount(0);
  // E: compatible broader evidence selects the specific class.
  await search("SYNTHETIC DDoS detected");
  await expect(detail).toContainText(/Attack Category: ddos/i);
  await expect(detail.getByRole("region", { name: "System Routing", exact: true })).toContainText("Routine Review");
  // D/F: unresolved and conflicting evidence always already have a system case.
  for (const title of ["Unresolved suspicious network activity", "DDoS conflicting evidence"]) {
    await search(title);
    await expect(detail).toContainText("Unknown / Needs Expert");
    await expect(detail.getByRole("region", { name: "System Routing", exact: true })).toContainText("Expert Review Required");
    await expect(detail.getByRole("link", { name: "Open Tier 2 Case", exact: true })).toBeVisible();
    await expect(detail.getByRole("button", { name: "Approve Tier 2", exact: true })).toHaveCount(0);
    await expect(detail.getByText(/Tier 2 Candidate/)).toHaveCount(0);
  }
  await search("critical SQL injection");
  await expect(detail.getByRole("region", { name: "System Routing", exact: true })).toContainText("Critical Escalation");
  // I: identical flow IDs/raw data, different stable scopes, distinct operational identities.
  await search("Capture-isolated port scan");
  await expect(queue.getByRole("button")).toHaveCount(2);
  const captureRefs: string[] = [], scopes: string[] = [];
  for (let i = 0; i < 2; i++) {
    await queue.getByRole("button").nth(i).click();
    captureRefs.push(new URL(page.url()).searchParams.get("alertRef")!);
    await detail.getByRole("tab", { name: "Evidence", exact: true }).click();
    const scope = detail.getByText(/^capture-(one|two)$/);
    await expect(scope).toBeVisible();
    scopes.push((await scope.textContent())!);
  }
  expect(new Set(captureRefs).size).toBe(2);expect(new Set(scopes).size).toBe(2);
  await search("Informational notice");
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["dark", "light"]) {
      if (await page.locator("html").getAttribute("data-theme") !== theme) await page.getByRole("button", { name: "Light theme", exact: true }).click();
      await expect(workload).toBeVisible();
      await expect(queue.locator('[aria-label^="Operational Priority:"]').first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `test-results/pre-freeze-${width}-${theme}.png`, fullPage: true });
    }
  }
  expect(errors).toEqual([]);
});
