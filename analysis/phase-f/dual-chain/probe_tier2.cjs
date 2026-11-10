
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  await p.goto("http://127.0.0.1:5173/login");
  await p.locator("#username").fill("g.ang"); await p.locator("#password").fill("analyst-demo");
  await p.getByRole("button", { name: /sign in/i }).click(); await p.waitForTimeout(2000);
  await p.goto("http://127.0.0.1:5173/analyst/tier2-cases"); await p.waitForTimeout(3000);
  console.log((await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 900));
  console.log("rows:", await p.getByRole("row").count());
  await b.close();
})();