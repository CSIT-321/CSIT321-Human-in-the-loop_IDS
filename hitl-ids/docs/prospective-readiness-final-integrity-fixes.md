# Prospective Readiness Final Integrity Fixes

Base: `feat/prospective-readiness-blocker-fixes` at
`20fb6d7d11c3e5540f9650595463d8fd876d3231`.
Branch: `feat/prospective-readiness-final-integrity-fixes`.

Status: implemented and automated regressions passed, NOT independent readiness approval.
The latest independent review was FAIL. Another independent final read-only review must return PASS
before registered collection. Protocol V2 remains unchanged, draft, undated and unopened; V1 is unchanged.
All automated collection windows below exist only in disposable synthetic test databases.

Subsequent independent review: FAIL because unbound operational overrides could bypass full validation
and still contribute to recall. The stacked [unbound override integrity fix](prospective-unbound-override-integrity.md)
addresses that remaining finding. A new independent PASS is still required; this historical test report
is not authorization to preregister or open collection.

## Complete inspection route inventory

All 40 database-backed GETs use the same non-migrating path. The 25 marked **new** are converted by
this increment; the 15 marked **prior** already used it. The test inventory is compared to the actual
FastAPI route/dependency graph, so an added GET cannot silently escape coverage.

| GET path | Conversion |
| --- | --- |
| `/api/auth/me` | prior |
| `/api/alerts` | new |
| `/api/alerts/families` | new |
| `/api/alerts/{alertRef}` | new |
| `/api/alerts/{alertRef}/score-adjustment` | new |
| `/api/alerts/{alertRef}/feedback-history` | new |
| `/api/alerts/{alertRef}/notes` | new |
| `/api/dashboard/breakdowns` | new |
| `/api/entities/ip/{ip}` | new |
| `/api/admin/reports/ips` | new |
| `/api/admin/reports/ip/{ip}` | new |
| `/api/dashboard/summary` | new |
| `/api/audit-log` | new |
| `/api/config/guardrails` | new |
| `/api/evaluation/scenarios` | prior |
| `/api/evaluation/runs` | prior |
| `/api/evaluation/runs/{runId}` | prior |
| `/api/evaluation/runs/{runId}/detection` | prior |
| `/api/v2/alerts` | new |
| `/api/v2/alerts/{alertRef}/triage-state` | new |
| `/api/v2/external-alerts` | new |
| `/api/v2/external-alerts/{inboxId}` | new |
| `/api/v2/tier2/cases` | new |
| `/api/v2/tier2/cases/{caseRef}` | new |
| `/api/v2/tier2/cases/{caseRef}/events` | new |
| `/api/v2/tier2/cases/{caseRef}/responses` | new |
| `/api/v2/triage-memory` | new |
| `/api/v2/triage-memory/{lessonRef}` | new |
| `/api/v2/triage-memory/{lessonRef}/events` | new |
| `/api/v2/alerts/{alertRef}/triage-memory/matches` | new |
| `/api/v2/selective-review/metrics` | prior |
| `/api/v2/selective-review` | prior |
| `/api/v2/alerts/{alertRef}/selective-review` | prior |
| `/api/v2/alerts/{alertRef}/selective-review/events` | prior |
| `/api/v2/context/facts` | prior |
| `/api/v2/alerts/{alertRef}/context` | prior |
| `/api/v2/collection/runs` | prior |
| `/api/v2/collection/runs/{runRef}` | prior |
| `/api/v2/collection/runs/{runRef}/export` | prior |
| `/api/v2/collection/runs/{runRef}/report` | prior |

Database-free GETs are separately tested: `/api/health`, `/openapi.json`, `/docs`,
and `/docs/oauth2-redirect`. Health reads file existence, not database contents.

## Dependency boundary and state conservation

`GET -> ReadConn / ReadPrincipal / readonly RBAC -> get_readonly_connection`.
SQLite opens a resolved URI with `mode=ro`; the first SQL is `PRAGMA query_only=ON`.
Authentication, role lookup, queue filters and the handler share one FastAPI-cached connection.
No db.connect, migration, schema initialization or replacement-write path is used. The Admin report
role gate opts into the same path with `require_role(..., readonly=True)`; its role rules are unchanged.

All POST/PUT/PATCH/DELETE dependency graphs retain the explicit writable dependency, including login,
eligibility/admission, routing, case/response/memory/context mutations and collection lifecycle operations.
Some mutations call a read handler as an ordinary helper to serialize a response; they keep their existing
transaction connection. No operational policy or transaction semantics change.

