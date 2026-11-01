# Canonical Analyst Verdict → Triage Memory

Base: `4c12177f594e659f93df07155bc800a9631706aa`.
Branch: `feat/verdict-memory-integration`.

## Product chain

System Detection → System Classification → System Routing → Human Verdict → Human Learning
Evidence → Triage Memory → Selective Review.

Verdict is the authenticated human conclusion. Memory Scope defines how narrowly that
conclusion can be reused. Memory activation determines whether enough independent, agreeing
evidence exists to use it. Selective Review separately evaluates whether a future matching
alert needs immediate review using active safe memory and trusted context.

The four outcomes map directly: confirmed_malicious, suspicious, expected_activity,
false_positive. The canonical Verdict reason is copied without a second required explanation.
System classification (for example Brute Force) can coexist with a False Positive verdict
and matching human memory; none of these actions changes the system Attack Category.

Recording Verdict still does not create memory, activate a lesson, train a detector or reroute
an alert. Scope contribution is a separate explicit human action. Activation remains another
explicit authorized human action after the existing configured evidence gate passes.

## Current API and permissions

`POST /api/v2/alerts/{alertRef}/triage-memory/from-verdict` accepts only:

- requestId
- verdictRef (must be this alert's latest canonical Verdict)
- expectedStateVersion (current operational workflow version)
- scope: exact or narrow

The server resolves outcome, reason, immutable source Verdict and author. Caller outcome,
reason, actorId and other extra fields are rejected. Active Security Analyst/System Admin
authority follows the existing human operational convention; Evaluator can only read.
Contribution requires a current system-routed Tier 1 triage workflow and a valid Verdict.
The internal scope/fan-out writer rechecks that the canonical record, reason and outcome
match rather than accepting a caller-created human snapshot.

`GET /api/v2/alerts/{alertRef}/triage-memory/verdict-state` returns latest Verdict reference
and revision, not_contributed / contributed / superseded, last scope and primary lesson link.
It uses the existing read-only connection and never repairs or materializes records.
Memory views, matches and history likewise derive effective evidence without writes.

The old candidate endpoint remains for historical non-system-routed compatibility records.
It rejects current system-routed alerts with an explanation to use the canonical Verdict
endpoint. Historical retries remain readable/idempotent; existing history is never rewritten.

## Provenance and migration

Migration 17 only adds two immutable tables:

- verdict_memory_contributions: source alert FK, unique canonical Verdict FK, contributor FK,
  explicit scope, primary lesson FK, unique requestId and immutable logical request payload.
- verdict_memory_evidence: per-contribution/per-lesson evidence edges with lesson/contribution
  FKs and an immutable evidence snapshot. These include supporting and conflicting fan-out.

Evidence records preserve sourceVerdictRef, sourceVerdictRevision, Verdict author ID/name,
contributor actorId, canonical outcome/reason, detector/context snapshot, Verdict source state
version, support/conflict relation and server timestamp. Author and contributor may differ;
the original Verdict actor is never overwritten. Existing tables/snapshots are not rebuilt.
Update/delete/replace triggers protect both new ledgers; migration and failed contributions
roll back atomically. The historical Memory audit links each new edge to its Verdict.

## Independent support, retries and corrections

A Verdict revision may be contributed once across all scopes/actors. Repeated clicks or a
new requestId for the same revision are rejected, not counted again. Exact actor/payload-bound
retry returns the existing contribution's primary lesson projection without inserting anything.
Changed actor or payload under the same key fails safely. Historical candidate request keys
cannot be reused for a canonical contribution.

Effective calculations include only evidence referencing the latest Verdict for its source
alert. Thus one alert has at most one current contribution. If that source had legacy evidence,
its first canonical contribution replaces the legacy evidence in effective counts too;
the historical rows remain untouched. Positive linked evidence may support only lessons at
least as narrow as the selected reuse scope; Exact cannot silently strengthen a broader
Narrow lesson. Conflicts still fan out to every compatible lesson across scopes, so a
contradiction cannot bypass an active narrow lesson by choosing Exact. Legacy evidence
retains its historical fan-out semantics.

A correction appends a new canonical Verdict. Old Memory evidence instantly becomes
non-current in server read projections, even before the corrected Verdict is contributed.
It remains in the evidence and Verdict histories. No background repair job or destructive
update is needed. The corrected Verdict can then be explicitly contributed with its chosen
scope and new requestId. Only the new revision counts. Correction alone does not invent
replacement evidence or select a scope on the human's behalf.

Example: three Expected Activity contributions are active. Correct one Verdict to Confirmed
Malicious: effective support falls 3→2, active guidance ceases, and previous deferrals on
future alerts fail closed. Contribute the correction: the lesson now has support 2/conflict 1
and follows existing conflict-review behavior. The source never counts as both outcomes.

The existing minimum-support, agreement, zero-conflict, expiry and trusted-context settings
are unchanged. A stored activation alone is no longer sufficient when its current evidence
gate fails: the read status is candidate (or conflict_review/expired as applicable), not
active. If current evidence safely satisfies the gate again while the original explicit
activation remains valid, it can resume guidance under that approval. No fresh lesson is
auto-activated. Optimistic Memory revisions include historical edges and source supersession
changes, so withdrawal cannot rewind an activation version or hide a stale decision.

Contribution marks a source as human-reviewed through the existing Selective Review input,
just as the historical human-memory review did. Verdict alone does not directly grant
No Immediate Review. Future automation still requires a recorded policy evaluation, eligible
active memory and all trusted-context guardrails. Changed evidence/conflicts invalidate old
deferrals through the existing effective review service.

## Workstation and standalone Memory

After saving Verdict, Use in Triage Memory opens the learning tab without contributing.
Human Learning shows the canonical outcome, reason, Verdict author/revision and explicit
Exact/Narrow scope. It contains no second outcome selector or required Human Memory Reason.
Without Verdict, a button opens the canonical Verdict editor. Tier 2 instead explains that
Investigation Finding supplies deeper human learning; no fake Tier 1 Verdict is requested.

After contribution the panel shows Contributed, scope, linked lesson, effective support,
conflicts and guidance state. After correction it says Previous Verdict evidence superseded
and offers the current contribution action. Reads refresh on tab entry, after contribution,
via Refresh learning and by a 15-second poll; backend validity does not depend on UI polling.
Local Verdict saves and contributions also refresh the Workstation projection immediately;
the assistance rail reloads when the effective review version changes, so it does not retain
old active guidance while the center panel already shows withdrawn evidence.

Standalone Memory shows Verdict reference/revision/author, contributor, source alert, scope
and current/superseded status in Memory Evidence History. Activation history and immutable
event snapshots stay distinct. Verdict revision history remains in the canonical Verdict UI.
Old non-linked evidence remains readable without pretending it came from a Verdict.

## Validation and boundaries

Tests use real staging, admission, Verdict, Memory, activation and Selective Review commands.
Coverage includes all four mappings, copied reason, coauthor provenance, forbidden caller
overrides, missing/stale Verdict, exact retries, duplicate clicks/scopes, 1→2→3 independent
support, cross-scope conflict fan-out, active-memory withdrawal, future deferral recall,
append-only histories, read-only projections, transaction failure and migration preservation.
Current operational fixtures now obtain evidence through actual Verdict contributions;
legacy fixtures continue exercising their original compatibility contract.

Detection/capture/correlation, Classification V3, attack taxonomy, priority formula and System
Routing are unchanged. Unknown and Critical still automatically create formal Tier 2 Cases;
Manual Escalation stays separate. There is no Suricata/XGBoost retraining or feature bridge,
human attack reclassification, response redesign, Tier 2 assistance or guided tour. Protocol V2
artifacts remain unchanged/unopened; no operational prospective collection is opened.

V1 limitations: scope is chosen once per Verdict revision; expiry/rejection does not make old
human evidence reusable by repeated clicks. Changing an already contributed scope requires a
new genuine canonical human revision. The finite local evidence projection performs additional
read-time joins/parsing at FYP scale; no streaming/high-volume performance claim is made.
External UI updates are polled; backend safety checks are immediate on each transactional read.
Stored activation and original lesson outcome remain audit history when guidance is suspended.

## Validation (2026-11-02)

| Check | Result |
| --- | --- |
| 17 relevant backend modules: contribution/Verdict/Memory/Selective Review, V3/Suricata, queue, routing/direct escalation, schema/migrations/read-only inspection and frozen protocol | 577 passed, 1 optional historical-data skip; 163.51s |
| Final contribution/Memory/Selective Review/Verdict/queue core after authentication/scope hardening, including new rollback/migration checks | 142 passed; 70.90s |
| Full frontend | 239 tests / 33 files passed; 24.44s |
| TypeScript, OpenAPI and generated schema freshness | Passed; 76 paths / 81 operations / 150 schemas |
| Production build | Passed; existing large-chunk advisory |
| Real canonical-learning browser journey | 1 passed; 20.1s, including center/rail invalidation consistency and all five requested cases |
| Existing Analyst Verdict browser journey | 1 passed; 17.6s |
| Existing pre-freeze browser journey | 1 passed; 18.8s |
| 1440 / 1024 / 390 × Dark / Light | Passed; screenshots inspected; no document horizontal overflow |
| Protocol V2 hashes and collectionOpened=false | Verified unchanged |
| git diff --check | Passed |

Backend validation was focused, not a full repository run. The final core pass covers the
last safety refinements after the larger regression batch. The optional skipped test requires
gitignored historical model output. Existing migration boundaries remain pinned for their own
tests; schema/FK/path inventories include the new additive tables and endpoints. Old manual
operational test fixtures now produce genuine canonical Verdicts and explicitly contribute
them; historical fixtures still cover the old non-linked path. No assertions were removed
to permit contradictory current evidence or unsafe activation.

Browser fixtures used only disposable databases, including isolated four-alert learning
contexts. data/demo.db was not created or modified. Screenshots/build/test output remain
ignored local artifacts. No actual collection, merge or PR was created.

## Exact changed files (repository-relative)

```text
hitl-ids/apps/api/contract/openapi.py
hitl-ids/apps/api/memory_routes.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/web/e2e/verdict-memory-fixture.py
hitl-ids/apps/web/e2e/verdict-memory.spec.ts
hitl-ids/apps/web/playwright.verdict-memory.config.ts
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/features/alert/AnalystVerdict.tsx
hitl-ids/apps/web/src/features/alert/VerdictLearning.test.tsx
hitl-ids/apps/web/src/features/alert/VerdictLearning.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.tsx
hitl-ids/apps/web/src/pages/analyst/TriageMemoryPage.tsx
hitl-ids/docs/verdict-memory-integration.md
hitl-ids/packages/contracts/db.py
hitl-ids/packages/contracts/verdict_memory.sql
hitl-ids/packages/detection/selective_review.py
hitl-ids/packages/detection/triage_memory.py
hitl-ids/tests/operational_queue_fixture.py
hitl-ids/tests/pre_freeze_fixture.py
hitl-ids/tests/test_analyst_verdict.py
hitl-ids/tests/test_api_contract.py
hitl-ids/tests/test_canonical_api.py
hitl-ids/tests/test_contracts.py
hitl-ids/tests/test_inspection_readonly.py
hitl-ids/tests/test_operational_v2.py
hitl-ids/tests/test_pre_freeze_review_fixes.py
hitl-ids/tests/test_triage.py
hitl-ids/tests/test_triage_policy.py
hitl-ids/tests/test_verdict_memory.py
```
