# Selective Human Review V1

Base: `feat/triage-memory-v1` at `9a5133ba6c87ba6d11dedaac4b73a58b5590ec63`.
Branch: `feat/selective-human-review-v1`.

## Boundaries

Legacy: human feedback -> guarded numeric adjustment -> family re-ranking (unchanged).
Triage Memory V1: human feedback + reason + context -> reusable lesson (unchanged).
Selective Review: validated memory + current evidence + safety guardrails -> attention disposition.
Future: evidence-gated broader automation, after independent safety/workload evaluation.

No Immediate Review != Closed. No Immediate Review != False Positive.
No Immediate Review != Human Verdict. It is not response authorization, Tier 2, deletion,
resolution or priority reduction. No SOAR, live capture or XGBoost retraining is introduced.

Review disposition is **separate** from core operational triage state. Priority, priority band,
Tier2Recommended, handlingRoute and reviewRequired remain unchanged. A deferred alert may show
core route Tier 1 / reviewRequired=Yes: those are the original workflow, not immediate attention.
The new attention queue has All, Must Review, Recommended Review and No Immediate Review filters.
V2 Routing and the legacy workstation are not replaced; deferred alerts remain inspectable.
Policy evaluation is an explicit authenticated action, not an ingestion hook/background dispatcher.
No persisted evaluation means Must Review even when the current policy could qualify the alert.

## Trusted context and policy

The user approved reading existing immutable `operational_triage_policy_audit` context rather than
adding a new operator safety-assessment workflow. The latest audit id/time and context are retained.
HTTP callers cannot submit safety context, actor identity, thresholds or a chosen disposition.
Only the disposable six-alert scenario supplies explicitly synthetic safe facts at admission.
Normal admission retains unknown context; production/demo.db is not edited to force success.

Configuration: `config/selective-review-v1.json`, version `selective-review-v1`:

- Expected activity minimum support 3; false positive minimum 5.
- Minimum agreement 0.67, zero conflicts; stronger lesson thresholds also apply.
- Context validity 24 hours; future-dated context fails closed.
- Campaign threshold 5; any explicitly repeated campaign also forces review.
- Deterministic audit sample 10 percent.

Qualification requires active, unexpired, High, guidanceActive, **exact-scope** benign memory.
Every scope field must match; any available context mismatch blocks qualification. Narrow lessons
remain advisory. Missing scoped context cannot count as a match. Organisational memory attributes
stay null; they are not inferred from prose. Required current safety context comes separately from
the trusted policy audit, and every TriageContext field must be known.

High/critical assets, known malicious indicators, evidence conflict, confirmed-malicious context,
response required, analyst escalation, unresolved Tier 1, repeated/excessive campaign,
Tier2Recommended and detector signature_override force Must Review. Unsupported workflow states
also force review. Only Tier 1 / triage can qualify. Existing human memory reviews or primary-case
findings block deferral: teaching examples are not treated as newly saved review work.

Related malicious/suspicious or conflicted memory is a conservative veto even for a partial related
match. Candidate/rejected/expired/partial/conflict_review lessons cannot qualify. A stale benign
lesson does not qualify; a separate valid lesson still must pass all other gates.
Must Review is the fallback. Recommended Review is used only for deterministic audit sampling.
Sampling: `int(SHA256(str(alert UUID))[:8],16) % 100 < auditSamplePercent`. No randomness or
evaluation labels enter the policy. Priority 85 can coexist with No Immediate Review: urgency
and immediate attention differ. Reusing a persisted policy version with changed config is rejected.

## Persistence and human override

Migration 11 adds `selective_review_events` plus indexes and append-only triggers, no table rebuild.
Each event stores UUID, alert FK, authenticated actor, action, required reason, request ID/payload,
time/type and a full decision snapshot. The snapshot preserves detector/triage state, trusted
context/audit reference, related memory snapshots, configuration, reasons, selected lesson and
input fingerprint. Memory, case, detector, feedback, routing and response tables are not mutated.

Events: `V2_SELECTIVE_REVIEW_DECIDED` (decisionSource=selective_review_policy) and
`V2_HUMAN_REVIEW_REQUIRED` (decisionSource=human_override). Neither is an analyst outcome verdict.
BEGIN IMMEDIATE, active actor checks, request identity and stale view versions protect writes.
Exact retries return current state without duplicates/rewind. Failed inserts roll back completely.
UPDATE/DELETE/replacement attempts cannot rewrite history.

Every read revalidates current evidence. A changed input fingerprint invalidates a stored deferral,
even if the change is additional benign support. Conflict, expiry, changed context, a new human
verdict or workflow advancement thus removes effective deferral on the next read. Reads do not
append recall events. The UI refreshes every 15 seconds while idle, plus explicit refresh; this is
not a push stream. Historical decisions remain inspectable separately from effective disposition.

Require Human Review records actor/reason and forces Must Review. A deferred alert's core route
already remains Tier 1, so no fake reverse transition or score rewrite is needed. The action cannot
overwrite advanced workflow states. The override is sticky; V1 has no override-release action.

## API and UI

```text
GET  /api/v2/selective-review
GET  /api/v2/selective-review/metrics
GET  /api/v2/alerts/{alertRef}/selective-review
GET  /api/v2/alerts/{alertRef}/selective-review/events
POST /api/v2/alerts/{alertRef}/selective-review/evaluate
POST /api/v2/alerts/{alertRef}/selective-review/require-human
```

