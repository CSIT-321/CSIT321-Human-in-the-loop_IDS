# Tier 1 Analyst Verdict V1

Base: `4e3a54a17b9bd2c1d9c69c448e0224e689bb8ef1`.
Branch: `feat/analyst-verdict-v1`.

## Product semantics

Detection ≠ Classification ≠ Routing ≠ Verdict ≠ Tier 2 Finding.

- Detection is Suricata evidence, including the immutable native category/signature.
- Classification is the system's normalized attack type or explicit informational status.
- System Routing decides who handles the alert using existing priority and trusted context.
- Analyst Verdict is the canonical authenticated Tier 1 human conclusion.
- Tier 2 Investigation Finding remains the separate deeper investigation conclusion.

Examples: Brute Force classification + False Positive verdict is valid. Informational / Policy
Signal + Expected Activity verdict is valid. Tier 1 + Suspicious verdict stays Tier 1 until
the analyst separately uses Manual Escalation / Override. Confirmed Malicious alone does not
create a case. Unknown / Needs Expert already has its automatic Expert Tier 2 Case and does
not wait for Tier 1 Verdict. No Immediate Review is automation, never a human verdict.

The four outcomes are exactly `confirmed_malicious`, `suspicious`, `expected_activity`,
`false_positive`; labels are Confirmed Malicious, Suspicious, Expected Activity, False Positive.
There is no Benign or Unknown verdict.

## API, authorization and workflow

Authenticated endpoints:

- `GET /api/v2/alerts/{alertRef}/verdict`: latest verdict, revision, workflow state version and
  whether this caller may record. Initially latest is null and revision is 0.
- `GET /api/v2/alerts/{alertRef}/verdict-history?limit=50&offset=0`: newest-first immutable
  history, with total and paging metadata (limit 1–200).
- `POST /api/v2/alerts/{alertRef}/verdict`: requestId, expectedRevision,
  expectedStateVersion, outcome and nonblank reason (maximum 4,000 characters).

Actor identity is taken from the authenticated session and checked against an active user
inside the transaction. Security Analyst and System Admin can record/correct. Admin authority
follows the existing authenticated human routing and Triage Memory conventions; it is an
explicit equivalent human role, not system-policy attribution. Evaluator is read-only.
Caller-supplied actorId/decisionSource are rejected. `system_policy` cannot create a verdict.

Recording is permitted only for a current system-routed operational alert in
`tier1_review + triage`. This includes a deferred alert if an analyst elects to inspect it.
Historical-only records, dormant alerts and Tier 2 workflows cannot receive a new Tier 1
verdict. Once escalated, existing Verdict history remains readable; later investigation uses
Tier 2 Finding. No Tier 1 Verdict is required before automatic Tier 2 case creation.

## Storage, corrections and audit

Migration 16 adds only `analyst_verdict_events` and its append-only triggers/indexes. It does
not rebuild or rewrite existing tables. Foreign keys bind operational alert, actual user and
the superseded verdict. Each alert has unique increasing revision; requestId is unique across
this verdict ledger. Updates, deletes and replace-based overwrites are rejected by triggers.
Transaction failure rolls back the entire migration; repeated startup is a no-op.

Each event contains a server UUID, alert reference, actor ID and recorded display name,
literal analyst attribution, outcome, reason, server timestamp, revision, supersedes reference,
source state version and immutable source snapshot. The snapshot includes the canonical
detector evidence, normalized classification, original system-routing decision and current
triage state the analyst assessed. This is a dedicated human audit ledger, separate from
system-routing audit, legacy feedback, memory activation and Tier 2 findings.

A correction appends a new event pointing to the prior verdict. Latest means the greatest
revision; old entries remain unchanged. `BEGIN IMMEDIATE` serializes competing writers;
both expected revision and expected routing state version must match. A stale correction is
409. Exact actor/alert/body-bound request replay returns the original event without inserting
another or rewinding the latest verdict, including after subsequent escalation. Reusing a key
with different actor or payload is 409. Authorization is rechecked even on replay.

GET uses the existing read-only, non-migrating connections and consistent read transactions.
It does not create events or repair state. The explicit POST follows the existing writable
connection convention. Its business transaction inserts only the verdict ledger entry.

## Workstation

Overview exposes Analyst Verdict separately from System Routing and Manual Escalation.
The same mounted form is reachable through the Analyst Verdict tab after evidence/context
review, preserving drafts while switching tabs. Initial state says Not recorded. The form
has four options, required reason and explicit Record Verdict / Correct Verdict actions.
After save it shows current outcome, actual actor, timestamp, reason and revision. Retry
identity is retained after an uncertain failure. Conflict feedback offers explicit refresh.

