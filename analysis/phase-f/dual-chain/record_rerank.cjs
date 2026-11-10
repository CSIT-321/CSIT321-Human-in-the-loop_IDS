/**
 * Record the reranking gate as the UI can show it.
 *
 * The Web Attack family carries 3 recorded verdicts, so its gate is open and
 * the applied adjustment is visible. One window, one video.
 *
 *   node record_rerank.cjs
 */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const OUT = path.resolve(__dirname, "recording");
const WEB = "http://127.0.0.1:5173";
const WEB_ATTACK = "ba82414a-6e3b-4737-ad71-dc08160a6a27";
fs.mkdirSync(OUT, { recursive: true });
const started = Date.now();
const manifest = [];
const errors = [];
const wait = ms => new Promise(r => setTimeout(r, ms));
const stamp = () => Math.round((Date.now() - started) / 1000);
function chapter(name) { manifest.push({ t: stamp(), name }); console.log(`[${stamp()}s] ${name}`); }
function card(title, body) {
  const html = `<!doctype html><meta charset="utf-8"><body style="margin:0;background:#0b1220;color:#e6edf7;font:600 30px/1.35 Segoe UI,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh">
  <div style="max-width:1180px;padding:0 48px"><div style="font-size:50px">${title}</div>
  <div style="font:400 25px/1.6 Segoe UI,sans-serif;color:#9fb3cc;margin-top:18px">${body}</div></div></body>`;
  return "data:text/html;charset=utf-8," + encodeURIComponent(html);
}
const ws = page => page.getByRole("region", { name: "Operational alert workspace", exact: true });

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

  await page.goto(card("Reranking: three agreeing verdicts in one family",
    "Family = attack class + destination port + protocol + first rule.<br>Gate opens at 3 verdicts and 67 % agreement. Caps: +20 up, -30 down. Critical floor 70."));
  await wait(4000);

  await page.goto(`${WEB}/analyst/operations?view=all&alertRef=${WEB_ATTACK}`);
  await page.waitForFunction(r => document.body.innerText.includes(r), WEB_ATTACK, { timeout: 20000 });
  await page.waitForTimeout(1500);
  await ws(page).getByRole("tab", { name: "Flow & Score", exact: true }).click();
  await page.waitForTimeout(3000);
  const family = page.getByText("Similar alerts (family)").first();
  if (await family.count()) await family.scrollIntoViewIfNeeded();
  else errors.push("family card missing");
  await page.waitForTimeout(1200);
  chapter("Web Attack family: gate open, 3 of 3, applied adjustment");
  await page.screenshot({ path: path.join(OUT, "rerank-webattack-panel.png") });
  await wait(6000);

  await page.goto(card("The same alert now reads P3 / 22.39",
    "Detector score 52.39. The verdict asked for -30 and applied -30. The queue orders by this effective score."));
  await wait(4000);
  chapter("Caption: P3 / 22.39 after the verdict");

  await page.goto(card("Why 1 of 3 and 2 of 3 are not on this recording",
    "A verdict needs a Tier 1 alert with its own page. Grouped members have none.<br>The two FTP alerts are both Tier 2 cases, so the family cannot reach 3 from the screen."));
  await wait(5000);

  const video = page.video();
  await context.close(); await browser.close();
  const file = await video.path();
  const final = path.join(OUT, "demo-rerank.mp4");
  const ff = spawnSync("ffmpeg", ["-y", "-i", file, "-c:v", "libx264", "-preset", "veryfast",
    "-crf", "23", "-pix_fmt", "yuv420p", final], { encoding: "utf8" });
  if (ff.status !== 0) errors.push(`ffmpeg: ${ff.stderr.slice(-400)}`);
  fs.writeFileSync(path.join(OUT, "rerank-manifest.json"), JSON.stringify({ chapters: manifest, errors }, null, 1));
  console.log(JSON.stringify({ video: final, chapters: manifest.length, errors }, null, 1));
})();
