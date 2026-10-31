# Suricata Operational Admission

Base: `feat/tier-routing-workflow`, `01ad4c9c4a145fa066f7c42c596b5e25e6869031`.
Feature: `feat/suricata-operational-admission`.

## Explicit eligibility review

The old inbox schema requires admission_decision=hold_for_review on every immutable row.
The user explicitly approved a separate authenticated eligibility review rather than treating
those historical holds as acceptance. Migration 7 creates external_eligibility_review and
external_operational_admission, their indexes and append-only triggers. It does not rebuild
tables, modify core alerts, or rewrite existing staging evidence.

State machine:

- Original staged hold -> explicit accepted eligibility review -> eligible.
- Original staged hold -> explicit held review -> held.
- Held/eligible -> another explicit review, requiring the latest review ID.
- Eligible -> atomic operational admission -> admitted.
- Invalid source or unsupported policy -> failed validation, blocked.
- Existing V2 projection without an admission receipt -> held for manual reconciliation.

No transition silently releases a hold. Review decisions require a reason and have actor-bound
idempotency keys, optimistic expectedReviewId protection, immutable source digests and timestamps.
An accepted review verifies the source again; admission rechecks it under the same write lock
as materialization. Reviews cannot be replaced after materialization/admission.

Eligibility requires valid Suricata canonical/raw evidence, reproducible source identity,
agreement of all denormalized fields, a valid captured staging-policy decision, supported
operational-policy inputs, reviewRequired=true and learning/evaluation eligibility=false.
The raw EVE content hash and adapter output are reconstructed and compared to the snapshot;
this also revalidates recursive ground-truth exclusion. Severity alone is never acceptance.
Original rejected/invalid importer events still produce no inbox row and cannot be admitted.
An invalid persisted source cannot receive an accepted eligibility decision.

## Atomic operational path

Suricata EVE -> immutable inbox -> explicit eligibility review -> Operational Admission
-> OperationalAlertV2 -> Operational Triage Policy V1 -> Tier 1 -> existing human routing
-> Tier 2 Candidate.

The orchestrator owns BEGIN IMMEDIATE. Its private transaction-joining calls:

1. Materialize through the existing external projection. Initially priority/band=null,
   route=unassigned, stage=staged, reviewRequired=true and recommendation=false.
2. Apply operational-triage-v1 with a full policy audit. Only this private admission path
   defers route mutation, leaving the scored alert unassigned/staged for the routing service.
3. Invoke the existing authenticated admit_tier1 transition and append V2_TIER1_ADMITTED.
4. Append V2_EXTERNAL_ALERT_ADMITTED and commit all the above together.

Standalone materialization, policy application, routing defaults, and existing endpoints retain
their previous behavior. Policy scoring logic/configuration is unchanged. The private joining
path requires an already-open transaction, a fresh dormant external projection for policy, and
the admit_tier1 action for routing. No new network option exposes these internal controls.

Every exception rolls back materialization, policy, routing and final admission receipt.
The accepted review remains available for an explicit retry, but no partial operational alert
or partial audit remains. There is no asynchronous incomplete-admission state to recover.
Infrastructure errors do not create a misleading admitted status or overwrite the accepted review.

No-context severity mappings remain 1=85/P1, 2=65/P2, 3=40/P3, 4=20/P4. Every optional context
field stays null/unknown. The local service may receive explicitly trusted TriageContext;
HTTP requests cannot supply context, policy configuration or detector evidence. Confidence
remains null and never participates in priority. Recommendations do not create Tier 2 candidates.

## Authorization and audit

Admission and eligibility review use the signed-in active security_analyst/system_admin under
the already-reviewed operational RBAC. The verified JWT principal is bound to actor_id and the
service rechecks active role under its write lock. Evaluators can inspect but cannot mutate.
No service account or fabricated analyst identity was introduced.

The admission record stores external inbox ID, canonical ID, operational ID, actor, accepted
review ID, request identity, reason, policy/routing audit IDs, trusted context snapshot, complete
resulting triage state and timestamp. This captures effective priority/band, policy version,
route/stage and recommendation. UPDATE, DELETE and replacement INSERT are blocked.
The original inbox row, canonical evidence, policy audit and routing audit all remain intact.

Unique source and operational IDs plus BEGIN IMMEDIATE serialize competing attempts. Repeated
admission returns the immutable admission receipt without reapplying policy or routing, even
after a human has advanced the alert. Conflicting reuse of the same request key is rejected.
New requests for the same already-admitted row return its existing result only with matching
review/context. No duplicate projections, policy applications or routing events are created.
Current routing is read through the V2 API, not restored from the original receipt.

## API and UI

