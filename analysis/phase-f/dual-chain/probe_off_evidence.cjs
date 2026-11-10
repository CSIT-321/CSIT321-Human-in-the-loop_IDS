
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  await p.goto("http://127.0.0.1:5173/login");
  await p.locator("#username").fill("g.ang"); await p.locator("#password").fill("analyst-demo");
  await p.getByRole("button", { name: /sign in/i }).click(); await p.waitForTimeout(2000);
  await p.goto("http://127.0.0.1:5173/analyst/operations?view=all&q=ET%20SCAN");
  await p.waitForTimeout(2500);
  await p.getByRole("list", { name: "Operational alerts" }).getByRole("button").first().click();
  await p.waitForTimeout(2000);
  const ws = p.getByRole("region", { name: "Operational alert workspace", exact: true });
  await ws.getByRole("tab", { name: "Evidence", exact: true }).click();
  await p.waitForTimeout(2500);
  const sections = await p.evaluate(() => {
    const root = document.querySelector('[aria-label="Operational alert workspace"]');
    return [...root.querySelectorAll("section")].filter(s => s.offsetParent !== null)
      .map(s => s.getAttribute("aria-label") || s.querySelector("h2,h3")?.textContent?.slice(0,48)).filter(Boolean);
  });
  const tabs = await root_tabs(p);
  async function root_tabs(page) { return page.getByRole("region", { name: "Operational alert workspace", exact: true }).getByRole("tab").allTextContents(); }
  console.log(JSON.stringify({ tabs, sections }, null, 1));
  await p.screenshot({ path: process.env.LOCALAPPDATA + "/Temp/hitl-review/walk-off/evidence-suricata.png" });
  await b.close();
})();