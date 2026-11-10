
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  await p.goto("http://127.0.0.1:5173/login");
  await p.locator("#username").fill("admin"); await p.locator("#password").fill("admin-demo");
  await p.getByRole("button", { name: /sign in/i }).click(); await p.waitForTimeout(2500);
  await p.goto("http://127.0.0.1:5173/admin/guardrails"); await p.waitForTimeout(3000);
  const inputs = await p.locator("input").evaluateAll(xs => xs.map(x => ({ label: x.getAttribute("aria-label") || x.id, value: x.value, type: x.type, disabled: x.disabled })));
  const buttons = await p.getByRole("button").evaluateAll(xs => xs.map(x => x.textContent.trim()).filter(Boolean));
  const text = (await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 1200);
  console.log(JSON.stringify({ inputs, buttons, text }, null, 1));
  await p.screenshot({ path: process.env.LOCALAPPDATA + "/Temp/hitl-review/guardrails-page.png" });
  await b.close();
})();