Analyst/admin can mutate; evaluator reads only. Mutation body: requestId, expectedVersion, reason.
Pagination is bounded to 200. UI shows disposition, reasons, unchanged priority, policy, decision
memory snapshot, current safety evidence and immutable history. It always warns:
**No Immediate Review is an automation decision, not a human verdict.**
Evaluate/override require reasons. API failure never displays a false safe disposition.

## Metrics and counterfactual evaluation

Live counts cover all V2 alerts. Eligible denominator is the current Tier 1 / triage population,
including reviewed/guarded alerts still in that workflow. Reduction rate is effective deferred /
eligible, with zero for an empty denominator. It is a decision-count ratio, not measured time saved.

Unsafe suppression counts distinct alerts with any historical deferral followed by confirmed-malicious
or suspicious human memory evidence/primary-case finding on that same alert. This is observed human
contradiction, not inferred ground truth. Conflict-triggered recall counts currently invalidated latest
deferrals with MEMORY_CONFLICT, not lifetime recalls. Sample count is current recommended-review
sampling. New explicit decisions may change current counts; immutable history preserves older events.

Read-only evaluator from `hitl-ids`:

```powershell
python scripts/evaluate_selective_review.py --database <disposable-db-path>
python scripts/evaluate_selective_review.py --database <disposable-db-path> --labels <labels.json>
```

SQLite opens in `mode=ro` under a read transaction. Optional labels are UUID-to-outcome JSON,
used only to score outputs, never as policy inputs. Unknown UUIDs/outcomes are rejected. Baseline
is all V2 alerts requiring review. Outputs include selective immediate review, eligible-denominator
reduction, malicious/suspicious wrongly deferred, expected/FP safely deferred, unlabelled coverage,
conflicts and samples. Human overrides remain effective.

This is a **current-state counterfactual, not a temporal backtest**. It does not claim memory existed
at each historical alert time. Tests intentionally label a qualifying fixture malicious to prove the
unsafe-deferral metric can report failure. Fixture success is not real-world workload/safety evidence.

## Demo and verification

The separate six-alert scenario preserves the earlier memory scenario. Alerts 1-3 receive explicit
expected-activity reviews and human activation. Alert 4 earns No Immediate Review with trusted
synthetic context, support=3/conflict=0/High exact match, priority still 85. Its sample bucket is 47,
outside the normal 10% sample; configuration is not weakened. Alert 5's confirmed-malicious human
review creates conflict. Alert 6 is Must Review; alert 4 is recalled on read. An explicit human
override remains sticky. Original Suricata/Tier 2/response scenarios run in the same browser suite.
Desktop/mobile screenshots are ignored local files in `apps/web/test-results/`:
`selective-review-desktop.png`, `selective-review-mobile.png`.

Verified: Python **776 passed, 5 unchanged fixture skips**; frontend **198 passed in 27 files**;
browser **10 passed**. Final provenance/API tests: **61 passed**. TypeScript, Python OpenAPI check,
frontend schema check and Vite build pass. Existing API paths/schemas remain structurally unchanged.
The existing large-bundle and jsdom navigation warnings remain non-failing. Full-table snapshots
and regression suites protect legacy learning, guardrails, evaluation, memory, case and response.
The standalone evaluator was also run against a fresh disposable database before teaching:
14 total / 13 eligible, baseline immediate review 14, selective immediate review 14, zero deferrals,
14 unlabelled. SHA-256 of the database was identical before and after the read-only command.
These zeroes are a safe-default smoke check, not labelled safety-performance measurements.

Limits: ordinary unknown context stays Must Review. Queue/filter/metrics scan current evidence in
Python and target demo volumes, not unbounded production scale. No background audit writer,
push notifications, override release, trusted-context enrichment, auto-close or response execution.
Next: temporal holdout, trusted-context provenance/freshness integration and prospective safety/
workload measurement before broader evidence-gated automation.

## Exact file manifest

Relative to `hitl-ids/`:

```text
apps/api/contract/openapi.py
apps/api/main.py
apps/api/openapi.json
apps/api/selective_review_routes.py
apps/web/e2e/selective-review.spec.ts
apps/web/playwright.routing.config.ts
apps/web/src/App.tsx
apps/web/src/api/schema.d.ts
apps/web/src/components/layout/AppShell.tsx
apps/web/src/pages/analyst/SelectiveReviewPage.test.tsx
apps/web/src/pages/analyst/SelectiveReviewPage.tsx
apps/web/src/pages/analyst/V2RoutingPage.test.tsx
apps/web/src/pages/analyst/V2RoutingPage.tsx
apps/web/src/session/roles.ts
config/selective-review-v1.json
docs/HANDOVER.md
docs/deviations.md
docs/selective-human-review-v1.md
docs/system-workflow.md
packages/contracts/db.py
packages/contracts/selective_review.sql
packages/detection/selective_review.py
packages/detection/selective_review_policy.py
packages/evaluation/selective_review.py
scripts/evaluate_selective_review.py
scripts/serve_routing_rehearsal.py
tests/fixtures/selective-review-demo.json
tests/test_api_contract.py
tests/test_canonical_api.py
tests/test_contracts.py
tests/test_external_staging.py
tests/test_operational_v2.py
tests/test_selective_review.py
tests/test_triage.py
tests/test_triage_policy.py
```
