# Detection → Classification → Routing → Queue review remediation

Base: `a74f56e450eb7c940f621f3b09a3b9a0d822740f` (`feat/operational-queue-prioritization`).
Candidate branch: `feat/pre-freeze-review-fixes`.

## UNKNOWN PRODUCT INVARIANT

**`unknown_needs_expert` always routes automatically to Tier 2 Expert Review.**
The completed admission transaction creates a formal Tier 2 Case, with workflow
`investigation`, route class `EXPERT_REVIEW_REQUIRED`, decision source `system_policy`,
and no human creator or owner. No Tier 1 approval or visible Candidate stage is required.
F2 reduces incorrect Unknown classifications; it does **not** reduce routing of genuine
Unknown detections. True incompatible attack evidence follows this same invariant.

Suricata remains the primary operational detection/evidence source. The workflow remains
Traffic/PCAP → Suricata → EVE → correlated bundle → classification → Operational Priority
→ System Routing → Analyst Workstation. This increment uses offline synthetic EVE tests;
it does not claim validated real-PCAP detection or a live feed.

## F5 / F6: isolated capture identity and provenance-first deduplication

### Root cause and repair

Previously a durable correlation key used only sensor and flow ID. Reused flow IDs in
independent captures could therefore join evidence or collide with a sealed bundle.
The helper also deduplicated by raw hash before checking sensor identity, allowing identical
raw bytes from different provenances to hide a mixed-sensor input.

New imports require an explicit `capture_scope` / CLI `--capture-scope`:

```text
python scripts/import_suricata_eve.py --database <existing.db> --input <eve.json> --sensor-id <sensor> --capture-scope <stable-capture-id>
```

The scope is an operator-chosen, stable name for **one logical capture or Suricata session**,
not a newly generated import-attempt ID. Use the same name for repeated imports or parts of
that capture; use another name for a different capture/session. It is 1–200 characters,
nonblank, with no surrounding whitespace. Neither absolute file paths nor random per-import
IDs are used. The operator is responsible for supplying the correct logical identity.

New bundle identity is UUID5 of the versioned tuple:

- With flow ID: `suricata-bundle-v2 + sensor + capture_scope + flow_id`.
- Without flow ID: `suricata-bundle-v2 + sensor + capture_scope + canonical raw-record hash`.

The helper reparses and checks **all** provenance/correlation keys before deduplicating.
Deduplication uses `(sensor, scope, raw hash)`. Same-capture reimport is idempotent; the same
raw data in another sensor or capture remains independent. Records without a flow ID do
not acquire inferred flow/campaign relationships. Capture scope is visible in Evidence.

Within one claimed identity, the guard checks available IPs, ports, protocol, and explicit
`flow.start` instants. It preserves both possible endpoint orientations until evidence
resolves them; A:port1→B:port2 and B:port2→A:port1 are compatible. All partial records must
admit one globally consistent flow, so three different single-ended addresses are rejected
even when each pair could be interpreted as opposite directions. Missing anchors are not
invented. Protocol/start contradictions reject the whole import transaction, including
evidence-only groups and records accumulated in earlier batches.

### Compatibility and migration

Migration 15 rebuilds only `suricata_eve_records`, adding nullable `capture_scope` and scoped
uniqueness/flow indexes. Existing IDs, raw snapshots, timestamps and sensor identities are
copied unchanged, with NULL scope. Update/delete/replace immutability triggers are restored.
It reuses the transactional rebuild, FK validation and failure rollback used by Migration 14;
Migration 14 itself is unchanged. Repeated migration/startup is a no-op.

Existing canonical inbox snapshots and operational/classification/routing snapshots are not
rewritten. Legacy `suricata-bundle-v1` reconstruction excludes the new fields and preserves
its original identity/serialization. Historical unscoped evidence remains readable and
admissible. It is not silently attributed to a newly named capture. A pre-migration database
can be inspected with dry-run without migration or writes. Normal import migrates explicitly.

