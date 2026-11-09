import { expect, test } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

/** Legacy flow lane screenshots (CICIDS2018 features). Labelled for removal in the walkthrough page.
 *  Read-only: opens rows and screenshots them. */
const OUT = path.resolve(process.cwd(), "../../../analysis/phase-f/packet-to-workstation/shots");
const lane = JSON.parse(readFileSync(
  path.resolve(process.cwd(), "../../../analysis/phase-f/packet-to-workstation/data/lane_flow.json"), "utf8"));

test("flow lane: group row, alert panel, tier 2 case", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  const shot = async (name: string) => page.screenshot({ path: path.join(OUT, name), fullPage: false });
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);

  const ref = lane.representative.operational_alert_ref;
  await page.goto(`/analyst/operations?view=all&q=${ref}`);
  const queue = page.getByRole("list", { name: "Operational alerts" });
  await expect(queue.getByRole("button").first()).toBeVisible();
  await shot("05-queue-flow-group.png");

  await queue.getByRole("button").first().click();
  await expect(page.getByRole("heading", { name: "System Routing", exact: true })).toBeVisible();
  await shot("06-flow-alert-panel.png");

  await page.goto("/analyst/tier2-cases");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await shot("07-tier2-case-list.png");

  const caseRef = lane.case?.case_ref;
  if (caseRef) {
    await page.goto(`/analyst/tier2-cases/${caseRef}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await shot("08-tier2-case-detail.png");
  }
});
