
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  await p.goto("http://127.0.0.1:5173/login");
  await p.locator("#username").fill("g.ang"); await p.locator("#password").fill("analyst-demo");
  await p.getByRole("button", { name: /sign in/i }).click(); await p.waitForTimeout(2000);
  await p.goto("http://127.0.0.1:5173/analyst/operations?view=all&q=FTP%20Brute%20Force");
  await p.waitForTimeout(2500);
  await p.getByRole("list", { name: "Operational alerts" }).getByRole("button").first().click();
  await p.waitForTimeout(2000);
  const ws = p.getByRole("region", { name: "Operational alert workspace", exact: true });
  for (const tab of ["Evidence", "Flow & Score", "Overview"]) {
    await ws.getByRole("tab", { name: tab, exact: true }).click();
    await p.waitForTimeout(1500);
    const state = await p.evaluate(() => {
      const root = document.querySelector('[aria-label="Operational alert workspace"]');
      const heads = [...root.querySelectorAll("h1,h2,h3,section[aria-label]")].map(n => (n.getAttribute("aria-label") || n.textContent || "").trim().slice(0, 60));
      return { selected: root.querySelector('[role=tab][aria-selected=true]')?.textContent,
               visibleSections: [...root.querySelectorAll("section")].filter(s => s.offsetParent !== null).map(s => s.getAttribute("aria-label") || s.querySelector("h2,h3")?.textContent?.slice(0,40)).filter(Boolean).slice(0,8),
               headings: [...new Set(heads)].slice(0, 12) };
    });
    console.log(tab, JSON.stringify(state));
  }
  await b.close();
})();