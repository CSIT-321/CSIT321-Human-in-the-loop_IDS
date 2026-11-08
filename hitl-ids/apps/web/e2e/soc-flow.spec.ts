import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";

/**
 * SOC flow on the real routed demo data (soc-flow-fixture.py: a temp copy of data/demo.db, routed by
 * scripts/materialize_flow_queue.py). One analyst walks the branch's whole triage loop:
 *   1 queue views and tier counts -> 2 claim (row click) -> 3 note -> 4 Why Tier 2 -> escalate
 *   5 routine group: verdict -> 6 auto-escalated case -> 7 Tier 2: start, conclude, resolve -> 8 release.
 * After each write the spec reads the stored row through a read-only /__soc route, so a step that only
 * looks right on screen fails. Screenshots land in GUIDE_OUT (default test-results/soc-guide) for the guide.
 */
const OUT = process.env.GUIDE_OUT ?? "test-results/soc-guide";
const API = "http://127.0.0.1:8040";

test("SOC flow: queue views, claim, note, Why Tier 2, verdict, auto case, Tier 2 resolve, release", async ({ page }) => {
  test.setTimeout(300_000); page.setDefaultTimeout(20_000); mkdirSync(OUT, { recursive: true });
  const errors: string[] = []; page.on("pageerror", e => errors.push(e.message));
  const shot = async (name: string, subject?: Locator) => {
    if (subject) await subject.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" });
  };
  const proof = async (ref: string) => (await page.request.get(`${API}/__soc/proof/${ref}`)).json();
  const picks = await (await page.request.get(`${API}/__soc/picks`)).json();
  const workspace = page.getByRole("region", { name: "Operational alert workspace", exact: true });
  const work = workspace.getByRole("region", { name: "Human work status" });

  async function openRow(p: Page, ref: string) {
    await p.goto(`/analyst/operations?view=all&q=${ref}`);
    await p.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${ref}"]`).click();
    await expect(workspace).toContainText(ref);
  }
  async function tab(name: string) { await workspace.getByRole("tab", { name, exact: true }).click(); }

  // 0 sign in
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang"); await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await shot("00-login");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations/);

  // 1 queue views: the tabs an SOC analyst works from, with counts from the routed demo data
  const views = page.getByRole("tablist", { name: "Operational queue views" });
  for (const key of ["active", "tier1", "tier2-candidates", "auto-escalated", "tier2"])
    await expect(views.locator(`#queue-view-${key}`)).toBeVisible();
  await expect(views.locator("#queue-view-auto-escalated")).toContainText("3");
  await shot("01-queue-views");

  // 2 claim: opening a Tier 2 candidate row claims it for this analyst
  const A = picks.recommended;
  await openRow(page, A);
  await expect(work).toContainText("Your Access: Owner");
  expect((await proof(A)).work).toEqual(["in_review", "Glenn Ang", null]);
  await shot("02-claimed");

  // 3 note: append-only, named
  await tab("History & Notes");
  await workspace.getByPlaceholder("Add a note (you own this alert)").fill("Grouped infiltration flows from one source; checking scope.");
  await workspace.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(workspace.getByRole("list", { name: "Investigation notes" })).toContainText("Glenn Ang");
  expect((await proof(A)).notes).toEqual(["Glenn Ang"]);
  await shot("03-note", workspace.getByRole("list", { name: "Investigation notes" }));

  // 4 Why Tier 2: the reasons are shown; the analyst escalates with a reason
  await tab("Overview");
  const why = workspace.getByRole("region", { name: "Why Tier 2 is recommended" });
  await expect(why).toBeVisible();
  await why.getByLabel(/^Reason/).fill("Repeated infiltration from one source; needs an expert.");
  await shot("04-why-tier2", why);
  await why.getByRole("button", { name: "Escalate to Tier 2", exact: true }).click();
  await expect.poll(async () => (await proof(A)).case?.[2]).toBe("open");
  const pA = await proof(A);
  expect(pA.work[0]).toBe("escalated"); expect(pA.case[1]).not.toBe("system_policy");
  await shot("05-escalated", work);

  // 5 routine group: verdict (claim -> verdict closes the Tier 1 work)
  const V = picks.routine;
  await openRow(page, V);
  await expect(work).toContainText("Your Access: Owner");
  await tab("Flow & Score");
  await expect(workspace.getByRole("region", { name: "Flow and score" })).toBeVisible();
  await shot("06-flow-score");
  await tab("Analyst Verdict");
  const verdict = workspace.getByRole("region", { name: "Analyst Verdict", exact: true });
  await verdict.getByLabel("Verdict outcome").selectOption("confirmed_malicious");
  await verdict.getByLabel("Verdict reason").fill("DoS pattern on port 80 from one source; matches the capture.");
  await verdict.getByRole("button", { name: "Record Verdict", exact: true }).click();
  await expect.poll(async () => (await proof(V)).verdicts).toBe(1);
  await expect.poll(async () => (await proof(V)).work?.[0]).toBe("completed");
  await shot("07-verdict", verdict);

  // 6 auto-escalated: the system opened the case; Tier 1 never had to claim it
  const S = picks.auto;
  const pS = await proof(S);
  expect(pS.case[1]).toBe("system_policy"); expect(pS.work?.[1] ?? null).toBeNull();
  await page.goto("/analyst/tier2-cases");
  await expect(page.getByLabel("Status", { exact: true })).toHaveValue("active");
  const autoRow = page.getByRole("row").filter({ hasText: pS.case[0].slice(0, 8) });
  await expect(autoRow).toContainText("Rule");
  const manualRow = page.getByRole("row").filter({ hasText: pA.case[0].slice(0, 8) });
  await expect(manualRow).toContainText("Glenn Ang");
  await shot("08-case-list");

  // 7 Tier 2: start, conclude, resolve the analyst's case
  await manualRow.getByRole("link").first().click();
  const summary = page.getByRole("region", { name: "Case summary", exact: true });
  const resolution = page.getByRole("region", { name: "Case Resolution", exact: true });
  await page.getByRole("tab", { name: "Audit Timeline", exact: true }).click();
  await page.getByLabel("Decision reason", { exact: true }).fill("Taking this case.");
  await page.getByRole("button", { name: "Start investigation", exact: true }).click();
  await expect(summary).toContainText("investigating");
  await page.getByRole("tab", { name: "Investigation Conclusion", exact: true }).click();
  await page.getByLabel("Human Investigation Finding", { exact: true }).selectOption("confirmed_malicious");
  await page.getByLabel("Human Final Attack Classification", { exact: true }).selectOption("infiltration");
  await page.getByLabel("Investigation Reason", { exact: true }).fill("Confirmed infiltration from the grouped source.");
  await page.getByRole("button", { name: "Record Investigation Conclusion", exact: true }).click();
  await expect(resolution).toContainText("Latest Finding: confirmed malicious");
  await shot("09-conclusion", resolution);
  await resolution.getByLabel("Resolution Reason").fill("Confirmed and documented; no plan executed.");
  await resolution.getByRole("button", { name: "Resolve Case", exact: true }).click();
  await expect(resolution).toContainText("Resolved by: Glenn Ang");
  expect((await proof(A)).case[2]).toBe("resolved");
  await shot("10-resolved", resolution);
  await page.getByRole("link", { name: "All Tier 2 cases", exact: true }).click();
  await expect(manualRow).toHaveCount(0);                 // D1: resolved leaves Active ...
  await page.getByLabel("Status", { exact: true }).selectOption("resolved");
  await expect(manualRow).toContainText("Resolved");      // ... and stays findable

  // 8 release: a claimed alert goes back to the queue (shift change, wrong pick)
  const R = (await (await page.request.get(`${API}/__soc/picks`)).json()).recommended;
  expect(R).not.toBe(A);
  await openRow(page, R);
  await expect(work).toContainText("Your Access: Owner");
  await workspace.getByRole("button", { name: "Release claim", exact: true }).click();
  await shot("11-release");
  await workspace.getByRole("button", { name: "Release", exact: true }).click();
  await expect.poll(async () => (await proof(R)).work?.[0]).toBe("available");

  expect(errors).toEqual([]);
});