Already sealed bundles still reject late additions that would change their immutable
snapshot. Streaming/late-evidence revision is deliberately deferred.

Tests: `test_capture_identity_reimport_and_provenance`,
`test_flow_contradiction_fails_entire_import`,
`test_bidirectional_and_partial_evidence_remain_valid`,
`test_partial_anchors_require_one_globally_consistent_flow`,
`test_earlier_evidence_is_capture_scoped_and_guarded`,
`test_capture_boundary_requires_stable_scope_and_rejects_truth`,
`test_migration_fifteen_preserves_unscoped_history_and_rolls_back`, plus existing staging,
correlation and Migration 14 tests. Migration tests assert identical pre/post historical
snapshots, failure rollback, FK restoration, integrity checks and immutable triggers.

## F3: explicit classification compatibility

Root cause: the former classifier treated any two normalized categories as a conflict,
including compatible specific and broad evidence.

`config/suricata-classification-v2.json` adds a directed specificity graph. Only configured
relationships apply: `ddos → dos` and `botnet_c2 → malware_exploit`. The classifier computes
the graph's transitive reachability and selects the unique matched category that dominates
all other matched categories. Configuration validation rejects cycles, unknown endpoints,
duplicate rule IDs and an Unknown category used as a known mapping.

Thus DDoS + broader DoS selects DDoS; C2 + generic Trojan/malware selects Botnet/C2.
A known mapping with unmapped supporting text remains known. DDoS + Web Attack has no
configured common winner and becomes `unknown_needs_expert` / `conflict`, automatically
creating an Expert Tier 2 Case.

Every successful rule/input match retains rule ID, source-record reference, signature ID,
input field/value and matched category. Reasons explain the selected specificity or list
conflicts; `conflictingCategories` preserves the incompatible categories. Source and policy
version remain explicit. The v1 config and stored historical classifications are unchanged;
new decisions use `suricata-classification-v2`. Historical models accept absent new match
fields without rewriting storage.

Tests: parameterized `test_classification_rules`,
`test_specificity_is_configured_acyclic_and_preserves_matches`, and the conflicting-alert
part of `test_bulk_informationals_and_mandatory_unknown_cases`.

## F2: informational/policy status without inventing a verdict

Root cause: every unmapped signal previously became Unknown, producing unnecessary Expert
Cases for explicitly recognizable notices.

The new representation is `attackCategory: null` with
`classificationStatus` (contract field `status`): `informational_policy_signal`.
The UI says **Classification: Informational / Policy Signal**. It adds no attack category,
benign label, false-positive label or human verdict.

Rules are case-insensitive **full matches of both signature and native category**:

| Signature pattern (optional `SYNTHETIC ` prefix where shown in config) | Native category |
| --- | --- |
| `Informational notice` or `Informational notification`, optional space/colon suffix | `Misc activity` or `Not Suspicious Traffic` |
| `Policy event` / `Policy notice`, optional space/colon suffix, or `ET POLICY ` followed by text | `Potential Corporate Privacy Violation` or `Misc activity` |
| `Protocol notice` / `Protocol informational event`, optional space/colon suffix | `Generic Protocol Command Decode` or `Misc activity` |

In addition, signature text must pass the versioned attack-like veto (word boundaries):
`attack`, `suspicious`, `exploit`, `malware`, `trojan`, `shellcode`, `botnet`, `c2`, `beacon`,
`brute force`/`brute-force`, `infiltration`, `exfiltration`, `injection`, `traversal`,
`reconnaissance`, `scan`, `ddos`, `dos`, `denial of service`, `credential theft`,
`privilege escalation`. The exact regexes are in the versioned JSON; they do not use severity.
The native category is separately allowlisted, avoiding a false veto on the literal category
`Not Suspicious Traffic`.

