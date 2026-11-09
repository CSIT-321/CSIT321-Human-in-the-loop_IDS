import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

/**
 * Data-flow trace for the decision tree. Runs on a temp copy of data/demo.db routed by the product's own
 * scripts/materialize_flow_queue.py (data-trace-fixture.py). Five real records, one per branch of the tree:
 *   A auto-escalated (E1)  B Tier 2 candidate escalated by a human (E3)  C model-only false positive kept in Tier 1
 *   D routine group with a verdict  E unflagged missed attack found by a human.
 * For every step: the stored state BEFORE, the action, the stored state AFTER (read-only /__trace/state), a
 * screenshot. Output: TRACE_OUT/trace.json + PNGs. The step ids (A0, A1, ...) key the rule citations in tree.json.
 */
const OUT = process.env.TRACE_OUT ?? "test-results/data-trace";
const API = "http://127.0.0.1:8041";

type Step = { id: string; label: string; actor: string; action: string; before: unknown; after: unknown; shot: string };
type Path = { id: string; title: string; ref: string; steps: Step[] };

test("data-flow trace: one real record per decision-tree branch", async ({ page }) => {
  test.setTimeout(600_000); page.setDefaultTimeout(20_000); mkdirSync(OUT, { recursive: true });
  const errors: string[] = []; page.on("pageerror", e => errors.push(e.message));
  const state = async (ref: string) => (await page.request.get(`${API}/__trace/state/${ref}`)).json();
  const picks = await (await page.request.get(`${API}/__trace/picks`)).json();
  const workspace = page.getByRole("region", { name: "Operational alert workspace", exact: true });
  const work = workspace.getByRole("region", { name: "Human work status" });
  const verdict = workspace.getByRole("region", { name: "Analyst Verdict", exact: true });
  const why = workspace.getByRole("region", { name: "Why Tier 2 is recommended" });
  const summary = page.getByRole("region", { name: "Case summary", exact: true });
  const resolution = page.getByRole("region", { name: "Case Resolution", exact: true });
  const paths: Path[] = [];

  /** Run one action and record it with the stored state on both sides. */
  async function step(p: Path, id: string, label: string, actor: string, action: string,
                      run: () => Promise<void>, subject?: Locator) {
    const before = await state(p.ref);
    await run();
    // Let panels finish loading so the picture matches the stored state (soft: a panel that keeps a
    // "Loading" line must not fail the trace).
    await expect(page.getByText(/^Loading\b|^—$/).first()).toBeHidden({ timeout: 10_000 }).catch(() => {});
    if (subject) await subject.scrollIntoViewIfNeeded();
    const shot = `${id}.png`;
    await page.screenshot({ path: `${OUT}/${shot}`, animations: "disabled" });
    p.steps.push({ id, label, actor, action, before, after: await state(p.ref), shot });
  }
  async function openRow(ref: string) {
    await page.goto(`/analyst/operations?view=all&q=${ref}`);
    await page.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${ref}"]`).click();
    await expect(workspace).toContainText(ref);
  }
  async function tab(name: string) { await workspace.getByRole("tab", { name, exact: true }).click(); }
  async function recordVerdict(outcome: string, reason: string) {
    await tab("Analyst Verdict");
    await verdict.getByLabel("Verdict outcome").selectOption(outcome);
    await verdict.getByLabel("Verdict reason").fill(reason);
    const saved = page.waitForResponse(r => r.url().endsWith("/verdict") && r.request().method() === "POST");
    await verdict.getByRole("button", { name: "Record Verdict", exact: true }).click();
    expect((await saved).ok()).toBe(true);
  }
  async function caseFlow(p: Path, prefix: string, caseRef: string, finding: string, category: string) {
    await step(p, prefix + "1", "Expert starts the investigation", "Tier 2 analyst", "Start investigation (reason required)", async () => {
      await page.goto(`/analyst/tier2-cases/${caseRef}`);
      await page.getByRole("tab", { name: "Audit Timeline", exact: true }).click();
      await page.getByLabel("Decision reason", { exact: true }).fill("Taking this case.");
      await page.getByRole("button", { name: "Start investigation", exact: true }).click();
      await expect(summary).toContainText("investigating");
    }, summary);
    await step(p, prefix + "2", "Expert records the conclusion", "Tier 2 analyst", `Conclusion: ${finding}, ${category}`, async () => {
      await page.getByRole("tab", { name: "Investigation Conclusion", exact: true }).click();
      await page.getByLabel("Human Investigation Finding", { exact: true }).selectOption(finding);
      await page.getByLabel("Human Final Attack Classification", { exact: true }).selectOption(category);
      await page.getByLabel("Investigation Reason", { exact: true }).fill("Confirmed from the grouped flows and the rule conditions.");
      await page.getByRole("button", { name: "Record Investigation Conclusion", exact: true }).click();
      await expect(resolution).toContainText("Latest Finding:");
    }, resolution);
    await step(p, prefix + "3", "Expert resolves the case", "Tier 2 analyst", "Resolve Case (reason required)", async () => {
      await resolution.getByLabel("Resolution Reason").fill("Confirmed and documented; no plan executed.");
      await resolution.getByRole("button", { name: "Resolve Case", exact: true }).click();
      await expect(resolution).toContainText("Resolved by: Glenn Ang");
    }, resolution);
  }

  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang"); await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations/);

  // A: E1 auto-escalation. No Tier 1 claim is possible; the system opened the case.
  const A: Path = { id: "A", title: "Corroborated group, auto-escalated (E1)", ref: picks.auto, steps: [] };
  paths.push(A);
  await step(A, "A0", "Detected, grouped and routed by the system", "System", "Detection -> grouping -> routing", async () => {
    await openRow(A.ref);
  }, work);
  const aCase = (await state(A.ref)).case.case_ref;
  expect((await state(A.ref)).case.decision_source).toBe("system_policy");
  await caseFlow(A, "A", aCase, "confirmed_malicious", "brute_force");

  // B: E3 candidate. A human reads Why Tier 2 and escalates.
  const B: Path = { id: "B", title: "Tier 2 candidate, escalated by a human (E3)", ref: picks.candidate, steps: [] };
  paths.push(B);
  await step(B, "B0", "Detected, grouped and routed as a Tier 2 candidate", "System", "Detection -> grouping -> routing", async () => {
    await page.goto(`/analyst/operations?view=all&q=${B.ref}`);
    await expect(page.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${B.ref}"]`)).toBeVisible();
  });
  await step(B, "B1", "Analyst opens the group (claims it)", "Tier 1 analyst", "Row click = claim", async () => {
    await page.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${B.ref}"]`).click();
    await expect(work).toContainText("Your Access: Owner");
  }, work);
  await step(B, "B2", "Analyst reads Why Tier 2 and escalates", "Tier 1 analyst", "Escalate to Tier 2 (reason required)", async () => {
    await tab("Overview");
    await why.getByLabel(/^Reason/).fill("Repeated infiltration-class flows from one internal host; needs an expert.");
    await why.getByRole("button", { name: "Escalate to Tier 2", exact: true }).click();
    await expect.poll(async () => (await state(B.ref)).case?.status).toBe("open");
  }, work);

  // C: model-only false positive. The analyst keeps it in Tier 1 and marks it false positive; the floor holds.
  const C: Path = { id: "C", title: "Model-only false positive, kept in Tier 1", ref: picks.falsePositive, steps: [] };
  paths.push(C);
  await step(C, "C0", "Detected and routed as a Tier 2 candidate", "System", "Detection -> group of 1 -> routing", async () => {
    await page.goto(`/analyst/operations?view=all&q=${C.ref}`);
    await expect(page.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${C.ref}"]`)).toBeVisible();
  });
  await step(C, "C1", "Analyst opens the alert (claims it)", "Tier 1 analyst", "Row click = claim", async () => {
    await page.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${C.ref}"]`).click();
    await expect(work).toContainText("Your Access: Owner");
    await tab("Overview");
  }, why);
  await step(C, "C2", "Analyst rejects the recommendation", "Tier 1 analyst", "Keep in Tier 1 (reason required)", async () => {
    await why.getByLabel(/^Reason/).fill("Single flow to a known internal web server; no attack pattern.");
    await why.getByRole("button", { name: "Keep in Tier 1", exact: true }).click();
    await expect(why).toHaveCount(0);
  }, work);
  await step(C, "C3", "Analyst records False Positive", "Tier 1 analyst", "Verdict: false_positive", async () => {
    await recordVerdict("false_positive", "Benign request pattern; the model over-scored one flow.");
    await expect.poll(async () => (await state(C.ref)).work?.status).toBe("completed");
  }, verdict);

  // D: routine group. Verdict confirmed malicious; score already at 100.
  const D: Path = { id: "D", title: "Routine group, confirmed by a Tier 1 verdict", ref: picks.routineGroup, steps: [] };
  paths.push(D);
  await step(D, "D0", "Detected, grouped and routed to routine Tier 1", "System", "Detection -> grouping -> routing", async () => {
    await openRow(D.ref);
    await tab("Flow & Score");
    await expect(workspace.getByRole("region", { name: "Flow and score" })).toBeVisible();
  });
  await step(D, "D1", "Analyst records Confirmed Malicious", "Tier 1 analyst", "Verdict: confirmed_malicious", async () => {
    await recordVerdict("confirmed_malicious", "DoS pattern on port 80 from one source; matches the capture.");
    await expect.poll(async () => (await state(D.ref)).work?.status).toBe("completed");
  }, verdict);

  // E: unflagged missed attack (D4). Only reachable because unflagged flows stay in the queue.
  const E: Path = { id: "E", title: "Unflagged flow, missed attack found by a human (D4)", ref: picks.missed, steps: [] };
  paths.push(E);
  await step(E, "E0", "Not flagged; kept as a single bottom-band item", "System", "Detection -> no group -> routing", async () => {
    await page.goto(`/analyst/operations?view=all&q=${E.ref}`);
    await expect(page.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${E.ref}"]`)).toBeVisible();
  });
  await step(E, "E1", "Analyst searches and opens it (claims it)", "Tier 1 analyst", "Search by reference, row click = claim", async () => {
    await page.getByRole("list", { name: "Operational alerts" }).locator(`button[data-alert-ref="${E.ref}"]`).click();
    await expect(work).toContainText("Your Access: Owner");
  }, work);
  await step(E, "E2", "Analyst records Confirmed Malicious", "Tier 1 analyst", "Verdict: confirmed_malicious", async () => {
    await recordVerdict("confirmed_malicious", "Repeated web requests from a known attacker IP; the model missed it.");
    await expect.poll(async () => (await state(E.ref)).work?.status).toBe("completed");
  }, verdict);

  writeFileSync(`${OUT}/trace.json`, JSON.stringify({ generatedAt: new Date().toISOString(), paths }, null, 1));
  expect(errors).toEqual([]);
});
