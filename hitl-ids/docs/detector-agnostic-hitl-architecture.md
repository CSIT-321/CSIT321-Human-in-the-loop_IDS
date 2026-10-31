# Detector-agnostic HITL alert foundation

Original foundation base: feat/demo-build at 305c4d390ce9cd08bbc17f737053182a4ab61b7d.
Current stacked increment: `feat/suricata-operational-admission`, based on routing commit
`01ad4c9c4a145fa066f7c42c596b5e25e6869031`. Historical increment sections below retain their
original scope; this current-status section and suricata-operational-admission.md describe the latest boundary.

## Current external operational path

Suricata EVE -> immutable external staging -> explicit authenticated eligibility review
-> Operational Admission -> OperationalAlertV2 -> Triage Policy V1 -> Tier 1
-> existing human approval/manual escalation -> Tier 2 Candidate.

Implemented: Suricata adapter, external staging, OperationalAlertV2, Operational Triage Policy V1,
Authenticated Tier Routing Workflow, and Suricata Operational Admission.
Not implemented: live ingestion, Tier 2 Case management, Triage Memory, selective/no-immediate
review, automatic dismissal or SOAR/blocking.

All historical staging holds remain immutable. An additional append-only eligibility decision,
explicitly approved as part of this increment, distinguishes accepted from held source rows.
Only a current accepted decision can enter the atomic operational admission transaction.
Materialization, policy scoring, the existing Tier 1 routing action, and an admission event
commit together. Policy defers route mutation only in this private orchestration path;
standalone policy and routing callers retain their prior behavior.

See [Suricata Operational Admission](suricata-operational-admission.md) for authorization,
failure behavior, audit linkage, tests and the exact change manifest.
This document separates implemented behavior from future work. The older system-workflow.md
contains historical status statements; current code and HANDOVER.md take precedence.

## A. Current implemented architecture

1. pipeline/source.py strips labels from recorded CIC flows. CsvReplaySource supplies features.
2. signature/observable.py projects rule inputs; signature/engine.py evaluates enabled rules.
3. pipeline/predictor.py runs XGBoost or replays its output. ml/inference.py validates the trained
   feature schema and calculates native TreeSHAP contributions with an additivity check.
4. fusion/cef.py produces CEF evidence, immutable detection score, severity and review flag.
5. pipeline/runner.py applies existing family learning and inserts alerts plus 1:1 flow_data
   through pipeline/store.py. Detection run metadata and its audit event preserve provenance.
6. apps/api/routes.py and mappers.py produce queue and evidence panels; Workstation uses AlertPane.
7. feedback/service.py records the analyst verdict, invokes guardrail/policy.py, and applies
   feedback/learning.py to the exact-match family. AuditWriter records the result transactionally.
8. Admin IP Reports aggregate stored flows and alerts. Evaluation joins external truth by source
   record ID, runs the three arms, and measures operational queue changes.

### Detector-specific assumptions found

| Boundary | Current assumption retained |
|---|---|
| runner.py | At least one enabled rule, a predictor version and a dataset-backed run are required |
| source.py / ml/inference.py | CIC columns, model feature order and finite-value handling |
| models.py / schema.sql | Alert is a scored flow; confidence and flow ports are non-null |
| cef.py / Alert validators | Four CEF evidence classes, eight attack categories, signature/ML consistency |
| guardrail/policy.py | Signature override immunity and Infiltration-specific protection |
| feedback/learning.py | Exact category/port/protocol/rule families, destination for unflagged flows |
| ranking/severity.py | Configured class chart for existing learning weights |
| pipeline/store.py | Queue joins flow_data, CIC Timestamp, rule-ID search and CEF evidence filters |
| API panels / AlertPane | Signature and ML panels, legacy fused confidence, flow-specific details |
| Admin IP Reports | Flow endpoints and existing score/severity aggregation |
| evaluation | Source-record truth joins and complete-flow denominators, not alert-only recall |

These constraints are not silently relaxed. In particular, an external rule alert is not
misrepresented as signature_override (which would invoke the wrong guardrail), ml_only, or none.

## B. This increment

Detector output -> typed DetectorAdapter -> CanonicalAlert -> existing alert's detector snapshot.

The current runner creates the snapshot before learned placement can change operational severity.
The snapshot is stored in a nullable alerts.detector JSON column by migration 2. Existing alert
IDs, fields, queue ordering, API summary shape, feedback, guardrails and evaluator logic remain.
SQL triggers refuse snapshot updates, deletion and replacement of alerts carrying snapshots.
Contracts freeze nested evidence containers as well as scalar fields.

Legacy rows remain null on disk. Alert detail projects their original evidence on read, using
their own run's configuration to recover detection severity from detectionScore. It records
legacyProjection=true. For ml_only/none with an available prediction, legacy confidence is
recoverable because CEF copied it directly from the model. Corroboration/override confidence
may mix rule severity, so those legacy projections leave canonical confidence null.
confidenceBasis records the distinction.
The legacy fused confidence stays available as legacyFusionConfidence, not ML confidence.
Historical capture-local time is retained without inventing a UTC offset; timestampBasis
distinguishes it from the fallback detection-time timestamp.

