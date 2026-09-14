/**
 * Screenshots for the demo guide, taken from the real console against a disposable database copy.
 *
 *     GUIDE_CAPTURE=1 npx playwright test capture-guide
 *
 * Skipped otherwise, so `npm run e2e` stays the S16 gate only. The walk follows the guide's acts in
 * order, because each verdict changes what later screens show. Images land in docs/img/demo-guide/.
 */

import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Locator, type Page } from "@playwright/test";

const OUT = resolve(process.env.GUIDE_OUT ?? "../../docs/img/demo-guide");

test.skip(!process.env.GUIDE_CAPTURE, "set GUIDE_CAPTURE=1 to capture the demo guide screenshots");

async function shot(target: Page | Locator, name: string) {
  await target.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" });
}

/** The card (<section>) a level-2 heading titles. */
function card(page: Page, heading: string): Locator {
  return page
    .getByRole("heading", { level: 2, name: heading, exact: true })
    .locator("xpath=ancestor::section[1]");
}

async function searchQueue(page: Page, record: string) {
  await page.goto("/analyst/queue");
  await expect(page.getByRole("heading", { level: 1, name: "Alert Queue" })).toBeVisible();
  const search = page.getByLabel("Search", { exact: true });
  await search.fill(record);
  await search.press("Enter");
  await expect(page.getByRole("link", { name: record, exact: true })).toBeVisible();
}

async function openAlert(page: Page, record: string) {
  await searchQueue(page, record);
  await page.getByRole("link", { name: record, exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: record })).toBeVisible();
  await expect(card(page, "Score adjustment")).toBeVisible();
}

async function recordVerdict(page: Page, verdict: RegExp) {
  await page.getByRole("radio", { name: verdict }).click();
  await page.getByRole("button", { name: "Record verdict" }).click();
  await expect(page.getByRole("region", { name: "Verdict outcome" })).toBeVisible();
}

async function switchRole(page: Page, label: string, home: string) {
  await page.getByLabel("Switch role").selectOption({ label });
  await expect(page).toHaveURL(new RegExp(`${home}$`));
}

