# Safe Automatic Human Learning & Policy-Controlled Memory Auto-Activation V1

Base: `c18b65f578106479f77c79e3366712a86b0bc2b6` (`feat/canonical-verdict-review-safety`).
Branch: `feat/safe-memory-auto-activation`.

## Evidence and authority

Saving a canonical Tier 1 Analyst Verdict captures Exact evidence in the same SQLite transaction. The source Verdict reference, revision, outcome, reason, authenticated author and detector/context snapshot remain inspectable. Saving a canonical Tier 2 Investigation Conclusion does the same for `confirmed_malicious`, `suspicious` and `expected_activity`, preserving the conclusion event, case, finding, final attack classification and expert author.

Inconclusive creates no reusable evidence. The latest Tier 2 conclusion nevertheless supersedes earlier Tier 1 and expert evidence immediately. Otherwise the latest Tier 1 Verdict supersedes older Verdicts; historical compatibility evidence has the lowest authority. Counts use distinct operational alert identities, not events, clicks, users or contributions. Exact and explicit Narrow contributions from one alert still represent one current vote per lesson. Contradictions reach compatible lessons across scopes; positive Exact evidence cannot broaden a Narrow lesson.

Automatic contributions, lesson creation and activation use `decision_source=system_policy`, `actor_id=NULL`, and `policy_version=safe-memory-auto-activation-v1`. The actual authenticated human judgment author is stored separately. There is no synthetic System user. Historical human-owned rows retain their original actor, identifiers, payloads and snapshots.

The canonical command owns commit/rollback. An evidence or activation failure rolls back the new canonical command, evidence and decision together. Missing required Exact context can skip learning without weakening the independent canonical review guard. Deterministic source contribution identities and source-plus-scope uniqueness prevent repeated processing from adding evidence. Canonical command retries return their existing receipt. Compatibility requests for an already contributed current source/scope return the existing Memory as a no-op; they do not create another vote or activation. Such no-op requests do not create a new durable request receipt. Existing recorded manual command receipts retain their identity checks.

## Exact activation conditions

The versioned policy is `config/safe-memory-auto-activation-v1.json`, version **safe-memory-auto-activation-v1**. It reuses the unchanged **triage-memory-v1** configuration in `config/triage-memory-v1.json`:

| Condition | Implemented value |
| --- | --- |
| Automatic evidence scope | Exact only |
| Automatic activation scope | Exact only |
| Eligible lesson outcomes | `expected_activity`, `false_positive` |
| Minimum current independent support | 3 distinct operational alerts |
| Minimum agreement ratio | 0.67 |
| Maximum current conflicts | 0 |
| Rejection / prior decision | No existing decision; rejected lessons are never reconsidered |
| Configuration | Lesson snapshot must equal the current pinned Memory configuration |
| Authority | One alert, one current vote; latest Tier 2 > latest Tier 1 > historical evidence |
| Trigger | Eligible canonical judgment write, inside its transaction |
| Attribution | System Policy, NULL actor, versioned policy and activation audit |
| Validity | 30 days from activation |

One and two supporting judgments remain Candidate. The third compatible independent benign judgment auto-activates if every condition holds. Malicious and suspicious evidence are retained but never auto-activated. Narrow expansion requires an explicit authenticated human action and is never auto-activated.

GET/list/detail/history/match/queue/metric reads do not contribute, activate, migrate, renew or persist status changes. Existing eligible historical candidates are not activated merely by inspecting them. A later eligible canonical evidence write can evaluate an undecided compatible Exact candidate.

## Fixed aging and expiry

`validFrom` is the activation timestamp. `expiresAt = validFrom + 30 days`, using the snapshotted Memory configuration. Fresh support at day 15 updates support/history but does not alter either timestamp. At `now >= expiresAt`, the lesson is expired and cannot provide active guidance or reduce immediate review. Historical evidence and activation remain auditable. Candidate expiry also retains the existing configuration-based age limit.

The validity window is not a promise of trust: a current contradiction or loss of current support withdraws guidance earlier. These status changes are derived on reads without database mutation. Conflict status can take precedence over an expiry label; either status disables guidance. An expired or rejected context retains its existing lesson and immutable decision when later evidence arrives. V1 does not create an automatic replacement generation.

There is **no mathematical decay, sliding renewal, fresh-evidence validity extension, post-expiry automatic reactivation or revalidation workflow**. Expiring Soon is not implemented. Controlled post-expiry revalidation is future work; it requires a separately reviewed product policy, not a background renewal job.

