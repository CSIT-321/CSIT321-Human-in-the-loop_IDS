# Prospective Trusted Context Provenance V1

Base: `feat/selective-review-temporal-evaluation` at `81ba46cb2733a0fd7087d4c117dca4b0d5915d99`.
Branch: `feat/prospective-context-provenance`.

Before: unknown context -> Must Review. Now: scoped timestamped facts distinguish trusted safe,
trusted risky, unknown, expired and conflicting evidence. Still: unknown/expired/conflict or unsupported
subject bindings -> Must Review. Selective Review V1 thresholds and its pure policy are unchanged.
No attack generation, external enrichment, live capture, automatic response or SOAR is introduced.

## Fact model and collection

TrustedContextFact stores factRef, optional database id, subject type/value, typed key/value, source
type/reference/snapshot, observedAt, availableAt, validFrom, nullable expiresAt, recordedAt, optional
confidenceBasis, actor, reason, status and a saved freshness-policy configuration. Supported keys are
exactly the nine existing TriageContext fields. Boolean keys require booleans, criticality a fixed enum,
and correlated count a nonnegative integer. Null is unknown. Text is never extracted into facts.

Provenance categories: asset_inventory, threat_intelligence, analyst_assessment, detector_context,
case_context, approved_registry, synthetic_fixture. These are **not claims of implemented CMDB/intel
integrations**. Implemented collection is structured analyst assessment plus disposable fixture input.

```text
GET  /api/v2/context/facts?limit=50&offset=0
POST /api/v2/context/facts
GET  /api/v2/alerts/{alertRef}/context
```

GET returns paginated immutable facts and a global revision. POST requires an active analyst/admin
JWT, requestId, expectedRevision, subjectType/value, contextKey, structured value, observedAt,
validFrom, expiresAt, nonblank reason and sourceReference. The server fixes sourceType to
analyst_assessment and stamps actor, fact UUID, availableAt=recordedAt=server time and sourceSnapshot.
Callers cannot backdate availability, impersonate another source/actor or submit arbitrary snapshots.
Alert/case subjects must exist. Evaluator reads only. No collection changes verdicts, routes or scores.

BEGIN IMMEDIATE serializes collection. Exact actor/payload retries are idempotent; reused IDs with
different payloads and stale global revisions return 409. Failed inserts roll back. Same-source updates
append versions, never overwrite. Withdrawn status is supported in local/archive history but is not an
HTTP action; manual collectors can append unknown or allow expiry. No free-text extraction exists.

## Resolution, conflicts and freshness

Migration 12 adds only `trusted_context_facts` and `triage_context_provenance`. UPDATE/DELETE/REPLACE
are blocked by append-only triggers. Existing tables/rows are not rebuilt or normalized.

At decision time T the pure resolver requires recordedAt <= T, availableAt <= T, validFrom <= T and
T < effective expiry. Future facts cannot replace earlier facts. Supported resolution bindings are exact
operational-alert UUID and destination-IP assetCriticality. Asset names, case membership, host identity
and alert-wide negative safety from a single IP indicator are **not inferred**. Unsupported bindings
remain inspectable but cannot qualify an alert.

Within `(subject, key, sourceType, sourceReference, actor)`, the newest available applicable version
replaces only that source stream. New expired/withdrawn records never revive an older safe version.
Other sources/actors are not superseded. Disagreement, including null versus false, is explicit conflict;
there is no invented source precedence. Equal-time disagreements also conflict. Unusable fields map
to null, not false. Each result includes status, selected source facts/UUIDs, timestamps and explanation.

Versioned maximum ages are saved with each fact, measured from observedAt:

| Keys | Maximum age |
| --- | --- |
| assetCriticality | 168 hours |
| knownMaliciousIndicator, repeatedCampaign, correlatedAlertCount | 4 hours |
| responseRequired, confirmedMalicious, evidenceConflict, analystEscalated, unresolvedByTier1 | 8 hours |

Effective expiry is min(explicit expiry, observation + saved maximum age). Null explicit expiry is
therefore not indefinite trust. Reusing a configuration version with changed contents is rejected on
collection. Current configuration edits cannot refresh historical facts. Expiry exactly at T is invalid.

## Integration boundaries

Selective Review consumes resolved context instead of accepting old unprovenanced triage snapshots
as trusted safety facts. `selective_review_policy.py` and its configuration are unchanged, including
the existing 24-hour context-age gate, which remains an additional conservative constraint even for
longer-lived asset facts. Trusted risk triggers original guards; unresolved fields remain unknown.
New decision snapshots retain context provenance and fingerprint it, excluding only the moving
evaluation timestamp. Fact changes/expiry invalidate a prior deferral on read, never automatically
grant another. Old decision snapshots remain readable with nullable provenance. No production backfill.

Operational Triage keeps its existing explicit context input and scoring. Resolved provenance is an
audit sidecar written atomically with its policy audit; this does not claim old/manual inputs already
had provenance. An identical retry does not manufacture a new past snapshot. Admission, memory,
Tier 2, response approval, legacy feedback and guardrails retain their workflows.

