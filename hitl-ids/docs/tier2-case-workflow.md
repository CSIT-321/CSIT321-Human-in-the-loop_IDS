# Tier 2 Case Workflow

Base: `feat/suricata-operational-admission`,
`434ca2d3ec50fcfb33187c7c5021b37e31336c9d`.
Feature: `feat/tier2-case-workflow`.

## Operational path

Suricata -> Staging -> Eligibility Review -> Operational Admission -> OperationalAlertV2
-> Triage Policy -> Tier 1 -> explicit Tier 2 Candidate -> explicit Tier 2 Case -> Investigation.

FUTURE ONLY: Tier 2 Case -> Response Recommendation -> Human Approval -> Notification / simulated
SOAR. This increment contains no response execution, notification, firewall blocking, live ingestion,
automatic correlation, Triage Memory or selective/no-immediate review.

## Persistent model

Migration 8 adds three tables and indexes/triggers, without altering or rebuilding any existing table:

- tier2_cases: immutable UUID identity, unique primaryOperationalAlertId, title, ownerActorId,
  createdByActorId, createdAt, and a typed immutable creation snapshot.
- tier2_case_state: status (open or investigating), monotonic revision and updatedAt.
- tier2_case_events: immutable, ordered investigation ledger. Notes, findings and explicit links
  are typed event rows, rather than separate mutable records with a duplicated audit history.
  Each has actor, request identity, reason/note, timestamp and before/after state.
  Linked operational IDs have foreign keys and a per-case uniqueness constraint.

The creator is the initial owner. No owner reassignment or closure is introduced. Cases are
identified publicly by caseRef UUID; the primary alert retains its own operational UUID.
One alert can be primary for only one case. An additional alert may be explicitly linked to more
than one case, but never twice within one case. Primary-alert self-linking is rejected.

## Candidate-to-case transition

Case creation requires tier2_candidate / assessment and the current state-version token.
It additionally requires a matching immutable routing audit from approve_tier2 or manual_escalate;
an out-of-band candidate state without that authenticated decision is rejected.
Neither high priority, native severity nor a recommendation creates a case automatically.

One BEGIN IMMEDIATE transaction inserts the case, open lifecycle state and creation audit, and
changes the primary V2 route/stage to tier2_case / investigation. It keeps reviewRequired true
and records analyst decision ownership. Any failure rolls back every write, including the route.
The new transition is owned by the case service; the existing Tier 1 routing service is unchanged.

The case snapshot contains the complete immutable OperationalAlertV2 evidence/provenance,
triage state at creation (including priority/band, policy version and recommendation reasons),
the authenticated Tier 1 escalation decision and its reason, the explicit human handoff summary,
and the case-creation reason. Source/destination, title/category, detector source, native severity,
nullable confidence, occurrence timestamp and detailed detector evidence remain exact.
The latest Tier 1 reason is preserved from the escalation audit; V2 has no separate Tier 1 notes
thread. This snapshot is never written back to detector evidence.

An explicit Start investigation action changes case status open -> investigating.
Notes, links and findings are also allowed on an open case and do not imply a response action.
There is no resolution, containment or remediation state in this increment.

## Investigation and audit

Explicit linked-alert actions record the linked UUID, actor, reason and time without changing
the linked alert's route, stage, score, policy or detector evidence. No similarity engine or
automatic correlation is invoked.

Investigation notes are append-only text, with a nonblank maximum of 4000 characters.
Findings are append-only records: confirmed_malicious, suspicious, inconclusive or expected_activity,
each with a required reason. Later findings do not overwrite earlier ones. They are case opinions,
not detector outputs, training labels, legacy verdicts or response authorization.

Events:

- V2_TIER2_CASE_CREATED
- V2_TIER2_ALERT_LINKED
- V2_TIER2_NOTE_ADDED
- V2_TIER2_FINDING_RECORDED
- V2_TIER2_INVESTIGATION_STARTED

Creation audit before/after snapshots contain the old/new alert route/stage, priority/band,
policy version and recommendation reasons; the immutable case snapshot adds escalation/handoff.
All subsequent events snapshot lifecycle state before/after. SQL triggers block event updates,
deletion and replacement, and protect the complete case creation snapshot.

## Concurrency and authorization

Existing active security_analyst and system_admin capabilities are retained. Evaluator is read-only.
The API binds actor_id to the verified JWT principal; services recheck active role under the write
lock. No caller-supplied actor, owner or detector evidence is accepted. There is no dedicated
senior/Tier 2 role yet; workflow state, not a new role migration, distinguishes Tier 2.

Creation uses the complete V2 state hash; all investigation mutations require expectedRevision.
Each append increments the case revision and advances updatedAt monotonically. Stale decisions
return 409. Request UUIDs are unique across the case ledger, bound to actor, action, target and
normalized complete payload. Exact retries return the original event ID and current case state,
never rewind status or append duplicate notes/findings. Reusing a key with different input fails.
Competing distinct case creations or note appends have one winner; exact retries are safe.
All state/event writes share a transaction; failed audit insertion cannot advance the revision.