## Independent Selective Review gate and unchanged domains

Active Memory supplies guidance only. The existing Selective Review evaluation still checks matching scope, freshness and availability of trusted context, risk/criticality, uncertainty, malicious indicators, campaign/conflict/response requirements, workflow eligibility, audit sampling, human override and canonical human judgments. The existing explicit Evaluate Review Policy command persists a decision; this feature does not add read-triggered evaluation or automatic admission-time suppression. No Immediate Review is an automation disposition, never a human Verdict or a Safe/Closed outcome.

R01 remains independent of Memory: a latest canonical Verdict recalls source review even when learning is unavailable. R02 counts distinct previously deferred alerts using their latest authoritative human outcome; expert conclusions and corrections override earlier Tier 1 outcomes. Automatic learning does not substitute for either guard.

Detection, classification, routing and priority algorithms, response approval/execution and Case resolution semantics are unchanged. No response execution is introduced. Protocol V2 and its pinned artifacts remain unchanged and unopened. Tests use disposable synthetic databases; no real/demo learning data or prospective collection is used. No merge or PR is part of this increment.

## UI and compatibility

Tier 1 Human Learning and Tier 2 Expert Learning show automatically recorded Exact evidence, support/conflicts, current Memory status, System Policy activation and validity timestamps. The normal Exact flow has no contribution or activation click. Optional **Expand Learning Scope to Narrow** / **Expand Expert Learning Scope to Narrow** retains human control over broader scope. Superseded evidence remains historical and is marked non-current in Memory history.

Memory details distinguish the System Policy contributor/activator from the real human Verdict/expert author. Manual Exact endpoints remain for compatibility and historical judgments; replaying an already automatically contributed source/scope is a no-op. Legacy noncanonical alert panels retain their historical manual controls. Manual activation remains for undecided eligible historical or explicitly human-controlled lessons, including Narrow. It cannot overwrite an automatic decision, activate a rejected/expired lesson, or bypass Selective Review. No broad UI redesign or unrelated role-link cleanup is included.

Migration 20 rebuilds the attribution-bearing tables, preserves historical rows and foreign keys, and restores append-only triggers. Canonical contributions are unique per source and scope to permit controlled Narrow expansion without duplicate voting. Historical JSON defaults to analyst attribution; no history is rewritten to look automatic.

## Assessor-ready wording

**Automatic evidence learning:** “Canonical Tier 1 Verdicts and eligible Tier 2 Investigation Conclusions are automatically captured as Exact learning evidence. Each alert contributes at most one current vote, and the latest Tier 2 investigation takes precedence over Tier 1. The human remains the judgment author; automatic contribution is attributed to System Policy.”

**Safe auto-activation:** “The system does not trust a single analyst decision. Reusable Exact benign guidance is automatically activated only after at least three independent alerts satisfy the configured agreement threshold of 0.67 with zero conflicts. Active Memory does not directly suppress an alert: each future alert must still pass Selective Review safety guardrails. Later contradictory human evidence withdraws the guidance.”

**Memory aging/expiry:** “Memory has a fixed 30-day validity window starting at activation. Fresh evidence does not extend it. At expiry the lesson remains auditable but can no longer reduce immediate human review. V1 has no mathematical decay, sliding renewal or automatic post-expiry reactivation.”

## Validation map

- `test_safe_memory_auto_activation.py`: automatic support progression, outcome restrictions, honest attribution, duplicate/cross-scope voting, expert precedence, correction/Inconclusive withdrawal, rejection, fixed expiry, independent review gate, query-only inspection and atomic failures.
- Canonical Verdict, Verdict/Conclusion Memory, Selective Review, operational queue and R01/R02 regressions retain their domain safety assertions under automatic learning. The independent no-learning R01/R02 cases deliberately disable the learning hook to prove guard independence.
- The populated schema-18 fixture migrates through 19 and 20 while preserving original columns/event IDs/Memory/response foreign keys. Injected migration-20 failure verifies full rollback and restored foreign-key enforcement.
- Frontend tests cover automatic provenance, validity, explicit Narrow expansion, read-only roles and retry behavior. TypeScript, OpenAPI freshness and production build are required.
- `playwright.automatic-learning.config.ts` runs the real frontend/API against a disposable database: A/B/C human Verdicts → automatic Exact evidence → automatic activation → D passes the independent review gate → malicious conflict recalls D → E requires review. A historical fixed-clock fixture verifies expired Memory cannot defer a future alert with fresh safety context. Light/dark screenshots at 1440, 1024 and 390 pixels check Memory presentation and horizontal overflow.
- Protocol V2 freeze regression verifies pinned hashes and `collectionOpened=false` without opening collection.