The read-only Safety Evidence panel in V2 Selective Review shows values, status, source/subject,
observation/availability/validity/effective expiry, reason and Must Review effects. Synthetic sources
are visibly labelled. Collection is via API; no dashboard redesign or new response action is included.

## Temporal evaluation and coverage

New database exports include fact history and resolve it at original alert occurrence time. An empty
ledger is unknown, not a fallback to today's context. Pre-fact archives retain original snapshot
semantics for reproducibility and are counted as `legacySnapshotsWithoutFactProvenance`; they cannot
qualify as registered prospective evaluations. Old databases are never migrated by the read-only
exporter. Missing historical triage still excludes an alert rather than backdating admission.

CLI synthetic scenarios now include synthetic fact provenance. The older pure fixture builder keeps
legacy mode by default only for regression tests. Disposable browser scenarios seed labelled facts;
real `demo.db` and production-like data are not seeded. Fixture success is not production evidence.

Reports add eligible count, complete trusted-context count, unknown/not-applicable, expired and
conflicting blocked counts, coverage (complete / eligible), and trusted-context deferral rate
(deferred with complete context / complete). Trusted risky facts count as complete, not safe. Blocking
categories may overlap. With zero complete observations the deferral rate is null, not a safety claim.

## Frozen prospective protocol

`config/prospective-context-protocol-v1.json` specifies a **planned**, not already executed, window:
2026-11-01 00:00 +08:00 inclusive through 2026-11-15 00:00 +08:00 exclusive. Targets: at least 100
eligible alerts and 95% informative outcome completeness. These are collection goals, not statistical
power/significance claims. Rescheduling requires a new preregistered version, not retrospective edits.

The protocol saves exact policy configurations as well as versions. For every alert: preserve occurrence
time; snapshot available context and policy; record immutable decision inputs/result; obtain later human
outcome; never rewrite inputs; evaluate only after closure. Report missing/inconclusive outcomes,
unsafe deferrals and reduction even when collection targets fail. Later malicious evidence cannot be
erased by a later benign label. Observed-feedback replay is still not a causal workload experiment.

```powershell
python scripts/evaluate_temporal_review.py --synthetic safe_learning --format markdown
python scripts/evaluate_temporal_review.py --archive collected-history.json --protocol config/prospective-context-protocol-v1.json
```

`--protocol` rejects evaluation before closure, wrong windows/configurations and archives lacking
fact history. Reports include completeness and target status. Without that option, exploratory temporal
evaluation remains available but is not a registered prospective result. SQLite stays mode=ro/query_only.

## Limitations and next step

Verification: full Python **841 passed, 5 unchanged missing-fixture skips**; provenance/protocol
**36 passed**; frontend **203 passed in 28 files**; browser workflow regressions **10 passed**.
TypeScript, Python OpenAPI check, frontend generated-schema check, production Vite build and the
12 documentation synchronization tests pass. Existing bundle-size/jsdom warnings remain non-failing.
One initial browser run hit a OneDrive EBUSY lock during trace cleanup; the full suite passed with
artifacts in a disposable temp directory. Desktop/mobile provenance display and no horizontal
overflow were verified. The live preview uses a temporary database, not the source demo database.

Authenticated provenance is not proof that a human/source is correct. There is no live CMDB/intel,
automatic discovery, identity resolver or broad negative-IP inference. Scans target research-scale
histories; a global revision conservatively rejects unrelated concurrent writes. No firewall blocking,
host isolation, account disabling, attack traffic, malware or external SOAR is enabled.

Next: perform registered prospective collection using independently verified scoped context and
complete human outcomes, inspect coverage/unsafe deferrals, and only then consider broader automation.

## Exact file manifest

Relative to `hitl-ids/`:

```text
apps/api/context_routes.py
apps/api/contract/openapi.py
apps/api/main.py
apps/api/openapi.json
apps/web/e2e/selective-review.spec.ts
apps/web/src/api/schema.d.ts
apps/web/src/pages/analyst/SelectiveReviewPage.tsx
apps/web/src/pages/analyst/TrustedContextPanel.tsx
apps/web/src/pages/analyst/TrustedContextPanel.test.tsx
config/context-provenance-v1.json
config/prospective-context-protocol-v1.json
docs/HANDOVER.md
docs/deviations.md
docs/prospective-context-provenance.md
docs/system-workflow.md
packages/contracts/db.py
packages/contracts/trusted_context.sql
packages/detection/context_store.py
packages/detection/selective_review.py
packages/detection/triage_policy_service.py
packages/detection/trusted_context.py
packages/evaluation/context_protocol.py
packages/evaluation/temporal_fixture.py
packages/evaluation/temporal_review.py
packages/evaluation/temporal_source.py
scripts/evaluate_temporal_review.py
scripts/serve_routing_rehearsal.py
tests/test_api_contract.py
tests/test_canonical_api.py
tests/test_contracts.py
tests/test_external_staging.py
tests/test_operational_v2.py
tests/test_selective_review.py
tests/test_triage.py
tests/test_triage_policy.py
tests/test_trusted_context.py
```
