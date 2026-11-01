# Unified Analyst Workstation

Base: `feat/analyst-workflow-consolidated` at
`0b8571aff696734240545e81ebee433be5481198`.
Implementation branch: `feat/unified-analyst-workstation`.

## Analyst experience

Previously, analysts saw both Legacy Flow Workstation and Alert Triage as
normal destinations. The primary experience is now **Analyst Workstation →
Tier 2 Cases**. Security Analyst login and the analyst index resolve to
`/analyst/operations`.

Primary navigation, in order:

1. Analyst Workstation
2. Tier 2 Cases
3. Triage Memory
4. Selective Review
5. Dashboard
6. Incoming Alerts (secondary intake)

Incoming Alerts retains its separate eligibility/admission workflow. Admin
and Evaluator navigation, home pages and authorization remain unchanged.

## Three-pane interaction

The existing compact SOC typography, colors, sidebar, dark/light themes and
queue/detail/context interaction pattern are retained.

* Left: `/api/v2/alerts`, server order, 50 records per page, title, detector,
  priority/band, review requirement, route and machine Tier 2 recommendation.
  Search explicitly filters the current page. Selection, pagination and
  search use URL parameters (`alertRef`, `offset`, `q`). `j`/`k` select alerts;
  `/` focuses search outside editable fields. A deep-linked alert can be
  read even when absent from the current queue page.
* Center: Overview, Evidence, Context & Review, Triage Memory, History &
  Notes and Technical tabs. Overview contains the human routing controls.
  Routing drafts, retry identities and success state survive tab changes.
  Context and memory reuse existing operational components. History shows
  the latest routing decision and links to case notes/timeline when a case
  exists. It does not invent a unified historical feedback/audit ledger.
* Right: review reasons, machine recommendation, trusted-field coverage,
  review disposition, memory guidance and support/conflict summaries.
  Summaries refresh every 15 seconds or explicitly. Full provenance and
  action forms remain in center tabs.

Desktop uses three columns. At 1024px the assistance rail follows the
queue/detail pair. At 390px queue, detail and assistance stack, with local
scrolling for dense queue/evidence content and horizontal scrolling tabs.

## Detector evidence

All evidence is taken from the immutable operational canonical snapshot:

* Suricata: rule/signature, category, endpoints, protocol and native
  severity. Missing confidence says **Not provided**. No fabricated ML or
  TreeSHAP panels appear.
* XGBoost: actual model/version, prediction and supplied confidence;
  TreeSHAP feature/value/contribution rows appear only when supplied.
* `current_flow`: explicitly **Legacy Flow Detector**, **Historical
  Signature Evidence**, **Historical XGBoost Evidence**, and supplied
  historical TreeSHAP. Historical ML probability remains separate from
  canonical confidence and operational priority.
* Other detector sources retain source-neutral provenance/network summary
  and their supplied structured evidence. Technical exposes the full
  immutable canonical snapshot.

Native severity/confidence never become a new operational priority score.

## Human escalation

1. Select an operational alert and inspect evidence, context and memory.
2. Admit to Tier 1 if the existing state requires that decision.
3. Enter an authenticated decision reason.
4. Choose **Escalate to Tier 2**, or **Approve Tier 2** when a policy
   recommendation is available. **Keep in Tier 1** rejects an applicable
   recommendation using the existing command.
5. Escalation calls the existing compound endpoint exactly once:
   `POST /api/v2/alerts/{alertRef}/tier2/escalate-case`.
6. Show **Escalated to Tier 2**, **Tier 2 Case created successfully.**, the
   case reference, **Open Tier 2 Case** and **Continue Reviewing**.

There is no visible candidate/manual-create step and no forced redirect.
Continue Reviewing stays in Workstation. Opening the case retains the
existing investigation, notes, findings and response approval experience.
An earlier incomplete escalation still has explicit recovery controls;
reads do not repair it automatically. Recommendation remains a machine
signal, distinct from the authenticated human action.

## Compatibility boundary

| Route | Behavior |
| --- | --- |
| `/analyst/operations` | Canonical operational Analyst Workstation/home |
| `/analyst/v2-triage?alertRef=…` | Same unified component, preserving selection |
| `/analyst/workstation` | Retained historical flow workstation, explicitly labeled, with a link to Analyst Workstation |
| `/analyst/tier2-cases/:caseRef` | Existing case investigation/response page |
| `/admin/v2-triage`, `/evaluator/v2-triage` | Existing role-specific triage page/permissions |

Historical queue, investigations, feedback impact, overview and old flow
Workstation routes remain accessible through **Advanced / Historical**.
They do not compete in primary navigation. Legacy **Escalation Recommended**
still submits feedback category `escalate` and uses historical score
behavior. Its explanation now points to Analyst Workstation for real
operational escalation. No routing API was connected to legacy feedback.

## Minimal additive API

Existing routing views did not provide complete canonical detector evidence.
The only runtime backend additions are:

* `RoutingView.detectorSource`, populated from the existing persisted source
  so queue labels can distinguish canonical legacy evidence.
* Authenticated `GET /api/v2/alerts/{alertRef}/evidence`, returning the existing
  `OperationalAlertV2` model through `read_projection` with `ReadConn` and
  `ReadPrincipal`. One read-only transaction; no migration, ingestion,
  materialization, scoring or mutation on GET.

