# Direct Tier 2 escalation

Base: `5271653d12c96a7035fc8fbd8c4aff231afd0f15` on `feat/analyst-ui-refinement`.
Implementation branch: `feat/tier2-direct-escalation`. The later navigation cleanup at `2f830d0`
is deliberately excluded. Existing navigation/page names at this base are retained.

## Workflow

Old: Tier 1 → escalation → Tier 2 Candidate → manual title/handoff/reason form → Tier 2 Case.

New: Tier 1 → **Escalate to Tier 2** (or **Approve Tier 2**) → automatic formal Tier 2 Case.
The final operational state is `tier2_case / investigation`; the case initially remains `open`.
The analyst stays on the alert and sees **Escalated to Tier 2**, **Tier 2 Case created successfully**,
the case reference, **Open Tier 2 Case**, and **Continue Reviewing**. Neither action is forced.
After Continue Reviewing or a reload, the existing case link remains available.

There is no candidate callout or manual creation form in the new primary journey. An intermediate
`tier2_candidate / assessment` transition remains in immutable routing/case audit evidence only.
The old routing and explicit case APIs remain backward compatible. Reject / Keep in Tier 1 is unchanged.
No finding, malicious verdict, response recommendation, approval, or response execution is automated.
Investigation, notes, findings, links, timeline and Approved — Not Executed behavior are preserved.

The legacy Workstation's **Escalation Recommended** still submits `category="escalate"` only to the
legacy feedback endpoint. It does not invoke this operational command or create an operational case.

## Additive command and transaction

`POST /api/v2/alerts/{alertRef}/tier2/escalate-case`

Request:

```json
{
  "requestId": "<UUID>",
  "expectedStateVersion": "<current 64-character state hash>",
  "reason": "The analyst's nonblank escalation reason",
  "action": "manual_escalate"
}
```

`action` defaults to `manual_escalate`; `approve_tier2` requires an existing policy recommendation.
`recover_case` is the explicit historical compatibility action described below. Actor identity comes
from the authenticated active analyst/admin principal; client-supplied actor/title/handoff fields are rejected.
The response includes the current routing `view`, immutable routing `audit`, created `case`, creation
`eventId`, and `replayed`. Routing views additionally expose nullable `caseRef` for reopening cases.

The service owns one SQLite `BEGIN IMMEDIATE` transaction. Routing and case creation reuse their
existing validation and write logic in narrowly scoped transaction-participant modes; neither participant
commits. The outer command commits only after the routing audit, case snapshot/state, final operational
transition and creation event have all succeeded. Any exception rolls all of those writes back.
Failure injection covers the routing audit, case insert, case-state insert and creation-event insert for
both manual and policy-approved commands. An HTTP failure test also proves no success is returned and
Tier 1 remains intact. Existing admission orchestration and standalone case/routing commits retain their behavior.
No database migration is needed.

## Idempotency and concurrency

The immutable case creation event stores the original normalized logical command (version marker,
alert reference, action, expected state hash, reason) as its request payload, under the same request UUID
as the routing audit. Actor identity is separately bound by the event's actor field.
An identical retry reads that receipt and returns the same case/reference and creation event, without
regenerating metadata or rewinding later investigation work. A changed actor, alert, reason, action or
expected hash conflicts. Reusing an old standalone routing/case request ID for this command also conflicts.
The API returns a typed `ROUTING_CONFLICT` (409) for request/state/action conflicts.

`BEGIN IMMEDIATE` serializes writers before checking the optimistic version. A second distinct request
using the old version fails; duplicate identical requests replay. The existing unique constraint on the
primary operational alert is retained as a second defense against duplicate cases.

## Deterministic case metadata

- Title: actual detection title plus ` — Tier 2 Investigation`; truncate only the title prefix to fit
  the existing 200-character limit.
- Handoff: detector name/version, detection title, operational priority/band, review reason, Tier 2
  recommendation reasons, and the complete submitted analyst reason. Individual descriptive fields
  are bounded to fit the existing 4,000-character field; unavailable priority/version is explicitly marked.
- Creation reason: `Authenticated Tier 2 escalation: ` plus the submitted reason.
- The immutable snapshot also retains the complete original detector evidence, triage state, authenticated
  routing decision/actor and unabridged escalation reason. No inference or generated evidence is introduced.

## Historical compatibility

Reading historical candidates never writes or backfills a case. Operational roles may explicitly choose
**Complete Earlier Escalation** and supply a reason. That invokes `recover_case` with the current state hash.
The existing case service must still verify a matching authenticated historical escalation audit before
creating a case. The snapshot preserves that original escalation decision/reason; the new creation event
attributes recovery to the current actor and records the new reason. Invalid/stale/unaudited historical
states fail safely. Evaluators can inspect but have no recovery control. Raw candidate/assessment names
are replaced with Tier 2 / Awaiting case recovery in the primary routing display.

