
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  await p.goto("http://127.0.0.1:5173/login");
  await p.locator("#username").fill("g.ang"); await p.locator("#password").fill("analyst-demo");
  await p.getByRole("button", { name: /sign in/i }).click(); await p.waitForTimeout(2500);
  const first = (await p.getByRole("tablist", { name: "Operational queue views" }).innerText()).replace(/\s+/g, " ");
  await p.waitForTimeout(12000);
  const second = (await p.getByRole("tablist", { name: "Operational queue views" }).innerText()).replace(/\s+/g, " ");
  console.log(JSON.stringify({ first, second, grew: first !== second }, null, 1));
  await p.screenshot({ path: process.env.LOCALAPPDATA + "/Temp/hitl-review/off-live-queue.png" });
  await b.close();
})();