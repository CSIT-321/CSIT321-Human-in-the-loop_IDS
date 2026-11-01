# Correlated Suricata evidence and system routing

This increment starts at `b0077d792dfd66dd58e7155f481911d3322ca4c7` on
`feat/unified-analyst-workstation`. Implementation branch:
`feat/suricata-correlation-auto-routing`.

## Before and after

Before:

```text
EVE alert → one signature → canonical alert → Tier 1
          → Tier 2 Recommended → Human Routing Decision → case
```

New, explicitly admitted Suricata detections:

```text
EVE records → sensor/flow evidence bundle → normalized attack classification
            → operational priority + persisted trusted context → system routing
                 ├─ ROUTINE_REVIEW → Tier 1
                 ├─ CRITICAL_ESCALATION → real Tier 2 Case
                 └─ EXPERT_REVIEW_REQUIRED → real Tier 2 Case
            → manual analyst override only when needed
```

Offline ingestion still stages evidence for an explicit source-eligibility review and admission.
This is an ingestion trust boundary, not an analyst approval of system Tier 2 routing.
Admission commits evidence, classification, priority, route, audit and any case in one transaction.
No inference or write happens during a GET. No capture service or response execution is added.

## EVE records, identity and sealing

The importer accepts JSON objects, arrays and JSONL, retaining `alert`, `flow`, `http`, `dns`,
`tls`, `ssh`, `fileinfo` and `anomaly`. Unsupported types are ignored; malformed records are
reported without echoing untrusted payloads. Non-alert records require their event-specific
object and do not create security detections by themselves. Original timestamps must have an
explicit offset; no timezone is guessed. Supplied endpoint fields are validated. Recursive
ground-truth key rejection applies to every supported type, including metadata and extensions.

Every preserved raw record is stored in append-only `suricata_eve_records`. Its source reference
is `eve-sha256:` plus SHA-256 of sorted, compact UTF-8 JSON. `(sensor_id, source_record_ref)` is
unique. Whitespace, object-key order, file location and file order do not change identity.
The raw JSON value, original timestamp, sensor, flow ID and transaction ID remain available.
Raw JSON serialization whitespace is not treated as evidence. Identical JSON on one sensor
deliberately deduplicates.

Detection identity is UUIDv5 over canonical JSON:

```text
["suricata-bundle-v1", sensor_id, "flow", string(flow_id)]
```

Without a flow ID it is:

```text
["suricata-bundle-v1", sensor_id, "record", source_record_ref]
```

No host/time-window inference, cross-sensor merge or campaign inference is performed.
Transaction references group only within their existing parent flow; a transaction without a
flow is not used to join unrelated events. Flow and transaction IDs are strings in the bundle
contract/storage so unsigned IDs survive the JavaScript number boundary. Original raw JSON
numbers remain in the immutable server snapshot; use the normalized string IDs for exact UI
inspection of very large IDs.

An offline batch is the completeness boundary. Earlier evidence-only batches can contribute to
the first detection snapshot. The first staged detection seals the bundle, more strictly than
the required admission boundary. Reimporting the same bundle is a no-op. New evidence for a
sealed flow fails the entire batch with an explicit conflict and rollback: it cannot mutate
reviewed evidence, silently discard a secondary signature, or create a duplicate detection.
Supply the complete EVE capture before staging. Streaming completion and explicit late-evidence
revisions are future work; this implementation does not claim to support them.

## Bundle contract and native severity

`SuricataEvidenceBundle` is carried under canonical `structuredEvidence.suricataBundle`:

- `schemaVersion`, `sensorId`, `flowId`, `correlationBasis`;
- `primaryRecordRef`, `nativeSeverity`;
- `relatedSignatures`: source reference, original timestamp, signature ID/text, native category,
  native severity, action and supplied metadata for **every** related alert;
- `records`: stable reference, sensor, timestamp, flow/transaction IDs, type and raw JSON;
- `transactionRecords`: transaction ID → record references within this flow;
- `evidenceTypes` and `mlEnrichment=unavailable_no_validated_feature_bridge`.

