import { expect, test } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

/** Suricata lane screenshots, on a database that holds ONLY the external alerts (no flow routing rows),
 *  because the product refuses mixed lanes today (see the walkthrough page). Read-only: no clicks that write. */
const OUT = path.resolve(process.cwd(), "../../../analysis/phase-f/packet-to-workstation/shots");
const lane = JSON.parse(readFileSync(
  path.resolve(process.cwd(), "../../../analysis/phase-f/packet-to-workstation/data/lane_suricata.json"), "utf8"));

test("suricata lane: inbox, admitted record, analyst workstation", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  const shot = async (name: string) => page.screenshot({ path: path.join(OUT, name), fullPage: false });
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);

  await page.goto("/analyst/external-admission");
  const picker = page.locator("#external-alert");
  await expect(picker).toBeVisible();
  const options = await picker.locator("option").allInnerTexts();
  console.log("staged options:", options.length, JSON.stringify(options.slice(0, 3)));

  // 1. the backlog: real ET SCAN alerts staged from the capture
  await shot("01-inbox-backlog.png");

  // 2. the admitted record for this case
  const admitted = options.find(o => o.includes("(admitted)"));
  expect(admitted, "one staged alert must be admitted").toBeTruthy();
  await picker.selectOption({ label: admitted! });
  await expect(page.getByText("Open Analyst Workstation")).toBeVisible();
  await shot("02-admitted-record.png");

  // 3. the same alert in the analyst workstation
  await page.getByText("Open Analyst Workstation").click();
  await expect(page).toHaveURL(/alertRef=/);
  await expect(page.getByRole("heading", { name: "System Routing", exact: true })).toBeVisible();
  await shot("03-workstation-suricata-alert.png");

  // 4. the queue row
  await page.goto("/analyst/operations");
  await expect(page.getByRole("list", { name: "Operational alerts" })).toBeVisible();
  await shot("04-queue-suricata-lane.png");

  await expect(page.getByRole("list", { name: "Operational alerts" }).getByRole("button")).toHaveCount(lane.counts.operational_alerts_v2);
});
