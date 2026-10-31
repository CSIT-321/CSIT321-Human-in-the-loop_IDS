# Response Recommendation + Human Approval

Base: `feat/tier2-case-workflow` at `d39fbd9dc123a35c59e5f7ea7a2027d46b6157da`.
Branch: `feat/response-recommendation-approval`.

## Implemented boundary

Suricata -> Staging -> Eligibility Review -> Operational Admission -> Triage Policy ->
Tier 1 -> Tier 2 Candidate -> Tier 2 Case -> Investigation -> Response Recommendation ->
Human Approval. The final state is **Approved - Not Executed**.

Detector finding != Tier 2 finding != response recommendation != human approval != execution.
Human approval is a safety boundary, not a cosmetic UI step. No response execution,
notification delivery, network blocking, host isolation, account disabling, live ingestion,
SOAR integration, Triage Memory or automatic dismissal is implemented.

**FUTURE:** Approved Response -> Notification / simulated SOAR. A downstream executor must
revalidate current evidence/authorization; this increment contains no executor or dispatch API.

## Persistence and state

Migration 9 adds two tables without changing existing tables. Proposals have UUID identity,
formal-case foreign key, authenticated proposer, source (`system_policy` or `analyst`), type,
explicit target, rationale, human proposal reason, creation timestamp, case revision,
optional policy version and evidence snapshot. Evidence includes the latest finding, its
actor/reason/time, and primary/linked detector snapshot when the target needs one.

Decisions have a unique proposal foreign key, authenticated actor, approved/rejected outcome,
reason, timestamp and the complete proposal snapshot. Both tables store immutable event types
and request identity/payload. UPDATE, DELETE and replacement inserts are blocked by triggers.
No mutable proposal status column exists: absence of a decision means pending; one immutable
decision means approved or rejected. Reconsideration requires a new proposal, never a rewrite.

`pending -> approved` or `pending -> rejected` only. Response revision is 1 then 2.
Every mutation uses BEGIN IMMEDIATE, active-user authorization, foreign keys and rollback.
Unique request IDs bind the canonical request and actor. Exact retries return existing/current
state without duplicates or rewinding it. Conflicting retries return 409.
Case revision must match every fresh command. Approval also requires the original proposal's
case revision and finding to remain current and revalidates the target. Any case mutation
(including notes/links) makes old proposals unapprovable; they can still be rejected using
the current revision. A new proposal is required for approval. Historical approvals remain
historical if the case changes later; they do not execute anything.

## Deterministic policy and targets

| Latest recorded finding | System proposal |
|---|---|
| confirmed_malicious + valid primary source IP | block_source_ip, explicit source IP |
| confirmed_malicious without valid primary source IP | further_investigation, case |
| suspicious | monitor, case |
| inconclusive or no finding | further_investigation, case |
| expected_activity | monitor, case; no containment |

Policy `response-policy-v1` has no severity, priority or Tier2Recommended input.
Every suggestion contains its reason. A suggestion is generated only upon an authenticated
human request; the requester's identity is preserved even when proposal source is system_policy.
It is never an automatic action. A malicious finding alone creates no response record.

Manual proposals can supplement/override suggestions with a nonblank reason and supported
target. `block_source_ip` accepts only a valid primary or explicitly linked source IP.
`monitor` accepts the case or a primary/explicitly linked operational-alert UUID.
`further_investigation` and `notify_security_team` use the case as scope, with no fabricated
recipient and no delivery. `isolate_host` and `disable_account` are recognized contract types
but rejected: current case evidence has no trusted structured host/account identifier.
Free-text case notes, arbitrary addresses and destination IPs alone cannot authorize targets.

## API, RBAC and UI

Authenticated endpoints under `/api/v2/tier2/cases/{caseRef}/responses`:

- GET: bounded paginated history plus current case revision.
- POST `/recommend`: `requestId`, `expectedCaseRevision`, `reason`.
- POST `/manual`: same plus `recommendationType`, `targetType`, `targetValue`.
- POST `/{recommendationRef}/approve` or `/reject`: same base fields plus `expectedRevision`.

All mutation actors come from the JWT, never the body. Existing active analyst/admin users
may propose and decide; evaluator is read-only. A dedicated Tier 2/Senior Analyst role and
four-eyes separation remain future refinements; the proposer may currently approve a plan.
Extra body fields are rejected. Missing formal cases return 404, stale/unsupported targets
409, malformed requests 400 and unauthorized mutations 401/403.