Records are ordered by timestamp instant then content hash. The primary signature is selected
by the smallest numeric native severity, then timestamp instant and content hash. This follows
the [documented native priority semantics](https://docs.suricata.io/en/latest/rules/meta.html#priority). Severity is
never added, averaged or turned into probability; every individual severity is retained.
Unsupported bundle severity remains in raw staging but cannot pass the existing admission
priority policy. Suricata confidence stays null / “Not provided”, even if free-form rule metadata
contains strings such as “High”. The original native category is never overwritten by platform
classification.

Structure follows the [official Suricata EVE format](https://docs.suricata.io/en/suricata-8.0.7/output/eve/eve-json-format.html),
including flow-based correlation and transaction identifiers. Fixtures use documentation IP
addresses and explicitly synthetic signatures. No real PCAP/Suricata execution has been performed.

## Classification V1

The normalized taxonomy is:

```text
brute_force                  botnet_c2
dos                          ddos
web_attack                   infiltration
reconnaissance_port_scan     malware_exploit
other_known_attack          unknown_needs_expert
```

There is no benign attack category. Human verdicts and Tier 2 findings remain separate.
`config/suricata-classification-v1.json` contains explicit, case-insensitive regular-expression
rules over every signature text and native category. V1 does not interpret free-form metadata
as an authoritative attack label; it retains it as evidence. One distinct supported class maps
to that class; no matches yields `unmapped`; materially conflicting supported matches yield
`conflict`. Both latter states use `unknown_needs_expert`. A nonmatching secondary signature
does not create a contradictory class. Every matched rule records its ID, signature ID, input
field and mapped class. The immutable decision records category, status, source, reasons and
policy version, with the full configuration snapshot. There is no numerical ML confidence.
Changing a recorded configuration under the same version is rejected.

Unknown / Needs Expert means unresolved classification requiring investigation. It is not
confirmed malicious, suspicious, false positive or a human verdict.

## Priority and system routing

Priority preserves `operational-triage-v1` score/band arithmetic: severity 1/2/3/4 maps to
85/65/40/20 before the existing bounded context adjustments. That remains urgency, not probability.
The old recommendation-only evaluator remains for historical compatibility; new bundled
admission uses its scoring values and a separate final routing policy. It does not copy the
old “no automatic Tier 2 transition” sentence into new decisions.

`config/system-routing-v1.json` defines the enabled rules and thresholds:

| Outcome | Explicit condition |
| --- | --- |
| Expert Review Required | Unknown / Needs Expert classification |
| Expert Review Required | Trusted `unresolvedByTier1=true` |
| Critical Escalation | Trusted `confirmedMalicious=true` AND `responseRequired=true` |
| Critical Escalation | Priority ≥ 80 AND trusted `assetCriticality=critical` |
| Critical Escalation | Trusted `repeatedCampaign=true` AND independent `correlatedAlertCount ≥ 3` |
| Routine Review | None of the above |

Expert uncertainty takes the route-class label if expert and critical conditions coexist; all
matched reasons remain recorded. Both expert and critical outcomes create a real case. Severity
1 or a high priority alone is insufficient. Unknown, expired or conflicting context is never
treated as true. The existing trusted-context resolver selects persisted, scoped facts at the
decision timestamp; its full provenance snapshot is audited. The HTTP admission body cannot
supply context, policies, source evidence or actor identity. The new bundle path also rejects
the old internal caller-supplied context shortcut.

Same-flow signature count never populates campaign context or independent alert count.
Initial system routing is immutable. Later trusted facts do not silently reroute or downgrade a
case; an analyst can manually escalate a remaining Tier 1 alert. A versioned re-evaluation
workflow is future work. Existing Selective Review evaluation/disposition remains independent,
including its evidence-gated No Immediate Review behavior and recall/override controls.

## Atomicity, attribution and migration 14

Migration 14 adds the raw-record and immutable `operational_system_routing` tables. SQLite
requires rebuilding four tables to permit nullable system actors: `operational_routing_audit`,
`operational_triage_policy_audit`, `tier2_cases`, and `tier2_case_events`. Existing IDs, original
columns, rows, immutable snapshots, foreign-key relationships, indexes and append-only triggers
are preserved. Historical rows receive `decision_source=analyst`.

The migration temporarily disables foreign-key enforcement **outside** its write transaction,
rebuilds/copies within that transaction, checks all foreign keys before commit, and restores the
original pragma in `finally`, including failure paths. Read-only inspection never migrates.
The original migration files, Protocol V2 and collection state machine are unchanged.

For new system decisions:

- routing action is `system_route`, event `V2_SYSTEM_ROUTED`, source `system_policy`, actor NULL;
- priority audit also has source `system_policy`, actor NULL;
- automatic case creation and its event have source `system_policy`, creator/actor NULL;
- case ownership is unassigned (NULL); no arbitrary analyst is substituted;
- the source admission receipt still truthfully identifies the human who admitted the source;
- database CHECK constraints reject invalid actor/source combinations.

Case UUIDv5 is bound to the operational detection. Unique primary-alert and request constraints,
the existing admission write lock and receipt replay semantics prevent duplicate cases/audits.
The system route audit's after-state is already `tier2_case / investigation`; no intermediate
candidate is written. A failure in any write rolls back the projection, state, scoring/routing
audits, case/event, system decision and admission receipt. Replaying a completed admission never
rewinds a later manual decision. There is no public anonymous system-routing mutation API.

Human `start`, notes, links, findings and responses retain authenticated actors. Ownership stays
unassigned on system-created cases in this increment, including after starting investigation;
the investigation event identifies the acting analyst. An explicit assignment/claim workflow is
future work. This avoids rewriting immutable creation provenance.

## Analyst workflow

Analyst Workstation remains the main home; `/analyst/v2-triage` is its compatibility route.
Overview displays primary signature, separate normalized/native categories, signature count,
evidence types, native severity, operational priority, current route and route class.
System Routing replaces Human Routing Decision and shows source, version, reasons, classification
basis and the case link. After an override, the UI distinguishes the current analyst decision
from the initial system route. New system decisions keep compatibility recommendation fields
false/empty; the workstation no longer presents Tier 2 Recommended as its primary concept.
Historical snapshots retain their original recommendation fields and provenance.

Tier 1 offers **Manual Escalation / Override → Escalate to Tier 2** with an explicit reason.
It uses the existing authenticated compound case command. Automatic Tier 2 has a case link and
no approval button. Historical incomplete escalation recovery remains explicit and secondary.
Case ownership/source and audit history display System Policy / Unassigned safely.

Evidence groups the summary, all signature rows, supplied flow/application/anomaly records,
correlation details and raw inspection. Missing evidence types do not get fabricated sections.
Legacy Signature + XGBoost/TreeSHAP evidence, feedback and scoring remain under Historical.
New Suricata evidence never pretends to be XGBoost output; enrichment is explicitly unavailable
until a validated feature bridge exists. No new Tier 1 human verdict is introduced.

## Validation and limits

`tests/test_suricata_correlation_routing.py` covers event types, safe grouping, transactions,
identity, immutability, classification, context guardrails, attribution, atomic failure/retry,
manual override, configuration immutability and populated/failed migration paths. Existing
historical workflow tests use a test-only original-adapter snapshot fixture rather than
misrepresenting old records as new bundles; security and read-only assertions remain enforced.

`apps/web/e2e/suricata-fixture.py` builds a fresh disposable synthetic database without opening
`data/demo.db`. `playwright.suricata.config.ts` runs the real API/frontend on 8009/5182 and exercises
cases A–E, links, attribution, historical evidence and Dark/Light at 1440/1024/390 widths.
The fixture creates no prospective run. Full backend regression may exercise isolated synthetic
collection tests; it does not open a real collection or alter Protocol V2.

Remaining limits: finite offline batches; no late bundle revisions/streaming; no cross-flow
campaign inference; small explicit mapping coverage; no ML feature bridge; no automatic
post-admission policy re-evaluation, downgrade or ownership claim; no real-PCAP validation.
Operational tuning requires reviewed policy versions and evidence, not inferred probabilities.

## Recorded validation

| Check | Result |
| --- | --- |
| New correlation/classification/routing/migration tests | 48 passed |
| Historical compatibility subset | 273 passed, 1 missing-artifact skip |
| Full backend (`pytest tests -q`) | 1256 passed, 1 clock-fixture failure, 5 missing-artifact skips |
| Final temporal + new architecture + inspection/read-only + Protocol V2 freeze rerun | 229 passed; includes the repaired failing test |
| Full frontend Vitest | 227 passed across 31 files |
| Final routing/workstation frontend subset after override-label clarification | 19 passed |
| TypeScript (`tsc -b`) | Passed |
| OpenAPI build/check and generated TypeScript freshness | Passed |
| Production Vite build | Passed; existing >500 kB chunk advisory remains |
| Real API/frontend Chromium A–E journey | Passed; final run 16.4 seconds |
| Themes/responsive | Dark/Light at 1440, 1024, 390; 12 focused screenshots; no page-width overflow |
| `git diff --check` | Passed |

The full backend run found a Windows wall-clock tick collision: the last supporting review and
activation both had `2026-11-01T11:16:46.235539Z`. The temporal export correctly refused it.
Only that test's teaching fixture now uses a deterministic forward-only clock; strict temporal
validation and all read-only checks are unchanged. The final 229-test rerun passes with this
fix. The whole 1262-test suite was not redundantly rerun after this fixture-only change; no
known test failure remains. The five skips require uncommitted large datasets/predictions,
not disabled security checks.

Browser screenshots are generated under `apps/web/test-results/suricata-{evidence,routing}-{width}-{theme}.png`;
they are local validation artifacts, not production assets. Browser tests use no network mocks.
No real-PCAP validation is claimed. No production/source database was opened, no merge/PR was
created, and Protocol V2 / prospective collection were not opened.

## Exact change manifest

47 files. Paths are relative to the repository root (`hitl-ids/` is included).

```text
hitl-ids/apps/api/contract/routing.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/api/routing_routes.py
hitl-ids/apps/web/e2e/suricata-fixture.py
hitl-ids/apps/web/e2e/suricata-routing.spec.ts
hitl-ids/apps/web/playwright.suricata.config.ts
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/features/alert/OperationalEvidence.tsx
hitl-ids/apps/web/src/features/alert/SuricataEvidence.tsx
hitl-ids/apps/web/src/features/alert/SuricataRouting.test.tsx
hitl-ids/apps/web/src/features/alert/SystemRouting.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.tsx
hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/Tier2CasesPage.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.tsx
hitl-ids/config/suricata-classification-v1.json
hitl-ids/config/system-routing-v1.json
hitl-ids/docs/suricata-correlation-auto-routing.md
hitl-ids/packages/contracts/db.py
hitl-ids/packages/contracts/suricata_bundle.py
hitl-ids/packages/contracts/suricata_system_routing.sql
hitl-ids/packages/detection/adapters/staging.py
hitl-ids/packages/detection/adapters/suricata_bundle.py
hitl-ids/packages/detection/attack_classification.py
hitl-ids/packages/detection/external_admission.py
hitl-ids/packages/detection/routing.py
hitl-ids/packages/detection/system_routing.py
hitl-ids/packages/detection/tier2_cases.py
hitl-ids/packages/detection/triage_policy_service.py
hitl-ids/tests/fixtures/suricata-correlated.json
hitl-ids/tests/legacy_suricata_fixture.py
hitl-ids/tests/test_canonical_api.py
hitl-ids/tests/test_contracts.py
hitl-ids/tests/test_external_operational_admission.py
hitl-ids/tests/test_external_staging.py
hitl-ids/tests/test_operational_v2.py
hitl-ids/tests/test_prospective_blockers.py
hitl-ids/tests/test_prospective_collection.py
hitl-ids/tests/test_routing_workflow.py
hitl-ids/tests/test_selective_review.py
hitl-ids/tests/test_suricata_correlation_routing.py
hitl-ids/tests/test_temporal_review.py
hitl-ids/tests/test_triage.py
hitl-ids/tests/test_triage_memory.py
hitl-ids/tests/test_triage_policy.py
```
