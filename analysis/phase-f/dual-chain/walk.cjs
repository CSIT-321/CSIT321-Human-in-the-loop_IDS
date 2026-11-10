/**
 * Walk the live demo in one state (on|off) and print what the analyst sees.
 *   node walk.cjs on
 * Screenshots: %LOCALAPPDATA%/Temp/hitl-review/walk-<state>/
 */
const { chromium } = require("playwright");
const fs = require("node:fs");
const state = process.argv[2] ?? "on";
const out = `${process.env.LOCALAPPDATA}/Temp/hitl-review/walk-${state}`;
fs.mkdirSync(out, { recursive: true });

async function signIn(browser, user, password, urlPart) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  await page.goto("http://127.0.0.1:5173/login");
  await page.locator("#username").fill(user);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(new RegExp(urlPart), { timeout: 20000 });
  await page.waitForTimeout(2000);
  return { page, errors };
}

(async () => {
  const browser = await chromium.launch();
  const report = { state };

  const admin = await signIn(browser, "admin", "admin-demo", "/admin");
  await admin.page.goto("http://127.0.0.1:5173/admin/workspaces");
  await admin.page.waitForTimeout(2000);
  const sw = admin.page.getByRole("switch", { name: "CICFlowMeter flow chain" });
  report.toggle = await sw.getAttribute("aria-checked");
  report.toggleText = (await admin.page.locator("body").innerText()).split("\n").find(l => l.includes("flow records"));
  await admin.page.screenshot({ path: `${out}/admin-workspaces.png` });

  const analyst = await signIn(browser, "g.ang", "analyst-demo", "/analyst/operations");
  const page = analyst.page;
  report.tabs = (await page.getByRole("tablist", { name: "Operational queue views" }).innerText()).replace(/\s+/g, " ").trim();
  await page.screenshot({ path: `${out}/queue.png` });

  const query = state === "on" ? "FTP Brute Force" : "ET SCAN";
  await page.goto(`http://127.0.0.1:5173/analyst/operations?view=all&q=${encodeURIComponent(query)}`);
  await page.waitForTimeout(2500);
  const first = page.getByRole("list", { name: "Operational alerts" }).getByRole("button").first();
  report.firstRow = (await first.innerText()).replace(/\s+/g, " ");
  report.searchUsed = query;
  await first.click();
  await page.waitForTimeout(2500);
  const workspace = page.getByRole("region", { name: "Operational alert workspace", exact: true });
  const overview = (await workspace.innerText()).replace(/\s+/g, " ");
  report.overview = {
    signatureAndModel: /Signature \+ XGBoost/.test(overview),
    agreementLine: /Signature and ML agreement/.test(overview),
    suricataSignatures: /Related Suricata signatures/.test(overview),
    hasScore: /Operational Priority/.test(overview),
  };
  await page.screenshot({ path: `${out}/detail-overview.png` });

  for (const [tab, key] of [["Evidence", "evidence"], ["Flow & Score", "flowScore"]]) {
    const button = workspace.getByRole("tab", { name: tab, exact: true });
    if ((await button.count()) === 0) { report[key] = "tab absent"; continue; }
    await button.click();
    await page.waitForTimeout(1800);
    const text = (await workspace.innerText()).replace(/\s+/g, " ");
    report[key] = {
      modelEvidence: /Model Evidence|Historical XGBoost Evidence/.test(text),
      shap: /TreeSHAP|Attributions/.test(text),
      suricataRules: /Related Suricata signatures|Suricata Rule Evidence/.test(text),
      text: text.slice(0, 400),
    };
    await page.screenshot({ path: `${out}/detail-${key}.png` });
  }
  report.errors = [...admin.errors, ...analyst.errors];
  fs.writeFileSync(`${out}/report.json`, JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1));
  await browser.close();
})();
