# Prospective Collection Readiness V2

Stacked base: `feat/prospective-context-provenance` at `2c921a87edeca7a0dc4272e2bd19a1596ec7459f`.
Branch: `feat/prospective-collection-readiness-v2`.
Historical implementation baseline; the final review identified three blockers. The stacked
[blocker fixes](prospective-readiness-blocker-fixes.md) require a new independent readiness review.
The subsequent review found two remaining blockers; the
[final integrity fixes](prospective-readiness-final-integrity-fixes.md) document the complete 40-route
read-only inventory and source event/request identity enforcement. A new independent PASS is still required.
Registered collection has NOT started.
Protocol V1 is unchanged. `config/prospective-context-protocol-v2-draft.json` is undated and not open.

## Corrected timeline

`alertOccurredAt -> operationalAdmittedAt -> context availability -> reviewEligibleAt -> decisionAt -> outcomeAt`

- `alertOccurredAt` is immutable detector/network provenance. It is never changed to make a cohort eligible.
- `operationalAdmittedAt` comes from the first immutable `admit_tier1` routing audit, not a guessed creation time.
- `reviewEligibleAt` is a conservative input-availability boundary, NOT a claim about the earliest possible
  historical deferral. It is the maximum of admission, triage update, frozen policy availability (run opening),
  referenced fact availability/recording/validity, and memory creation/support/conflict/activation/validity.
  Unknown context or absence of matching memory is first observed at this evaluation, so that boundary is decisionAt.
  It means the inputs, including explicit unknowns, can be evaluated; it does not mean the deferral gates passed.
- `decisionAt` is the server's snapshot timestamp inside the serialized decision transaction, persisted identically
  in the actual selective event and collection sidecar. It is never supplied by the client.
- `outcomeAt` is availability of a later explicit human memory review or primary case finding, not a detector label.

## Persistence and isolation

Migration 13 adds only prospective_runs, prospective_run_events, prospective_decisions and
prospective_observations. No existing table rebuild. UPDATE/DELETE/REPLACE are blocked by triggers.
Run records and events preserve frozen protocol/configuration hashes, commit SHA, clean-tree status,
participant classification, evidence basis, start/end/outcome cutoff, actors and opening/closure timestamps.
State and decision count are derived from the append-only ledger: draft -> open -> closed -> evaluated.
Recording the evaluation receipt is a separate authenticated Admin mutation; report generation remains read-only.

Registration and opening must precede the future holdout start. Opening needs a final PASS review reference;
the reference is an Admin attestation requiring independent human verification, not an automated approval service.
Non-synthetic registration/opening/recording requires a clean committed source tree. A synthetic test run records
when it used a dirty development tree and never claims that the HEAD alone describes those uncommitted changes.
Opening/recording rejects a changed commit or policy/configuration. There is no protocol editing endpoint.
Changing a draft's frozen content means creating a new identity, not rewriting an old run.

An eligible optional run/ref revision on Evaluate/Require Human Review atomically appends the
ordinary selective event and a collection snapshot. The latter contains exact alert identity, all four decision
times, availability components, actor/action, disposition/reasons, policy/configuration hash, complete context
provenance, full memory matches/status/support/conflict, route/stage/priority and deterministic snapshot fingerprint.
Exact retries preserve identity. Evaluate still rejects ineligible/stale collection requests. Require Human
Review instead records its operational audit with an explicit skipped-collection receipt when a selected run
is ineligible, including expired/closed/missing/stale runs. No collection tables change in that case.
Operational workflow/state/RBAC checks still apply. No run selected = existing behavior.
Context assessment does not change triage policy input/scoring; admission already applies the existing policy.

## Evaluation modes

1. `retrospective_reconstruction`: existing chronological replay at original occurrence time, labelled explicitly.
   Missing historical triage still excludes an alert; future evidence is never backfilled. This is counterfactual,
   not a record of an operational decision. The former registered wrapper now rejects reconstructed-only claims.
   Its retained exploratory protocol helper validates only referenced in-window configurations.
2. `prospective_recorded`: consumes actual immutable collection decisions and matching persisted selective events.
   Validates run lifecycle, admission evidence, fingerprints, referenced configuration and context chronology.
   No reevaluation from today's current alert, policy, context or memory state. Only this mode can be registered.