## API

All routes authenticate. Mutation routes retain existing analyst/admin RBAC.

- POST /api/v2/alerts/{alertRef}/tier2/case
- GET /api/v2/tier2/cases
- GET /api/v2/tier2/cases/{caseRef}
- GET /api/v2/tier2/cases/{caseRef}/events
- POST /api/v2/tier2/cases/{caseRef}/alerts
- POST /api/v2/tier2/cases/{caseRef}/notes
- POST /api/v2/tier2/cases/{caseRef}/findings
- POST /api/v2/tier2/cases/{caseRef}/start-investigation

Lists use limit 1..200 (default 50) and nonnegative offset. Events optionally filter by action;
this powers bounded linked-alert, note, finding and full timeline views. Existing API paths and
component definitions remain structurally unchanged; the case contract is additive.
Validation/auth/not-found/conflict use the existing 400/401/403/404/409 error envelopes.

## UI and demonstration

Tier 2 Cases is a separate navigation page for every existing role, listing formal cases only:
UUID, title, priority at creation, status, owner, creation time and primary alert. Detail shows
summary, Tier 1 handoff, detector evidence, explicit linked alerts, notes, findings and audit.
Native severity, detector confidence and operational priority are separately labelled.
Response is explicitly shown as Not yet recommended.

Only authorized users on a candidate see the case creation form in V2 Routing. It requires title,
handoff and reason, uses stale-state protection and preserves retry identity on transport failure.
Success navigates to the new case. Investigation forms preserve retry identity and do not
optimistically alter state on errors. Read-only evaluators see history without mutation controls.
Case pages use the existing responsive V2 shell; the legacy Workstation/Admin/Evaluator views
are unchanged.

The browser E2E selects a genuinely staged Suricata fixture, accepts eligibility, admits it to
Tier 1, manually escalates it, explicitly creates a case, starts investigation, adds a note and
records a suspicious finding. It verifies that the primary alert becomes tier2_case/investigation.
It uses the existing disposable rehearsal database, not data/demo.db.

## Verification and limits

Verified results: 694 Python tests passed, five unchanged missing-data skips (699 collected);
176 frontend tests passed across 24 files; seven browser smoke tests passed. Python OpenAPI,
generated frontend schema, TypeScript and Vite checks pass. Structural comparison with the
base found no changed existing API paths or component schemas. Existing non-failing warnings
remain: Vite bundle size and jsdom full-document navigation notices.

Backend coverage includes blocked Tier 1/recommended/staged creation, matching escalation audit,
RBAC, stale state/revisions, same/different-key concurrency, rollback at each creation boundary,
immutable snapshots/notes/findings, explicit link uniqueness and unchanged linked routes,
legacy table isolation and additive/idempotent migration. Full admission, routing, policy,
Signature/XGBoost, feedback, guardrail and evaluator regressions remain part of the suite.
Frontend coverage includes case-only lists, evidence/handoff separation, evaluator read-only,
required notes, retry identity, conflicts and API failures. Browser tests retain all prior paths.

No ownership reassignment, full closure, response recommendation engine or dispatch is implemented.
No dedicated Tier 2 role is introduced. Case handoff and priority are historical snapshots, not
live updates to detector evidence or future learning. Next increment: Response Recommendation
plus explicit Human Approval, separately reviewed before any notification or simulated response.

The previously stale HANDOVER.md count is updated, and its regression check now accepts an honest
nonzero optional-data skip count rather than requiring a false zero-skips claim.

## Exact file manifest

Paths relative to repository root:

```text
hitl-ids/apps/api/contract/openapi.py
hitl-ids/apps/api/main.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/api/tier2_case_routes.py
hitl-ids/apps/web/e2e/tier2-case.spec.ts
hitl-ids/apps/web/playwright.routing.config.ts
hitl-ids/apps/web/src/App.tsx
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/components/layout/AppShell.tsx
hitl-ids/apps/web/src/pages/analyst/Tier2CasesPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/Tier2CasesPage.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.tsx
hitl-ids/apps/web/src/session/roles.ts
hitl-ids/docs/HANDOVER.md
hitl-ids/docs/detector-agnostic-hitl-architecture.md
hitl-ids/docs/tier2-case-workflow.md
hitl-ids/packages/contracts/db.py
hitl-ids/packages/contracts/tier2_cases.sql
hitl-ids/packages/detection/tier2_cases.py
hitl-ids/tests/test_api_contract.py
hitl-ids/tests/test_canonical_api.py
hitl-ids/tests/test_contracts.py
hitl-ids/tests/test_external_operational_admission.py
hitl-ids/tests/test_external_staging.py
hitl-ids/tests/test_operational_v2.py
hitl-ids/tests/test_plan_sync.py
hitl-ids/tests/test_tier2_cases.py
hitl-ids/tests/test_triage.py
hitl-ids/tests/test_triage_policy.py
```