History & Notes contains a distinct Analyst Verdict History section with latest/superseded
labels and paging. The assistance rail continues to explain attention/context; it does not
duplicate the editing form. Existing KPI strip and queue layout are unchanged.

## Temporary Triage Memory boundary

Verdict is the canonical human conclusion. The old Human Memory Outcome mechanism remains
functional compatibility input to Triage Memory, not an alias for Verdict. Saving Verdict
does not require recording another outcome, create memory, activate memory, or alter
Selective Review eligibility/disposition. The next feature will integrate Verdict evidence
into Memory and remove duplicate human outcome entry. This V1 intentionally does not add
that integration or any automatic verdict-driven learning, routing, scoring or response.

## Integrity and scope

Verdict alone does not modify detector evidence, classification, priority, routing, case
count/state, trusted facts, memory or effective review disposition. Tests compare all existing
business tables and the effective review disposition/version before and after every outcome.
Detection/capture correlation, V3 positive informational allowlist, specificity graph,
Unknown → automatic Tier 2 invariant, Critical policy and score formula are unchanged.
Ground-truth protections and the unavailable Suricata ML feature bridge remain intact.

No Analyst reclassification, Tier 2 assistance, new detection, new response automation,
Verdict→Memory integration or final independent freeze review is performed. Protocol V2 and
its artifact hashes remain unchanged/unopened; no operational prospective collection is opened.

Remaining limitations: corrections are available while Tier 1 review remains current; they
are not a Tier 2 finding editor. Existing historical-only records remain outside this new
canonical workflow. Verdict history is paginated; source snapshots intentionally duplicate
immutable evidence for reconstruction. Recording a verdict intentionally does not mark an
alert no-review or remove it from the current queue.

## Validation (2026-11-01)

- Backend coverage: 17 focused modules spanning Verdict, API/schema, migrations, raw-source
  preservation, routing/direct escalation/recovery, Selective Review, queue, Suricata/V3,
  read-only inspection and Protocol V2. The consolidated run had 583 passing checks and one
  unchanged optional-data skip; its only failure was the inspection inventory missing the
  newly added GET paths. Adding those paths also enabled six additional read-only cases.
  Final complete inspection + Verdict rerun: **152 passed** (45.51s), including the corrected
  inventory and the new missing-database/old-schema/current-schema assertions. No production
  implementation changed between these runs. Combined unique coverage is 590 passing cases
  and one optional skip; this is not a full repository backend run.
- Frontend full suite: **235 passed / 32 files** (22.18s). Final Verdict component rerun after
  test-only TypeScript matcher fixes: **3 passed**.
- TypeScript, OpenAPI freshness, generated schema freshness and production build passed.
  Contract: 74 paths / 79 operations / 148 schemas. Existing large-chunk advisory remains.
- Real disposable frontend/API Verdict journey: **1 passed** (18.4s), all five requested
  scenarios and 1440/1024/390 × Dark/Light; screenshots visually inspected.
- Accepted pre-freeze browser journey with Verdict installed: **1 passed** (22.0s), preserving
  effective review recall, queue counts, automatic Cases, old API blocking and capture isolation.
- Protocol V2 artifact hashes unchanged; collectionOpened=false. No demo database was created.
- git diff --check passed. Migration 16 has explicit populated-data preservation, rollback,
  repeated migration and FK tests; event immutability includes replace-based overwrite tests.

Existing schema/path inventories were extended for the new table, FKs and endpoints. Legacy
data snapshot helpers exclude the newly added human ledger, while dedicated Verdict tests
compare every pre-existing business table before/after each outcome. Migration 15's own
regression remains pinned to its original migration boundary. Existing assertions were not
removed to permit mutation of historical evidence.

## Exact changed files (repository-relative)

```text
hitl-ids/apps/api/contract/openapi.py
hitl-ids/apps/api/main.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/api/verdict_routes.py
hitl-ids/apps/web/e2e/analyst-verdict.spec.ts
hitl-ids/apps/web/playwright.verdict.config.ts
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/features/alert/AnalystVerdict.test.tsx
hitl-ids/apps/web/src/features/alert/AnalystVerdict.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.tsx
hitl-ids/docs/analyst-verdict-v1.md
hitl-ids/packages/contracts/analyst_verdict.sql
hitl-ids/packages/contracts/db.py
hitl-ids/packages/detection/analyst_verdict.py
hitl-ids/tests/test_analyst_verdict.py
hitl-ids/tests/test_api_contract.py
hitl-ids/tests/test_canonical_api.py
hitl-ids/tests/test_contracts.py
hitl-ids/tests/test_inspection_readonly.py
hitl-ids/tests/test_operational_v2.py
hitl-ids/tests/test_pre_freeze_review_fixes.py
hitl-ids/tests/test_triage.py
hitl-ids/tests/test_triage_policy.py
```
