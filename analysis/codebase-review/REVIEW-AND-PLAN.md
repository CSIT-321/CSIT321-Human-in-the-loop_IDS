# Final-product codebase review and phase plan

Review commit: `050274f` (branch `feat/tier-views-auto-escalation`, LCK tip `f91ac78` + Phase A).
Date: 2026-11-05. Status: **plan only — no product code changed by this review.**

## 1. How this review was done

| Item | Value |
|---|---|
| Workers | 9 opencode workers, `deepseek/deepseek-v4.1-flash`, variant `max`, one disjoint slice each, isolated worktrees |
| Coverage claimed | 210 of 210 listed files read (slices 1-9: 26, 25, 20, 15, 11, 25, 31, 23, 59 — the 25 in slice 6 and the 23 in slice 8 are the header counts) |
| Findings | 94 (1 CRITICAL, 24 HIGH, 42 MEDIUM, 27 LOW) |
| Citations checked mechanically | 199 `path:line` citations, **0 unresolved** (`collect.py`) |
| Claims re-measured by the orchestrator | S3-01/S2-01/S4-01 (code read), S3-02, S3-03, S3-04, S1-03, S5-01=S8-04 (live probe), S6-01 (timed), S9-02 (signature check) — **all confirmed** |
| Not covered | `docs/`, the 40+ design documents, `apps/web/e2e/*` beyond fixtures, Playwright runs, the full test suite after Phase A |

Per-slice reports: `slice-1.md` … `slice-9.md` in this folder. Every finding ID below links to one.

## 2. The verdict in five lines

1. **The product has two generations wired side by side, and the final console only drives the new one.** The approved
   engine (fusion, guardrails, family learning, five-category verdict) is intact and unchanged since `f1b74b6`, but
   **no page reaches it** (S2-02). The new V2 workflow (claim, four-outcome verdict, Tier 2 cases, memory) only accepts
   Suricata bundles (S3-01).
2. **The 996 flow alerts are visible but dead.** They cannot be claimed, verdicted, prioritised, or escalated; the one
   manual door (`admit-tier1`) leads nowhere (S2-01, S3-01, S4-01, S6-02, S7-01 — five workers found this independently).
3. **Automatic escalation exists but points the wrong way.** The only rule that can fire escalates the *least certain*
   alerts (unknown classification), and four context rules can never fire because their facts cannot exist at
   admission time (S3-03, S3-04). The measured-safe rule (E1) is not implemented.
4. **Tier 2 candidates with reasons are computed and then thrown away** (S3-02, `system_routing.py:101`).
5. **The design cannot be documented as-is**: one analyst judgment has four vocabularies (S1-07, S4-02), "priority"
   has five meanings (S7 challenge), and the published API calls itself "deliberately narrow" while exposing 107 routes
   (S6-08).

## 3. Decisions the team must make before coding (block Phase B)

| # | Decision | Recommendation | Why | Findings |
|---|---|---|---|---|
| D1 | **Source of truth for a flow alert's score/band/verdict** | V2 reads the legacy row (read-through), legacy engine stays the writer for flow alerts | Engine is approved, tested, unchanged; a second mutable copy will disagree (S1-01) | S1-01, S2-02, S7-04 |
| D2 | **One analyst-judgment vocabulary** | Keep the 4 V2 outcomes as *the* verdict; map each to a guardrailed legacy category for flow alerts (confirmed_malicious→confirm_true_positive, suspicious→needs_investigation, expected_activity→mark_expected_activity, false_positive→mark_false_positive) | One form for both sources; flow alerts still get guarded score movement and family learning | S1-07, S2-02, S4-02 |
| D3 | **Automatic escalation rule set** | E1 only (corroborated ∧ score ≥ 80). Unknown classification → **Tier 2 candidate**, not auto-case. Context rules → candidates until a fact producer exists | E1: 0 FP on demo and stress. Unknown-class auto-case contradicts "uncertain waits for Tier 1" | S3-03, S3-04, my measurement |
| D4 | **Queue population** | 996 flagged (as Phase A) | Matches the approved "awaiting review" set; but the approved demo script uses unflagged `AL-03086` — that step must be rewritten | S9 challenge, S2 challenge |
| D5 | **Claim recovery** | Add owner-or-admin **release** with audit | Auto-claim on row click strands alerts permanently today | S4-03 |
| D6 | **What is "final product" vs "research surface"** | Final = Tier 1, Tier 2, Admin (workspaces, governance, current audit, users). Research = evaluation pages, prospective collection, external admission UI, selective-review page, IP report | Lets the API contract and design docs describe one product | S6-06, S6-08, S8-01, S8 challenge |

## 4. Phase plan

