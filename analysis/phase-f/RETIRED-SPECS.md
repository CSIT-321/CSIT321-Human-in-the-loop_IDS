# Retired browser specs — coverage map (2026-11-09)

User decision (2026-11-09): retire the browser specs that test screens and flows the product no longer has.
Do not rewrite them. Moved with `git mv` to `apps/web/e2e/historical/`. Removed from every Playwright
config. Configs deleted: `refinement`, `direct`, `unified`, `prospective` (they ran only these specs).
`routing` now runs `role-surfaces.spec.ts`. Its fixture is still the base for 4 current configs.
`playwright.config.ts` now matches only `capture-guide.spec.ts`, which is skipped unless GUIDE_CAPTURE=1.

The team's own freeze record already classed these as *"historical increment-specific harnesses"*:
`docs/final-legacy-cleanup.md` lines 16–17.

## Why they failed (measured: logs `%LOCALAPPDATA%/Temp/hitl-review/left/`, head and `f91ac78`)

Same tests failed on `f91ac78` (before this branch) and on the branch head. Causes:

1. Old routes or landing pages (`/admin/status`, `/analyst/workstation` provenance region, "Open Alert Triage").
2. Old labels that now match 2–3 elements (strict mode): "Legacy Flow Detector", "Decision reason".
3. Rule V3 (2026-11-01, `4e3a54a`): a classification that is not on the allowlist opens a Tier 2 Expert case.
   The fixture's `TEST ICMPv6 policy event` therefore never reaches Tier 1, which the specs expect.
   Probe: `analysis/phase-f/route_probe.py`.

## Map: each old check -> current coverage

"Covered" names a current spec that runs in the gate, or a Python test file. Checked by a search of the
spec code (`rg`) and a read of the matching test, not by its title only.

| Retired spec (tests) | What it checked | Current coverage |
|---|---|---|
| detector-foundation (3) | Admin IP reports open | **role-surfaces.spec.ts** (kept, updated to `/admin/overview`) |
| | Evaluator scenarios and metrics | **role-surfaces.spec.ts** (kept) |
| | Analyst sees detector provenance | investigation-assistance.spec.ts (provenance); soc-flow.spec.ts (Flow & Score) |
| routing-workflow (3) | Claim, route, approve, reject Tier 2 | soc-flow.spec.ts (Why Tier 2 -> Escalate); final-golden-path; human-reclassification |
| | Evaluator can inspect, cannot act | operational-workspaces.spec.ts; current-surface.spec.ts |
| | Analyst lands in triage | every current spec asserts `/analyst/operations` after sign-in |
| external-admission (1) | Staged Suricata review and admission | final-golden-path.spec.ts (`admit()`), persistent-workstation |
| tier2-case (1) | Case: note and finding | case-resolution.spec.ts; soc-flow.spec.ts; human-reclassification |
| response-approval (1) | Response plan approved, never executed | case-resolution.spec.ts ("Approved - Not Executed"); final-golden-path |
| triage-memory (1) | Reviews -> lesson -> guidance -> contradiction | automatic-learning, verdict-memory, conclusion-memory specs |
| selective-review (1) | Lessons defer review; conflict recalls it | canonical-verdict-review-safety; automatic-learning; final-golden-path |
| direct-escalation (1) | Escalate creates a case and stays on the alert | analyst-verdict.spec.ts; soc-flow.spec.ts |
| unified-workstation (2) | One workstation: evidence, context, themes | current-surface; operational-queue; soc-flow |
| | XGBoost presentation fixture (synthetic route stub) | **Not covered in a browser.** It stubbed the API; the screen is checked in Vitest only |
| analyst-refinement (2) | Old console layout, saved preferences, deep links | operational-queue.spec.ts (URL state, panes); current-surface (themes) |
| demo (1) | S16 demo narrative (old `/analyst/queue` console) | **Not covered.** That console was replaced (`docs/final-legacy-cleanup.md`) |
| prospective-collection, prospective-override (2) | Open a prospective collection run in the browser | **Not covered in a browser.** Python: `test_prospective_collection.py` (15), `test_prospective_blockers.py` (11), `test_prospective_event_identity.py` (11) |

## Gaps that remain (stated, not hidden)

- Prospective collection has no browser test. The team's freeze record says no prospective collection was
  opened (`docs/final-legacy-cleanup.md`). The SOC triage path does not use it.
- The old S16 console narrative has no test, because that console no longer exists.
- The XGBoost presentation stub has no browser test. Its rendering is a Vitest case.

## New coverage added in place of the retired specs

`soc-flow.spec.ts` + `soc-flow-fixture.py` (`playwright.soc-flow.config.ts`). It runs on a temp copy of
`data/demo.db` routed by `scripts/materialize_flow_queue.py` — the real demo data, not a synthetic fixture.
It checks, screen and stored row each time: tier views and counts, claim by row click, a named append-only
note, Why Tier 2 -> Escalate, a verdict on a routine group, the 3 auto-escalated cases shown as "Rule",
start -> conclude -> resolve, D1 default filter, and Release. Planted-fault check: making the case list show
the creator's name for system cases fails the spec at line 95.