Contract/OpenAPI/generated TypeScript and the explicit inspection inventory
are updated together. Tests check all read roles, missing/old schemas,
immutable data and authorization. No database schema, policy threshold,
ranking/order, detector algorithm, Tier 2 command, memory/review rule,
response behavior or collection state change is introduced.

## Validation and artifacts

Frontend: full Vitest suite, TypeScript build, generated schema freshness
check and production Vite build. Backend: API contract, read-only inspection,
authentication, routing, direct escalation, cases, memory, selective review
and Protocol V2 freeze regression tests.

Browser command (set `HITL_PYTHON` to a Python environment with project deps):

```text
node node_modules/@playwright/test/cli.js test --config playwright.unified.config.ts
```

This config uses ports 5181/8008 and `e2e/unified-fixture.py`, which creates a
fresh synthetic database. Its copy hook builds the fixture instead of
reading or mutating `data/demo.db`. No prospective collection suites run.
The primary UI escalation journey uses real frontend/backend requests.
Pure XGBoost visual validation explicitly substitutes read-only presentation
fixtures; it does not claim a new ML ingestion implementation or real
inference. Canonical legacy and Suricata evidence use actual fixture API
responses.

Screenshots are local ignored artifacts under `apps/web/test-results/`:

* `unified-desktop-dark.png`
* `unified-direct-success-0.png`, `unified-direct-success-1.png`
* `unified-suricata-{1440,1024,390}-{dark,light}.png`
* `unified-mobile-evidence-{dark,light}.png`
* `unified-mobile-context-{dark,light}.png`
* `unified-xgboost-presentation.png`
* `unified-legacy-canonical.png`

Visual review checks one obvious operational destination, the original
queue/detail/context interaction style, readable evidence, subtle historical
access, no page-width overflow, and usable light/dark responsive layouts.

Protocol V2 remains unchanged and unopened. This increment does not merge,
create a PR, or open a collection. Only the new feature branch is pushed.

## Recorded validation results

* Full frontend: **225 passed**, 30 files.
* TypeScript `tsc -b`: passed.
* Vite production build: passed; bundle size warning remains (no runtime error).
* OpenAPI document and generated TypeScript freshness: passed.
* Targeted backend inventory: **318 distinct tests passed** across API,
  authentication, routing/direct cases, memory/review, read-only and freeze
  runs. The new read endpoint was added to the explicit inspection inventory;
  its dependency/current/missing/old-schema checks then passed on recheck.
* Final isolated Chromium run: **16 passed** using
  `playwright.unified.config.ts`. Frontend unit tests finish before this run
  to avoid development-server dependency reloads during form entry.
* Inspected desktop three-pane, Suricata, XGBoost presentation, legacy
  canonical, direct success, 1024px and 390px dark/light captures. No document
  width overflow. At narrower widths the context rail intentionally stacks.
* `data/demo.db` is absent in this worktree and never opened by the fixture.
  Protocol/config/policy/service implementation files have no diff from base.

## Exact changed-file inventory

41 files, relative to the repository root:

```text
hitl-ids/apps/api/contract/openapi.py
hitl-ids/apps/api/contract/routing.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/api/routing_routes.py
hitl-ids/apps/web/e2e/analyst-refinement.spec.ts
hitl-ids/apps/web/e2e/detector-foundation.spec.ts
hitl-ids/apps/web/e2e/direct-escalation.spec.ts
hitl-ids/apps/web/e2e/external-admission.spec.ts
hitl-ids/apps/web/e2e/response-approval.spec.ts
hitl-ids/apps/web/e2e/routing-workflow.spec.ts
hitl-ids/apps/web/e2e/selective-review.spec.ts
hitl-ids/apps/web/e2e/tier2-case.spec.ts
hitl-ids/apps/web/e2e/triage-memory.spec.ts
hitl-ids/apps/web/e2e/unified-fixture.py
hitl-ids/apps/web/e2e/unified-workstation.spec.ts
hitl-ids/apps/web/playwright.unified.config.ts
hitl-ids/apps/web/src/App.tsx
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/components/layout/AppShell.tsx
hitl-ids/apps/web/src/features/alert/OperationalEvidence.tsx
hitl-ids/apps/web/src/features/feedback/FeedbackPanel.tsx
hitl-ids/apps/web/src/features/feedback/__tests__/feedback.test.tsx
hitl-ids/apps/web/src/features/feedback/categories.ts
hitl-ids/apps/web/src/index.css
hitl-ids/apps/web/src/pages/admin/__tests__/ipSecurityReport.test.tsx
hitl-ids/apps/web/src/pages/analyst/ExternalAdmissionPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/ExternalAdmissionPage.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.tsx
hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.tsx
hitl-ids/apps/web/src/pages/analyst/WorkstationPage.tsx
hitl-ids/apps/web/src/pages/analyst/__tests__/workstation.test.tsx
hitl-ids/apps/web/src/session/roles.test.ts
hitl-ids/apps/web/src/session/roles.ts
hitl-ids/apps/web/src/test/shell.test.tsx
hitl-ids/docs/unified-analyst-workstation.md
hitl-ids/tests/test_api_contract.py
hitl-ids/tests/test_inspection_readonly.py
hitl-ids/tests/test_operational_workstation.py
```