Known attack matches take precedence. Informational status is granted only when **every
alert signature** satisfies an explicit rule and there are no mapped attack categories.
Bare `Generic activity / Misc activity` stays Unknown. An informational-looking signature
with unresolved attack-like content, or a mixed bundle containing an unresolved signature,
stays Unknown. Rules are intentionally finite; unrecognized real signatures require review
and a future explicitly versioned mapping rather than broad automatic suppression.

Normal routing still applies to informational signals. No Expert Case is created solely
because attackCategory is null. Existing trusted Critical conditions are unchanged, so this
status is not an exemption from Critical routing or human attention.

Tests: 53 explicit notices at severities 1–4 produce **zero Expert Cases** without critical
trusted context. Four genuine low-severity unresolved alerts plus one true DDoS/Web conflict
produce **five formal Expert Cases**, all system-created with null human creator/owner and
no surviving Candidate. Explicit policy, protocol, `Not Suspicious Traffic`, veto and mixed
bundle cases are covered by `test_classification_rules`. Recursive dataset-truth rejection
is also tested under newly introduced capture metadata.

## F1: one effective attention projection

Root cause: queue/KPI/header/rail used persisted route/review flags while Selective Review
revalidated live trusted context and memory. A valid deferral intentionally does not rewrite
`tier1_review + triage`, so the raw flags disagreed with the actual attention decision.

`selective_review.effective_review()` delegates to the existing authoritative `read_review()`
and returns disposition, reviewRequired, reasonCodes, explanation, recalled and version.
No policy is reimplemented in SQL or changed. Missing decisions, changed evidence, expiry,
memory/context conflict, overrides and unsupported workflows retain existing fail-closed
semantics. Labels distinguish Human Review Required, Recommended Review and No Immediate Review.

The API's `RoutingView.effectiveReview`, KPI attention counts, `reviewRequired` filter and
new `reviewDisposition` filter use this service. Attention filtering happens before
pagination and retains Operational Priority/time/reference ordering. Raw `state` stays
available in Technical/audit for tier/workflow/history; raw flags no longer define current
attention. `handlingRoute` filters still mean actual route, so deferred Tier 1 alerts remain
in Tier 1 while also appearing in No Immediate Review.

The selected header/Overview, queue rows, assistance rail and Selective Review panel use the
same disposition. Local review/context commands propagate the refreshed version and reload
summary/queue immediately. External changes are picked up by the existing 15-second review
poll plus synchronized workstation refresh; this is not streaming. The selected panel and
its tab remain mounted even when recalling the last row removes it from the filtered queue.

GET uses read-only connections and snapshot transactions. It does not migrate, materialize,
repair, change routes, write review events, create memory or create cases. Request-local
projections are reused between attention filtering and serialization, not persisted.

Performance: an attention-filtered queue evaluates each otherwise matching alert before
paging; summary evaluates every alert. Cost is O(N × existing context/memory review lookup),
plus normal SQL sorting. Unfiltered queues only project their page. This favors correctness
at FYP scale; no claim of high-throughput/live-scale performance is made.

Tests use real Triage Memory support/activation, trusted facts and recorded Selective Review
commands. Six alerts yield three deferrals/three needs-review; a single override or context
conflict yields two/four. Memory conflict and expiry/context expiry withdraw all affected
deferrals. Summary, queue totals, routing detail and Selective Review agree while raw route
remains Tier 1 and raw reviewRequired remains true. Whole-database dumps before/after reads
are identical. See `test_effective_attention_real_services_and_readonly` (five withdrawal
variants), `test_operational_queue.py`, and workstation frontend/browser tests.

## F4: current alerts cannot escape through standalone Candidate commands

Root cause: the old public escalation/approval command could commit a Candidate without
creating a formal case for a current system-routed alert.

`route_alert()` now rejects standalone `manual_escalate` / `approve_tier2` for alerts with an
`operational_system_routing` record. The API returns 409 before state/audit mutations. Modern
manual escalation uses only `POST /api/v2/alerts/{alertRef}/tier2/escalate-case`; Candidate is
allowed internally only inside that atomic case transaction. The existing atomic automatic
system-routing path is unchanged.

