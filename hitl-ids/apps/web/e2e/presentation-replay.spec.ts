import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const database = process.env.HITL_WORKSPACES_DB!;
const replay = resolve(dirname(database), "workspaces", "v3-1-replay.db");
const python = (script: string) => execFileSync(process.env.HITL_PYTHON ?? "python", ["-c", script, replay],
  { cwd: resolve(process.cwd(), "../.."), encoding: "utf8" }).trim();
const digest = () => createHash("sha256").update(readFileSync(database)).digest("hex");

async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

async function responsive(page: Page) {
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["dark", "light"]) {
      await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
        `${width}px ${theme}: ${page.url()}`).toBe(true);
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test("progressive frozen Replay reaches Analyst queue and automatic Tier 2 without touching Operational", async ({ browser }) => {
  const adminContext = await browser.newContext();
  const analystContext = await browser.newContext();
  const viewerContext = await browser.newContext();
  const admin = await adminContext.newPage();
  const analyst = await analystContext.newPage();
  const viewer = await viewerContext.newPage();
  const errors: string[] = [];
  for (const page of [admin, analyst, viewer]) page.on("pageerror", error => errors.push(error.message));

  await login(admin, "admin", "admin-demo");
  await admin.goto("/admin/workspaces");
  await expect(admin.getByRole("heading", { name: /V3\.1 Demo Replay/ })).toBeVisible();
  const before = digest();
  await expect(admin.getByText("Last prepared: Never")).toBeVisible();
  await admin.getByLabel("Replay preparation mode").selectOption("presentation");
  await admin.getByRole("button", { name: "Prepare Replay" }).click();
  await expect(admin.getByText("40 processed")).toBeVisible({ timeout: 90_000 });
  await expect(admin.getByText("10 / 160")).toBeVisible();
  await expect(admin.getByText("Remaining:").locator("..")).toContainText("150");
  await expect(admin.getByText("Operational alerts: 50")).toBeVisible();
  expect(digest()).toBe(before);
  await responsive(admin);
  const replayCard = admin.getByText("10 / 160").locator("xpath=ancestor::section[1]");
  await replayCard.getByRole("button", { name: "Activate" }).click();
  await expect(admin.getByText("V3.1 Demo Replay", { selector: "p" })).toBeVisible();

  python("import sys; from apps.api import auth; from packages.contracts import db,models as m; c=db.connect(sys.argv[1]); db.insert(c,m.User(username='bob',display_name='Bob',password_hash=auth.hash_password('work-demo'),email='bob@replay.test',role='security_analyst')); c.commit(); c.close()");
  await login(analyst, "g.ang", "analyst-demo");
  await expect(analyst.getByText("Workspace: V3.1 Demo Replay")).toBeVisible();
  await expect(analyst.getByRole("button", { name: /^Total Alerts 50$/ })).toBeVisible();
  await expect(analyst.getByRole("tablist", { name: "Operational queue views" })).toBeVisible();
  await analyst.getByRole("tablist", { name: "Operational queue views" }).getByRole("tab", { name: /^Completed 40$/ }).click();
  await expect(analyst.getByRole("list", { name: "Operational alerts" }).getByRole("button").first()).toBeVisible();
  await responsive(analyst);
  const tier1 = analyst.getByRole("tablist", { name: "Operational queue views" }).getByRole("tab", { name: /^Tier 1 / });
  await tier1.click();
  await analyst.getByRole("list", { name: "Operational alerts" }).getByRole("button").first().click();
  await expect(analyst.getByRole("region", { name: "Human work status" })).toContainText("Your Access: Owner");
  const ownedRef = new URL(analyst.url()).searchParams.get("alertRef");
  expect(ownedRef).toBeTruthy();
  await expect(analyst.getByText("Arrival updates connected")).toBeVisible();
  await analyst.getByRole("tab", { name: "Analyst Verdict" }).click();
  await analyst.getByLabel("Verdict reason").fill("Investigation draft stays open across arrivals");
  await analyst.evaluate(() => {
    const state = window as unknown as { queueLoadingSeen: boolean };
    state.queueLoadingSeen = false;
    const queue = document.getElementById("operational-queue-panel")!;
    new MutationObserver(() => {
      if (queue.textContent?.includes("Loading operational alerts")) state.queueLoadingSeen = true;
    }).observe(queue, { childList: true, subtree: true, characterData: true });
  });
  await login(viewer, "bob", "work-demo");
  await viewer.goto(`/analyst/operations?alertRef=${ownedRef}`);
  await expect(viewer.getByRole("region", { name: "Human work status" })).toContainText("Your Access: Viewer");
  await expect(viewer.getByRole("region", { name: "Human work status" })).toContainText("Glenn Ang");

  await admin.getByRole("button", { name: "Next Alert" }).click();
  await expect(admin.getByText("11 / 160")).toBeVisible();
  await expect(analyst.getByRole("button", { name: /^Total Alerts 51$/ })).toBeVisible({ timeout: 15_000 });
  expect(new URL(analyst.url()).searchParams.get("alertRef")).toBe(ownedRef);
  await expect(analyst.getByRole("tab", { name: "Analyst Verdict" })).toHaveAttribute("aria-selected", "true");
  await expect(analyst.getByLabel("Verdict reason")).toHaveValue("Investigation draft stays open across arrivals");
  expect(await analyst.evaluate(() => (window as unknown as { queueLoadingSeen: boolean }).queueLoadingSeen)).toBe(false);
  await admin.getByRole("button", { name: "Next Alert" }).click();
  await expect(admin.getByText("12 / 160")).toBeVisible();
  await expect(analyst.getByRole("button", { name: /^Total Alerts 52$/ })).toBeVisible({ timeout: 15_000 });
  expect(new URL(analyst.url()).searchParams.get("alertRef")).toBe(ownedRef);
  await expect(analyst.getByLabel("Verdict reason")).toHaveValue("Investigation draft stays open across arrivals");
  await analyst.getByPlaceholder("Search operational alerts…").fill("b905da10-a86d-5509-9064-a6525524abb0");
  const newlyAvailable = analyst.locator('[data-alert-ref="b905da10-a86d-5509-9064-a6525524abb0"]');
  await expect(newlyAvailable).toContainText("Available");
  await newlyAvailable.click();
  await expect(analyst.getByRole("region", { name: "Human work status" })).toContainText("Your Access: Owner");
  await analyst.getByPlaceholder("Search operational alerts…").fill("");
  await analyst.getByRole("tablist", { name: "Operational queue views" }).getByRole("tab", { name: /^Tier 2 / }).click();
  await expect(analyst.getByRole("list", { name: "Operational alerts" }).getByRole("button").first()).toBeVisible();
  await analyst.goto("/analyst/tier2-cases");
  await expect(analyst.getByRole("heading", { name: /Tier 2 Cases/ })).toBeVisible();
  expect((await analyst.locator("body").innerText()).toLowerCase()).not.toContain("oracle outcome");
  await responsive(analyst);

  await admin.goto("/admin/evaluation/audit");
  await expect(admin.getByRole("heading", { name: "Current HITL Audit" })).toBeVisible();
  await admin.getByRole("combobox", { name: "Category" }).selectOption("WORKSPACE");
  await expect(admin.getByText("Presentation Replay prepared", { exact: true }).first()).toBeVisible();
  await expect(admin.getByText("Presentation manually advanced", { exact: true }).first()).toBeVisible();
  await admin.goto("/admin/workspaces");
  await admin.getByRole("button", { name: "Start Arrivals" }).click();
  await expect(admin.getByText("Running", { exact: true })).toBeVisible();
  await admin.getByRole("heading", { name: "Operational Inactive" }).locator("xpath=ancestor::section[1]")
    .getByRole("button", { name: "Activate" }).click();
  await expect(admin.getByText("Paused", { exact: true })).toBeVisible();
  expect(digest()).toBe(before);
  expect(errors).toEqual([]);
  await Promise.all([adminContext.close(), analystContext.close(), viewerContext.close()]);
});