Case detail shows proposal type/target/source/actor/time, rationale, proposal reason, finding,
policy version, event/reference, and immutable human decision history. Approve/reject require
reasons; stale approval is disabled. Evaluators see no mutation controls. Unavailable host/account
targets are disabled. The warning **APPROVAL DOES NOT EXECUTE THE ACTION.** is always visible.
Approved plans show **Approved - Not Executed**. Load failures have a retry path, not empty success.

Audit event types: `V2_RESPONSE_RECOMMENDED`, `V2_RESPONSE_MANUAL_RECOMMENDATION`,
`V2_RESPONSE_APPROVED`, `V2_RESPONSE_REJECTED`. The response section is its own immutable
ledger; the existing case timeline/findings, detector, triage and routing records are not rewritten.

## Verification and reproducibility

The disposable browser rehearsal copies the demo database into a temporary database, seeds
fixture alerts and exercises real authentication. `e2e/response-approval.spec.ts` performs
eligibility acceptance, operational admission, Tier 1 escalation, case creation, investigation,
confirmed_malicious finding, system recommendation and human approval. It asserts no automatic
recommendation after the finding, a reason-required approval button, immutable approved state,
no execution, no page errors and no horizontal overflow at 390px.
Screenshots: `apps/web/test-results/response-approval-desktop.png` and
`apps/web/test-results/response-approval-mobile.png` (local ignored artifacts).

Backend tests cover policy, formal-case enforcement, target validation, manual override,
authenticated actor/retry identity, stale cases, terminal decisions, concurrency, failed-write
rollback, append-only triggers and migration integrity/idempotency. Full-table snapshots prove
proposal/decision operations do not change detector, case/findings, routing, feedback or evaluation.
UI tests cover reason requirements, retry identity, read-only access, stale approval, unavailable
targets, terminal history and failures. Existing OpenAPI paths/schemas are structurally unchanged.

Verification commands from `hitl-ids` (Python 3.11): `python -m pytest -q`,
`python scripts/build_openapi.py --check`. From `apps/web`: `npm test`, `npm run build`,
the package's generated schema check, and `playwright test --config playwright.routing.config.ts`.
This environment uses the existing Python 3.11 test venv and bundled Node runtime.
Optional missing dataset fixtures retain their five baseline skips; no skipped response tests.

Verified results: Python **720 passed, 5 skipped**; frontend **183 passed in 25 files**;
disposable browser suite **8 passed**; TypeScript, Python OpenAPI check, frontend generated-schema
check and Vite production build all pass. Existing API paths and component schemas compare
equal to the base after JSON parsing. Vite's existing >500 kB bundle warning and jsdom's
navigation warnings remain non-failing. The first browser attempt had an ambiguous text
locator; an exact status match fixed the test and the complete eight-test rerun passed.

## Exact changed-file manifest

Paths below are relative to `hitl-ids/`:

```text
apps/api/contract/openapi.py
apps/api/contract/responses.py
apps/api/main.py
apps/api/openapi.json
apps/api/response_routes.py
apps/web/e2e/response-approval.spec.ts
apps/web/e2e/tier2-case.spec.ts
apps/web/playwright.routing.config.ts
apps/web/src/api/schema.d.ts
apps/web/src/pages/analyst/ResponseRecommendations.test.tsx
apps/web/src/pages/analyst/ResponseRecommendations.tsx
apps/web/src/pages/analyst/Tier2CasesPage.test.tsx
apps/web/src/pages/analyst/Tier2CasesPage.tsx
docs/HANDOVER.md
docs/deviations.md
docs/response-recommendation-approval.md
docs/system-workflow.md
packages/contracts/db.py
packages/contracts/response_approval.sql
packages/detection/response_approval.py
packages/detection/response_policy.py
tests/test_api_contract.py
tests/test_canonical_api.py
tests/test_contracts.py
tests/test_external_staging.py
tests/test_operational_v2.py
tests/test_response_approval.py
tests/test_tier2_cases.py
tests/test_triage.py
tests/test_triage_policy.py
```

The older migration tests change only their expected migration/table inventories or explicitly
bound the migration under test. Existing detection algorithms, scores, queue ordering,
feedback/guardrails, evaluation and Suricata admission/routing implementations are unchanged.