Decision cohort: first eligible `apply` per alert in `[holdoutStart, holdoutEnd)`, with Tier 1/triage and no prior
human verdict. Repeated evaluation and override snapshots are retained, not counted as additional alerts.
Truth window: `decisionAt < outcomeAt < outcomeCutoff`. Any malicious/suspicious outcome makes a deferral unsafe;
a later benign finding cannot erase it. Missing/inconclusive truth is not safe. Closure is only at/after cutoff.
Recall counts are explicit overrides or subsequently recorded live recall observations. They do not claim
continuous background recall monitoring. An analyst can persist a visible recall using Record Task Observation.

Exports retain all actual decisions, decision-time context/policy/memory snapshots, raw selective events,
admission/routing events, run lifecycle events, human outcomes, observations and unrelated fact history.
Closed reports validate/hash only referenced in-window evidence and outcomes/observations inside cutoff.
An unrelated post-window v2 fact/configuration, later outcome, or evaluation receipt cannot change the closed report.
Referenced incompatible configurations still fail. Both SQLite exporter and evaluator are read-only; CLI uses
mode=ro/query_only and never migrates or creates a missing database.
API inspection routes and their authentication dependency now also use mode=ro/query_only from connection
open, never the migrating dependency. Unsupported schemas fail explicitly without upgrade; mutable endpoints
retain the existing migration path. See the final-integrity document for the complete endpoint scope.

Before reporting, reconcile every immutable recorded decision with run.decisionCount, unique decision/raw
event identities, run-bound review events, receipts and matching snapshots. Missing/duplicate/inconsistent
records fail with archive-integrity rather than being inferred. decisionCount counts all ledger events,
including repeats/overrides; eligibleAlerts still counts only the first eligible apply per alert.

```powershell
python scripts/evaluate_temporal_review.py --synthetic safe_learning --format markdown
python scripts/evaluate_recorded_collection.py --database <approved-db> --run-ref <uuid> --export
python scripts/evaluate_recorded_collection.py --archive <frozen-export.json> --format markdown
```

## Authenticated UI

Analyst: Suricata Admission -> inspect -> eligibility review -> admit -> Open V2 Routing -> inspect triage policy ->
Add Trusted Context -> select explicit assessed values/observation/expiry/reason -> Record Safety Assessment ->
Prospective Collection -> select open run -> Evaluate Review Policy -> inspect persisted timestamp/disposition ->
later human outcome/case finding -> record stopwatch duration, errors, rework and optional recall observation.
Each explicitly selected context field is an individual append-only fact; a partial network failure does not
roll back successful earlier fields. Unconfirmed retries retain their original request identity and revision.
Unknown/unselected is never silently false. Server fixes actor/source/availability/recording metadata.

Admin: Selective Review -> Collection Runs -> create draft -> inspect frozen identity -> open approved future
window -> wait until cutoff -> close -> inspect/download JSON -> evaluate -> optionally record evaluation receipt.
Evaluator: inspect runs/context/decisions and export/evaluate closed runs, never mutate.

UI displays protocol/run/status, original occurrence, admission, eligibility, decision timestamp, recorded
disposition/policy/context and outcome completion. Existing context evidence panel remains read-only.
Desktop/mobile have stable controls and overflow checks. The workflow is opt-in, not automatic collection.

## Workload and UAT

Report baseline/actual immediate reviews, deferred alerts and review-volume reduction separately from
human-reported stopwatch analyst-review seconds and total-task seconds. Errors/rework are separate counts.
No measured time reduction is reported without a paired time baseline. Targets are collection goals, not power
calculations or proof of safety. Synthetic/demo evidence is visibly labelled; external histories remain unverified.
The [manual UAT checklist](prospective-collection-uat.md) includes unfilled observed-result/pass/fail/start/end/
duration/confusion fields and explicitly separates professional analysts from proxy/student analysts.

## Safety and next review

No attack traffic, malware, scanners, firewall actions, host isolation, account disabling, SOAR, live enrichment,
automatic lesson creation/closure or widened policy threshold. Tests use disposable fixtures/databases only.
Selective Review pure policy, Triage Memory, context resolver, detectors, legacy feedback, routing, case and
response logic are unchanged. Only the selective-event persistence path gains optional collection metadata.

Next: independent FINAL READ-ONLY readiness review of this exact commit. After PASS, create a new immutable
future-dated V2 registration using the reviewed clean SHA/configurations and participant classification.
Do not repurpose the synthetic browser run, backdate anything or edit V1 retrospectively.

## Verification commands

Run Python tests with a new disposable `--basetemp` directory. Browser configurations use separate
rehearsal databases; never point them at a source database. If legacy ports are occupied, set
`HITL_E2E_API_PORT` and `HITL_E2E_WEB_PORT`; do not reuse another running service.

