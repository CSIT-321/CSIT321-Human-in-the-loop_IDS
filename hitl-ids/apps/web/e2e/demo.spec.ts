/**
 * The S16 gate, in a browser: the whole demo narrative against the real API, with no manual database
 * fixes. `scripts/rehearse_demo.py` asserts the same story at the API level; this proves a person can
 * actually perform it through the interface.
 *
 * One test, in order, because the narrative is cumulative: each verdict changes what the next screen
 * shows. The API serves a disposable copy of the demo database (see playwright.config.ts).
 */

import { expect, test, type Page } from "@playwright/test";

async function searchQueue(page: Page, record: string) {
  await page.goto("/analyst/queue");
  await expect(page.getByRole("heading", { level: 1, name: "Alert Queue" })).toBeVisible();
  const search = page.getByLabel("Search", { exact: true });
  await search.fill(record);
  await search.press("Enter");
  const link = page.getByRole("link", { name: record, exact: true });
  await expect(link).toBeVisible();
  return link;
}

async function openAlert(page: Page, record: string) {
  await (await searchQueue(page, record)).click();
  await expect(page.getByRole("heading", { level: 1, name: record })).toBeVisible();
}

async function recordVerdict(page: Page, verdict: RegExp) {
  await page.getByRole("radio", { name: verdict }).click();
  await page.getByRole("button", { name: "Record verdict" }).click();
  await expect(page.getByRole("region", { name: "Verdict outcome" })).toBeVisible();
}

async function signIn(page: Page, username: string, password: string, home: string) {
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(new RegExp(`${home}$`));
}

/** Since S18a there is no role switch: another view means signing in as its account. */
async function signInAs(page: Page, username: string, password: string, home: string) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await signIn(page, username, password, home);
}

test("the demo narrative holds end to end in the browser", async ({ page }) => {
  // 1. Sign in as the analyst and land on the workstation.
  await page.goto("/login");
  await signIn(page, "g.ang", "analyst-demo", "/analyst/workstation");
  await expect(page.getByText("5,000 alerts")).toBeVisible();

  // 2. AL-00478: a confident model, no rule, and ground truth says benign.
  await openAlert(page, "AL-00478");
  await expect(page.getByText("No rule matched (ML-only alert).")).toBeVisible();
  await expect(page.getByText("Pushed towards Web Attack")).toBeVisible();
  await expect(page.getByText("→ Tier 2 candidate")).toBeVisible();

  // Dismiss it: the Critical floor caps the change, and says so.
  await recordVerdict(page, /False Positive/);
  const outcome = page.getByRole("region", { name: "Verdict outcome" });
  await expect(outcome.getByText("Capped by a guardrail")).toBeVisible();
  // exact: the API's summary sentence quotes the guardrail's sentence, so a substring match finds both.
  await expect(
    outcome.getByText("This alert is Critical, so its score was held at the floor of 70.", { exact: true }),
  ).toBeVisible();
  await expect(outcome.getByText("Tier 2 candidate", { exact: true })).toBeVisible();

  // Refresh: the adjusted score persists (the plan's S12 end-to-end check).
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "AL-00478" })).toBeVisible();
  const chain = page.getByRole("group", { name: "Score adjustment" }).first();
  await expect(chain.getByText("Capped by a guardrail")).toBeVisible();
  // exact: the intervention line also contains "configured 70.00".
  await expect(chain.getByText("70.00", { exact: true })).toBeVisible();
  await expect(page.getByText("In effect")).toBeVisible();

  // 3. AL-03086: an attempted Web Attack both detectors missed. Confirm it.
  await openAlert(page, "AL-03086");
  await recordVerdict(page, /True Positive/);
  await expect(
    page.getByRole("region", { name: "Verdict outcome" }).getByText("Applied as requested"),
  ).toBeVisible();

  // 4. Three agreeing verdicts in the Port Scan / 445 family open its learning gate.
  for (const record of ["AL-01696", "AL-03873"]) {
    await openAlert(page, record);
    await recordVerdict(page, /True Positive/);
    await expect(page.getByText("Similar-alert learning did not apply.")).toBeVisible();
  }
  await openAlert(page, "AL-03153");
  await recordVerdict(page, /True Positive/);
  await expect(
    page.getByText("Similar-alert learning applied: 2 other alerts in this family moved."),
  ).toBeVisible();

  // The two members nobody judged are now Tier 2 candidates, with no verdict of their own.
  for (const record of ["AL-03044", "AL-04526"]) {
    await searchQueue(page, record);
    const row = page
      .getByRole("row")
      .filter({ has: page.getByRole("link", { name: record, exact: true }) });
    await expect(row.getByText("Tier 2 candidate")).toBeVisible();
    await expect(row.getByText("Verdict recorded")).toHaveCount(0);
  }

  // 5. The administrator finds the cap in the guardrail log.
  await signInAs(page, "admin", "admin-demo", "/admin/status");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Guardrails" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Guardrails" })).toBeVisible();
  await expect(
    page
      .getByText("This alert is Critical, so its score was held at the floor of 70.", { exact: true })
      .first(),
  ).toBeVisible();

  // 6. The evaluator reads the three-arm deltas, including the one that went the wrong way.
  await signInAs(page, "evaluator", "evaluator-demo", "/evaluator/scenarios");
  await page.getByRole("link", { name: "20260912T032022Z" }).click();
  await expect(page.getByText(/Precision fell under feedback/)).toBeVisible();
  await expect(page.getByText("−0.020").first()).toBeVisible();
});