Each of the 40 GETs is called with a real signed Admin token against a disposable schema-12 database.
It returns `503 DATABASE_SCHEMA_UNSUPPORTED`, not an upgrade. Before/after evidence compares:
user_version=12, schema_version, complete sqlite_master definitions (including table set), logical dump
SHA-256, byte SHA-256 and nanosecond mtime. No prospective tables are created.
Each route also checks a missing path: `503 DATABASE_MISSING`, no file or parent directory creation.
The legacy explicit run_detection.py recovery instruction remains in the missing-database message.

Current-schema checks forbid writable/migration helpers, inspect the SQLite URI and first SQL, and prove
exactly one connection per authenticated request plus unchanged database fingerprints. Separate response
checks cover 200, 400, 403, 404 and an injected 409; schema/missing-path tests cover 503. These guards apply
before a handler can fail, including a nonexistent triage-state response. No assertion was weakened.
OpenAPI and generated TypeScript add the standard 503 error response to the remaining GETs only.

## Raw event and request identity

The source `selective_review_events` table has global UNIQUE event_ref/request_id constraints and a
numeric primary key. Archive validation applies those uniqueness rules before cohort selection.
All raw rows need a strict positive integer ID, nonempty valid UUID event_ref/request_id and parseable
originating request provenance. Numeric IDs, normalized event UUIDs and request UUIDs must each be unique
across the entire export, including unrelated rows; a duplicate could not represent two source events.
Run binding compares UUID values, not formatting; uppercase, compact and braced UUID text cannot hide a
missing legacy sidecar. Malformed run UUID text is rejected rather than treated as an unrelated event.

Every run-bound or sidecar-referenced row additionally validates:

- Strict positive actor and operational alert IDs, nonempty UUID alertRef, valid action/event type.
- Timezone-aware persisted timestamp, nonempty reason, typed original ReviewCommand and ReviewSnapshot.
- Raw request_id equals original request.request_id; action, reason and alert match the original payload.
- Action matches event_type; numeric/UUID alert identities and timestamp match the original snapshot.
- Original request binds to the run; receipt runRef and decisionRef agree with its collection sidecar.
- Sidecar actor/action/time/alert and complete snapshot agree with the raw event.

The existing sidecar has no duplicated request_id field. Its request identity is validated transitively:
`sidecar.reviewEventId -> raw.id -> raw.request_id == payload.request.request_id`, with receipt
`decisionRef -> sidecar.decisionRef` and matching runRef. No new identity is invented or repaired.
Duplicate prospective decisionRef/reviewEventId, missing decisions/raw events, swapped receipts and a
lowered count that hides a ledger row are rejected. The HTTP report returns `400 ARCHIVE_INTEGRITY`.

Receipt-free legacy records retain their atomic event/sidecar requirement. A valid not_recorded human
override may be present without a sidecar, including expired/closed runs. It cannot inflate decisionCount.
Unrelated future snapshot/configuration content is not reinterpreted using today's contract. Valid
post-cutoff additions leave the closed report byte-identical; impossible global identity duplicates fail.

Count meanings are unchanged:

- `run.decisionCount`: all immutable recorded ledger events, including repeats and in-window overrides.
- `eligibleAlerts`: unique alerts represented by their first eligible applied evaluation.

## Verification

The new three-event fixture records apply, repeated apply and an in-window override. The valid report has
three ledger events but one eligible/deferred/recalled alert. Individually tested damages cover missing,
null, empty, malformed, duplicate and spliced identities, request/receipt chains and ledger completeness.
A copied unrelated-event fixture now supplies distinct event/request UUIDs, as the actual source database
requires; its existing post-window invariance assertion is unchanged.

| Check | Result |
| --- | --- |
| Inspection + identity + blocker + collection targeted suites | 269 passed |
| Full Python | 1111 passed, 5 existing optional-data skips |
| Full frontend | 207 passed, 29 files |
| TypeScript | Passed |
| Python OpenAPI + frontend generated-schema check | Passed |
| Vite production build | Passed; existing >500 kB bundle warning |
| Routing browser suite | 10 passed |
| Prospective browser suite | 2 passed |
| Pristine S16 browser suite | 1 passed; optional guide capture intentionally skipped |

