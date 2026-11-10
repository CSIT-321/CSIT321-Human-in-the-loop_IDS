
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  const out = {};
  await p.goto("http://127.0.0.1:5173/login");
  await p.locator("#username").fill("g.ang"); await p.locator("#password").fill("analyst-demo");
  await p.getByRole("button", { name: /sign in/i }).click(); await p.waitForTimeout(2000);
  // Tier 2: take the flow rule case through investigation, conclusion, resolve.
  await p.goto("http://127.0.0.1:5173/analyst/tier2-cases"); await p.waitForTimeout(2500);
  out.caseRows = (await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 700);
  const row = p.getByRole("row").filter({ hasText: "FTP Brute Force" }).first();
  await row.getByRole("link").first().click();
  await p.waitForTimeout(2500);
  await p.getByRole("tab", { name: "Audit Timeline", exact: true }).click();
  await p.getByLabel("Decision reason", { exact: true }).fill("Taking this case for verification.");
  await p.getByRole("button", { name: "Start investigation", exact: true }).click();
  await p.waitForTimeout(2000);
  await p.getByRole("tab", { name: "Investigation Conclusion", exact: true }).click();
  await p.getByLabel("Human Investigation Finding", { exact: true }).selectOption("confirmed_malicious");
  await p.getByLabel("Human Final Attack Classification", { exact: true }).selectOption("brute_force");
  await p.getByLabel("Investigation Reason", { exact: true }).fill("Scan followed by brute force from one source.");
  await p.getByRole("button", { name: "Record Investigation Conclusion", exact: true }).click();
  await p.waitForTimeout(2500);
  const res = p.getByRole("region", { name: "Case Resolution", exact: true });
  out.conclusion = (await res.innerText()).replace(/\s+/g, " ").slice(0, 400);
  await res.getByLabel("Resolution Reason").fill("Confirmed and documented for verification.");
  await res.getByRole("button", { name: "Resolve Case", exact: true }).click();
  await p.waitForTimeout(2500);
  out.resolved = (await res.innerText()).replace(/\s+/g, " ").match(/Resolved by:[^·]{0,40}/)?.[0];
  await p.screenshot({ path: process.env.LOCALAPPDATA + "/Temp/hitl-review/walk-on/tier2-resolved.png" });
  // Claim then release an available alert.
  await p.goto("http://127.0.0.1:5173/analyst/operations?view=all&q=ET%20SCAN"); await p.waitForTimeout(2500);
  await p.getByRole("list", { name: "Operational alerts" }).getByRole("button").first().click();
  await p.waitForTimeout(1800);
  const ws = p.getByRole("region", { name: "Operational alert workspace", exact: true });
  out.claim = (await ws.getByRole("region", { name: "Human work status" }).innerText()).replace(/\s+/g, " ");
  await ws.getByRole("button", { name: "Release claim", exact: true }).click();
  await ws.getByRole("button", { name: "Release", exact: true }).click();
  await p.waitForTimeout(2000);
  out.release = (await ws.getByRole("region", { name: "Human work status" }).innerText()).replace(/\s+/g, " ");
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})();