Final run counts and commit identity are reported with the implementation delivery. Final Golden Path E2E should proceed only after the feature validation and regression results are green; this focused browser scenario does not claim to replace the whole-system Golden Path.

## Delivery validation results

- Backend whole-suite first run: **1,500 passed, 7 failed, 5 skipped**. The seven failures were schema-20 expectations, automatic-learning side-effect expectations, and historical migration fixtures. All seven were corrected and re-run together with the final 17 feature tests: **24 passed**. Four of those feature tests were added after the whole-suite collection. Cumulative final coverage is **1,511 passing tests and 5 data-artifact skips** (not a claim of a second single whole-suite run). Additional focused runs passed 76 canonical/Memory tests, 68 contract/migration tests (1 data skip), and 94 triage/expert tests.
- Frontend: **254 tests / 35 files passed**; TypeScript passed. OpenAPI and generated client schema are fresh. Production build passed (existing bundle-size warning only).
- Real API/browser: **5 scenarios passed**: automatic-learning (including fixed-clock expiry), canonical Verdict review safety, Verdict Memory, expert Conclusion Memory and Case resolution. Light/dark at 1440/1024/390 passed overflow assertions; screenshots were visually inspected.
- Populated migration 19→20, injected rollback, foreign-key checks and historical attribution passed. A pre-existing schema-13 fixture now explicitly uses its historical absent-classification projection during setup; production classification logic was not changed.
- Protocol V2 artifact validation passed; hash `cfc9539c0b325919a60eb8a5722826affa53e1c253e3b96c15e3a6db41dd2541`; `collectionOpened=false`. Its exact pinned runtime SHA is intentionally not claimed to be this new product branch.
- No merge, PR, prospective collection, actual response execution, or real/demo data mutation.

The feature is ready for the Final Golden Path E2E. Five tests requiring absent, gitignored ML/demo datasets remain skipped. Controlled post-expiry revalidation, Expiring Soon, and general role-link cleanup remain future work.

## Exact changed files

Paths are relative to `hitl-ids/` in the repository.

- `apps/api/openapi.json`
- `apps/web/e2e/automatic-learning-fixture.py`
- `apps/web/e2e/automatic-learning.spec.ts`
- `apps/web/e2e/canonical-verdict-review-safety.spec.ts`
- `apps/web/e2e/case-resolution.spec.ts`
- `apps/web/e2e/conclusion-memory.spec.ts`
- `apps/web/e2e/verdict-memory-fixture.py`
- `apps/web/e2e/verdict-memory.spec.ts`
- `apps/web/playwright.automatic-learning.config.ts`
- `apps/web/playwright.verdict-memory.config.ts`
- `apps/web/src/api/schema.d.ts`
- `apps/web/src/features/alert/VerdictLearning.test.tsx`
- `apps/web/src/features/alert/VerdictLearning.tsx`
- `apps/web/src/pages/analyst/ConclusionLearning.test.tsx`
- `apps/web/src/pages/analyst/ConclusionLearning.tsx`
- `apps/web/src/pages/analyst/TriageMemoryPage.test.tsx`
- `apps/web/src/pages/analyst/TriageMemoryPage.tsx`
- `config/safe-memory-auto-activation-v1.json`
- `docs/safe-memory-auto-activation.md`
- `packages/contracts/db.py`
- `packages/contracts/safe_memory_auto_activation.sql`
- `packages/detection/analyst_verdict.py`
- `packages/detection/tier2_cases.py`
- `packages/detection/triage_memory.py`
- `tests/operational_queue_fixture.py`
- `tests/pre_freeze_fixture.py`
- `tests/test_analyst_verdict.py`
- `tests/test_canonical_api.py`
- `tests/test_canonical_verdict_review_safety.py`
- `tests/test_conclusion_memory.py`
- `tests/test_contracts.py`
- `tests/test_safe_memory_auto_activation.py`
- `tests/test_suricata_correlation_routing.py`
- `tests/test_tier2_case_resolution.py`
- `tests/test_tier2_human_reclassification.py`
- `tests/test_triage.py`
- `tests/test_triage_memory.py`
- `tests/test_triage_policy.py`
- `tests/test_verdict_memory.py`
