# Authenticated Tier Routing Workflow

Stacked base: `feat/operational-triage-policy`,
`8370b44b3dea4b55567cca2938d2bc12c8141212`.
Feature: `feat/tier-routing-workflow`.

## State machine and authorization

| Action | Required state | Result | Audit event |
| --- | --- | --- | --- |
| Admit | unassigned / staged | tier1_review / triage | V2_TIER1_ADMITTED |
| Approve | tier1_review / triage, recommendation true | tier2_candidate / assessment | V2_TIER2_APPROVED |
| Reject | tier1_review / triage, recommendation true | tier1_review / triage | V2_TIER2_REJECTED |
| Manual escalate | tier1_review / triage | tier2_candidate / assessment | V2_MANUAL_ESCALATION |

Every action requires a nonblank reason and sets reviewRequired true. All other transitions
are rejected. Recommendation and its reasons remain unchanged, including after rejection.
An analyst can reconsider a rejection with a new request and fresh state version.
Escalation/rejection sets decisionSource=analyst and existing policy application consequently
refuses to overwrite it. Admission preserves policy ownership so explicit policy application
can still follow admission; the separate routing audit attributes the human admission.

Existing legacy triage RBAC already permits security_analyst and system_admin. Both may route;
evaluator may only read. JWT identity supplies actor_id, never request data. Service authorization
rechecks the active actor inside the write transaction. Read responses omit allowed actions
for evaluators; hiding buttons is not the authorization boundary.

## API and persistence

All endpoints require authentication. The path alertRef is the V2 operational UUID, not a
legacy alert UUID. Numeric IDs in V2 state/audit bodies are correlation fields only.

- GET `/api/v2/alerts?limit=50&offset=0`: bounded, ID-ordered V2 listing, not the legacy queue.
- GET `/api/v2/alerts/{alertRef}/triage-state`: current state, stateVersion, policy reasons,
  latest human decision and authorized actions.
- POST `/api/v2/alerts/{alertRef}/admit-tier1`
- POST `/api/v2/alerts/{alertRef}/tier2/approve`
- POST `/api/v2/alerts/{alertRef}/tier2/reject`
- POST `/api/v2/alerts/{alertRef}/tier2/escalate`

POST body: requestId (UUID), expectedStateVersion (SHA-256 of the complete serialized state),
reason (trimmed nonblank string, maximum 2000 characters). Unknown fields are forbidden.
Responses include current view, original decision audit, and replayed. State tokens are
concurrency markers, not credentials. Stale state, illegal transitions, or conflicting reuse
of requestId return 409. Missing alert returns 404; invalid payload 400; auth failures 401/403.

Migration 6 creates only operational_routing_audit, its index and append-only triggers.
No existing table rebuild, column rewrite, or core alerts change. Existing migration locking
and version recheck provide concurrent startup safety. Routing uses BEGIN IMMEDIATE and
atomically writes mutable V2 state plus audit. Failed audit insertion rolls everything back.
The audit stores actor, event, request identity, reason, full before/after state, and timestamp.
Snapshots therefore include priority/band, scheme, policy version and recommendation reasons.
UPDATE, DELETE and replacement INSERT are blocked. Detector snapshots are never written.

Idempotency keys are globally unique and actor/alert/action/state-token/reason-bound. An exact
retry returns the original audit without replaying the old state; its view is current. A new
decision uses a fresh key and state token. Rejection advances updatedAt monotonically even
though route/stage remain unchanged. Reads use a transaction for coherent state/history.

## UI and scope

Each existing role has a V2 Triage Routing page at `/<role>/v2-triage` (analyst, admin, evaluator).
The separate page displays priority/band, actual route/stage, review requirement, recommendation
and reasons, policy version, latest decision, reason input and authorized actions. Null priority
is shown as not assigned. Submission does not optimistically change route. Transport retries keep
the request key; stale decisions require refresh/review. Errors, loading, empty results and paging
are handled. Mobile horizontal navigation is enabled only for this page; existing role pages
retain their original shell layout. No Workstation queue or evaluator data source is changed.

No automatic materialization or policy invocation occurs here. A normal database with no V2
projections has an honest empty screen. scripts/serve_routing_rehearsal.py creates a disposable
copy with three explicit test fixtures, including two policy recommendations. It is test/demo
setup, not ingestion or a production seeding path. Original demo.db is untouched.

Limitations: only the latest routing decision is exposed in this UI/API; complete immutable
history remains in SQLite. No Tier 2 Case, investigation workspace, resolution, notifications,
Triage Memory, automatic dismissal, SOAR, blocking or live ingestion. Next increment is explicit
Tier 2 Case creation from a candidate, under its own reviewed contract and authorization.

## Verification

Verified result: 648 Python tests passed, five unchanged missing-data skips; 166 frontend tests
passed across 22 files; five browser tests passed. Python OpenAPI check, generated TypeScript
schema check, TypeScript compilation, Vite production build and Git whitespace check passed.
The existing large-bundle warning and jsdom navigation notices remain non-failing.

Run the full Python suite with `python -m pytest`; run `python -B scripts/build_openapi.py --check`.
In apps/web run the generated-schema check, TypeScript build, full Vitest suite and Vite build.
Browser verification: set HITL_PYTHON to the desired Python executable, then run Playwright with
`--config playwright.routing.config.ts`. It uses isolated ports 8002/5175 and disposable data;
it refuses to reuse existing servers. Browser tests cover actual authenticated admission,
manual escalation, recommendation approval/rejection, evaluator read-only, desktop/mobile
layout, plus legacy analyst investigation, admin IP report and evaluator metrics.

Backend tests cover all four events, before/after state, recommendation preservation, illegal
transitions, authorization, malformed requests, stale tokens, retry collisions, delayed retries,
concurrency, rollback, audit immutability, additive migration and both source kinds' isolation.
Frontend tests cover recommendation/route distinction, required notes, read-only actions,
transport retry identity, conflicts, empty/failure states and unknown priority.

## Exact file manifest

Paths relative to repository root:

```text
hitl-ids/apps/api/contract/openapi.py
hitl-ids/apps/api/contract/routing.py
hitl-ids/apps/api/main.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/api/routing_routes.py
hitl-ids/apps/web/e2e/routing-workflow.spec.ts
hitl-ids/apps/web/playwright.routing.config.ts
hitl-ids/apps/web/src/App.tsx
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/components/layout/AppShell.tsx
hitl-ids/apps/web/src/components/layout/Sidebar.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.tsx
hitl-ids/apps/web/src/session/roles.ts
hitl-ids/apps/web/src/test/shell.test.tsx
hitl-ids/docs/authenticated-tier-routing-workflow.md
hitl-ids/packages/contracts/db.py
hitl-ids/packages/contracts/routing_workflow.sql
hitl-ids/packages/detection/routing.py
hitl-ids/scripts/serve_routing_rehearsal.py
hitl-ids/tests/test_api_contract.py
hitl-ids/tests/test_canonical_api.py
hitl-ids/tests/test_contracts.py
hitl-ids/tests/test_external_staging.py
hitl-ids/tests/test_operational_v2.py
hitl-ids/tests/test_routing_workflow.py
hitl-ids/tests/test_triage.py
hitl-ids/tests/test_triage_policy.py
```