Historical non-system-routed records retain existing compatibility commands and explicit
Candidate recovery. Authenticated manual escalation still requires a reason and binds the
actual analyst as creator; retries remain idempotent. System Cases retain system attribution,
null human creator/owner and no fabricated user.

Tests: `test_current_candidate_api_blocked_and_manual_override_atomic` checks unchanged
database contents on rejection, correct manual creator, final tier2_case and replay. Existing
direct-escalation/case tests preserve historical recovery, transaction rollback and concurrency.
Both current automatic Expert/Critical and manual paths are exercised through the browser.

## F7: scoped wording correction

The global badge is **Imported evidence**, with tooltip:
“Imported Suricata evidence, classification, Operational Priority and system routing; not a live feed”.
Global OpenAPI copy describes the current Suricata/classification/priority/routing workflow.
Legacy score ordering and “every flow becomes an alert” are explicitly scoped to the
historical recorded-flow API. Historical dashboards retain their already labeled historical
descriptions. The workstation layout, KPI strip, queue structure and navigation are unchanged.

## Validation and integrity

Validation results and exact file inventory are recorded below.
All integration/browser fixtures use disposable synthetic databases. No operational/demo
database, collection or frozen protocol artifact is edited by this remediation.

The old migration-version assertions were extended to include 15 and the schema inventory
now includes capture_scope; preservation/rollback assertions were retained. One older
browser locator was scoped to Overview because Unknown also legitimately appears in the
queue and attack filter. No invariant was removed to make tests pass.

Ground-truth protection remains recursive. No dataset label enters classification. No
XGBoost prediction, probability or TreeSHAP bridge is fabricated; current Suricata evidence
still states enrichment is unavailable. No score formula, Critical threshold/conditions,
legacy feedback behavior, Triage Memory policy, Selective Review policy or collection state
machine is redesigned. No Tier 1 verdict, Tier 2 assistance, human reclassification,
cross-flow campaign inference, streaming or PCAP-validation feature is added.

Protocol V2 and its frozen configs/manifest remain unchanged and unopened. Its pinned
reviewed runtime SHA is not repointed to this candidate. Passing freeze regression proves
preservation of that boundary, not authorization to open collection on this branch.

Remaining limitations are the explicit offline sealed-bundle lifecycle, operator-supplied
capture identity, finite text mappings, dynamic review lookup cost and polling latency.
Five optional backend checks require gitignored historical datasets/model outputs unavailable
in this checkout. Production build retains the existing large-bundle advisory.

F1–F7 are addressed within the requested scope. This branch is a candidate for focused
independent re-review, not a merge, freeze approval or permission to open collection.

### Executed checks (2026-11-01)

| Check | Result |
| --- | --- |
| Full backend: `python -m pytest -q --tb=short --basetemp=.pytest-tmp/full3` | **1,317 passed, 5 skipped**, 489.01s |
| Final changed-boundary regression after the last flow/classification refinements: `test_pre_freeze_review_fixes.py test_external_staging.py test_suricata_correlation_routing.py test_api_contract.py test_protocol_v2_freeze.py` | **140 passed**, 16.17s; includes 33 remediation cases |
| Full frontend: `node node_modules/vitest/vitest.mjs run` | **31 files, 232 tests passed**, 21.70s |
| TypeScript: `node node_modules/typescript/bin/tsc -b` | Passed |
| OpenAPI: `python scripts/build_openapi.py --check` | Passed; 72 paths, 76 operations, 143 schemas |
| Client schema: `openapi-typescript ../api/openapi.json -o src/api/schema.d.ts --check` | Passed |
| Production: `node node_modules/vite/bin/vite.js build` | Passed; existing >500 kB chunk advisory |
| New remediation browser journey: `playwright.pre-freeze.config.ts` | **1 passed**, 19.9s |
| Existing operational queue browser journey | **1 passed**, 20.5s |
| Existing Suricata/case browser journey | **1 passed**, 18.8s |
| Responsive themes | 1440 / 1024 / 390 × dark / light passed; screenshots inspected, no document horizontal overflow |
| Frozen artifact hashes via `check_protocol_v2_freeze.validate_artifacts` | Passed, `collectionOpened=false`, pinned SHA `7a961450dda7aa193653180f2d4c03b2a24ac5bb` unchanged |
| Migration 15 failure injection / preservation / repeat / FK / immutability | Passed in final changed-boundary regression |
| `git diff --check` | Passed |

