# Prospective Collection Protocol V2

## Status and scope
Repository preregistration record; collection is NOT open. No external registry submission, actual
collection run, human recruitment, or consent is implied. Freeze this commit and its manifest in the
project's designated preregistration record before the start. The timestamp is the observed UTC time
when this registration artifact was prepared; the Git commit supplies publication evidence.

Final readiness verdict: PASS WITH NON-BLOCKING LIMITATIONS.
Reviewed implementation: 7a961450dda7aa193653180f2d4c03b2a24ac5bb.
Review branch: feat/prospective-readiness-unbound-override-integrity.
This new branch carries artifacts only, not an additionally reviewed runtime build.

Objective: measure whether actual recorded selective-review decisions reduce immediate review volume
without concealing malicious/suspicious deferrals. Mode: prospective_recorded, not retrospective
reconstruction. All original policies and Protocol V1 remain unchanged.

## Window and participants
Asia/Singapore (+08:00):
- Holdout start: 2026-11-03T00:00:00+08:00 (inclusive).
- Holdout end: 2026-11-17T00:00:00+08:00 (exclusive).
- Outcome cutoff: 2026-11-20T00:00:00+08:00 (exclusive).
- Minimum 100 unique eligible alerts and 95% informative outcomes: targets, not power guarantees.

User-confirmed class: proxy/student analyst. Do not describe participants as professional analysts.
Codex/Playwright is system verification only, never human UAT or timing evidence.
No participants, alerts or outcomes have been fabricated. Confirm actual participants/consent separately.
If registration and explicit opening cannot complete before the start, leave unopened and preregister
a new future-window version. Do not edit or backdate this frozen record.

## Configuration manifest
config/prospective-protocol-v2-manifest.json contains all eight pre-existing config JSONs plus the new
V2 protocol. This deliberately includes upstream admission and visual config, and preserves V1/draft
hashes even though they are not the active V2 definition. Algorithm: Python json.dumps with sorted keys,
separators comma/colon, ensure_ascii=True, allow_nan=False; SHA-256 over UTF-8 bytes. Line endings and
JSON indentation do not affect hashes. Version, keys and values do.

The protocol hashes its source configurations; the manifest hashes the complete protocol. No circular
self-hash. The checker pins that protocol hash. Git commit/review is the authenticity anchor; these are
not signed attestations. Policy constants, detector/model paths and dependencies are pinned by reviewed
source, not rewritten as config. Preserve input/model provenance separately with the collection archive.
Database-resident historical lesson configurations, facts, guardrail/input state and outcomes are evolving
evidence, not silently represented as frozen config files. Preserve their decision-time snapshots and
availability boundaries; do not retroactively replace them with current configuration.

## Gate before opening
Run the new read-only checker against the artifact branch with --artifacts-only for artifact validation.
That mode does NOT qualify a runtime or authorize opening.

Deploy a separate clean checkout at the exact reviewed SHA. Run the checker by its absolute path from
the artifact checkout, with --source pointing to that reviewed checkout's hitl-ids directory, --artifacts
pointing to this artifact checkout's hitl-ids directory, and --pre-open. The gate rejects a changed runtime
SHA, dirty tracked/untracked source, any listed config mismatch, or a missed start. Do not deploy this
documentation branch as though it were the reviewed runtime. No branch switching/deployment is done here.

The existing operational API is unchanged and does not automatically load this standalone protocol.
Later, an authorized administrator must explicitly create a run with these exact dates, targets,
participant class, evidence basis and review reference. Inspect the resulting frozen snapshot against
this manifest before an explicit open action. A generic run with a matching name is not sufficient.
Recheck the gate throughout collection; policy/source changes require stopping qualification under V2
and a separately reviewed version. This is a registration procedure, not a new API enforcement hook.

## Metrics and evidence
The JSON protocol freezes every metric definition and denominator. Immediate review includes Must Review
and Recommended Review. First eligible applied decision defines the cohort; repeated evaluations and
recorded overrides remain in the ledger. Unbound valid overrides can contribute recall without adding
to decisionCount. Missing/inconclusive outcomes remain in the completeness denominator.

Primary report fields already exist in the reviewed evaluator. Conflict-attributed recalls, override
counts and unknown/expired/conflicting context breakdowns are supplementary archive-derived definitions,
not newly implemented API fields. They require a separately reviewed read-only analysis of validated
frozen inputs before being reported. Missing observations are unobserved, not zero. Context breakdowns
can overlap; conflict association is not proof of causation.

Review-volume reduction != analyst-time/workload reduction. This unpaired protocol can support a
percentage reduction in alerts requiring immediate review, not a percentage reduction in human time.
Stopwatch durations/errors/rework may be reported descriptively; automated timing is excluded.

## Evaluation and safety
Keep immutable occurred/admitted/eligible/decision/outcome timestamps, actor, policy/config identity,
memory, context provenance, route/stage/priority, disposition/reasons and input fingerprints.
No future fact, outcome, lesson or configuration may rewrite an earlier decision.
After cutoff, close the run and use the reviewed read-only export/evaluator (mode=ro, query_only).
Retain export/report hashes and validate all consumed evidence; corrupted archives fail, not silently
lose rows. Report actual achieved sample and completeness even when targets are missed.

Unknown is not false. Unknown/expired/conflicting required context means Must Review.
No Immediate Review is not closure, a false-positive label, or a human verdict.
Human override stays available regardless of collection eligibility.
Use approved recorded/offline inputs only; no attacks, live traffic generation or real response actions.

## Limitations and next action
Archive consistency is not cryptographic source authentication. Human identity and input provenance
need independent records. Synthetic/browser tests are not production evidence. The readiness review was
a fresh same-agent review, not a separate-model attestation. Supplementary analysis and a paired timing
study are not silently supplied by this freeze.

Next: preserve the exact artifact commit in the designated preregistration record, verify the frozen
runtime in a disposable browser rehearsal, then separately authorize an explicit open before the start.
Do not open now. No automated collection action is included in the checker.

## Verification
Protocol freeze tests plus existing prospective collection/blocker suites: 81 passed (22 new tests).
Artifact check passed. Runtime pre-open negative control rejected the dirty artifact worktree as required.
Reviewed runtime/policy files, V1 and the prior draft have zero diff from the reviewed SHA.
Source demo.db hash/mtime remained unchanged. No collection run was created outside disposable tests.
Full frontend/browser suites were not rerun for this artifact-only increment; a final frozen-runtime
browser verification is still required before opening.