The five Python skips require absent gitignored prediction/sample artifacts (contracts, fusion,
observable, rule-set and run tests); no data was regenerated to mask them. Frontend tests retain two
existing jsdom navigation notices without failures. An AST comparison confirms all 76 function bodies
across the six route-wiring modules are unchanged. A structured OpenAPI comparison confirms only 25
additional GET 503 responses: paths, operation IDs, schemas and mutation contracts are unchanged.

The prospective browser suite retains the actual UI workflow: learn/activate memory, defer, wait for
expired/closed collection boundaries, Require Human Review, visible success, reload, persistent Must
Review/audit/skip reason, and byte-equivalent collection ledger. It also checks desktop/mobile overflow.
No browser assertions or fixture code changed in this increment. S16 still seeds only its minimum pristine
disposable state; it does not copy, reset or reseed data/demo.db. The timing model and closed-window
configuration/fact isolation remain covered by the prior regression tests.

Reproduction uses the existing Python 3.11 environment and installed frontend dependencies. From hitl-ids/:

```powershell
python -B -m pytest -q -p no:cacheprovider tests/test_inspection_readonly.py tests/test_prospective_event_identity.py tests/test_prospective_blockers.py tests/test_prospective_collection.py --basetemp <new-disposable-directory>
python -B -m pytest -q -p no:cacheprovider --basetemp <another-new-disposable-directory>
python -B scripts/build_openapi.py --check
```

From apps/web/:

```powershell
npm test
npm run typecheck
npm run check:api
npm run build
npx playwright test --config=playwright.routing.config.ts
npx playwright test --config=playwright.prospective.config.ts
npx playwright test --config=playwright.config.ts
```

The actual run invokes these installed Node entrypoints directly, without installing packages.
HITL_PYTHON selects the existing Python interpreter; PYTHONDONTWRITEBYTECODE=1 prevents bytecode writes.
All pytest basetemps and browser output directories are unique temporary paths. S16 uses explicit free
ports 8013/5191 via HITL_E2E_API_PORT/HITL_E2E_WEB_PORT; it never reuses a demo server.
The initial full run exposed the retained legacy missing-database recovery-message assertion; the
read-only error message was corrected, not the test. Final results above refer to the final-source rerun.

Source data/demo.db SHA-256 before/after verification:
`DF34AB87760A8BB51DDF5A74D84A2B4C89DE0C5B157777292F15FC132A83AC00`.
Its LastWriteTimeUtc ticks remain `639252641490430974`; no legitimate feedback/history was changed.

## Boundaries and independent review

There is no change to database schema, Selective Review pure policy, Triage Memory logic, trusted context
resolver, temporal replay, Suricata admission, routing, Tier 2 case service, response approval, legacy
feedback/guardrails or detector pipeline. Their HTTP GET dependency wiring is changed, not their behavior.
No UI implementation changes, detector regeneration, real traffic, response execution or automation expansion.
No real registered collection has started; synthetic test runs are not participant UAT.

Internal reconciliation is not a cryptographic signature or proof of origin against a completely replaced
archive. Actor foreign keys cannot be independently authenticated from an archive without a trusted source;
recorded sidecar/raw actor identities are checked for equality. Independent history/provenance validation
remains necessary. Read-only access intentionally rejects old schemas; explicit operational maintenance
must upgrade them. Existing optional dataset-dependent skips and bundle warning are not readiness PASS.

Next step: an independent reviewer should compare this feature commit to the exact base above, rerun all
40 old-schema/missing/current-schema probes and archive identity negatives, inspect the dependency graph
and request/sidecar chain, rerun all three browser suites, and verify the untouched draft protocol.
Only a subsequent independent PASS may authorize planning a separately approved registered collection.

## Exact file manifest

Paths relative to hitl-ids/:

```text
apps/api/auth.py
apps/api/contract/openapi.py
apps/api/deps.py
apps/api/external_admission_routes.py
apps/api/memory_routes.py
apps/api/openapi.json
apps/api/response_routes.py
apps/api/routes.py
apps/api/routing_routes.py
apps/api/tier2_case_routes.py
apps/web/src/api/schema.d.ts
docs/HANDOVER.md
docs/prospective-collection-readiness-v2.md
docs/prospective-readiness-blocker-fixes.md
docs/prospective-readiness-final-integrity-fixes.md
packages/evaluation/prospective_recorded.py
tests/test_inspection_readonly.py
tests/test_prospective_blockers.py
tests/test_prospective_event_identity.py
```