Phase letters continue the plan already approved (A done). Every phase is TDD: failing test first, then code.

### Phase B — Routing core (orchestrator writes; never delegated)

| Step | Change | Findings closed |
|---|---|---|
| B1 | Source-neutral routing: split `admit_system_route` into a per-source classifier + one decide/persist path; add a flow classifier from CEF fields; run it in `materialize_flow_queue` with a deterministic request id | S3-01, S2-01, S4-01, S6-02, S7-01 (backend) |
| B2 | Three outcomes per alert: **auto-escalate (E1)** / **Tier 2 candidate with reasons** (E3, unknown class, context, verdict promotion) / **routine Tier 1**. Persist `tier2_recommended` + reasons; stop hard-coding False | S3-02, S3-03, S2-03 |
| B3 | Fail-safe: any classifier error or missing field → routine Tier 1 with the reason, never a case; never close, dismiss, or lower | S3 challenge ("not human-fallback") |
| B4 | Admin kill switch per automatic rule (rule off → its alerts become candidates); policy version on every decision | user requirement |
| B5 | Post-admission re-evaluation when a trusted fact arrives (idempotent, audited) — or explicitly scope context rules out and document it | S3-04, S3-09 |
| B6 | One eligibility predicate `tier1_workflow()` used by claim, verdict, selective review and routing | S4-05 |
| B7 | DB integrity: immutability triggers on `alerts.detection_score` etc.; delete guard on triage state; one band vocabulary | S1-03, S1-11, S1-04 |
| B8 | Single shared config for severity map and thresholds + consistency test | S3-06 |

### Phase C — Tier 1 view (orchestrator: verdict bridge; worker: React panels)

| Step | Change | Findings closed |
|---|---|---|
| C1 | V2 verdict command calls the approved guardrail engine for flow alerts (D2 mapping), inside `BEGIN IMMEDIATE` | S2-02, S2-07 |
| C2 | Queue tabs: **Incoming · Tier 2 candidates · Auto-escalated**; SQL `tier2Recommended` filter; reasons on each row | S6-05, S7-02 |
| C3 | "Why Tier 2" panel: reasons + **Escalate / Keep in Tier 1 / Record verdict** (wires `approve_tier2`/`reject_tier2`) | S7-02, S3-10, S4 challenge |
| C4 | Render the 4 items already on the wire (AL name, rule conditions, combined explanation, agreement) + correct confidence | S7-03, S7-05, S2-06 |
| C5 | Restore the 9 legacy display cards for `legacy_flow_alert` via one legacy GET (flow, family, score chain) | S7-04, S7-07 |
| C6 | Tier 1 notes (append-only, owner-guarded) | S4-07 |
| C7 | Claim release (D5); `verdict_ref` follows corrections | S4-03, S4-04 |
| C8 | Summary performance: one bulk pass, no double scan (8.2 s measured → target < 1 s) | S6-01 |
| C9 | Queue order: severity-first for flow alerts (settled decision 8) | S7-09, S2 challenge |

### Phase D — Tier 2 view (worker, orchestrator review)

| Step | Change | Findings closed |
|---|---|---|
| D1 | Tier 2 list: status/owner filter, stable sort; shows who escalated (rule or analyst) and why | S6 challenge |
| D2 | Restored evidence panels inside the case | S7-04 |
| D3 | Remove the legacy `/findings` route and `CreateCasePanel` | S4-08, S7-08 |
| D4 | Optional: Return to Tier 1 (migration 22) — only if time allows | earlier decision 4 |

### Phase X — Correctness and security fixes (independent; can run in parallel with C/D)

| Step | Change | Findings |
|---|---|---|
| X1 | **Role-gate legacy feedback** (evaluator can write verdicts today — measured) | S5-01, S8-04 |
| X2 | CSV formula injection in audit export | S8-03 |
| X3 | Guardrail cross-field rules enforced in the API, not only the browser | S8-02 |
| X4 | `run_detection` refuses a second run on the same dataset (or `--replace`) | S2-05 |
| X5 | Detection uses the live guardrail policy it records | S2-04 |
| X6 | Product API stops importing `scripts/` and `evaluation/` (replay data → product fixture) | S9-05 |
| X7 | Small UI bugs: UTC in current audit, error states, per-action reason, role-aware memory links | S8-06/07/08/09, S7-06 |
| X8 | Dead code removal (scripts, UI symbols, unused routes) | S2-09, S8-11, S9-09, S6-06 |

### Phase E — Tests, contract, and the frozen-evidence repair

