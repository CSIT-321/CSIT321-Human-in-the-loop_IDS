import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const database = process.env.HITL_WORKSPACES_DB;
const replayDatabase = () => resolve(dirname(database!), "workspaces", "v3-1-replay.db");
const python = (script: string, path: string) => execFileSync(process.env.HITL_PYTHON ?? "python", ["-c", script, path],
  { cwd: resolve(process.cwd(), "../.."), encoding: "utf8" }).trim();
const countClaims = (path: string) => Number(python("import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('SELECT count(*) FROM analyst_claim_intents').fetchone()[0])", path));
const fingerprint = () => {
  if (!database) throw new Error("HITL_WORKSPACES_DB must name the disposable Operational database");
  return createHash("sha256").update(readFileSync(database)).digest("hex");
};

async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

async function token(page: Page): Promise<string> {
  return page.evaluate(() => {
    const raw = sessionStorage.getItem("hitl-ids.session.v1");
    if (!raw) throw new Error("No signed-in browser session");
    return (JSON.parse(raw) as { token: string }).token;
  });
}

async function noPageOverflow(page: Page) {
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["dark", "light"]) {
      await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
        `Page overflow at ${width}px in ${theme} theme: ${page.url()}`).toBe(true);
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test("Admin workspace selection, isolated Analyst replay, and shared frozen Evaluation", async ({ browser }) => {
  const adminContext = await browser.newContext();
  const analystContext = await browser.newContext();
  const bobContext = await browser.newContext();
  const evaluatorContext = await browser.newContext();
  const admin = await adminContext.newPage();
  const analyst = await analystContext.newPage();
  const bob = await bobContext.newPage();
  const evaluator = await evaluatorContext.newPage();
  const errors: string[] = [];
  for (const page of [admin, analyst, bob, evaluator]) page.on("pageerror", error => errors.push(error.message));

  await login(admin, "admin", "admin-demo");
  await admin.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Operational Workspace" }).click();
  await expect(admin.getByRole("heading", { name: "Operational Workspace" })).toBeVisible();
  await expect(admin.getByRole("heading", { name: /V3.1 Demo Replay/ })).toBeVisible();
  if (await admin.getByRole("heading", { name: "V3.1 Demo Replay Active" }).count()) {
    await admin.getByRole("heading", { name: "Operational Inactive" }).locator("xpath=ancestor::section[1]")
      .getByRole("button", { name: "Activate" }).click();
  }
  const reset = admin.getByRole("button", { name: "Reset Replay" });
  if (await reset.isEnabled()) {
    admin.once("dialog", dialog => void dialog.accept());
    await reset.click();
    await expect(admin.getByText("Last prepared: Never")).toBeVisible();
  }
  await noPageOverflow(admin);
  const before = fingerprint();
  await admin.getByRole("button", { name: "Prepare Replay" }).click();
  await expect(admin.getByText("Raw frozen workload records: 200")).toBeVisible();
  await expect(admin.getByText("Operational alerts: 200")).toBeVisible();
  expect(fingerprint()).toBe(before);
  // A second Analyst exists only in the disposable Replay database for the Viewer journey.
  python("import sys; from apps.api import auth; from packages.contracts import db,models as m; c=db.connect(sys.argv[1]); db.insert(c,m.User(username='bob',display_name='Bob',password_hash=auth.hash_password('work-demo'),email='bob@replay.test',role='security_analyst')); c.commit(); c.close()", replayDatabase());
  const replayCard = admin.getByText("Raw frozen workload records: 200").locator("xpath=ancestor::section[1]");
  await replayCard.getByRole("button", { name: "Activate" }).click();
  await expect(admin.getByText("V3.1 Demo Replay", { selector: "p" })).toBeVisible();

  await login(analyst, "g.ang", "analyst-demo");
  await expect(analyst.getByText("Workspace: V3.1 Demo Replay")).toBeVisible();
  await expect(analyst.getByRole("button", { name: /^Total Alerts 200$/ })).toBeVisible();
  await noPageOverflow(analyst);
  const tier1 = analyst.getByRole("tablist", { name: "Operational queue views" }).getByRole("tab", { name: /^Tier 1 / });
  await tier1.click();
  await analyst.getByRole("list", { name: "Operational alerts" }).getByRole("button").first().click();
  await expect(analyst.getByRole("region", { name: "Operational alert workspace" })).toBeVisible();
  await expect(analyst.getByRole("region", { name: "Human work status" })).toContainText("Your Access: Owner");
  const ownedRef = new URL(analyst.url()).searchParams.get("alertRef");
  expect(ownedRef).toBeTruthy();
  expect(countClaims(replayDatabase())).toBe(1);
  await login(bob, "bob", "work-demo");
  await bob.goto(`/analyst/operations?alertRef=${ownedRef}`);
  await expect(bob.getByRole("region", { name: "Human work status" })).toContainText("Your Access: Viewer");
  await expect(bob.getByRole("region", { name: "Human work status" })).toContainText("Glenn Ang");
  await bob.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${ownedRef}"]`).click();
  await bob.getByRole("tab", { name: "Analyst Verdict", exact: true }).click();
  await expect(bob.getByLabel("Verdict reason")).toHaveCount(0);
  await expect(bob.getByLabel("Decision reason", { exact: true })).toHaveCount(0);
  expect(countClaims(replayDatabase())).toBe(1);
  expect(fingerprint()).toBe(before);
  await analyst.getByRole("tab", { name: "Analyst Verdict", exact: true }).click();
  await analyst.getByLabel("Verdict outcome").selectOption("expected_activity");
  await analyst.getByLabel("Verdict reason").fill("Interactive replay browser validation");
  await analyst.getByRole("button", { name: "Record Verdict", exact: true }).click();
  await expect(analyst.getByRole("region", { name: "Human work status" })).toContainText("Completed");
  expect(countClaims(replayDatabase())).toBe(1);
  expect(fingerprint()).toBe(before);

  const opCard = admin.getByText("Operational alerts: 0").locator("xpath=ancestor::section[1]");
  await opCard.getByRole("button", { name: "Activate" }).click();
  await expect(admin.getByText("Operational", { selector: "p", exact: true })).toBeVisible();
  await analyst.reload();
  await expect(analyst.getByText("Workspace: Operational")).toBeVisible();
  await expect(analyst.getByRole("button", { name: /^Total Alerts 0$/ })).toBeVisible();
  // Analyst sign-in updates last_login; operational alert state remains empty.

  await admin.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Final V3.1 Evaluation" }).click();
  await expect(admin.getByRole("heading", { name: "Final Evaluation V3.1" })).toBeVisible();
  await expect(admin.getByLabel("Frozen workload composition")).toContainText("200");
  await expect(admin.getByLabel("Official primary effectiveness, denominator 140")).toContainText("37 / 26.43%");
  await expect(admin.getByText("Memory Impact", { exact: true })).toBeVisible();
  await expect(admin.getByText("Drift proof", { exact: true })).toBeVisible();
  await noPageOverflow(admin);
  await admin.getByLabel("Deferral", { exact: true }).selectOption("safe");
  await expect(admin.getByText(/matching records · showing/)).toBeVisible();
  await admin.getByRole("link", { name: /^Open record / }).first().click();
  await expect(admin.getByRole("heading", { name: "Memory evidence" })).toBeVisible();
  await expect(admin.getByText("Policy-selected lesson:")).toBeVisible();
  await noPageOverflow(admin);
  await admin.getByRole("link", { name: "All records" }).click();
  await admin.getByLabel("Deferral", { exact: true }).selectOption("unsafe");
  await expect(admin.getByText(/^2 matching records/)).toBeVisible();
  await admin.getByRole("link", { name: "Open record 191" }).click();
  await expect(admin.getByText(/Initial unsafe deferral/)).toBeVisible();
  await noPageOverflow(admin);

  await login(evaluator, "evaluator", "evaluator-demo");
  await evaluator.goto("/evaluator/final-v3-1");
  await expect(evaluator.getByRole("heading", { name: "Final Evaluation V3.1" })).toBeVisible();
  await expect(evaluator.getByLabel("Frozen workload composition")).toContainText("200");
  await noPageOverflow(evaluator);
  expect(await evaluator.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Operational Workspace" }).count()).toBe(0);
  const deniedSwitch = await evaluator.request.post("/api/admin/workspaces/v3-1-replay/activate", {
    headers: { Authorization: `Bearer ${await token(evaluator)}` }, data: { reason: "Forbidden evaluator switch" },
  });
  expect(deniedSwitch.status()).toBe(403);
  const deniedEvidence = await analyst.request.get("/api/evaluation/final-v3-1", {
    headers: { Authorization: `Bearer ${await token(analyst)}` },
  });
  expect(deniedEvidence.status()).toBe(403);
  await analyst.goto("/admin/evaluation/final-v3-1");
  await expect(analyst).toHaveURL(/\/analyst\/operations$/);
  expect(errors).toEqual([]);
  await Promise.all([adminContext.close(), analystContext.close(), bobContext.close(), evaluatorContext.close()]);
});
