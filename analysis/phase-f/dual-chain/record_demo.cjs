/**
 * Recorded demo of every program function (reliable capture).
 *
 * Playwright records each window; on close the videos are finalised, then ffmpeg joins them side by side.
 *   node record_demo.cjs
 * Output: recording/demo-full.mp4 (admin left, analyst right) + chapter manifest + screenshots.
 */
const { chromium } = require("playwright");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const OUT = path.resolve(__dirname, "recording");
const API = "http://127.0.0.1:8000";
const WEB = "http://127.0.0.1:5173";
fs.mkdirSync(OUT, { recursive: true });
const started = Date.now();
const manifest = [];
const errors = [];
const wait = ms => new Promise(r => setTimeout(r, ms));
const stamp = () => Math.round((Date.now() - started) / 1000);

function chapter(name) { manifest.push({ t: stamp(), name }); console.log(`[${stamp()}s] ${name}`); }
async function shot(page, name) {
  try { await page.screenshot({ path: path.join(OUT, `${String(manifest.length).padStart(2, "0")}-${name}.png`) }); }
  catch { /* never stop the demo for a screenshot */ }
}
async function callApi(pathname, token, body) {
  const response = await fetch(API + pathname, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  return response.json();
}
async function chainState() {
  const state = await callApi("/api/admin/workspaces", TOKEN);
  return state.detection.flowChainEnabled;
}
async function setChain(page, want) {
  const toggle = page.getByRole("switch", { name: "CICFlowMeter flow chain" });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if ((await chainState()) === want) return true;
    await toggle.click(); await wait(1400);
  }
  return (await chainState()) === want;
}
let TOKEN = null;
async function openFirst(page, query) {
  const list = page.getByRole("list", { name: "Operational alerts" });
  for (const attempt of [0, 1]) {
    await page.goto(`${WEB}/analyst/operations?view=all&q=${encodeURIComponent(query)}`);
    await page.waitForTimeout(attempt === 0 ? 3000 : 5000);
    const rows = list.getByRole("button");
    if ((await rows.count()) > 0) { await rows.first().click(); await page.waitForTimeout(2200); return true; }
  }
  await page.goto(`${WEB}/analyst/operations?view=all`);
  await page.waitForTimeout(3000);
  const rows = list.getByRole("button");
  if ((await rows.count()) > 0) { await rows.first().click(); await page.waitForTimeout(2200); return true; }
  return false;
}
async function signIn(context, user, password) {
  const page = await context.newPage();
  page.on("pageerror", e => errors.push(`${user}: ${e.message}`));
  await page.goto(`${WEB}/login`);
  await page.locator("#username").fill(user);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForTimeout(2500);
  return page;
}

