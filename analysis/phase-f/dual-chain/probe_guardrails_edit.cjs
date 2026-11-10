
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  const out = {};
  await p.goto("http://127.0.0.1:5173/login");
  await p.locator("#username").fill("admin"); await p.locator("#password").fill("admin-demo");
  await p.getByRole("button", { name: /sign in/i }).click(); await p.waitForTimeout(2500);
  await p.goto("http://127.0.0.1:5173/admin/guardrails"); await p.waitForTimeout(2500);
  const box = p.locator("#guardrail-maxFeedbackIncrease");
  out.before = await box.inputValue();
  await box.fill(String(Number(out.before) + 1));
  await p.getByLabel(/Reason for this change/i).fill("Verification run: prove the admin can edit reranking limits.");
  await p.getByRole("button", { name: "Save changes" }).click();
  await p.waitForTimeout(3000);
  out.afterSave = await p.locator("#guardrail-maxFeedbackIncrease").inputValue();
  out.savedText = (await p.locator("body").innerText()).replace(/\s+/g, " ").match(/Guardrail[^.]{0,120}|saved[^.]{0,120}/i)?.[0];
  await p.screenshot({ path: process.env.LOCALAPPDATA + "/Temp/hitl-review/guardrails-saved.png" });
  // restore
  await p.locator("#guardrail-maxFeedbackIncrease").fill(out.before);
  await p.getByLabel(/Reason for this change/i).fill("Verification run: restore the original value.");
  await p.getByRole("button", { name: "Save changes" }).click();
  await p.waitForTimeout(2500);
  out.restored = await p.locator("#guardrail-maxFeedbackIncrease").inputValue();
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})();