All endpoints authenticate. Numeric inbox IDs identify immutable staging records, not legacy
alerts; operational links still use the canonical operational UUID.

- GET /api/v2/external-alerts, bounded limit/offset pagination.
- GET /api/v2/external-alerts/{inboxId}.
- POST /api/v2/external-alerts/{inboxId}/eligibility.
- POST /api/v2/external-alerts/{inboxId}/admit.

Review body: requestId, expectedReviewId (null for first review), decision=accepted|held, reason.
Admission body: requestId, expectedReviewId, reason. Extra fields are rejected. Responses expose
safe staging summaries, status/reason, original staging decision, explicit eligibility review,
actor attribution and operational reference. Errors use existing 400/401/403/404/409 envelopes.

Suricata Admission is a small separate page for each role. It displays native severity,
Confidence: Not provided, endpoints/nullable ports, exact occurrence timestamp, staging priority
proposal and its policy provenance, eligibility/admission status and the operational link.
The action defaults to keeping held; accepting eligibility and admitting are separate commands
with required reasons. Failed requests do not optimistically change status; retry keys are
preserved. The linked V2 alert is fetched directly, including when outside the first list page.
Evaluator controls are hidden and backend authorization remains authoritative.

No raw-event upload, watcher, live capture, Suricata process management, Tier 2 Case, Suricata
verdict/learning, Triage Memory, selective review, automatic dismissal, notifications or SOAR
was added. Next increment: explicit Tier 2 Case creation from an authorized Tier 2 Candidate.

## Limitations and verification

Final verification: 675 Python tests passed, five unchanged missing-data skips; 171 frontend
tests passed across 23 files; six browser tests passed. OpenAPI and frontend schema checks,
TypeScript compilation, Vite production build and Git whitespace check passed. Structural
comparison with the exact base found no changed existing OpenAPI paths or component schemas.
The existing Vite bundle-size warning and jsdom navigation notices remain non-failing.

Pre-existing manually materialized projections are deliberately not silently adopted, reset or
re-scored. They are shown held with a reconciliation reason. Review and admission history are
fully retained in SQLite; this UI shows the latest eligibility decision and admission result.
Failed source validation is shown as failed; a transient transaction failure leaves the prior
eligible state available for retry. There is no automatic ingestion or admission.

The existing disposable routing rehearsal server supplies staged fixtures for browser tests;
no production/demo database is modified. Run `python -m pytest` and the normal OpenAPI,
generated-schema, TypeScript, Vitest and Vite checks. Browser command:
`playwright test --config playwright.routing.config.ts`, with HITL_PYTHON selecting Python.
Ports 8002/5175 are isolated and existing servers are not reused.

Tests cover severity 1-4, unknown context, nullable ports/exact timestamp, immutable evidence,
explicit hold/release, stale reviews, malformed sources, RBAC, same-key collisions, duplicate
and concurrent admission, rollback injected at each operational write boundary, migration 7,
legacy table isolation and existing Tier 2 rejection/approval/manual escalation. Browser tests
cover staging -> review -> admission -> V2 Tier 1 and all prior role/routing smoke paths.

## Exact file manifest

Paths relative to repository root:

```text
hitl-ids/apps/api/contract/external_admission.py
hitl-ids/apps/api/contract/openapi.py
hitl-ids/apps/api/external_admission_routes.py
hitl-ids/apps/api/main.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/web/e2e/external-admission.spec.ts
hitl-ids/apps/web/playwright.routing.config.ts
hitl-ids/apps/web/src/App.tsx
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/components/layout/AppShell.tsx
hitl-ids/apps/web/src/pages/analyst/ExternalAdmissionPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/ExternalAdmissionPage.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.tsx
hitl-ids/apps/web/src/session/roles.ts
hitl-ids/docs/detector-agnostic-hitl-architecture.md
hitl-ids/docs/suricata-operational-admission.md
hitl-ids/packages/contracts/db.py
hitl-ids/packages/contracts/external_operational_admission.sql
hitl-ids/packages/detection/adapters/operational_v2.py
hitl-ids/packages/detection/external_admission.py
hitl-ids/packages/detection/routing.py
hitl-ids/packages/detection/triage_policy_service.py
hitl-ids/tests/test_api_contract.py
hitl-ids/tests/test_canonical_api.py
hitl-ids/tests/test_contracts.py
hitl-ids/tests/test_external_operational_admission.py
hitl-ids/tests/test_external_staging.py
hitl-ids/tests/test_operational_v2.py
hitl-ids/tests/test_routing_workflow.py
hitl-ids/tests/test_triage.py
hitl-ids/tests/test_triage_policy.py
```
