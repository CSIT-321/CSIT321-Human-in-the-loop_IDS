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

### Canonical contract

| Fields | Meaning |
|---|---|
| canonicalAlertId, occurredAt | Existing UUID for current alerts; event occurrence time |
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
and rule metadata. UUID5 uses sensor identity plus raw-event reference, not flow_id alone.
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

Exact changed files, relative to hitl-ids/:

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
