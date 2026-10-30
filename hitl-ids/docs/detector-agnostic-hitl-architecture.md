# Detector-agnostic HITL alert foundation

Base: feat/demo-build at 305c4d390ce9cd08bbc17f737053182a4ab61b7d.
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