## Verification

- 275 targeted backend tests: direct escalation, old routing/cases, response approval, API/contract,
  external admission, selective review and prospective-readiness blockers.
- 22 existing Protocol V2 freeze tests on temporary copies/fixtures.
- Full frontend suite: 215 tests across 29 files; TypeScript passes.
- OpenAPI generation check, generated TypeScript schema check and Vite build pass. The existing build-size advisory remains.
- Ten Chromium checks in `playwright.direct.config.ts`: two successive direct escalations; no manual form
  or visible candidate step; case reference; staying on the alert; both result actions; case reload/list;
  existing manual/policy routing and rejection; investigation and response approval without execution;
  plus retained theme/mobile, memory and selective-review coverage.

Backend command (from `hitl-ids`):

```text
python -m pytest tests/test_tier2_direct_escalation.py tests/test_routing_workflow.py tests/test_tier2_cases.py tests/test_response_approval.py tests/test_api.py tests/test_api_contract.py tests/test_external_operational_admission.py tests/test_selective_review.py tests/test_prospective_blockers.py -q
python -m pytest tests/test_protocol_v2_freeze.py -q
python scripts/build_openapi.py --check
```

Frontend commands (from `hitl-ids/apps/web`):

```text
node node_modules/vitest/vitest.mjs run --maxWorkers=4
node node_modules/typescript/bin/tsc -b
node node_modules/openapi-typescript/bin/cli.js ../api/openapi.json -o src/api/schema.d.ts --check
node node_modules/vite/bin/vite.js build
node node_modules/@playwright/test/cli.js test --config playwright.direct.config.ts
```

The browser fixture builds a pristine synthetic database in a temporary directory, with two extra
staged policy-event alerts reserved for the new journeys. It never reads or writes `data/demo.db`.
`HITL_PYTHON` selects the API's Python environment when necessary. Windows tests use workspace-local
TEMP/TMP and pytest basetemp directories. Screenshots under ignored `test-results/` include
`direct-tier2-result.png` and `direct-created-cases.png`.

## Research boundary

Protocol V2/configuration/manifest files are unchanged, and the registered collection remains unopened.
Synthetic disposable regression fixtures are not a prospective collection or research result.
This product SHA intentionally differs from Protocol V2's previously frozen runtime; that old SHA
does not represent this new workflow. Product stabilization needs a future independent freeze/protocol review.
No merge, PR, real response execution, or collection-opening action is part of this increment.

## Changed-file inventory

| Repository-relative file | Purpose |
| --- | --- |
| `docs/tier2-direct-escalation.md` | Workflow, atomicity, compatibility, research boundary and validation. |
| `hitl-ids/packages/detection/tier2_escalation.py` | Compound authenticated transaction and deterministic metadata. |
| `hitl-ids/packages/detection/routing.py` | Allow the existing routing command to participate without committing. |
| `hitl-ids/packages/detection/tier2_cases.py` | Allow existing case creation to participate and preserve logical retry payload. |
| `hitl-ids/apps/api/routing_routes.py` | Add endpoint and persisted case references to read views. |
| `hitl-ids/apps/api/contract/routing.py` | Add the compound response and nullable case reference. |
| `hitl-ids/apps/api/contract/openapi.py` | Declare the additive endpoint/request/response. |
| `hitl-ids/apps/api/openapi.json` | Regenerated OpenAPI artifact. |
| `hitl-ids/apps/web/src/api/schema.d.ts` | Regenerated frontend contract. |
| `hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.tsx` | Single command, explicit result actions and safe historical recovery. |
| `hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx` | Direct/manual approval, retry, non-navigation, display and recovery regressions. |
| `hitl-ids/tests/test_tier2_direct_escalation.py` | Atomicity, API, audit, authorization, concurrency and idempotency tests. |
| `hitl-ids/tests/test_api_contract.py` | Declare the new endpoint in the explicit API allowlist. |
| `hitl-ids/apps/web/playwright.direct.config.ts` | Synthetic routing browser suite on separate preview ports. |
| `hitl-ids/apps/web/e2e/direct-fixture.py` | Additional disposable data without consuming other journey fixtures. |
| `hitl-ids/apps/web/e2e/direct-escalation.spec.ts` | Complete single-action and both result-action journeys. |
| `hitl-ids/apps/web/e2e/routing-workflow.spec.ts` | Assert direct manual/policy escalation while preserving rejection. |
| `hitl-ids/apps/web/e2e/tier2-case.spec.ts` | Assert automatic creation and retained investigation behavior. |
| `hitl-ids/apps/web/e2e/response-approval.spec.ts` | Use direct creation and retain Approved — Not Executed regression. |
