# Triage Memory V1

Base: `feat/response-recommendation-approval` at `f54958129957cf4c0671c903d6184d62b2ffb66b`.
Branch: `feat/triage-memory-v1`.

## Separation and safety

LEGACY LEARNING: human verdict -> guarded numeric adjustment -> similar family -> queue re-ranking.
That implementation, combined_score, detector evidence, XGBoost, feedback/guardrails and evaluation
are unchanged.

TRIAGE MEMORY V1: human verdict + reason + context -> candidate lesson -> support/conflict ->
explicit human activation -> future contextual guidance. Memory is scoped to this deployment's
database (one organisation), not a shared cross-organisation service.

The existing Suricata -> staging -> eligibility -> admission -> policy -> Tier 1 -> Tier 2 case ->
investigation -> response recommendation -> human approval path remains intact.
Memory never changes operationalPriority, route, reviewRequired, case or response state. It never
automatically dismisses/closes an alert, escalates it, approves a response or executes anything.
The visible boundary is **Memory guidance only - Human review still required.**

FUTURE: Triage Memory -> Selective Human Review -> Evidence-Gated Automation -> No Immediate
Review only for sufficiently safe cases. V1 does **not** claim workload reduction; it creates
the knowledge foundation needed to test that later. Notification/simulated SOAR is also deferred.

## Explicit human source

The existing V2 routing decisions are routing actions, not outcome verdicts. Therefore the new
candidate endpoint itself records an authenticated **Human Memory Review** with one of:
`expected_activity`, `false_positive`, `confirmed_malicious`, `suspicious`, plus a nonblank reason.
There is no automatic conversion of a routing decision, detector result, policy recommendation,
case finding, response approval or legacy feedback into memory.

For terminology only: legacy `mark_expected_activity` corresponds to expected_activity,
`mark_false_positive` to false_positive, and `confirm_true_positive` to confirmed_malicious.
`needs_investigation`/`escalate` have no automatic outcome mapping; suspicious must be explicitly
selected. No backfill is performed. The independent review does not rewrite a Tier 2 finding.
The source case is recorded when this alert is a formal case's primary alert; linked-only alerts
do not silently inherit a case identity.

Only admitted Tier 1, Tier 2 candidate or Tier 2 case alerts are reviewable. Unassigned/staged
alerts are rejected. The real JWT actor is server-bound and rechecked as active analyst/admin.
Evaluator reads only. Senior Analyst/four-eyes approval is a future refinement. One distinct alert
can contribute one human review in V1, preventing repeated clicks or a fresh request UUID from
inflating support. Distinct alerts may be reviewed by the same actor; V1 does not require three
different people. Correcting a mistaken source review is not implemented; history is immutable.

## Context and scope

Context comes solely from the immutable OperationalAlertV2: detectorSource, detectionTitle,
detectionCategory, sourceIp, destinationIp, sourcePort, destinationPort, protocol. Full detector
evidence is also retained in support/conflict snapshots. Optional organisational attributes are
explicitly null: assetCriticality, assetIdentifier, knownScannerIdentity, authorisedActivityType,
scheduleWindow, analystDefinedTag. The API accepts none of these from callers in V1.
"Authorised internal vulnerability scanner" stays a human reason, not a verified scanner identity
or schedule. No free-text extraction, embeddings, LLM lessons or ground-truth inputs are used.

- **exact (default):** all available structured detector context fields at candidate creation;
  detector source, title, source/destination IP and protocol are mandatory. Known ports/category
  are included; originally unavailable fields remain reported as unavailable, not invented facts.
- **narrow:** detector source + detection category + source IP + protocol, all mandatory.
- **category_context:** unsupported. A category without an identity anchor is never a scope.

Scope fields and the configuration snapshot are immutable. A stable context/configuration key
groups matching reviews into the current lesson. Each new human review is also applied once to
every existing compatible, nonexpired/nonrejected lesson, regardless of the review's selected
scope or config version. Thus an exact-scope contradiction cannot bypass a narrow active lesson.
The primary evidence record identifies the original request result; secondary evidence references
the same review and cannot double-count an alert within a lesson.

