/**
 * Record the ten unique end results listed on workflow-layout/index.html.
 *
 * One window, one video: a caption card names the result, then the analyst
 * workstation opens that result's operational ref. No second window, so the
 * recording cannot drift out of sync.
 *
 *   node record_results.cjs
 */
const { chromium } = require("playwright");
const fs = require("node:fs");
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const OUT = path.resolve(__dirname, "recording");
const WEB = "http://127.0.0.1:5173";
const RESULTS = JSON.parse(fs.readFileSync(path.join(__dirname, "results_index.json"), "utf8"));
fs.mkdirSync(OUT, { recursive: true });
const started = Date.now();
const manifest = [];
const errors = [];
const wait = ms => new Promise(r => setTimeout(r, ms));
const stamp = () => Math.round((Date.now() - started) / 1000);
function chapter(name) { manifest.push({ t: stamp(), name }); console.log(`[${stamp()}s] ${name}`); }

function card(result) {
  const html = `<!doctype html><meta charset="utf-8"><body style="margin:0;background:#0b1220;color:#e6edf7;font:600 30px/1.35 Segoe UI,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh">
  <div style="max-width:1100px;padding:0 48px">
    <div style="color:#7fb2ff;font-size:22px;letter-spacing:.12em">UNIQUE END RESULT ${result.id}</div>
    <div style="font-size:52px;margin:14px 0 10px">${result.title}</div>
    <div style="font:400 26px/1.5 Segoe UI,sans-serif;color:#9fb3cc">
      ${result.chain.toUpperCase()} chain · ${result.count.toLocaleString("en-US")} alert${result.count === 1 ? "" : "s"} · ${result.route}
    </div>
  </div></body>`;
  return "data:text/html;charset=utf-8," + encodeURIComponent(html);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 },
    recordVideo: { dir: OUT, size: { width: 1600, height: 900 } } });
  const page = await context.newPage();
  page.on("pageerror", e => errors.push(e.message));

  await page.goto(`${WEB}/login`);
  await page.locator("#username").fill("g.ang");
  await page.locator("#password").fill("analyst-demo");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForTimeout(2500);
  chapter("Analyst workstation signed in");

  for (const result of RESULTS) {
    await page.goto(card(result));
    await wait(1500);
    chapter(`${result.id} ${result.title}`);
    await page.goto(`${WEB}/analyst/operations?view=all&alertRef=${result.ref}`);
    try { await page.waitForFunction(r => document.body.innerText.includes(r), result.ref, { timeout: 15000 }); }
    catch { errors.push(`${result.id}: ${result.ref} did not render`); }
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(OUT, `results-${result.id}.png`) });
    await wait(4200);
  }

  await page.goto(card({ id: "END", title: "All ten unique end results shown", chain: "both", count: RESULTS.length, route: "see workflow-layout/index.html" }));
  await wait(2000);
  chapter("End of the ten results");

  const video = page.video();
  await context.close(); await browser.close();
  const file = await video.path();
  const final = path.join(OUT, "demo-results.mp4");
  const ff = spawnSync("ffmpeg", ["-y", "-i", file, "-c:v", "libx264", "-preset", "veryfast",
    "-crf", "23", "-pix_fmt", "yuv420p", final], { encoding: "utf8" });
  if (ff.status !== 0) errors.push(`ffmpeg: ${ff.stderr.slice(-400)}`);
  fs.writeFileSync(path.join(OUT, "results-manifest.json"), JSON.stringify({ chapters: manifest, errors }, null, 1));
  console.log(JSON.stringify({ video: final, chapters: manifest.length, errors }, null, 1));
})();