(async () => {
  const token = (await callApi("/api/auth/login", null, { username: "admin", password: "admin-demo" })).token;
  TOKEN = token;
  await callApi("/api/admin/workspaces/operational/activate", token, { reason: "Recorded demo: clean start" });
  await callApi("/api/admin/workspaces/v3-1-replay/reset", token, { reason: "Recorded demo: clean start" });
  const cleanState = await callApi("/api/admin/workspaces", token);
  if (cleanState.workspaces[1].ready) throw new Error("replay is still prepared after reset — refusing to record");
  console.log("clean slate:", cleanState.workspaces[1].ready, cleanState.detection);

  const browser = await chromium.launch({ headless: false,
    args: ["--window-position=0,0", "--window-size=1280,1400"] });
  const adminContext = await browser.newContext({ viewport: { width: 1260, height: 880 }, recordVideo: { dir: OUT, size: { width: 1260, height: 880 } } });
  const analystContext = await browser.newContext({ viewport: { width: 1260, height: 880 }, recordVideo: { dir: OUT, size: { width: 1260, height: 880 } } });
  const admin = await signIn(adminContext, "admin", "admin-demo");
  const analyst = await signIn(analystContext, "g.ang", "analyst-demo");

  try {
    chapter("Admin — Operational Workspace");
    await admin.goto(`${WEB}/admin/workspaces`); await wait(2500); await shot(admin, "admin-workspaces");

    chapter("Admin — CICFlowMeter switch off, then on");
    await setChain(admin, true);
    console.log("chain before clicks:", await chainState());
    await setChain(admin, false); await wait(1800); await shot(admin, "chain-off");
    console.log("chain after off:", await chainState());
    await setChain(admin, true); await wait(1800); await shot(admin, "chain-on");
    console.log("chain after on:", await chainState());

    chapter("Admin — reranking guardrails: edit and restore");
    await admin.goto(`${WEB}/admin/guardrails`); await wait(2500); await shot(admin, "guardrails");
    const limit = admin.locator("#guardrail-maxFeedbackIncrease");
    const original = await limit.inputValue();
    await limit.fill(String(Number(original) + 1));
    await admin.getByLabel(/Reason for this change/i).fill("Recorded demo: the limits are editable.");
    await admin.getByRole("button", { name: "Save changes" }).click(); await wait(2500);
    await shot(admin, "guardrails-saved");
    await limit.fill(original);
    await admin.getByLabel(/Reason for this change/i).fill("Recorded demo: restore the original limit.");
    await admin.getByRole("button", { name: "Save changes" }).click(); await wait(2000);

    chapter("Admin — prepare, activate, start the replay");
    await admin.goto(`${WEB}/admin/workspaces`); await wait(2000);
    const modeSelect = admin.getByLabel("Replay preparation mode");
    if ((await modeSelect.count()) > 0) {
      await modeSelect.selectOption("packet");
      await admin.getByRole("button", { name: "Prepare Replay" }).click(); await wait(4000);
    } else {
      console.log("replay already prepared — skipping prepare");
    }
    await callApi("/api/admin/workspaces/v3-1-replay/activate", token, { reason: "Recorded demo: activate replay" });
    await admin.reload(); await wait(2500);
    const start = admin.getByRole("button", { name: "Start Arrivals", exact: true });
    if ((await start.count()) > 0) { await start.click(); await wait(2000); }
    console.log("playback:", (await callApi("/api/admin/workspaces", token)).workspaces[1].playbackState);
    await shot(admin, "replay-running");

    chapter("Analyst — live arrivals, both chains");
    await analyst.goto(`${WEB}/analyst/operations`); await wait(4000); await shot(analyst, "queue-arriving");
    await wait(12000); await shot(analyst, "queue-arriving-2");

    chapter("Admin — flow chain off during the capture");
    console.log("off ok:", await setChain(admin, false));
    await wait(1500); await shot(admin, "chain-off-live");
    chapter("Analyst — only Suricata keeps arriving");
    await wait(25000); await shot(analyst, "suricata-only-live");

    chapter("Admin — flow chain on again (backlog caught up)");
    console.log("on ok:", await setChain(admin, true));
    await wait(25000); await shot(analyst, "both-chains-back");

    chapter("Admin — overview");
    await admin.goto(`${WEB}/admin/overview`); await wait(3000); await shot(admin, "admin-overview");
    chapter("Admin — governance");
    await admin.goto(`${WEB}/admin/governance`); await wait(3000); await shot(admin, "admin-governance");
    chapter("Admin — users and access");
    await admin.goto(`${WEB}/admin/users`); await wait(3000); await shot(admin, "admin-users");
    chapter("Admin — evaluation and audit");
    await admin.goto(`${WEB}/admin/evaluation`); await wait(3000); await shot(admin, "admin-evaluation");

    chapter("Analyst — incoming alerts");
    await analyst.goto(`${WEB}/analyst/external-admission`); await wait(3000); await shot(analyst, "incoming-alerts");
    chapter("Analyst — selective review");
    await analyst.goto(`${WEB}/analyst/selective-review`); await wait(3000); await shot(analyst, "selective-review");
    chapter("Analyst — triage memory");
    await analyst.goto(`${WEB}/analyst/triage-memory`); await wait(3000); await shot(analyst, "triage-memory");
    chapter("Analyst — tier 2 cases");
    await analyst.goto(`${WEB}/analyst/tier2-cases`); await wait(3000); await shot(analyst, "tier2-cases");

    chapter("Analyst — queue views while the capture runs");
    await analyst.goto(`${WEB}/analyst/operations`); await wait(2000);
    for (const view of ["tier1", "tier2", "auto-escalated", "expert", "critical"]) {
      await analyst.locator(`#queue-view-${view}`).click(); await wait(3000);
      await shot(analyst, `view-${view}`);
    }
    let state = await callApi("/api/admin/workspaces", token);
    let polls = 0;
    while (state.workspaces[1].playbackState !== "complete" && polls < 90) {
      await wait(15000); polls += 1;
      state = await callApi("/api/admin/workspaces", token);
      if (polls % 4 === 0) {
        chapter(`Analyst — queue at ${state.workspaces[1].holdoutArrived}/160 steps`);
        await analyst.goto(`${WEB}/analyst/operations`); await wait(1500);
        await shot(analyst, `queue-step-${state.workspaces[1].holdoutArrived}`);
      }
    }
    chapter("Capture complete — both chains in one queue");
    await analyst.goto(`${WEB}/analyst/operations`); await wait(3000); await shot(analyst, "complete-queue");

    const unique = [
      ["FTP Brute Force", "flow-corroborated-group"],
      ["XGBoost: Infiltration", "flow-model-only-group"],
      ["XGBoost: Web Attack", "flow-model-only-group-2"],
      ["XGBoost: Benign", "flow-unflagged-single"],
      ["Sipvicious", "suricata-unknown-expert"],
      ["JA3", "suricata-malware-medium"],
      ["Terminal Server", "suricata-recon-medium"],
      ["SSH Scan", "suricata-recon-high"],
      ["ETERNALBLUE", "suricata-malware-critical"],
    ];
    for (const [query, name] of unique) {
      chapter(`Alert — ${name}`);
      if (!(await openFirst(analyst, query))) { await shot(analyst, `${name}-empty`); continue; }
      await shot(analyst, `${name}-overview`);
      const ws = analyst.getByRole("region", { name: "Operational alert workspace", exact: true });
      for (const tab of ["Evidence", "Flow & Score"]) {
        const button = ws.getByRole("tab", { name: tab, exact: true });
        if ((await button.count()) === 0) continue;
        await button.click(); await wait(2500);
        await shot(analyst, `${name}-${tab.replace(/\W/g, "")}`);
      }
    }

    chapter("Analyst — record a verdict (rerank)");
    try {
    if (await openFirst(analyst, "XGBoost: Web Attack")) {
      const ws = analyst.getByRole("region", { name: "Operational alert workspace", exact: true });
      await ws.getByRole("tab", { name: "Analyst Verdict", exact: true }).click(); await wait(1500);
      const verdict = ws.getByRole("region", { name: "Analyst Verdict", exact: true });
      await verdict.getByLabel("Verdict outcome").selectOption("false_positive");
      await verdict.getByLabel("Verdict reason").fill("Recorded demo: model-only signal, no rule matched.");
      await verdict.getByRole("button", { name: "Record Verdict", exact: true }).click(); await wait(3000);
      await shot(analyst, "verdict-rerank");
    }
    } catch (cause) { errors.push("verdict: " + String(cause).slice(0, 200)); }

    chapter("Analyst — escalate a Suricata alert to Tier 2");
    try {
    if (await openFirst(analyst, "SSH Scan")) {
      const ws = analyst.getByRole("region", { name: "Operational alert workspace", exact: true });
      await ws.getByLabel("Decision reason", { exact: true }).fill("Recorded demo: scan and brute force from one source.");
      await ws.getByRole("button", { name: "Escalate to Tier 2", exact: true }).click(); await wait(3000);
      await shot(analyst, "escalated");
    }
    } catch (cause) { errors.push("escalate: " + String(cause).slice(0, 200)); }

    chapter("Tier 2 — investigate, conclude, resolve");
    try {
    await analyst.goto(`${WEB}/analyst/tier2-cases`); await wait(3000);
    const caseRow = analyst.getByRole("row").filter({ hasText: "SSH Scan" }).first();
    if ((await caseRow.count()) > 0) {
      await caseRow.getByRole("link").first().click(); await wait(3000);
      await analyst.getByRole("tab", { name: "Audit Timeline", exact: true }).click();
      await analyst.getByLabel("Decision reason", { exact: true }).fill("Taking the case for the recorded demo.");
      await analyst.getByRole("button", { name: "Start investigation", exact: true }).click(); await wait(2000);
      await analyst.getByRole("tab", { name: "Investigation Conclusion", exact: true }).click();
      await analyst.getByLabel("Human Investigation Finding", { exact: true }).selectOption("confirmed_malicious");
      await analyst.getByLabel("Human Final Attack Classification", { exact: true }).selectOption("brute_force");
      await analyst.getByLabel("Investigation Reason", { exact: true }).fill("Scan followed by brute force from one source.");
      await analyst.getByRole("button", { name: "Record Investigation Conclusion", exact: true }).click(); await wait(2500);
      const resolution = analyst.getByRole("region", { name: "Case Resolution", exact: true });
      await resolution.getByLabel("Resolution Reason").fill("Confirmed and documented; no plan executed.");
      await resolution.getByRole("button", { name: "Resolve Case", exact: true }).click(); await wait(2500);
      await shot(analyst, "case-resolved");
    }

    } catch (cause) { errors.push("tier2: " + String(cause).slice(0, 200)); }

    chapter("Analyst — claim and release");
    try {
    if (await openFirst(analyst, "JA3")) {
      const ws = analyst.getByRole("region", { name: "Operational alert workspace", exact: true });
      await ws.getByRole("button", { name: "Release claim", exact: true }).click();
      await ws.getByRole("button", { name: "Release", exact: true }).click(); await wait(2000);
      await shot(analyst, "released");
    }
    } catch (cause) { errors.push("release: " + String(cause).slice(0, 200)); }
    chapter("Demo complete");
  } catch (cause) {
    errors.push(String(cause));
    console.error("DEMO ERROR:", String(cause).slice(0, 400));
  } finally {
    const adminVideo = admin.video();
    const analystVideo = analyst.video();
    await adminContext.close();
    await analystContext.close();
    await browser.close();
    const adminFile = adminVideo ? await adminVideo.path() : null;
    const analystFile = analystVideo ? await analystVideo.path() : null;
    let combined = null;
    if (adminFile && analystFile) {
      combined = path.join(OUT, "demo-full.mp4");
      const result = spawnSync("ffmpeg", ["-y", "-i", adminFile, "-i", analystFile,
        "-filter_complex", "[0:v]scale=1260:880[a];[1:v]scale=1260:880[b];[a][b]hstack=inputs=2,fps=10",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p", combined],
        { encoding: "utf8" });
      if (result.status !== 0) errors.push(`ffmpeg: ${String(result.stderr).slice(-400)}`);
    }
    fs.writeFileSync(path.join(OUT, "manifest.json"),
      JSON.stringify({ combined, adminFile, analystFile, chapters: manifest, errors }, null, 1));
    console.log(JSON.stringify({ combined, chapters: manifest.length, errors: errors.slice(0, 3) }, null, 1));
  }
})();