## Support, activation and expiry

`config/triage-memory-v1.json` is versioned `triage-memory-v1`:
minimumSupport=3, minimumAgreementRatio=0.67, maximumConflicts=0, defaultValidityDays=30.
The support threshold can be raised; validation prevents weakening the V1 minimum or removing
scope identity anchors. Agreement is support/(support+conflict). Every different outcome is a
conflict, including expected_activity vs false_positive; no implicit outcome grouping exists.

Initial evidence counts as support=1. Thresholds produce **eligible_for_activation**, never active.
Only an authenticated activation with a reason and current lesson revision creates **active**.
Activation requires all gates, including zero conflicts, and snapshots support/conflict/ratio,
context, scope, config, actor and time. Reject records an immutable terminal decision.

Later contradicting evidence changes the derived state active -> **conflict_review**; it does not
overwrite the proposal or approval. Conflicted memory remains inspectable but is not active
guidance. Conflict resolution/re-approval is intentionally absent. Additional support cannot erase
a conflict. Both undecided candidates and active lessons expire: candidates 30 days from creation,
active lessons 30 days from activation. Thirty days is a conservative demo review interval, not an
empirically established security guarantee. It is configurable and snapshotted per lesson.
Support does not silently extend expiry. Expired/rejected lessons are preserved; a later new alert
may start a new candidate generation, never reuse the old support count. Expiry is evaluated on
read using aware UTC time, with no destructive cleanup task.

## Matching

Matching is deterministic equality, without a numeric score or hidden weights. Each context field
is classified exact/mismatch/unavailable. **High** means every lesson scope field is exactly
matched; otherwise **Partial**. Lookup retrieves paginated related lessons sharing detector source
and either title or category. It includes candidates, rejected, expired and conflicted history with
explicit status. `guidanceActive` is true only for High + active. `reviewRequired` is always true
in a memory match; it is not a triage-state write. Unknown organisation/schedule attributes are
reported unavailable and never claimed matched. No priority penalty or routing policy is applied.

## Persistence, API and UI

Migration 10 adds only:

- `triage_memory_lessons`: immutable original lesson/context/configuration and source identity.
- `triage_memory_support_events`: immutable human outcome/reason, actor, source alert/case,
  detector/context snapshot, support/conflict relation, idempotency identity and payload.
- `triage_memory_decisions`: one immutable activation/rejection, full predecision snapshot,
  actor/reason/time and validFrom/expiresAt.
- `triage_memory_audit`: immutable event snapshots and human evidence.

UPDATE, DELETE and replacement triggers protect all four tables. BEGIN IMMEDIATE serializes
mutations; inserts/audit commit together or roll back together. Exact retries return the existing
result's current derived status; conflicting actors/payloads return 409. Alert stateVersion protects
new reviews; lesson revision (evidence count + decision count) protects activation/rejection.
The shared migration runner handles version checks under its existing migration transaction.

Authenticated APIs:

```text
POST /api/v2/alerts/{alertRef}/triage-memory/candidate
GET  /api/v2/alerts/{alertRef}/triage-memory/matches
GET  /api/v2/triage-memory
GET  /api/v2/triage-memory/{lessonRef}
GET  /api/v2/triage-memory/{lessonRef}/events
POST /api/v2/triage-memory/{lessonRef}/activate
POST /api/v2/triage-memory/{lessonRef}/reject
```

All lists are paginated, maximum 200 per page. Matching scans source-compatible lessons for
evidence propagation; this V1 algorithm is deterministic, not a large-volume indexing solution.
The Triage Memory page shows outcome, reason, status, scope, counts, agreement, creator/time,
expiry and source links. Detail includes context/configuration and paginated immutable evidence
and audit. Activation/rejection requires a reason; insufficient support disables activation.
V2 Routing displays related history, match explanations and the separate Human Memory Review
form. Evaluators have no mutation controls. Failures display errors and refresh controls.

