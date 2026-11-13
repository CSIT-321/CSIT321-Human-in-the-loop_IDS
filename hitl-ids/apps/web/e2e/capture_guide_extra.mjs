// Capture the extra SOC-guide steps (reset to 0, family learning in both chains) on the LIVE demo app.
// Precondition: reset_demo.py was run (Replay active at step 150, no verdicts). This script records verdicts;
// run reset_demo.py again afterwards. Boxes are measured with boundingBox() at screenshot time (1440x900),
// the same way soc-packet.spec.ts measures them, and written to extra-pins.json / extra-facts.json.
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const BASE = "http://127.0.0.1:5173";
const OUT = process.argv[2];
const PY = "C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids/.venv/Scripts/python.exe";
const SEED = "C:/Users/Glenn Ang/AppData/Local/Temp/fyp-demo/seed_family.py";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pins = {}, facts = {};
const browser = await chromium.launch({ headless: true });

async function login(user, pass) {
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await page.goto(BASE + "/login");
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password", { exact: true }).fill(pass);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 20000 });
  await sleep(2000);
  return page;
}
async function shot(page, name, marks) {
  pins[name] = [];
  for (const [label, loc] of marks) pins[name].push({ label, box: await loc.boundingBox().catch(() => null) });
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
}

// ---- Admin: Reset Replay is available while Replay is active (no click)
const admin = await login("admin", "admin-demo");
await admin.goto(BASE + "/admin/workspaces"); await sleep(2500);
const reset = admin.getByRole("button", { name: "Reset Replay" });
facts.reset = { enabled: await reset.isEnabled(), title: await reset.getAttribute("title"),
  arrived: ((await admin.locator("body").innerText()).match(/Capture steps arrived:\s*([\d ]+\/ 160)/) || [])[1] };
await reset.scrollIntoViewIfNeeded(); await sleep(400);
await shot(admin, "a0-reset", [["Reset Replay", reset], ["Steps arrived", admin.getByText(/Capture steps arrived:/)]]);
console.log("reset:", JSON.stringify(facts.reset));

// ---- Two earlier verdicts per family (same API the UI uses)
execFileSync(PY, [SEED], { stdio: "inherit" });

const page = await login("g.ang", "analyst-demo");
const search = page.locator("#ops-search");
const rows = (p) => page.locator(`button:has([aria-label^="Operational Priority: ${p}"])`);
const setSearch = async (q) => { await search.fill(""); await search.fill(q); };
const waitRows = async (p, min) => {
  for (let t = Date.now(); Date.now() - t < 20000; await sleep(350)) if (await rows(p).count() >= min) return;
  throw new Error(`no ${min} rows at ${p}`);
};
const texts = async (p, n) => {
  const out = [];
  for (let i = 0; i < Math.min(n, await rows(p).count()); i++) out.push((await rows(p).nth(i).innerText()).replace(/\s+/g, " ").slice(0, 120));
  return out;
};
async function verdict(row, reason) {
  await row.click(); await sleep(2200);
  await page.getByRole("tab", { name: "Analyst Verdict", exact: true }).click(); await sleep(1000);
  await page.locator("#analyst-verdict-outcome").selectOption("false_positive");
  await page.getByLabel("Verdict reason").fill(reason);
  await page.getByRole("button", { name: /^(Record Verdict|Correct Verdict)$/ }).first().click();
  await sleep(2500);
}
const available = (p) => rows(p).filter({ hasText: "Available" }).first();
const judged = (p) => rows(p).filter({ hasText: "Completed" }).first();

// Suricata family: before
await setSearch("Terminal Server"); await waitRows("40", 3); await sleep(800);
facts.suriBefore = await texts("40", 3);
await shot(page, "f1-suri-before", [["Search", search], ["Unjudged row at 40", available("40")]]);
// third verdict
await verdict(available("40"), "Known scanner on the jump host, approved.");
await setSearch("Terminal Server"); await waitRows("10", 3); await sleep(800);
facts.suriAfter = await texts("10", 3);
await shot(page, "f2-suri-after", [["Judged (verdict)", judged("10")], ["Unjudged: 40 → 10", available("10")]]);

// Flow family
await setSearch("131.202.240.72"); await waitRows("36.4", 1); await sleep(800);
facts.flowBefore = await texts("36.4", 2);
await verdict(available("36.4"), "Normal HTTPS to a known update server.");
await setSearch("131.202.240.72"); await waitRows("6.4", 2); await sleep(800);
facts.flowAfter = await texts("6.4", 2);
await shot(page, "f3-flow-after", [["Judged (verdict)", judged("6.4")], ["Unjudged: 36.49 → 6.49", available("6.4")]]);

fs.writeFileSync(path.join(OUT, "extra-pins.json"), JSON.stringify(pins, null, 1));
fs.writeFileSync(path.join(OUT, "extra-facts.json"), JSON.stringify({ ...facts, capturedAt: new Date().toISOString(), step: 150 }, null, 1));
console.log(JSON.stringify(facts, null, 1));
await browser.close();
