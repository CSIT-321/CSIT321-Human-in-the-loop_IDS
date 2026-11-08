# Phase C / D / X / E status — 2026-11-08

User direction (2026-11-08): "we need to speed things up"; the product stays exploratory, features
functional for the full triage; expert decisions are mine unless they change the product shape.
Gate agreed: slow checks (full Python suite, live browser check) run ONCE per phase; planted-defect
checks only on high-risk code (routing, verdicts, guardrails, security). X8 and E6 cut.

## Landed (branch `feat/tier-views-auto-escalation`, local)

| Item | Commit | Notes |
|---|---|---|
| C2 + D4 cond. 3 | `780b123` | Tier 2 candidates + Auto-escalated tabs; Tier 1 split "G groups · S single"; row strip; group size on rows |
| C3 | `74305fb` | Why Tier 2 panel, server-gated actions |
| C4 | `009eb63` | fusion confidence vs model probability named apart |
| C5 | `fc79fec` | Flow & Score tab, 7 read-only cards restored from `f1b74b6` |
| D1–D3 | `4059a69` | Tier 2 list filters + Escalated by; flow panels in the case; `/findings` route and CreateCasePanel removed |
| X1 | `f37fd81` | evaluator cannot write legacy feedback (`TriageRoles`); all 48 write routes probed (47 after D3 removed `/findings`) — only feedback was open |
| X2 | `b6cd3f1` | CSV formula-injection guard in audit export |
| X3 | `5f5676f` | guardrail PUT enforces the page's cross-field rules; 7 tests; planted-defect check green |
| X4 + X5 | `4b43370` | second run on a dataset refused; detection applies the live guardrail policy it records; fresh demo build = real `data/demo.db` on all 5,000 alerts (0 differing) |
| X6 | `7b696f8` | product API no longer imports `scripts/`; boundary test |
| X7 | `4536f7b` | UTC audit times, error states, per-action workspace reasons, role-aware memory links |
| E1 | `d355260` | end-to-end flow triage over HTTP (queue→claim→verdict→guardrail→family→order; escalate→case); planted-defect check green |
| E2 | `63fe59b` | frozen-evidence checker holds on any branch; the 4 live-tree preflight tests skip by name in conftest (hashed files untouched) |
| E3 | `a0e9149` | routing-rehearsal fixture stages (`capture_scope`), admits bundled detections the current way |
| E4 | `7ab6cad` | evaluation accepts `system_route` admissions; temporal exporter coalesces paired same-instant audits; planted-regression check green |
| E5 | `a1bafea` | 4 Tier 1/Tier 2 mutations role-gated in the contract; 401 stamped on the whole surface; one role key; scope rewritten |
| E7 | `0b82ad0` | changelog v1.33, handover rev 25; `test_plan_sync` green |

## Final gate (2026-11-08)

- Python: `1846 passed, 4 skipped, 0 failed` (980 s, tree at `0b82ad0`). The 4 skips are the frozen
  live-tree preflight tests (3 in `test_protocol_v3.py`, 1 in `test_protocol_v3_1.py`).
- Web: TypeScript 0 errors; Vitest 307/307 (40 files).
- Frozen scripts unchanged since the 2026-11-02 freeze commits (`398fd99`, `0836502`).

## Whole-triage live walk (2026-11-08, after the final gate)

Script: `analysis/phase-f/walk_live_check.py` (Camoufox), proof: `analysis/phase-f/walk_db_check.py`.
Database: fresh copy of `data/demo.db` + `materialize_flow_queue.py` (81 groups; 3 auto-escalated, 74
candidates, 4,008 routine). Copy deleted after. Real `data/demo.db` hash `ad85a9149e380f80` before and after.

| Step | Screen | Stored row |
|---|---|---|
| Queue tabs | Tier 1 "78 groups · 4,004 single", Tier 2 candidates 74, Auto-escalated 3 | — |
| Row click claims alert A | "In Review — You" | `analyst_work_events` |
| Escalate A to Tier 2 | case opens | `approve_tier2` / `analyst` routing audit; route `tier2_case`; work `escalated`; feedback `escalate` |
| Flow & Score on alert V | 5 cards | — |
| Verdict on V | "Completed — Reviewed by Glenn Ang" | work `completed`; feedback `confirm_true_positive` |
| Case list | "Analyst #1" in Escalated by | case `decision_source=analyst` |
| Start / conclude / resolve | "Case Resolved · investigating → Resolved" | 4 case events: create, start, finding (`confirmed_malicious`), resolve; status `resolved`, revision 4 |

Found, not fixed (display only): 8 places show "Actor #N" / "Analyst #N" where the API has the
display name (`Tier2CasesPage.tsx:20,55,130`, `InvestigationConclusion.tsx:19`,
`ResponseRecommendations.tsx:46`, `SelectiveReviewPage.tsx:114`, `TriageMemoryPage.tsx:35,97,116`).
The resolution line already shows "Glenn Ang / #1".

## Delegated decisions (recorded, not asked)

- **E2 skip by name, not by file**: the 4 frozen tests fail only on the live-tree pin; a conftest
  skip keeps the frozen hashes intact. `test_frozen_evidence.py` re-checks the evidence chain.
- **E3**: the fixture's selective-demo admission now follows the bundled-detection path (facts seeded
  after admission), because the admission rule refuses caller-supplied context.
- **C8**: measured again on the routed demo copy with the new summary fields: ~100 ms. No change owed.
- **E5 kept, S6-07 cut**: moving the wire models out of `apps/api` only matters before FastAPI is
  installed; no such environment exists. Recorded as cut.

## What is deliberately NOT done

- **X8** (dead-code removal) — cut with the user.
- **E6** (model/column parity test) — cut with the user.
- **S6-07** (contract imports no FastAPI) — cut as above.
- The **live browser check for X/E** — the Phase C+D gate ran the Camoufox checks (`cgate_live_check.py`,
  `dgate_live_check.py`); X2–X7 and E1–E5 are covered by unit/API tests instead.