Audit events: `V2_TRIAGE_MEMORY_CANDIDATE_CREATED`, `V2_TRIAGE_MEMORY_SUPPORT_ADDED`,
`V2_TRIAGE_MEMORY_CONFLICT_ADDED`, `V2_TRIAGE_MEMORY_ACTIVATED`,
`V2_TRIAGE_MEMORY_ACTIVATION_REJECTED`, `V2_TRIAGE_MEMORY_CONFLICT_REVIEW_REQUIRED`.
MATCHED is deliberately not persisted: GET lookup is side-effect-free and does not grow the audit
ledger on every render. Dedicated lookup telemetry and expiry audit events are deferred.

## Demo and regression evidence

The disposable rehearsal adds five Suricata SSH scan fixtures from 10.0.0.50. Eligibility and
admission are prepared explicitly in the disposable database; no memory verdicts are preseeded.
Browser E2E records expected_activity + reason on three independent alerts, observes eligibility,
activates with a reason, and opens the fourth alert. It verifies High active guidance with support=3,
no conflict, priority still 85, Tier 1 route unchanged and review required. A fifth confirmed_malicious
review produces conflict_review and disables active guidance without changing priority or route.
Desktop/mobile screenshots are local ignored artifacts under `apps/web/test-results/` named
`triage-memory-desktop.png` and `triage-memory-mobile.png`.

Backend tests cover explicit outcomes, null context, no text extraction, support/agreement,
configuration snapshots, activation gates, cross-scope conflict, expiry, matching explanations,
JWT/RBAC, retries, stale state, concurrency, immutability, rollback and additive migration. Full-table
snapshots verify zero changes to existing detector/triage/case/response/feedback/evaluation tables.
The existing eight browser regression scenarios remain in the same disposable suite.

Final verification: Python **741 passed, 5 unchanged optional-fixture skips**; frontend
**192 passed in 26 files**; disposable Chromium browser suite **9 passed**; TypeScript,
Python OpenAPI check, frontend schema check and Vite production build pass. Existing API paths
and component schemas compare equal to the base after JSON parsing. Existing Vite large-bundle
and jsdom navigation warnings remain non-failing. The first browser run exposed sibling React
key reuse; distinct keys fixed it and the complete nine-scenario clean rerun passed.

Reproduce from `hitl-ids` using Python 3.11: `python -m pytest -q` and
`python scripts/build_openapi.py --check`. From `apps/web`: `npm test`, `npm run typecheck`,
`npm run check:api`, `npm run build`, and
`playwright test --config playwright.routing.config.ts` (set HITL_PYTHON to the Python 3.11 interpreter).

## Exact file manifest

Relative to `hitl-ids/`:

```text
apps/api/contract/openapi.py
apps/api/main.py
apps/api/memory_routes.py
apps/api/openapi.json
apps/web/e2e/triage-memory.spec.ts
apps/web/playwright.routing.config.ts
apps/web/src/App.tsx
apps/web/src/api/schema.d.ts
apps/web/src/components/layout/AppShell.tsx
apps/web/src/pages/analyst/TriageMemoryPage.test.tsx
apps/web/src/pages/analyst/TriageMemoryPage.tsx
apps/web/src/pages/analyst/V2RoutingPage.test.tsx
apps/web/src/pages/analyst/V2RoutingPage.tsx
apps/web/src/session/roles.ts
config/triage-memory-v1.json
docs/HANDOVER.md
docs/deviations.md
docs/system-workflow.md
docs/triage-memory-v1.md
packages/contracts/db.py
packages/contracts/triage_memory.sql
packages/detection/triage_memory.py
scripts/serve_routing_rehearsal.py
tests/fixtures/triage-memory-scans.json
tests/test_api_contract.py
tests/test_canonical_api.py
tests/test_contracts.py
tests/test_external_staging.py
tests/test_operational_v2.py
tests/test_triage.py
tests/test_triage_memory.py
tests/test_triage_policy.py
```