| Step | Change | Findings |
|---|---|---|
| E1 | End-to-end test per flow alert: materialize → route → claim → verdict → guardrail → family move → Tier 2 | S2-10, S3-12, S4-09, S7-10 |
| E2 | Additive frozen-evidence checker + conftest skip of the 4 live-tree tests (do **not** edit hashed files) | S9-01 |
| E3 | Fix stale e2e fixture servers (`stage_file` signature) | S9-02 |
| E4 | Evaluation path accepts `system_route` admissions; temporal exporter coalesces paired audits | S9-03, S9-04 |
| E5 | OpenAPI: roles/401/403 on every mutation, one role-extension key, contract-vs-handler test beyond operationIds; rewrite the scope description | S6-03, S6-04, S6-07, S6-08 |
| E6 | V2 table models + one JSON key convention; extend the model/column parity test | S1-05 |
| E7 | Plan, changelog v1.33, deviations, handover → `test_plan_sync` green | known |

### Phase F — Design documents (after the product is fixed — **not now**)

Inputs already prepared by this review: the module maps (sections "Module map" in each slice — 230+ modules classified
legacy / V2 / shared / research / frozen), the one-name-per-concept conflicts (S1-07, S7 challenge "priority" ×5,
S3 challenge `external_signature`/`external_rule`), the script classification (S9 map: operator / research / frozen /
test-only / dead) and the endpoint-per-view map (S6 challenge). Documents to update: architecture, data dictionary,
API, UI specification, routing/escalation policy, test plan, runbook, user manual.

## 5. Delegation rules for implementation

- **Orchestrator only:** B1–B8, C1, C7, X1, X3, E2 (routing, guardrails, verdict, security, frozen evidence).
- **Workers (opencode / deepseek-v4.1-flash, max):** C2–C6, C8–C9 UI parts, D1–D3, X2, X4–X8, E3–E6. One file set per
  worker, isolated worktree under `C:\Users\Glenn Ang\fyp-review-wt\` (never under `%LOCALAPPDATA%\Temp` —
  opencode remaps it to `C:\tmp` and fails), red-green proof required, orchestrator re-runs every test.
- Each phase ends with the full Python suite + `vitest` + one browser capture on a copy of `demo.db`.

## 5b. Revised after the grilling session (2026-11-05) — supersedes section 3 and the phase order above

Decision owner: **Glenn Ang**. Full facts and options: `DECISION-BRIEF.md`.

| # | Decision |
|---|---|
| D1 | Approved engine stays the writer for flow alerts; the console reads it |
| D2 | One verdict form: LCK's 4 outcomes, mapped to approved categories on flow alerts; Escalate separate (+15) |
| D3 | Automation: E1 = score >= 80 AND ML model agrees with **Suricata OR our flow rule engine**; both branches ON; unknown classification -> Tier 2 candidate; selective-review deferral kept |
| D3a | Safety: Admin switch per branch; share limit 90% over the last 500 arrivals (measured peak 0.268, 0 correct E1 blocked); trip -> candidate, never close |
| D3b | Grouping: same signature + same source IP, any destination, 30 min; visible "Grouped: N alerts" flag; one group verdict applies to every member, audited per member, member can be split out; **family learning counts a group verdict once**; group escalates whole when any member qualifies |
| D4 | All 5,000 flow alerts in the queue; unflagged in the bottom band; summary speed fix first |
| D5 | Claims expire after 15 min with no activity (Admin can change it); Admin release with reason; audited |
| D6 | All 7 analyst menu entries kept |
| D7 | Data: **A + B-spike**. A = two labelled workspaces (Suricata live; flow detection and learning). B-spike = 1 day, capture day 2018-02-14 (37.17 GiB), pass = both tools run on one PC + >= 90% of Suricata alerts link to a flow + one corroborated alert arrives live and E1 escalates it. Pass -> B is the live input. Suricata is added **beside** CICFlowMeter (record in `docs/deviations.md`; `HANDOVER.md:489` rejected Suricata as a **replacement**) |
| D8 | Return from Tier 2 to Tier 1 waits |

Revised order:

1. **Spike B** first (1 day, time-boxed) — its result decides the live input and the E1-suricata data.
2. **C8** summary speed fix (needed for D4: 5,000 alerts).
3. **Phase B** routing core with E1 two branches, switches, share limit, grouping.
4. **Phase X1** evaluator write gap (security) in parallel.
5. **Phase C**, then **D**, then **X**, then **E**. Phase F (design docs) after the product is verified.

## 6. Open unknowns

- Decision owner for D1–D8 is Glenn Ang (user's statement, 2026-11-05); no supervisor sign-off required.
- Whether the supervisor accepts dropping the share-based rate limit (measured: it trips on correct E1 bursts).
- The Suricata routing rules have no measured precision: the only Suricata data is the synthetic V3.1 workload.
- The `docs/` tree and the design documents were not reviewed in this pass.