test("capture the demo guide", async ({ page }) => {
  test.setTimeout(300_000);
  mkdirSync(OUT, { recursive: true });

  // Act 1 — sign in.
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await shot(page, "01-login");
  await page.getByRole("radio", { name: "Analyst" }).click();
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("5,000 alerts")).toBeVisible();

  // Act 1b — the workstation: queue, alert and context in one view. Captured before any verdict.
  await expect(
    page.getByRole("region", { name: "Alert detail" }).getByRole("heading", { level: 2 }).first(),
  ).toBeVisible();
  await page.waitForTimeout(800);
  await shot(page, "01b-workstation");
  const wsSearch = page.getByLabel("Search alerts");
  await wsSearch.fill("AL-00478");
  await wsSearch.press("Enter");
  // Wait for the search to narrow the list: clicking the first card before it does opens another alert.
  const wsCards = page.getByRole("list", { name: "Alerts" }).getByRole("button");
  await expect(wsCards).toHaveCount(1);
  await wsCards.first().click();
  await expect(page.getByRole("region", { name: "Alert detail" }).getByText("AL-00478").first()).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "Alert context" }).getByText("Addresses in the recording"),
  ).toBeVisible();
  await page.waitForTimeout(800);
  await shot(page, "01c-workstation-al00478");
  await page.getByRole("tab", { name: /^Verdict/ }).click();
  await expect(page.getByRole("radio", { name: /False Positive/ })).toBeVisible();
  await shot(page, "01d-workstation-verdict-tab");
  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(page.getByLabel("Add a note")).toBeVisible();
  await shot(page, "01e-workstation-notes");

  // Act 2 — dashboard and queue.
  await page.goto("/analyst/dashboard");
  await expect(page.getByText("5,000").first()).toBeVisible();
  // The five highest-ranked alerts awaiting review — score-100 alerts, not AL-00478 (rank 639).
  await expect(card(page, "Needs a human").getByRole("link").first()).toBeVisible();
  await shot(page, "02-dashboard");
  await page.goto("/analyst/queue");
  await expect(page.getByText(/Showing 1–50 of 5,000/)).toBeVisible();
  await shot(page, "03-queue");
  await page.getByLabel("Band").selectOption({ label: "Model only" });
  await expect(page.getByText(/Showing 1–50 of 352/)).toBeVisible();
  await shot(page, "04-queue-filtered");

  // Act 2b — the overview and one address (R4), before any verdict changes the mixes.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Overview" }).click();
  await expect(card(page, "Top source addresses").getByRole("link").first()).toBeVisible();
  await shot(page, "04b-overview");
  await page.goto("/analyst/entities/ip/18.218.115.60");
  await expect(card(page, "Top peers").getByRole("link", { name: "172.31.69.28" })).toBeVisible();
  await shot(page, "04c-ip-entity");

  // Act 3 — AL-00478, the confident false positive.
  await openAlert(page, "AL-00478");
  await shot(page, "05-alert-header");
  const panels = card(page, "Flow").locator("xpath=..");
  await panels.scrollIntoViewIfNeeded();
  await shot(panels, "06-evidence-panels");
  await shot(card(page, "Similar alerts (family)"), "07-family-closed");
  await page.getByRole("radio", { name: /False Positive/ }).click();
  await shot(card(page, "Record a verdict"), "08-verdict-form");
  await page.getByRole("button", { name: "Record verdict" }).click();
  await expect(page.getByRole("region", { name: "Verdict outcome" })).toBeVisible();
  await expect(page.getByText("Capped by a guardrail").first()).toBeVisible();
  await shot(card(page, "Record a verdict"), "09-verdict-capped");
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "AL-00478" })).toBeVisible();
  await expect(card(page, "Score adjustment").getByText("Capped by a guardrail")).toBeVisible();
  await shot(card(page, "Score adjustment"), "10-chain-persisted");
  await expect(page.getByText("In effect")).toBeVisible();
  await shot(card(page, "Verdict history"), "11-history");

  // A rule-backed alert, for the signature panel.
  await openAlert(page, "AL-01958");
  await shot(card(page, "Signature rules"), "12-signature-rule");
  await shot(card(page, "Combined explanation"), "13-combined-explanation");

  // Act 4 — AL-03086, the missed attack.
  await openAlert(page, "AL-03086");
  await recordVerdict(page, /True Positive/);
  await shot(card(page, "Record a verdict"), "14-confirm-applied");

  // Act 5 — family learning.
  for (const record of ["AL-01696", "AL-03873"]) {
    await openAlert(page, record);
    await recordVerdict(page, /True Positive/);
  }
  await openAlert(page, "AL-03153");
  await recordVerdict(page, /True Positive/);
  await expect(
    page.getByText("Similar-alert learning applied: 2 other alerts in this family moved."),
  ).toBeVisible();
  await shot(card(page, "Record a verdict"), "15-family-gate-open");
  await expect(card(page, "Similar alerts (family)").getByText("Open")).toBeVisible();
  await shot(card(page, "Similar alerts (family)"), "16-family-open");
  await searchQueue(page, "AL-03044");
  await shot(page, "17-untouched-promoted");

  await page.goto("/analyst/investigations");
  await expect(page.getByRole("heading", { level: 1, name: "Investigations" })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await shot(page, "18-investigations");
  await page.goto("/analyst/feedback-impact");
  await expect(page.getByRole("heading", { level: 1, name: "Feedback Impact" })).toBeVisible();
  await expect(card(page, "Similar-alert learning").getByRole("table")).toBeVisible();
  await shot(page, "19-feedback-impact");
  await page.goto("/analyst/dashboard");
  await expect(page.getByText("5,000").first()).toBeVisible();
  await shot(page, "20-dashboard-after");

  // Act 7 — administrator.
  await switchRole(page, "System Administrator", "/admin/status");
  await expect(card(page, "Latest detection run").getByText("xgb-8class-20260911")).toBeVisible();
  // The figures row and service health come from two other requests; wait for both (R5).
  await expect(page.getByText("API answering")).toBeVisible();
  // Total alerts comes from the summary and Unresolved from the breakdowns; no alert has been closed,
  // so both read 5,000 once both requests have answered.
  await expect(page.getByLabel("Operations").getByText("5,000")).toHaveCount(2);
  await shot(page, "21-admin-status");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Guardrails" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Guardrails" })).toBeVisible();
  await page.getByLabel("Critical alert floor").fill("85");
  await page.getByLabel("Reason for this change").fill("demo");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByText("The critical alert floor must be below the critical alert threshold"),
  ).toBeVisible();
  await shot(card(page, "Feedback limits"), "22-guardrail-validation");
  await page.reload();
  const log = card(page, "Guardrail log");
  await expect(
    log.getByText("This alert is Critical, so its score was held at the floor of 70.", { exact: true }),
  ).toBeVisible();
  await shot(log, "23-guardrail-log");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Audit Trail" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Audit Trail" })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await shot(page, "24-audit-trail");

  // Act 8 — evaluator.
  await switchRole(page, "Evaluator", "/evaluator/scenarios");
  await expect(page.getByRole("link", { name: "20260912T032022Z" })).toBeVisible();
  await shot(page, "25-eval-scenarios");
  await page.getByRole("link", { name: "20260912T032022Z" }).click();
  await expect(page.getByText(/Precision fell under feedback/)).toBeVisible();
  await shot(page, "26-eval-run");
  await shot(card(page, "Deltas"), "27-eval-deltas");
  await shot(card(page, "Who moved"), "28-eval-who-moved");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Detection Metrics" }).click();
  await expect(card(page, "Per class")).toBeVisible();
  await shot(page, "29-eval-metrics");
  await shot(card(page, "Per class"), "30-per-class");
  await shot(card(page, "Score saturation"), "31-saturation");
});