occurredAt is validated ISO source text, preserved verbatim, including its separator, fractional
precision and any explicit offset. OpenAPI describes a patterned string, without format: date-time.
occurredAtTimezoneOffset is a nullable string: null for source-local time whose offset is unknown,
or the explicit source offset normalized as +/-HH:MM. A source Z yields +00:00 metadata while
the original Z stays in occurredAt. An explicit +0800 similarly yields +08:00 metadata.
No timezone is inferred and no timestamp is converted to UTC.

| Source occurredAt (unchanged) | occurredAtTimezoneOffset |
|---|---|
| 2018-02-14T12:28:54.334391 | null |
| 2018-02-14 12:28:54.334391 | null |
| 2026-10-29T15:30:10.123456+08:00 | +08:00 |

The current adapter uses the original capture text; only a missing capture timestamp falls back
to the already offset-aware detection time. Existing canonical JSON snapshots can be read without
the new metadata field: it is derived only from an offset explicitly present in their stored text.
The read does not rewrite that JSON or reinterpret any database timestamp. Explicit metadata
that contradicts the text is rejected. Operational created_at/updated_at, flow Timestamp and
queue sorting are unaffected.

### Canonical contract

| Fields | Meaning |
|---|---|
| canonicalAlertId, occurredAt | Existing UUID for current alerts; validated original timestamp string |
| occurredAtTimezoneOffset | Explicit source offset as +/-HH:MM, or null when unknown |
| detectorSource, detectorName, detectorVersion | Source and version; unavailable version is null |
| detectionTitle, detectionCategory | Detector-native signature/model description and category |
| detectorSeverity | Native severity value/scale, separate from probability |
| confidence | Optional numeric probability; null means not supplied or not recoverable |
| sourceIp, destinationIp, sourcePort, destinationPort, protocol | Network endpoints; ports may be null |
| evidenceClass | Native evidence kind; current CEF values retained, EVE uses external_signature |
| structuredEvidence | Checkable detector facts, not operational state |
| provenance | Adapter version, sensor/model/rule versions and timestamp basis |
| sourceRecordReference | Dataset record ID or caller-supplied immutable EVE record reference |
| originalDetectorFields | Immutable original detector facts; recursively rejects truth metadata |

CurrentDetectorAdapter preserves detectionScore, CEF evidence, rule matches/conditions, XGBoost
prediction, malicious probability and TreeSHAP. Canonical confidence is the original prediction's
modelConfidence, never the operational score or rule-severity proxy. The original legacy fusion
confidence is separately retained. Existing legacy confidence fields remain backward compatible.

SuricataEveAdapter accepts committed synthetic fixtures only in this increment. It validates
alert event type, offset-aware timestamp, IPs, protocol and required signature fields. Ports,
flow ID, action, metadata and engine version may be absent. Safe extensions are retained in the
original snapshot. Known truth keys are rejected recursively even inside unknown extensions.
It maps timestamp, endpoints, proto, flow_id, signature, signature_id, category, severity, action
and rule metadata. UUID5 uses the deterministic UTF-8 JSON encoding of
["suricata", sensor_id, raw_event_reference] as its NAMESPACE_URL name. Serialization uses
ensure_ascii=False and separators=(",", ":"); no repr(), unordered dictionaries, delimiter
concatenation or Unicode normalization is involved. Thus ["suricata","a","b:c"] and
["suricata","a:b","c"] remain distinct, including for Unicode/delimiter-containing inputs.
Suricata fixture IDs change from the original foundation algorithm, but remain deterministic.
Suricata has no operational admission/storage path, so no operational alert ID migration is needed.
Callers must supply a stable, unique per-record reference (for example immutable file ID + line).
Reusing that reference for a different event is a caller error; no ingestion/dedup service exists.

