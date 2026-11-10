/**
 * Tail of the recorded demo: escalate, Tier 2 investigation, release.
 *   node record_tail.cjs        -> recording/demo-tail.mp4
 */
const { chromium } = require("playwright");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const OUT = path.resolve(__dirname, "recording");
const WEB = "http://127.0.0.1:5173";
const manifest = [];
const errors = [];
const started = Date.now();
const wait = ms => new Promise(r => setTimeout(r, ms));

async function shot(page, name) {
  try { await page.screenshot({ path: path.join(OUT, `tail-${String(manifest.length).padStart(2, "0")}-${name}.png`) }); }
  catch { /* ignore */ }
}
async function openFirst(page, query) {
  const list = page.getByRole("list", { name: "Operational alerts" });
  for (const pause of [3000, 5000]) {
    await page.goto(`${WEB}/analyst/operations?view=all&q=${encodeURIComponent(query)}`);
    await page.waitForTimeout(pause);
    const rows = list.getByRole("button");
    if ((await rows.count()) > 0) { await rows.first().click(); await page.waitForTimeout(2200); return true; }
  }
  return false;
}

(async () => {
  const browser = await chromium.launch({ headless: false, args: ["--window-position=0,0", "--window-size=1300,1000"] });
  const context = await browser.newContext({ viewport: { width: 1260, height: 880 }, recordVideo: { dir: OUT, size: { width: 1260, height: 880 } } });
  const page = await context.newPage();
  page.on("pageerror", e => errors.push(e.message));

  try {
    await page.goto(`${WEB}/login`);
    await page.locator("#username").fill("g.ang");
    await page.locator("#password").fill("analyst-demo");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForTimeout(2500);

    manifest.push({ t: 0, name: "Analyst — escalate a Suricata alert to Tier 2" });
    if (await openFirst(page, "SSH Scan")) {
      const ws = page.getByRole("region", { name: "Operational alert workspace", exact: true });
      await ws.getByLabel("Decision reason", { exact: true }).fill("Recorded demo: scan and brute force from one source.");
      await ws.getByRole("button", { name: "Escalate to Tier 2", exact: true }).click();
      await page.waitForTimeout(3000);
      await shot(page, "escalated");
    }

    manifest.push({ t: 0, name: "Tier 2 — investigate, conclude, resolve" });
    await page.goto(`${WEB}/analyst/tier2-cases`); await page.waitForTimeout(3000);
    const row = page.getByRole("row").filter({ hasText: "SSH Scan" }).first();
    if ((await row.count()) > 0) {
      await row.getByRole("link").first().click(); await page.waitForTimeout(3000);
      await page.getByRole("tab", { name: "Audit Timeline", exact: true }).click();
      await page.getByLabel("Decision reason", { exact: true }).fill("Taking the case for the recorded demo.");
      await page.getByRole("button", { name: "Start investigation", exact: true }).click(); await page.waitForTimeout(2000);
      await page.getByRole("tab", { name: "Investigation Conclusion", exact: true }).click();
      await page.getByLabel("Human Investigation Finding", { exact: true }).selectOption("confirmed_malicious");
      await page.getByLabel("Human Final Attack Classification", { exact: true }).selectOption("brute_force");
      await page.getByLabel("Investigation Reason", { exact: true }).fill("Scan followed by brute force from one source.");
      await page.getByRole("button", { name: "Record Investigation Conclusion", exact: true }).click(); await page.waitForTimeout(2500);
      const resolution = page.getByRole("region", { name: "Case Resolution", exact: true });
      await resolution.getByLabel("Resolution Reason").fill("Confirmed and documented; no plan executed.");
      await resolution.getByRole("button", { name: "Resolve Case", exact: true }).click(); await page.waitForTimeout(2500);
      await shot(page, "case-resolved");
    } else {
      await shot(page, "no-case");
    }

    manifest.push({ t: 0, name: "Analyst — claim and release" });
    if (await openFirst(page, "JA3")) {
      const ws = page.getByRole("region", { name: "Operational alert workspace", exact: true });
      const release = ws.getByRole("button", { name: "Release claim", exact: true });
      if ((await release.count()) > 0) {
        await release.click();
        await ws.getByRole("button", { name: "Release", exact: true }).click();
        await page.waitForTimeout(2000);
      }
      await shot(page, "released");
    }
    manifest.push({ t: 0, name: "Tail complete" });
    console.log("TAIL DONE");
  } catch (cause) {
    errors.push(String(cause).slice(0, 300));
    console.error("TAIL ERROR:", String(cause).slice(0, 300));
  } finally {
    const video = page.video();
    await context.close();
    await browser.close();
    const file = video ? await video.path() : null;
    let tail = null;
    if (file) {
      tail = path.join(OUT, "demo-tail.mp4");
      const result = spawnSync("ffmpeg", ["-y", "-i", file, "-vf", "fps=10", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p", tail], { encoding: "utf8" });
      if (result.status !== 0) errors.push(`ffmpeg: ${String(result.stderr).slice(-300)}`);
    }
    fs.writeFileSync(path.join(OUT, "tail-manifest.json"), JSON.stringify({ tail, chapters: manifest, errors }, null, 1));
    console.log(JSON.stringify({ tail, errors }, null, 1));
  }
})();
