# Temporal Holdout Evaluation for Selective Review

Base: `feat/selective-human-review-v1` at `8cda81b2b1fa14d2175160241d0ec669434bf229`.
Branch: `feat/selective-review-temporal-evaluation`.

This is **offline temporal holdout evaluation**, not broader automation. The live V1 policy,
admission, UI, routing, memory, detector, guardrail and response paths are unchanged. No schema
migration or API is added. Reports are printed to stdout as JSON or Markdown.

## Methodology and temporal isolation

An explicit `[holdoutStart, holdoutEnd)` window defines evaluated alerts. Earlier events provide
learning history but do not enter the workload denominator. Alerts are ordered by aware occurrence
timestamp and UUID. Timezone-naive timestamps are rejected rather than guessed. Source insertion
order has no meaning; shuffled input produces identical reports and normalized input SHA-256.

For each alert at T:

1. Reconstruct memory from immutable lesson creation, individual support/conflict events and human
   activation/rejection decisions. Only records with availability **strictly before T** participate.
   Never read final lesson aggregates or today's active memory and project them backward.
2. Recompute support, conflict, agreement, status, validity and expiry as of T. Activation itself
   must have qualifying distinct human reviews strictly earlier than the activation. Activation at
   exactly T cannot influence the alert. Expiry at T disqualifies guidance.
3. Use only triage/context observations available at or before T. Future safe context cannot fill
   historical unknowns. No historical triage means an explicitly excluded alert, not guessed eligibility.
4. Select a policy whose effective time AND availability time are at or before T. Missing policy
   forces Must Review. Same version/different configuration and ambiguous effective times are rejected.
5. Call the **unchanged** `evaluate_review` policy and matching function. Keep its sampling, safety
   gates and thresholds. Store the exact historical input/memory/configuration snapshots in the report.
6. After the decision, attach strictly later human outcomes before the holdout end for scoring.
   Any malicious/suspicious outcome counts unsafe; later benign evidence cannot erase it. Otherwise
   use the latest outcome. Missing or inconclusive outcomes are not treated as safely deferred.

Outcomes alone never activate memory: explicit support events and an explicit human activation
are required. Later conflicts can generate a recall observation but cannot rewrite an earlier
disposition. Human overrides available before T remain effective. This is an observed-feedback
replay, not a causal simulation of which feedback would disappear if humans stopped reviewing.
The comparison applies policy counterfactually at T; it does not claim that an operator actually
invoked V1's explicit evaluation action or persisted a review decision at that historical instant.

## Inputs and read-only boundary

Three sources are supported:

- `--synthetic`: deterministic, explicitly synthetic scenarios A-D below.
- `--archive`: a validated `TemporalArchive` JSON containing alerts, timed state/context observations,
  policy periods, immutable lessons, support events, activation decisions, outcomes and overrides.
- `--database`: existing application SQLite history, opened with `mode=ro`, `query_only=ON` and
  one read transaction. It reads immutable policy/routing audits, raw memory rows, primary memory
  outcomes, primary Tier 2 findings and human review overrides. It never reads mutable current triage
  or final memory aggregates, migrates the database, or inserts evaluation decisions.

The database has no authoritative historical Selective Review policy-effective registry. Database
evaluation therefore **requires an explicit policy-history JSON**; the current config is never
silently assigned a past effective time. Each period contains `effectiveAt`, `availableAt` and
`configuration` (the complete SelectivePolicy model). Archive timestamps are provenance assertions:
the evaluator can validate chronology, not prove the authenticity of the supplied history.

Examples, from `hitl-ids`:

```powershell
python scripts/evaluate_temporal_review.py --synthetic safe_learning
python scripts/evaluate_temporal_review.py --synthetic leakage_trap --format markdown
python scripts/evaluate_temporal_review.py --archive historical-archive.json
python scripts/evaluate_temporal_review.py --database historical.db --policy-history policy-history.json --holdout-start 2026-01-01T00:00:00Z --holdout-end 2026-02-01T00:00:00Z
```

Both formats include evidence labels. Synthetic reports say **not real-world production evidence**.
Database/archive historical inputs remain explicitly unverified, not a production-safety claim.
JSON includes per-alert snapshots, reasons, source/category/priority band, later truth history,
policy version and recall time. Markdown includes aggregate, memory and stratified tables.

## Metric definitions

- Eligible: historical route `tier1_review` and workflow `triage` at occurrence. Baseline reviews all
  eligible alerts; selective immediate review includes Must Review and Recommended Review.
- Workload reduction = deferred / eligible. It is a decision-count estimate, not measured time saved.
- Unsafe count = distinct deferred alerts with any later malicious/suspicious outcome. Safe count =
  deferred alerts scored expected activity/false positive with no later malicious/suspicious outcome.