Suricata severity is not ML confidence. Even rule metadata named confidence (such as High) does
not become a probability: confidence remains null. Missing required fields raise validation errors.
See the [official EVE format](https://docs.suricata.io/en/suricata-7.0.14/output/eve/eve-json-format.html).

### Separate concepts

| Concept | Responsibility |
|---|---|
| Detector severity | Detector-native assessment, frozen in snapshot |
| Optional detector confidence | Supplied probability, never synthesized from severity |
| Immutable detector evidence | Original signature/ML/SHAP or EVE facts |
| Detector provenance | Source, versions and record reference, auditable with the run/alert |
| Evidence class | What evidence exists, not how urgently the analyst should act |
| Operational priority | Existing combined score and severity-first ordering, mutable through feedback |
| Human review need | Existing requiresReview flag; no selective-review automation added |
| Analyst verdict | Existing human judgment and note, append-only history |
| Future triage memory / lesson | Future policy/knowledge layer; not today's exact-family learning |
| Incident / notification / response output | Future downstream output, not a detector fact |

UI changes are confined to alert detail and Workstation: source, name/version, signature/model,
native severity, and confidence or Not provided. No queue/ranking/filter/navigation changes.

### Compatibility and limits

- Migration 2 is additive and versioned; old rows, feedback, audit and IDs survive. Concurrent
  first-use requests recheck the version under a write lock. Fresh databases and existing
  version-1 databases reach the same schema.
- Existing API fields are neither removed nor renamed. AlertDetail.detector is additive/nullable.
- No ground truth enters the snapshot; evaluator labels remain outside analyst contracts.
- No weighted cross-detector score is introduced.
- Suricata adaptation is fixture-only. Its canonical envelope is not inserted into the legacy
  CEF queue. External queue admission requires an explicit reviewed triage policy next.
- Current Signature Engine, XGBoost and TreeSHAP remain active and unchanged.
- The existing five missing-data fixture skips are not converted into passing simulations.

## C. Future architecture

Suricata may be an external alert source. It cannot replace CICFlowMeter for the current XGBoost
path: that model requires the CIC feature schema used in training. Other anomaly/detector adapters
can supply their native evidence through the same envelope without claiming ML probabilities.
Different detector evidence must not be collapsed into an arbitrary weighted score.

The next increment should define and test external-alert admission and detector-specific triage
policy: taxonomy, native-severity interpretation, family isolation, missing ports, duplicate event
identity and evaluation denominators. Keep those policies outside feedback/audit/UI mechanisms.
Then prove a fixture alert through persistence, investigation, feedback and IP reports before
adding any live source. Alert-only EVE data cannot inherit a complete-flow recall denominator.

Live traffic capture, Suricata process management, anomaly detection, triage memory, selective
review, automatic dismissal/closure, blocking, SOAR, notifications, PostgreSQL and console redesign
are outside this increment.

## Verification and change manifest

Verified on 2026-10-30:

| Check | Base | Increment |
|---|---|---|
| Python full suite | 461 passed, 5 fixture skips | 493 passed, same 5 skips |
| Frontend full suite | 157 passed | 160 passed, 21 files |
| TypeScript | Pass | Pass |
| Python OpenAPI / frontend schema checks | Pass | Pass |
| Vite production build | Pass | Pass; existing large-chunk warning |
| Browser smoke | Not re-baselined | 3 pass: analyst provenance/verdict tab, loaded Admin IP report, evaluator metrics |

The 32 additional Python cases cover adapters, null confidence, native severity, evidence
immutability, leakage rejection, record identity, legacy projection, feedback persistence and
concurrent migration. Existing feedback/guardrail/learning/queue/audit/IP-report/evaluation
regressions all run in the full suite. Browser smoke is not the full historical demo narrative.

The existing .venv on this machine is Python 3.12.14, despite older handover instructions.
Verification used installed Python 3.11.9 through an ignored
.pytest-tmp/python311/.venv environment with system-site-packages and local bcrypt/PyJWT.
The original .venv was preserved. Bundled Node ran the existing package-script command bodies.
Because npx is absent, browser smoke used an ignored test-results/foundation.config.ts override
to invoke Vite with Node directly; the committed Playwright configuration is unchanged.
Browser servers used disposable database copies and were stopped by Playwright afterward.

Original foundation commit's changed files, relative to hitl-ids/:

- docs/detector-agnostic-hitl-architecture.md
- packages/contracts/canonical.py
- packages/contracts/models.py
- packages/contracts/db.py
- packages/detection/adapters/__init__.py
- packages/detection/adapters/current.py
- packages/detection/adapters/suricata.py
- packages/detection/pipeline/runner.py
- packages/detection/pipeline/store.py
- apps/api/contract/alerts.py
- apps/api/routes.py
- apps/api/openapi.json
- apps/web/src/api/schema.d.ts
- apps/web/src/features/alert/DetectorProvenance.tsx
- apps/web/src/features/alert/DetectorProvenance.test.tsx
- apps/web/src/features/workstation/AlertPane.tsx
- apps/web/src/pages/analyst/AlertDetailPage.tsx
- apps/web/src/pages/analyst/__tests__/fixtures.ts
- apps/web/e2e/detector-foundation.spec.ts
- tests/fixtures/suricata-alerts.json
- tests/test_detector_adapters.py
- tests/test_canonical_api.py
- tests/test_contracts.py
- tests/test_triage.py

## Final-review corrections

The focused follow-up to 52f10f77b9997241c66b6711f058954118b311e7 corrects timestamp
representation and Suricata identity only. It also strengthens the committed migration test:
a populated legacy alert with signature/SHAP evidence, adjusted score, owner, review flag, family
key, queue state, flow timestamp, feedback and audit survives migration 2 unchanged. The new
detector column is null and repeated migration is a no-op. Migration implementation is unchanged.

Follow-up verification (Python 3.11.9): targeted contract/adapter/migration/API checks
172 passed / 1 existing fixture skip; full Python 521 passed / the same 5 fixture skips;
frontend 160 passed; TypeScript, both schema checks and Vite build passed; all 3
Analyst/Admin/Evaluator browser smoke paths passed. The original chunk-size and jsdom warnings
remain. No runtime UI changes were required because the provenance timestamp remains text.

Fix files, relative to hitl-ids/:

- packages/contracts/canonical.py
- packages/detection/adapters/current.py
- packages/detection/adapters/suricata.py
- apps/api/openapi.json
- apps/web/src/api/schema.d.ts
- apps/web/src/features/alert/DetectorProvenance.test.tsx
- tests/test_detector_timestamp_identity.py
- tests/test_canonical_api.py
- docs/detector-agnostic-hitl-architecture.md

## Offline Suricata staging increment

Base: `f1b44d063d0fde50d86f509d8969a68a9b6a80ae`.
Branch: `feat/suricata-admission-staging`.

The implemented boundary is:

`EVE JSON/JSONL -> existing Suricata adapter -> canonical alert -> admission policy -> external_alert_inbox`

**Operational admission: pending.** Staged evidence has no operational alert ID, feedback,
family membership, evaluator denominator entry, Workstation row, or Admin IP report entry.
Inspection is CLI-only; no API contract or frontend changes are needed.

### Why Alert Contract V2 is required

The proposed core-table rebuild was rejected by automatic approval review, and that rejection
was accepted. Disabling foreign keys and reconstructing core tables exceeded the strictly
additive requirement and risked existing evidence and linked records. No such migration ran.

The existing schema is intentionally specialised:

- `alerts.confidence` is NOT NULL; Suricata has no model probability.
- Evidence classes describe Signature/XGBoost agreement, not external rules.
- Queue classes reuse those legacy meanings and promotion rules.
- `dataset_id` and `run_id` are mandatory, tied to current detection runs.
- `flow_data` requires CIC-oriented ports, duration and counters that EVE may omit.
- `feedback_events` references legacy alerts.
- Family learning uses current attack classes, rule fields and flow context.

A separately reviewed Alert Contract V2 must define source-neutral identity, nullable confidence
and observations, detector-native severity, operational priority, evidence and run provenance,
feedback references, explicit source-isolated learning eligibility, evaluation eligibility,
and a backward-compatible API/UI transition. It must define migration and rollback safety before
any operational admission. Fake model values or reusing an inaccurate evidence class are not an
acceptable bridge. V2 is not implemented in this increment.

### Policy and inbox

The original standalone policy and its 19 tests are retained. `config/external-admission.json`
maps native priorities 1/2/3/4 to proposed scores 85/65/40/20. This gives higher rule priorities
higher proposed review urgency on the current 0-100 scale; it is a configurable operational
proposal, not calibrated maliciousness probability. Unmapped severities are rejected.
Confidence stays null. Review is mandatory; learning and evaluation eligibility are false.
The proposed evidence type is `external_rule`; the canonical snapshot keeps `external_signature`.

Migration 3 only creates `external_alert_inbox` and three immutability triggers. It uses the
existing transactional, version-checked migration runner and leaves foreign keys enabled.
There is no foreign key to `alerts`, no core ALTER/DROP, and no core-row backfill. The unique
canonical identity index serves duplicate lookup; CLI listing uses the integer primary key,
so no additional secondary indexes are justified yet.

The inbox stores canonical identity, source/sensor/reference, exact timestamp and nullable offset,
native severity, nullable confidence and ports, title/category, addresses/protocol, complete
canonical JSON, full policy JSON/version, proposed score/evidence, review and eligibility flags,
decision/reason, import status and import time. All columns are immutable. UPDATE, DELETE and
replacement INSERT are rejected, including replacement on a plain SQLite connection with
recursive triggers disabled. Policy changes never rewrite a previously staged decision.

Accepted events are stored as `staged` / `hold_for_review`, with the pending V2 reason. Duplicate,
skipped, invalid and policy-rejected events are reported, not stored as incomplete inbox rows.
This preserves uniqueness and prevents invalid or ground-truth-bearing evidence being persisted.

### Commands and import semantics

Run from `hitl-ids` using an existing project database (use a disposable database for rehearsal):

```powershell
python scripts/import_suricata_eve.py --input tests/fixtures/suricata-alerts.json --sensor-id lab-a --database <existing-database>
python scripts/import_suricata_eve.py --input <eve.jsonl> --sensor-id lab-a --database <existing-database> --dry-run
python scripts/import_suricata_eve.py --database <existing-database> --list --limit 50
```

`--policy <json>` selects a validated policy. No database is created by a misspelled path.
Dry-run works with a missing database without creating it; existing databases are opened read-only
and are not migrated. Its `staged` count means would-stage. Listing is also read-only, including
against an older database without an inbox.

Identity uses the adapter's unambiguous JSON-encoded sensor/reference tuple. The importer supplies
`eve-sha256:<digest>` over sorted, compact event JSON. Moving/reformatting/reordering a file does
not change identities. Identical event objects from one sensor deliberately collapse; different
sensors remain separate. Changing any event content creates a new identity. This is content-based
replay deduplication, not semantic flow deduplication; V2 may need an explicit upstream event ID.

Output reports `parsed`, `staged`, `duplicate`, `skipped`, `invalid`, `rejected_by_policy` and
per-record reasons. `parsed` counts successfully decoded JSON records, including unsupported or
invalid-shaped ones; malformed JSON contributes only to `invalid`. Unsupported non-alert events
are skipped. Known ground-truth keys are rejected recursively by the existing adapter. Duplicate
JSON keys and non-finite JSON values are rejected. Raw validation input is not echoed in errors.

Import uses one write transaction and checks duplicates under its write lock. Invalid records do
not partially write rows; valid records in a mixed file can still be staged. Infrastructure errors
roll back the entire staging batch. Exit status is 0 for clean/duplicate/skipped results, 2 when
invalid or policy-rejected records occurred, and 1 for infrastructure/input-file errors.
Files are read into memory; bounded streaming and import-attempt audit history are future work.

### Verification boundary

Tests compare all existing operational table values before/after staging, and populated v2 schema
root pages/SQL before/after migration. They cover migration idempotence/concurrency, enabled foreign
keys, immutable evidence, concurrent/idempotent imports, dry-run byte preservation, invalid input,
rollback, CLI inspection, queue/detail/feedback isolation, evaluator inputs and Admin IP reports.
Tests use temporary databases only. Existing canonical identity regression tests remain in place.
No live capture, process management, operational admission or automated response is introduced.

Verified on Python 3.11.9: 57 targeted checks passed; full Python 551 passed with the same five
missing-fixture skips; frontend 160 passed across 21 files; TypeScript, Python OpenAPI check,
generated frontend schema check and Vite production build passed; all three Analyst/Admin IP
Report/Evaluator browser smoke paths passed. Existing jsdom navigation and Vite chunk-size
warnings remain non-failing. The browser used a disposable copy of the demo database.

Exact staging increment file manifest (relative to `hitl-ids/`):

- config/external-admission.json
- docs/detector-agnostic-hitl-architecture.md
- packages/contracts/db.py
- packages/contracts/external_inbox.sql
- packages/detection/adapters/admission_policy.py
- packages/detection/adapters/staging.py
- scripts/import_suricata_eve.py
- tests/test_canonical_api.py
- tests/test_contracts.py
- tests/test_external_admission_policy.py
- tests/test_external_staging.py
- tests/test_triage.py

## Operational Alert Contract V2 foundation

### Architecture status

| Status | Capability |
|---|---|
| IMPLEMENTED before this increment | Canonical detector foundation; offline Suricata staging |
| THIS INCREMENT | Source-neutral OperationalAlertV2; separate OperationalTriageStateV2; additive persistence; pure projection and read-only inspection |
| NEXT, not active | Operational triage policy; Tier 1 routing; Tier 2 candidate recommendations; Tier 2 Case workflow |
| FUTURE, not implemented | Triage memory; selective human review; evidence-gated automation; notifications/SOAR; live ingestion |

The legacy path remains authoritative and unchanged:
`Signature + XGBoost -> alerts -> Workstation -> feedback -> guardrails`.

V2 is a separate, opt-in foundation:
`legacy alert + canonical snapshot OR staged external alert -> immutable operational_alerts_v2`
with `operational_triage_state_v2` holding only independent workflow state. No importer, detection
runner, API request or migration automatically materializes V2 records. No V2 record enters the
existing queue, feedback foreign keys, family learning, evaluation denominator or Admin IP reports.

The old learning architecture remains the running implementation:
`human verdict -> numeric adjustment -> similar family -> queue re-ranking`.
The target, not yet implemented, is:
`human verdict + reason/context -> triage lesson -> evidence gate -> future review/routing decision`.

### Contracts and source mappings

OperationalAlertV2 exposes camelCase aliases with strict extra-field rejection and frozen models:

- Identity: `id`, `operationalAlertRef`, `canonicalAlertId`. The operational reference preserves
  the canonical UUID, including the original legacy alert reference; its database ID is separate.
- Source: `sourceKind`, `detectorSource`, `detectorName`, `detectorVersion`, nullable
  `legacyAlertId` / `externalInboxId`. Exactly one reference must match the source kind.
- Detection: `detectionTitle`, `detectionCategory`, `nativeSeverity`, nullable `detectorConfidence`,
  `detectorEvidence`, `occurredAt`, nullable `occurredAtTimezoneOffset`.
- Network: `sourceIp`, `destinationIp`, nullable ports, `protocol`.
- `sourceProvenance`: a typed legacy or external record; it is immutable and carries no mutable
  routing decision. The full canonical envelope is nested unchanged in `detectorEvidence`.

The legacy projection preserves the canonical detector confidence without inferring it from
the fused confidence. Both remain available: `detectorConfidence` is canonical confidence and
`sourceProvenance.legacyFusionConfidence` preserves `alerts.confidence`. This distinction matters
for corroborated/override legacy snapshots where pure ML confidence cannot be recovered.
Signature rules, XGBoost probability/prediction and TreeSHAP remain in canonical structured
evidence and original fields. Immutable detection score, dataset/run IDs and original reference
are recorded in legacy source provenance. Current operational score/queue class are not reinterpreted
as V2 state. For an old null canonical snapshot, the existing read-only adapter projects original
detector severity from the alert's own detection run; nothing is backfilled to `alerts`.

The external projection verifies inbox columns against the stored canonical snapshot. It preserves
source, canonical UUID, signature title/category, native severity, null confidence, nullable ports,
exact timestamp/offset and all canonical evidence. Source provenance records sensor/reference,
admission policy version/decision/reason, proposed score/evidence and review/eligibility flags.
The referenced immutable inbox retains the complete original policy snapshot.

### Triage and priority boundary

OperationalTriageStateV2 contains `operationalAlertId`, nullable `operationalPriority` and
`priorityBand`, `handlingRoute`, `workflowStage`, `reviewRequired`, `reviewReason`,
`tier2Recommended`, `tier2RecommendationReasons`, `decisionSource`, nullable `triagePolicyVersion`
and `updatedAt`. Priority and band must be assigned together; recommendations must have reasons.

| Concept | Meaning | Initial V2 behavior |
|---|---|---|
| Native severity | How bad could it be, on this detector's scale? | Preserved without conversion |
| Detector confidence | How certain is the detector? | Preserved; null when absent |
| Operational priority | How urgently should the SOC handle it? | Null, with null band |
| Handling route/tier | Who should handle it? | `unassigned` |
| Workflow stage | Where is it in the response lifecycle? | `staged` |

All new V2 triage rows require review with a pending-policy reason, have no Tier 2 recommendation,
and have null triage policy version. Legacy projections identify `decisionSource=legacy_projection`;
external projections use `system_policy` for the dormant initialization only. This does not copy
or override the legacy review flag. Enum support includes future routes/stages/decision sources,
but no policy automatically selects any tier. Explicit test-only triage updates demonstrate that
changing priority does not change route or detector evidence.

Suricata's 85/65/40/20 values remain **proposed priority provenance only**, never effective priority.
Neither severity nor priority triggers Tier 2. New Python DTOs remain frozen values; the separate
triage database row can be updated independently. There is no triage mutation API in this increment.

### Persistence and migration safety

Migration 4 creates only `operational_alerts_v2`, `operational_triage_state_v2` and their triggers.
It uses the existing BEGIN IMMEDIATE/version-check runner. Foreign keys remain enabled; no ALTER,
DROP, rebuild, constraint loosening or automatic backfill occurs. Original row values and schema
root pages/SQL are tested for equality across a populated v3-to-v4 migration.

The evidence table has UNIQUE operational/canonical references and UNIQUE nullable source IDs.
CHECK constraints enforce the exclusive source-kind/reference relationship and null Suricata
confidence. Foreign keys reference legacy alerts or inbox rows; triage references only V2.
Native severity uses JSON scalar text in SQLite to preserve integer vs string representation.
Canonical evidence/source provenance are valid JSON; identity/source/confidence/severity are
checked against that evidence. Contract validation additionally checks all duplicated display
fields against the canonical envelope. Primary/unique indexes cover current lookups; no speculative
secondary indexes are added.

All evidence-table UPDATE/DELETE/replacement INSERT operations fail. Triage updates do not touch
that table, and its identity cannot be reassigned. `materialize_source` reads the source and checks
duplicates under one write lock, then inserts evidence and dormant triage atomically. Repetition
returns the existing record without resetting triage; conflicting projections fail clearly.
An infrastructure failure rolls back both inserts. The caller must migrate first. This service
is not invoked by existing application flows and does not create any feedback/audit/family rows.

### Read-only inspection

From `hitl-ids`, using an existing database:

```powershell
python scripts/inspect_alert_v2.py --database <database> --legacy-alert-id 1
python scripts/inspect_alert_v2.py --database <database> --external-inbox-id 1
python scripts/inspect_alert_v2.py --database <database> --operational-alert-id 1
```

The first two preview a source without persistence (`id` and `triage` are null); the third reads
an explicitly materialized V2 record and its triage state. The CLI opens SQLite read-only, does
not migrate and states `operationalAdmission=pending`, `routingPolicy=inactive`. No Workstation
API or UI is replaced. Local SQLite access is required; an admin endpoint is intentionally absent.

### Limitations and next increment

This is a schema/projection foundation, not an active SOC workflow. Source snapshots are not
continuously synchronized, and legacy operational feedback is not mirrored into V2. Source IDs
are database-local; projection across unrelated databases needs a separately reviewed identity
strategy. There is no V2 triage update/audit service, permission layer, policy activation or case UI.
The next increment should review an explicit operational triage policy and authenticated/audited
transition service, including evidence requirements for route recommendations and compatibility
tests, before connecting V2 to any analyst workflow.

### V2 verification

The stacked base was verified before branching: Python 551 passed / 5 existing fixture skips,
frontend 160 passed, TypeScript, both schema checks, Vite and 3 browser smoke tests passed.
V2 targeted verification: 127 passed / 1 existing fixture skip. Final full verification on Python
3.11.9: 577 passed / the same 5 fixture skips; frontend 160 passed across 21 files; TypeScript,
Python OpenAPI check, generated TypeScript schema check and Vite build passed. Analyst, Admin IP
Report and Evaluator browser smoke: 3 passed using a disposable database on separate ports.
Existing jsdom navigation and Vite chunk-size warnings remain non-failing.

The 26 new V2 test cases cover legacy/external projections, canonical confidence vs fused
confidence, timestamp/null preservation, invalid references and mismatched evidence, dormant
defaults, immutable evidence, mutable independent triage, atomic rollback, concurrent idempotent
projection, populated v3 migration preservation, unchanged queue/evaluation/staging behavior,
and byte-preserving read-only CLI inspection. Existing concurrent migration tests now cover v4.

Exact V2 increment manifest (relative to `hitl-ids/`; staging-base files are not reintroduced):

- docs/detector-agnostic-hitl-architecture.md
- packages/contracts/db.py
- packages/contracts/operational_v2.py
- packages/contracts/operational_v2.sql
- packages/detection/adapters/operational_v2.py
- scripts/inspect_alert_v2.py
- tests/test_canonical_api.py
- tests/test_contracts.py
- tests/test_external_staging.py
- tests/test_operational_v2.py
- tests/test_triage.py

## Operational Triage Policy V1

This increment implements pure V2 triage calculation and explicitly invoked, audited application
to V2 triage state. It does not connect Suricata/V2 records to the legacy Workstation queue.
The existing detector, staging importer, feedback categories, guardrails, family learning,
operational scores, queue ordering, evaluation and Admin IP reports remain unchanged.

### Versioned priority and context rules

Policy version: `operational-triage-v1`, stored in `config/operational-triage-v1.json`.

| Suricata native severity | Base urgency | Band with no additional context |
|---|---:|---|
| 1 | 85 | P1 |
| 2 | 65 | P2 |
| 3 | 40 | P3 |
| 4 | 20 | P4 |

Configured band minima are P1=80, P2=60, P3=30, P4=0. Decimal scores use half-open ranges:
P4 [0,30), P3 [30,60), P2 [60,80), P1 [80,100]. Priority is bounded at 100.
Native severity is not confidence; operational priority is not attack probability; priority is not
Tier. Detector confidence is never used in this calculation and null confidence remains valid.
For explicit legacy V2 projection experiments, the immutable detection score supplies the base;
the current legacy combined score is neither read as a baseline nor changed by the policy.

Optional `TriageContext` fields are `assetCriticality` (low/medium/high/critical),
`repeatedCampaign`, `correlatedAlertCount`, `responseRequired`, `knownMaliciousIndicator`,
`analystEscalated`, `unresolvedByTier1`, and `evidenceConflict`. `confirmedMalicious` is an additional
explicit nullable boolean: a known indicator must not silently become confirmation of this alert.
Every field defaults to null, meaning unknown/not available, and remains null in audit snapshots.
Booleans are strict, counts are nonnegative integers, and invalid/extra fields are rejected.
Context is a complete supplied snapshot, not a patch or a learned memory. No context is fabricated
from detector confidence, severity, prior feedback or absent values.

Configured adjustments, applied in this deterministic order, are +10 for explicitly critical
assets, +10 for an explicitly known malicious indicator and +5 for explicitly conflicting evidence.
Each records requested/applied delta and reason, including clipping at 100. Missing/false context
does not trigger an adjustment. These are initial configurable operational rules, not statistically
calibrated risk estimates or organisationally validated thresholds. Configuration changes after
an applied version require a new version identifier; full config snapshots are preserved.

### Recommendation versus transition

V1 always outputs `reviewRequired=true`, `handlingRoute=tier1_review`, `workflowStage=triage`,
and `decisionSource=system_policy`. High priority alone never recommends or routes to Tier 2.
Tier 2 is recommended only for explicit conditions:

- `analystEscalated=true`.
- `confirmedMalicious=true` AND `responseRequired=true`.
- Final priority at least the configured high threshold (80) AND `assetCriticality=critical`.
- `repeatedCampaign=true` AND correlated alert count at least the configured threshold (3).
- `unresolvedByTier1=true`.

Each satisfied condition contributes its own reason. Recommendation never changes the output route
to `tier2_candidate` or `tier2_case`. Conflicting evidence always gets review and an explained
adjustment, but is not by itself a Tier 2 condition. Unknown-context fields are explicitly named
in review reasons. A future approved transition service must separately accept recommendations.

`TriagePolicyResult` returns `basePriority`, `basePriorityReason`, `contextAdjustments`,
`finalOperationalPriority`, `priorityBand`, `reviewRequired`, `reviewReasons`, `handlingRoute`,
`workflowStage`, `tier2Recommended`, `tier2RecommendationReasons`, `decisionSource` and `policyVersion`.
Base mapping, final band selection, all adjustments and all recommendations are explained.

### Additive storage compatibility

The V2 table from the preceding increment constrains `priority_band` to named labels. Migration 5
does not rebuild that table or loosen the constraint. It adds `priority_band_scheme`, defaulting
to `legacy_labels`, and creates `operational_triage_policy_audit` plus append-only triggers.
Existing rows retain their old values and interpretation. No legacy table is altered.

Policy-applied states use scheme `p1_p4`. The storage codec reversibly encodes P1/P2/P3/P4 as
critical/high/medium/low in the existing constrained column, and `read_triage` decodes them back
to P1/P2/P3/P4. This is an explicit storage encoding, not a detector-severity conversion.
Contract validation rejects a band inconsistent with its scheme. Earlier `legacy_labels` states
still read as critical/high/medium/low/informational. All before/after policy audit states use the
public band plus explicit scheme. No current operational alert score or band is touched.

The existing migration runner retains its write lock/version recheck, idempotence, rollback and
enabled foreign keys. Populated v4 migration tests prove original triage values and root page are
preserved, original core rows remain equal and foreign-key checks pass. Earlier migration tests
allow only this specific additive V2 column alteration, while continuing to reject DROP/rebuild,
legacy alterations and foreign-key disabling.

### Mutation and audit boundary

`apply_triage_policy` is an explicit trusted-local service, not a network endpoint or automatic
import hook. It verifies that the supplied actor is an active analyst or administrator. Any future
API must bind actor identity to its authenticated principal; an actor ID alone is not remote
authentication. No unauthenticated mutation endpoint is added.

Under BEGIN IMMEDIATE, the service reads immutable V2 evidence, calculates the result, compares
the supplied expected state and atomically updates only V2 triage plus a new audit entry.
Each entry stores actor/V2 identity, policy version/full configuration, complete nullable context,
full explained result, before state, after state and UTC time. UPDATE, DELETE and replacement
INSERT of audit entries are rejected. Audit-write failure rolls back the triage update.

An identical retry returns the previous audit ID without changing time or adding an entry, only
when the full current state still equals that audited result. A changed context/configuration
requires fresh expected state. Concurrent conflicting requests therefore leave one applied and
one stale. Versions cannot be reused with different configuration snapshots in that database.
UTC normalization and monotonically increasing application timestamps avoid timezone-induced
retry mismatches. Policy application refuses to overwrite analyst decisions or advanced routes/
workflow stages. Context changes can recompute recommendations, but always retain human review;
there is no automatic dismissal, case creation or candidate transition.

### Inspection and current limitations

From `hitl-ids`:

```powershell
python scripts/preview_triage_policy.py --database <database> --operational-alert-id 1
python scripts/preview_triage_policy.py --database <database> --operational-alert-id 1 --context <context.json>
python scripts/inspect_alert_v2.py --database <database> --operational-alert-id 1
```

Preview opens the database read-only and reports `preview_only`; optional `--policy` chooses a
validated versioned configuration. Existing V2 inspection reports the stored route/band/reasons
and whether policy has been applied. Neither CLI mutates state or admits records to Workstation.
Tests use disposable databases, and no committed demo database is modified.

Context currently comes from a trusted caller; asset inventory, indicator verification and campaign
correlation integrations are absent. The local role check is not a substitute for a future API
authentication boundary. There is no mutation UI/API, Tier 2 Case, triage memory, Suricata feedback
learning, no-review automation, live ingestion, notifications, SOAR, blocking or anomaly detection.
The recommended next increment is an authenticated, audited, explicitly approved V2 transition
service that distinguishes accepting a recommendation from creating a Tier 2 case, before any
separately reviewed operational queue integration.

Exact policy increment manifest (relative to `hitl-ids/`):

- config/operational-triage-v1.json
- docs/detector-agnostic-hitl-architecture.md
- packages/contracts/db.py
- packages/contracts/operational_v2.py
- packages/contracts/triage_policy_v1.sql
- packages/detection/adapters/operational_v2.py
- packages/detection/triage_policy.py
- packages/detection/triage_policy_service.py
- scripts/inspect_alert_v2.py
- scripts/preview_triage_policy.py
- tests/test_canonical_api.py
- tests/test_contracts.py
- tests/test_external_staging.py
- tests/test_operational_v2.py
- tests/test_triage.py
- tests/test_triage_policy.py

Verification on Python 3.11.9: targeted policy/V2/migration/regression suite 168 passed with one
existing fixture skip; full Python 618 passed with the same five fixture skips; frontend 160
passed across 21 files; TypeScript, Python OpenAPI check, generated schema check and Vite build
passed. Analyst/Admin IP Report/Evaluator browser smoke: 3 passed against a disposable database.
The 41 new policy tests cover baseline mappings and band boundaries, explicit/unknown context,
confidence independence, adjustments/clipping/reasons, recommendation without transition,
role/stale-state protection, identical retries, version reuse refusal, atomic rollback,
append-only audit, concurrent writers, read-only preview, migration compatibility and legacy
queue/feedback/evaluation/staging isolation. Existing jsdom navigation and Vite chunk-size
warnings remain non-failing. No committed demo database or legacy application code was changed.