The full backend run preceded the final five additional edge-case examples; the final
140-test pass covers the completed implementation and those additions. The five skipped
full-suite tests are unchanged optional checks in test_contracts, test_fusion, test_observable,
test_rule_set and test_run, requiring gitignored historical samples/predictions.
No tests were skipped because a remediation assertion failed.

Browser runs used Python from the existing local virtual environment, disposable databases
and separate ports. New suite: API 8014 / web 5187. Existing queue and Suricata configs used
ignored temporary copies overriding only working directories/ports (8015/5188 and 8020/5189)
to avoid interrupting existing previews. They did not reuse live database state.
Screenshots remain local under apps/web/test-results; generated browser artifacts are not
committed.

Browser scenarios cover routine Tier 1, valid No Immediate Review and human recall, 53
informational detections, genuine Unknown, compatible DDoS, incompatible attack evidence,
Critical auto-case, manual direct case, rejection of the old Candidate endpoint and separate
capture identities. Existing case screens additionally verify system ownership/creation
attribution and audit timeline. There were no browser JavaScript errors.

### Exact changed files (repository-relative)

```text
hitl-ids/apps/api/contract/openapi.py
hitl-ids/apps/api/contract/routing.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/api/operational_queue.py
hitl-ids/apps/api/routing_routes.py
hitl-ids/apps/web/e2e/operational-queue.spec.ts
hitl-ids/apps/web/e2e/pre-freeze-fixture.py
hitl-ids/apps/web/e2e/pre-freeze.spec.ts
hitl-ids/apps/web/e2e/suricata-fixture.py
hitl-ids/apps/web/e2e/suricata-routing.spec.ts
hitl-ids/apps/web/playwright.pre-freeze.config.ts
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/components/layout/TopBar.tsx
hitl-ids/apps/web/src/features/alert/EffectiveReview.ts
hitl-ids/apps/web/src/features/alert/OperationalQueue.tsx
hitl-ids/apps/web/src/features/alert/SuricataEvidence.tsx
hitl-ids/apps/web/src/features/alert/SystemRouting.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.tsx
hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx
hitl-ids/config/suricata-classification-v2.json
hitl-ids/docs/pre-freeze-review-fixes.md
hitl-ids/packages/contracts/db.py
hitl-ids/packages/contracts/suricata_bundle.py
hitl-ids/packages/contracts/suricata_capture_scope.sql
hitl-ids/packages/detection/adapters/staging.py
hitl-ids/packages/detection/adapters/suricata_bundle.py
hitl-ids/packages/detection/attack_classification.py
hitl-ids/packages/detection/external_admission.py
hitl-ids/packages/detection/routing.py
hitl-ids/packages/detection/selective_review.py
hitl-ids/packages/detection/system_routing.py
hitl-ids/scripts/import_suricata_eve.py
hitl-ids/tests/operational_queue_fixture.py
hitl-ids/tests/pre_freeze_fixture.py
hitl-ids/tests/test_canonical_api.py
hitl-ids/tests/test_contracts.py
hitl-ids/tests/test_external_staging.py
hitl-ids/tests/test_operational_queue.py
hitl-ids/tests/test_pre_freeze_review_fixes.py
hitl-ids/tests/test_suricata_correlation_routing.py
hitl-ids/tests/test_triage.py
hitl-ids/tests/test_triage_policy.py
```
