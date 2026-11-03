import { expect, test, type Page } from "@playwright/test";

async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

test("Analyst Workstation remains mounted, live, and safe across Analyst navigation", async ({ browser }) => {
  const adminContext = await browser.newContext();
  const analystContext = await browser.newContext();
  const admin = await adminContext.newPage();
  const analyst = await analystContext.newPage();
  const requests: string[] = [];
  analyst.on("request", request => requests.push(`${request.method()} ${new URL(request.url()).pathname}`));

  await login(admin, "admin", "admin-demo");
  await admin.goto("/admin/workspaces");
  await expect(admin.getByRole("heading", { name: "Operational Workspace" })).toBeVisible();
  if (await admin.getByText("Last prepared: Never").isVisible()) {
    await admin.getByLabel("Replay preparation mode").selectOption("presentation");
    await admin.getByRole("button", { name: "Prepare Replay" }).click();
  }
  const progress = admin.getByText(/\d+ \/ 160/).first();
  await expect(progress).toBeVisible({ timeout: 90_000 });
  const arrivedBefore = Number((await progress.innerText()).split("/")[0]);
  const replay = progress.locator("xpath=ancestor::section[1]");
  if (await replay.getByRole("button", { name: "Activate" }).isEnabled())
    await replay.getByRole("button", { name: "Activate" }).click();

  await login(analyst, "g.ang", "analyst-demo");
  await expect(analyst.getByRole("button", { name: `Total Alerts ${40 + arrivedBefore}` })).toBeVisible();
  await expect(analyst.getByText("Arrival updates connected")).toBeVisible();
  await analyst.getByRole("tablist", { name: "Operational queue views" }).getByRole("tab", { name: /^Tier 1 / }).click();
  await analyst.getByRole("list", { name: "Operational alerts" }).getByRole("button").first().click();
  await expect(analyst.getByRole("region", { name: "Human work status" })).toContainText("Your Access: Owner");
  const selected = new URL(analyst.url()).searchParams.get("alertRef");
  expect(selected).toBeTruthy();
  await analyst.getByRole("tab", { name: "Analyst Verdict" }).click();
  await analyst.getByLabel("Verdict reason").fill("Unsubmitted draft survives Analyst route navigation");
  const initialClaims = requests.filter(path => path.includes("/work/claim")).length;
  await analyst.evaluate(() => {
    const state = window as unknown as { workstationNode: Element | null; loadingSeen: boolean; mountCount: number };
    state.workstationNode = document.querySelector(".operational-workstation");
    state.loadingSeen = false;
    state.mountCount = 1;
    new MutationObserver(() => {
      if (document.querySelector(".operational-workstation")?.textContent?.includes("Loading operational alerts"))
        state.loadingSeen = true;
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
    new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) {
        if (node instanceof Element && (node.matches(".operational-workstation") || node.querySelector(".operational-workstation")))
          state.mountCount += 1;
      }
    }).observe(document.body, { childList: true, subtree: true });
  });
  const streamCount = () => requests.filter(path => path === "GET /api/v2/alerts/stream").length;
  const streamsBeforeNavigation = streamCount();
  expect(streamsBeforeNavigation).toBeGreaterThan(0);

  await analyst.getByRole("link", { name: "Selective Review" }).click();
  await expect(analyst).toHaveURL(/\/analyst\/selective-review$/);
  await expect.poll(() => analyst.evaluate(() => {
    const state = window as unknown as { workstationNode: Element | null };
    return state.workstationNode?.isConnected && state.workstationNode.closest("[hidden]") !== null;
  })).toBe(true);
  await admin.getByRole("button", { name: "Next Alert" }).click();
  await expect(admin.getByText(`${arrivedBefore + 1} / 160`)).toBeVisible();
  await expect.poll(() => analyst.evaluate(value => document.querySelector(`[aria-label="Total Alerts ${value}"]`) !== null,
    41 + arrivedBefore)).toBe(true);
  expect(streamCount()).toBe(streamsBeforeNavigation);

  const start = Date.now();
  await analyst.getByRole("link", { name: "Analyst Workstation" }).click();
  await expect(analyst.getByLabel("Verdict reason")).toBeVisible();
  const returnMs = Date.now() - start;
  expect(await analyst.evaluate(() => {
    const state = window as unknown as { workstationNode: Element | null; loadingSeen: boolean; mountCount: number };
    return document.querySelector(".operational-workstation") === state.workstationNode && !state.loadingSeen && state.mountCount === 1;
  })).toBe(true);
  expect(new URL(analyst.url()).searchParams.get("alertRef")).toBe(selected);
  await expect(analyst.getByRole("tab", { name: "Analyst Verdict" })).toHaveAttribute("aria-selected", "true");
  await expect(analyst.getByLabel("Verdict reason")).toHaveValue("Unsubmitted draft survives Analyst route navigation");
  await expect(analyst.getByRole("button", { name: `Total Alerts ${41 + arrivedBefore}` })).toBeVisible();

  for (const [name, path] of [["Tier 2 Cases", "/analyst/tier2-cases"],
    ["Triage Memory", "/analyst/triage-memory"], ["Incoming Alerts", "/analyst/external-admission"]]) {
    await analyst.getByRole("navigation", { name: "Main" }).getByRole("link", { name }).click();
    await expect(analyst).toHaveURL(new RegExp(path + "$"));
    await expect.poll(() => analyst.evaluate(() => {
      const state = window as unknown as { workstationNode: Element | null };
      return document.querySelector(".operational-workstation") === state.workstationNode &&
        state.workstationNode?.closest("[hidden]") !== null;
    })).toBe(true);
    await analyst.goBack();
    await expect(analyst.getByLabel("Verdict reason")).toHaveValue("Unsubmitted draft survives Analyst route navigation");
  }
  expect(requests.filter(path => path.includes("/work/claim")).length).toBe(initialClaims);
  await analyst.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Selective Review" }).click();
  await expect(analyst).toHaveURL(/\/analyst\/selective-review$/);
  const operational = admin.getByRole("heading", { name: "Operational Inactive" }).locator("xpath=ancestor::section[1]");
  await operational.getByRole("button", { name: "Activate" }).click();
  await expect(analyst.getByText("Workspace: Operational")).toBeVisible();
  await analyst.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Analyst Workstation" }).click();
  await expect(analyst.getByRole("button", { name: "Total Alerts 0" })).toBeVisible();
  expect(new URL(analyst.url()).searchParams.get("alertRef")).not.toBe(selected);
  // An Admin workspace change deliberately reloads the app to discard all old-workspace state.
  expect(await analyst.evaluate(() => (window as unknown as { workstationNode?: Element }).workstationNode)).toBeUndefined();
  expect(requests.filter(path => path.includes("/work/claim")).length).toBe(initialClaims);
  console.log(`Selective Review -> Workstation useful content: ${returnMs} ms; SSE streams: ${streamCount()}`);
  await Promise.all([adminContext.close(), analystContext.close()]);
});
