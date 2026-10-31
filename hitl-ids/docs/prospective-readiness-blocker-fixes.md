# Prospective Readiness Blocker Fixes

Base: `feat/prospective-collection-readiness-v2` at
`dd49cf4cfe979430912fa1a90c61cc594c81e75c`.
Branch: `feat/prospective-readiness-blocker-fixes`.
Status: fixes implemented; a NEW independent final read-only review is required.
The previous review was FAIL. No readiness PASS or authorization to collect is claimed.
Protocol V2 remains unchanged, draft, undated and unopened. V1 is unchanged.

Historical increment: the next independent review reproduced two remaining gaps in the unconverted
inspection GETs and raw event/request identities. The stacked
[final integrity fixes](prospective-readiness-final-integrity-fixes.md) supersede the limited 15-route
scope below, with all 40 database GETs and explicit global event/request uniqueness. Neither document
is an independent readiness PASS. Do not start collection.

## Operational override is independent of collection

The existing serialized selective-review transaction retains RBAC, state, reason, version and policy checks.
Collection eligibility is checked without writes. An eligible run attaches the operational event and its
collection sidecar atomically. A known eligibility failure for Require Human Review (expired, closed,
missing, stale, or incompatible frozen run) instead persists the normal immutable operational override
and an explicit not-recorded receipt. No collection table is changed. Evaluate remains strict.
Unexpected database/programming failures are not swallowed or reported as successful overrides.

The receipt is server-created metadata in the existing immutable request_payload, exposed through an
additive nullable collectionRecording field. It does not modify a policy snapshot, fingerprint or table
schema. Exact retries compare the original request excluding that server receipt. Legacy events without
receipts remain readable. The UI allows closed/expired-run override and displays persisted messages:

- `Human review required`
- `Not recorded in selected collection run because the run is closed.`

Reload retains Must Review, the skip reason and the audit event. A collection skip does not erase an
operational recall: a later override before outcomeCutoff can still count as a recall; a post-cutoff override
does not change the closed report. Neither changes the original decision or collection ledger.

## Read-only from connection open

The dedicated dependency opens a resolved SQLite URI with mode=ro. Its first SQL is
PRAGMA query_only=ON. It does not call db.connect, db.migrate or schema initialization. Authentication
uses this same cached read-only dependency with the existing JWT/account checks. A missing database fails
without creation. A non-current schema returns 503 DATABASE_SCHEMA_UNSUPPORTED without upgrade.

Scope: all four collection GETs (list/detail/export/report), both context GETs, four selective-review GETs,
/api/auth/me, and four existing /api/evaluation GETs. Mutation routes, including login, retain the existing
writable/migrating dependency. This is not a claim that every legacy GET in the application was converted.
CLI export/evaluation remains read-only. No migration or table rebuild is introduced.

## Complete recorded archives

Before cohort selection, the evaluator reconciles all immutable ledger events:

- run.decisionCount equals the number of exported collection decision records.
- Decision references and raw review event IDs are unique, run-bound and in the decision window.
- Each recorded run-bound raw event has exactly its sidecar, including matching receipt identities.
- Every sidecar has its original actor/action/time/alert and exact raw decision snapshot.
- A not-recorded receipt is permitted only for an operational human override without a sidecar.
- Legacy receipt-free run-bound events retain the original atomic event/sidecar requirement.
- Missing, duplicate or inconsistent evidence fails with archive-integrity; HTTP uses ARCHIVE_INTEGRITY.

As explicitly confirmed by the owner, decisionCount continues to count all ledger events, including repeated
evaluations and in-window overrides. eligibleAlerts separately counts the first eligible apply per alert.
No count is redefined, and no missing decision is reconstructed. Unrelated post-window events and valid
skipped overrides do not invalidate completeness or change the closed report after its cutoff.

## Verification

All automated scenarios use disposable synthetic databases, never data/demo.db. The new real-browser test
uses analyst/admin sign-in and UI actions to teach/activate synthetic memory, record actual deferrals, wait
for real window boundaries, override with expired/closed runs selected, reload and inspect the audit. It
compares the actual exported collection ledger before/after. It does not replace the workflow with API writes.
Schema-12 HTTP regressions cover all 15 read routes with byte hash, modification time, schema version and
table checks; writable connection/migration functions are made forbidden. Current-schema export/report
also proves authentication avoids that dependency. Missing-path and query-only write failures are tested.

Final regression results (2026-11-01 local time):

| Check | Result |
| --- | --- |
| Blocker + prospective + selective-review + API contract targeted suite | 120 passed |
| Full Python | 901 passed, 5 existing data-dependent skips |
| Full frontend | 207 passed across 29 files |
| TypeScript | Passed |
| Python OpenAPI and frontend generated-schema checks | Passed |
| Vite production build | Passed; existing >500 kB bundle warning |
| Routing browser suite | 10 passed |
| Prospective browser suite | 2 passed, including expired/closed override boundaries |
| Legacy pristine S16 browser suite | 1 passed; optional guide capture intentionally skipped |
| Desktop/mobile screenshots and changed-panel overflow check | Passed; captures inspected |

Python skips are the existing absent gitignored sample/prediction artifacts; no detector assets were
regenerated to mask them. Frontend tests retain two existing jsdom navigation notices without test failures.
data/demo.db SHA-256 remains
`DF34AB87760A8BB51DDF5A74D84A2B4C89DE0C5B157777292F15FC132A83AC00`.
Its legitimate feedback was not reset, reseeded or overwritten. Protected configuration, contract/schema,
policy/workflow, temporal replay and original S16 fixture/narrative files have zero diff from the base.

## Boundaries and next review

No changes to the pure Selective Review policy, memory policy, trusted context resolver, temporal replay,
Suricata admission, routing, Tier 2 cases, response approval, legacy feedback/guardrails or detector pipeline.
No live capture, attacks, real response actions, new automation or registered collection was performed.
Synthetic rehearsals are not participant UAT, production safety evidence or independent readiness approval.
Archive reconciliation establishes internal completeness, not a cryptographic proof against a completely
replaced archive; independent provenance of supplied histories remains required.
Older schemas must be upgraded through an explicitly writable operational path, not a read-only request.

Next: independently review this exact feature commit against the base above, rerun the blocker and browser
tests, inspect read-only connection/authentication wiring and ledger reconciliation, and confirm protocol V2
remains draft. Do not open a real registered run until that review returns PASS.

## Exact file manifest

Paths relative to hitl-ids/:

```text
apps/api/auth.py
apps/api/collection_routes.py
apps/api/context_routes.py
apps/api/contract/openapi.py
apps/api/deps.py
apps/api/openapi.json
apps/api/read_only.py
apps/api/routes.py
apps/api/selective_review_routes.py
apps/web/e2e/prospective-override.spec.ts
apps/web/playwright.prospective.config.ts
apps/web/src/api/schema.d.ts
apps/web/src/pages/analyst/SelectiveReviewPage.test.tsx
apps/web/src/pages/analyst/SelectiveReviewPage.tsx
docs/HANDOVER.md
docs/prospective-collection-readiness-v2.md
docs/prospective-collection-uat.md
docs/prospective-readiness-blocker-fixes.md
packages/detection/prospective_collection.py
packages/detection/selective_review.py
packages/evaluation/prospective_recorded.py
tests/test_prospective_blockers.py
```
