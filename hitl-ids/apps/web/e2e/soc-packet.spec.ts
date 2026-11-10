import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

/**
 * SOC guide on Packet Replay (soc-packet-fixture.py: a temp copy of data/demo.db on :8040).
 *   Admin: sign in -> choose Packet Replay -> prepare -> activate -> next 5 steps -> start arrivals
 *   Analyst (same login page): live arrivals -> both chains in one queue -> claim a Suricata alert -> evidence
 *     -> note -> escalate to Tier 2 -> flow group: Flow & Score -> verdict -> case list -> conclude -> resolve -> release
 * After each write the spec reads the stored row through a read-only /__soc route. Screenshots and facts.json
 * land in GUIDE_OUT (default test-results/soc-packet-guide). The guide text takes its numbers from facts.json.
 */
const OUT = process.env.GUIDE_OUT ?? "test-results/soc-packet-guide";
const API = "http://127.0.0.1:8040";

test("SOC packet replay: admin replay control, live arrivals, both chains, Tier 1 to Tier 2", async ({ browser }) => {
  mkdirSync(OUT, { recursive: true });
  const errors: string[] = [];
  const facts: Record<string, unknown> = {};
  const pins: Record<string, { label: string; box: { x: number; y: number; width: number; height: number } | null }[]> = {};
  const newPage = async () => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p = await context.newPage(); p.setDefaultTimeout(30_000);
    p.on("pageerror", e => errors.push(e.message)); return p;
  };
  const shot = async (p: Page, name: string, subject?: Locator, targets: [string, Locator][] = []) => {
    if (subject) await subject.scrollIntoViewIfNeeded();
    pins[name] = [];
    for (const [label, target] of targets) pins[name].push({ label, box: await target.boundingBox() });
    await p.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" });
  };
  const get = async (p: Page, route: string) => (await p.request.get(`${API}${route}`)).json();
  const signIn = async (p: Page, user: string, password: string, name?: string) => {
    await p.goto("/login");
    await p.getByLabel("Username").fill(user); await p.getByLabel("Password", { exact: true }).fill(password);
    if (name) await shot(p, name, undefined, [["Sign in", p.getByRole("button", { name: "Sign in" })]]);
    await p.getByRole("button", { name: "Sign in" }).click();
  };

  // ---------- Admin: one login, Packet Replay ----------
  const admin = await newPage();
  await signIn(admin, "admin", "admin-demo", "00-login");
  await expect(admin).toHaveURL(/\/admin\//);
  await admin.goto("/admin/workspaces");
  const mode = admin.getByLabel("Replay preparation mode");
  await mode.selectOption("packet");
  const prepare = admin.getByRole("button", { name: "Prepare Replay", exact: true });
  await shot(admin, "01-prepare", undefined, [["Preparation mode", mode], ["Prepare Replay", prepare]]);
  await prepare.click();
  await expect(admin.getByText("Packet Replay", { exact: true })).toBeVisible();
  const activate = admin.getByRole("button", { name: "Activate", exact: true }).nth(1);
  await activate.click();
  await expect(admin.getByText("Capture steps arrived:")).toBeVisible();
  await admin.getByRole("button", { name: "Next 5 Steps", exact: true }).click();
  await expect(admin.getByText(/Capture steps arrived:\s*5 \/ 160/)).toBeVisible({ timeout: 60_000 });
  await admin.getByRole("button", { name: "Start Arrivals", exact: true }).click();
  await expect(admin.getByText(/Playback:\s*Running/)).toBeVisible();
  facts.afterFive = await get(admin, "/__soc/counts");
  await shot(admin, "02-running", undefined, [["Steps arrived", admin.getByText("Capture steps arrived:")],
    ["Pause", admin.getByRole("button", { name: "Pause", exact: true })],
    ["Next Step", admin.getByRole("button", { name: "Next Step", exact: true })]]);

  // ---------- Analyst: same login page, live arrivals ----------
  const page = await newPage();
  await signIn(page, "g.ang", "analyst-demo");
  await expect(page).toHaveURL(/\/analyst\/operations/);
  const views = page.getByRole("tablist", { name: "Operational queue views" });
  const active = views.locator("#queue-view-all");
  await expect(page.getByText("Arrival updates connected")).toBeVisible();
  const first = (await active.innerText()).replace(/\s+/g, " ");
  await shot(page, "03-arrivals-before", undefined, [["Workspace", page.getByText(/Workspace: V3\.1 Demo Replay/)],
    ["Queue count", active], ["Live updates", page.getByText("Arrival updates connected")]]);
  await expect.poll(async () => (await active.innerText()).replace(/\s+/g, " "), { timeout: 60_000 }).not.toBe(first);
  const second = (await active.innerText()).replace(/\s+/g, " ");
  await shot(page, "04-arrivals-after", undefined, [["Queue count", active]]);
  facts.arrivals = { before: first, after: second };

  // Fast-forward the rest of the capture for the guide run (in a demo: let Start Arrivals run, ~13 min).
  const token = (await (await admin.request.post(`${API}/api/auth/login`, { data: { username: "admin", password: "admin-demo" } })).json()).token;
  const auth = { Authorization: `Bearer ${token}` };
  expect((await admin.request.post(`${API}/api/admin/workspaces/v3-1-replay/pause`, { headers: auth, data: { reason: "Guide run: fast-forward" } })).status()).toBe(200);
  const state = await (await admin.request.get(`${API}/api/admin/workspaces`, { headers: auth })).json();
  const remaining = state.workspaces[1].holdoutRemaining as number;
  const ff = await admin.request.post(`${API}/api/admin/workspaces/v3-1-replay/advance`, { headers: auth, timeout: 600_000,
    data: { reason: "Guide run: fast-forward", requestId: crypto.randomUUID(), count: 150 } });
  expect(ff.status()).toBe(200);
  for (let i = 0; i < remaining - 150; i += 1)
    expect((await admin.request.post(`${API}/api/admin/workspaces/v3-1-replay/advance`, { headers: auth, timeout: 120_000,
      data: { reason: "Guide run: fast-forward", requestId: crypto.randomUUID(), count: 1 } })).status()).toBe(200);
  facts.complete = await get(admin, "/__soc/counts");
  await admin.goto("/admin/workspaces");
  await expect(admin.getByText(/Playback:\s*Complete/)).toBeVisible();
  await shot(admin, "05-complete", undefined, [["Steps arrived", admin.getByText("Capture steps arrived:")]]);

  // ---------- Analyst: both chains in one queue ----------
  await page.goto("/analyst/operations?view=auto-escalated");
  const complete = facts.complete as { autoCases: number; tier2Cases?: number };
  await expect(views.locator("#queue-view-tier2")).toContainText(String(complete.tier2Cases ?? complete.autoCases));
  await shot(page, "06-both-chains", undefined, [["Tier 2", views.locator("#queue-view-tier2")],
    ["Queue", page.getByRole("list", { name: "Operational alerts" })]]);

  const workspace = page.getByRole("region", { name: "Operational alert workspace", exact: true });
  const work = workspace.getByRole("region", { name: "Human work status" });
  const proof = async (ref: string) => get(page, `/__soc/proof/${ref}`);
  async function openRow(ref: string) {
    await page.goto(`/analyst/operations?view=all&q=${ref}`);
    await page.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${ref}"]`).click();
    await expect(workspace).toContainText(ref);
  }
  const tab = async (name: string) => workspace.getByRole("tab", { name, exact: true }).click();
  const picks = await get(page, "/__soc/picks");
  facts.picks = picks;
  for (const key of ["suricataSsh", "flowAuto", "flowRoutine", "suricataRelease"])
    facts[key] = await get(page, `/__soc/facts/${picks[key]}`);

  // claim a Suricata alert and read its evidence
  const S = picks.suricataSsh as string;
  await openRow(S);
  await expect(work).toContainText("Your Access: Owner");
  expect((await proof(S)).work).toEqual(["in_review", "Glenn Ang", null]);
  await shot(page, "07-claimed", undefined, [["Claimed row", page.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${S}"]`)],
    ["Work status", work]]);
  await tab("Evidence");
  const sigs = workspace.getByRole("table", { name: "Related Suricata signatures" });
  await expect(sigs).toBeVisible();
  await shot(page, "08-suricata-evidence", sigs, [["Evidence", workspace.getByRole("tab", { name: "Evidence", exact: true })], ["Signatures", sigs]]);

  // note
  await tab("History & Notes");
  await workspace.getByPlaceholder("Add a note (you own this alert)").fill(
    `SSH scan from ${picks.sshSource}. The flow chain auto-escalated a brute-force group from the same source.`);
  await workspace.getByRole("button", { name: "Add note", exact: true }).click();
  const notes = workspace.getByRole("list", { name: "Investigation notes" });
  await expect(notes).toContainText("Glenn Ang");
  expect((await proof(S)).notes).toEqual(["Glenn Ang"]);
  await shot(page, "09-note", notes, [["History & Notes", workspace.getByRole("tab", { name: "History & Notes", exact: true })], ["Note", notes]]);

  // human escalation
  await tab("Overview");
  const escalate = workspace.getByRole("button", { name: "Escalate to Tier 2", exact: true });
  await expect(escalate).toBeDisabled();
  const reason = workspace.getByLabel("Decision reason", { exact: true });
  await reason.fill("Scan and flow brute force from one source: one campaign. Needs an expert.");
  await shot(page, "10-escalate", reason, [["Decision reason", reason], ["Escalate to Tier 2", escalate]]);
  await escalate.click();
  const result = workspace.getByRole("status", { name: "Tier 2 escalation result" });
  await expect(result).toContainText("Escalated to Tier 2");
  await expect.poll(async () => (await proof(S)).case?.[2]).toBe("open");
  const pS = await proof(S);
  expect(pS.work[0]).toBe("escalated"); expect(pS.case[1]).not.toBe("system_policy");
  await shot(page, "11-escalated", result, [["Result", result]]);

  // flow chain: Flow & Score, then a verdict
  const V = picks.flowRoutine as string;
  await openRow(V);
  await expect(work).toContainText("Your Access: Owner");
  await tab("Flow & Score");
  await expect(workspace.getByRole("region", { name: "Flow and score" })).toBeVisible();
  await shot(page, "12-flow-score", undefined, [["Flow & Score", workspace.getByRole("tab", { name: "Flow & Score", exact: true })]]);
  await tab("Analyst Verdict");
  const verdict = workspace.getByRole("region", { name: "Analyst Verdict", exact: true });
  await verdict.getByLabel("Verdict outcome").selectOption("false_positive");
  await verdict.getByLabel("Verdict reason").fill("Model-only, no rule matched; outbound web traffic from an internal host.");
  await verdict.getByRole("button", { name: "Record Verdict", exact: true }).click();
  await expect.poll(async () => (await proof(V)).verdicts).toBe(1);
  await expect.poll(async () => (await proof(V)).work?.[0]).toBe("completed");
  await shot(page, "13-verdict", verdict, [["Verdict outcome", verdict.getByLabel("Verdict outcome")],
    ["Record Verdict", verdict.getByRole("button", { name: /Record Verdict|Correct Verdict/ })]]);

  // Tier 2 case list: rule cases from both chains and the analyst's case
  const F = picks.flowAuto as string;
  const pF = await proof(F);
  expect(pF.case[1]).toBe("system_policy"); expect(pF.work?.[1] ?? null).toBeNull();
  await page.goto("/analyst/tier2-cases");
  await expect(page.getByLabel("Status", { exact: true })).toHaveValue("active");
  const flowRow = page.getByRole("row").filter({ hasText: pF.case[0].slice(0, 8) });
  await expect(flowRow).toContainText("Rule");
  const myRow = page.getByRole("row").filter({ hasText: pS.case[0].slice(0, 8) });
  await expect(myRow).toContainText("Glenn Ang");
  await shot(page, "14-case-list", undefined, [["Status filter", page.getByLabel("Status", { exact: true })],
    ["Flow rule case", flowRow], ["Your case", myRow]]);

  // investigate, conclude, resolve
  await myRow.getByRole("link").first().click();
  const summary = page.getByRole("region", { name: "Case summary", exact: true });
  const resolution = page.getByRole("region", { name: "Case Resolution", exact: true });
  await page.getByRole("tab", { name: "Audit Timeline", exact: true }).click();
  await page.getByLabel("Decision reason", { exact: true }).fill("Taking this case.");
  await page.getByRole("button", { name: "Start investigation", exact: true }).click();
  await expect(summary).toContainText("investigating");
  await expect(resolution.getByRole("button", { name: "Resolve Case", exact: true })).toBeDisabled();
  await page.getByRole("tab", { name: "Investigation Conclusion", exact: true }).click();
  await page.getByLabel("Human Investigation Finding", { exact: true }).selectOption("confirmed_malicious");
  await page.getByLabel("Human Final Attack Classification", { exact: true }).selectOption("brute_force");
  await page.getByLabel("Investigation Reason", { exact: true }).fill("Scan followed by brute force from the same source.");
  await page.getByRole("button", { name: "Record Investigation Conclusion", exact: true }).click();
  await expect(resolution).toContainText("Latest Finding: confirmed malicious");
  await shot(page, "15-conclusion", resolution, [["Resolution Reason", resolution.getByLabel("Resolution Reason")],
    ["Resolve Case", resolution.getByRole("button", { name: "Resolve Case", exact: true })]]);
  await resolution.getByLabel("Resolution Reason").fill("Confirmed and documented; no plan executed.");
  await resolution.getByRole("button", { name: "Resolve Case", exact: true }).click();
  await expect(resolution).toContainText("Resolved by: Glenn Ang");
  expect((await proof(S)).case[2]).toBe("resolved");
  await shot(page, "16-resolved", resolution, [["Resolved by", resolution.getByText(/^Resolved by:/)]]);

  // release a claim
  const R = picks.suricataRelease as string;
  await openRow(R);
  await expect(work).toContainText("Your Access: Owner");
  await workspace.getByRole("button", { name: "Release claim", exact: true }).click();
  await shot(page, "17-release", undefined, [["Release", workspace.getByRole("button", { name: "Release", exact: true })]]);
  await workspace.getByRole("button", { name: "Release", exact: true }).click();
  await expect.poll(async () => (await proof(R)).work?.[0]).toBe("available");

  facts.final = await get(page, "/__soc/counts");
  writeFileSync(`${OUT}/pins.json`, JSON.stringify(pins, null, 1));
  writeFileSync(`${OUT}/facts.json`, JSON.stringify(facts, null, 1));
  expect(errors).toEqual([]);
});