- Unsafe deferral rate = unsafe / labelled deferred. Missing/inconclusive labels are excluded and
  separately counted. The rate is null, not zero, when no deferred alert has an informative label.
- Recall count = unique historically deferred alerts that subsequently receive related conflicting
  memory before cutoff. It is not today's queue size and does not subtract past deferrals.
- Memory coverage = eligible alerts with any related lesson / eligible. Active coverage uses High,
  active guidance matches; neither metric implies all safety gates passed.
- Unknown-safety blocked percent = eligible alerts with unknown/missing required context / eligible
  times 100. It may overlap other blocking reasons; it is not a causal attribution.
- Memory lifecycle counts include pre-holdout learning through cutoff: candidate lessons created,
  activations, support-alert count and elapsed seconds before activation, intervening stream alerts,
  conflict events after activation, and lessons whose expiry has elapsed (rejected lessons excluded).
- Breakdowns: detection category, policy-selected memory outcome (or none), priority band, detector
  source. Missing triage coverage/exclusion counts remain visible instead of inflating reduction.

## Synthetic fixture results

All scenarios use three earlier expected-activity reviews at minutes 1, 3 and 5, explicit human
activation at minute 6, and holdout alerts at minutes 8, 10 and 14. Support is 3, conflicts initially
0, exact High match, priority remains 85. The unchanged 10% sampling policy is retained; fixed
holdout identities have buckets 92, 69 and 67. Safe context is explicitly synthetic only.

| Scenario | Eligible / baseline | Selective immediate | Deferred | Unsafe | Recalls | Unknown blocked |
| --- | --- | --- | --- | --- | --- | --- |
| A: safe learning | 3 | 0 | 3 | 0 | 0 | 0 |
| B: conflict at minute 12 | 3 | 1 | 2 | 1 | 2 | 0 |
| C: leakage trap, contradiction delayed until minute 16 | 3 | 0 | 3 | 1 | 3 | 0 |
| D: required safety context unknown | 3 | 3 | 0 | 0 | 0 | 3 |

B forces minute-14 alert to Must Review. C deliberately **does not** use the future malicious verdict
to prevent minute-14 deferral: its unsafe metric records the failure honestly. Historical decisions
and inputs in C are identical to A before outcome scoring and later recall observations.
These deliberately constructed results are not real-world workload or safety evidence.

## Verification and limitations

Focused tests cover chronology, strict ties, future lessons/verdicts/conflicts/context, activation,
expiry, policy effective/available timing, unchanged sampling, overrides, label isolation, missing
coverage, metrics, deterministic reordering, malformed histories, CLI formats and read-only SQLite.
The populated database test checks both byte SHA-256 and logical SQL dump equality and deliberately
attempts a write through the loader's read-only connection: SQLite rejects it.

Final verification on this increment:

| Check | Result |
| --- | --- |
| Full Python suite | 805 passed, 5 existing missing-fixture skips |
| Temporal tests | 29 passed |
| Temporal + documentation synchronization | 41 passed |
| Full frontend suite | 198 passed, 27 files |
| Browser routing/workflow regressions | 10 passed |
| TypeScript | Passed |
| Python OpenAPI / generated frontend schema checks | Passed |
| Vite production build | Passed; existing large-bundle warning |
| Git whitespace check | Passed |

No files in `apps/`, `config/`, `packages/contracts/` or `packages/detection/` changed.
The existing frontend jsdom navigation warnings remain non-failing.

Recorded network flows often predate their operational admission. Under occurrence-time evaluation
they can have **zero eligible historical alerts**. This is a coverage limitation, not permission to
backdate admission/context. An explicitly timestamped prospective dataset is needed for useful
historical operational evaluation. No ingestion-time substitution is silently made.

No counterfactual retraining, automatic activation, automatic actions, causal workload claim,
confidence interval or population-level safety estimate is included. The evaluator scans in-memory
history and targets demo/research scale. Legacy labels and linked-case findings are not borrowed as
V2 alert truth. Timestamp authenticity, event completeness, selective labelling and operator bias
require independent validation. Ambiguous observation timestamps fail clearly rather than choosing
an arbitrary table order. Future production policy algorithms need explicit version dispatch;
this increment supports versioned configurations of the unchanged V1 algorithm only.

Next recommended increment: prospective timestamped context/policy provenance collection, with a
frozen evaluation protocol, outcome-completeness reporting and independent temporal holdout data.

## Exact file manifest

Relative to `hitl-ids/`:

```text
packages/evaluation/temporal_review.py
packages/evaluation/temporal_source.py
packages/evaluation/temporal_fixture.py
scripts/evaluate_temporal_review.py
tests/test_temporal_review.py
docs/selective-review-temporal-evaluation.md
docs/HANDOVER.md
docs/system-workflow.md
```