```text
python -m pytest -q
python scripts/build_openapi.py --check
npm run check:api
npm run typecheck
npm test
npm run build
npx playwright test --config=playwright.routing.config.ts
npx playwright test --config=playwright.prospective.config.ts
npx playwright test --config=playwright.config.ts
```

The legacy configuration selects its S16 narrative and optional guide capture. The routing configuration
retains all ten prior V2 regressions. The prospective configuration has its own unadmitted synthetic fixture
and real wall-clock decision/outcome window; it never rewrites a timestamp to fast-forward collection.

### Pristine S16 baseline

S16 assumes an unopened similar-alert learning gate. The existing `data/demo.db` has legitimate historical
feedback and is not a valid fresh baseline. `scripts/serve_s16_rehearsal.py` creates a new temporary database
without opening or copying that database. It explicitly seeds seven narrative alerts plus inert rows needed
by the unchanged 5,000-alert assertion, detector configuration metadata and authenticated demo accounts.
No feedback, family learning history or audit events are seeded. Stable identities/timestamps make the scenario
data deterministic; auth salts and live UI event timestamps remain naturally fresh. Existing paths are refused,
and the temporary directory is disposed when the rehearsal server exits.

The original S16 actions and assertions are unchanged. Synthetic evidence tests workflow behavior, not model
performance. Its final evaluator screen still displays the existing committed three-arm results artifact;
those historical results are not generated by, or attributed to, this synthetic fixture. A unit regression
checks deterministic scenario rows, zero learning history, valid legacy detector projection, integrity,
refusal to overwrite and that every SQLite connection targets the disposable test directory.

### Original V2 baseline verification (before blocker fixes)

- Full Python: 866 passed, 5 existing skips for absent gitignored sample/prediction artifacts.
- Full frontend: 206 passed across 29 files.
- Python OpenAPI check, frontend generated-schema check, TypeScript and Vite production build: passed.
- Browser: unchanged S16 narrative 1 passed; prior V2 regressions 10 passed; prospective recorded journey
  1 passed. The optional guide-capture test remains intentionally skipped unless explicitly enabled.
- Prospective desktop/mobile screenshots inspected; main-content overflow assertion passed.
- Vite retains its existing >500 kB bundle warning. No detector assets were regenerated to remove data skips.
- `data/demo.db` SHA-256 before/after these final runs:
  `DF34AB87760A8BB51DDF5A74D84A2B4C89DE0C5B157777292F15FC132A83AC00`.
  The source database was never reset, reseeded or overwritten; legitimate historical feedback was retained.
- Selective Review pure policy/configuration, Triage Memory, trusted context resolver, V1 protocol,
  routing, case, response, detector pipeline and legacy feedback are unchanged from the stacked base.

These results verify the implementation and disposable rehearsals, not manual UAT or production effectiveness.
The subsequent independent review failed. Current readiness remains pending a NEW independent review of
the blocker-fix branch; these original baseline numbers are not the blocker-fix verification results.

## Exact file manifest

All paths below are relative to `hitl-ids/`:

```text
apps/api/collection_routes.py
apps/api/contract/openapi.py
apps/api/main.py
apps/api/openapi.json
apps/web/e2e/demo.spec.ts
apps/web/e2e/prospective-collection.spec.ts
apps/web/playwright.config.ts
apps/web/playwright.prospective.config.ts
apps/web/src/api/schema.d.ts
apps/web/src/pages/analyst/CollectionPanel.test.tsx
apps/web/src/pages/analyst/CollectionPanel.tsx
apps/web/src/pages/analyst/SelectiveReviewPage.tsx
config/prospective-context-protocol-v2-draft.json
docs/HANDOVER.md
docs/deviations.md
docs/prospective-collection-readiness-v2.md
docs/prospective-collection-uat.md
docs/system-workflow.md
packages/contracts/db.py
packages/contracts/prospective_collection.sql
packages/detection/prospective_collection.py
packages/detection/selective_review.py
packages/evaluation/context_protocol.py
packages/evaluation/prospective_recorded.py
packages/evaluation/temporal_review.py
scripts/evaluate_recorded_collection.py
scripts/serve_routing_rehearsal.py
scripts/serve_s16_rehearsal.py
tests/fixtures/prospective-collection-demo.json
tests/test_api_contract.py
tests/test_canonical_api.py
tests/test_contracts.py
tests/test_external_staging.py
tests/test_operational_v2.py
tests/test_prospective_collection.py
tests/test_s16_pristine_fixture.py
tests/test_triage.py
tests/test_triage_policy.py
tests/test_trusted_context.py
```
