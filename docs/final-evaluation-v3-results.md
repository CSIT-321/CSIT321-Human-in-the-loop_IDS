# Final Evaluation V3 — blocked formal run

**BLOCKED — ENVIRONMENT DEVIATION. No valid final effectiveness result.**

The operator reused the preflight interpreter without verifying its minor version before opening.
It was Python **3.12.14**, while the frozen methodology's execution instructions require **Python 3.11**.
The frozen validator checks artifact identities but does not check interpreter version. This was an
execution error and validation gap, not an established product defect. No claim is made that the
version difference necessarily changed decisions. It nevertheless prevents claiming protocol compliance.
The discrepancy was detected during Adaptive; processing was stopped and all partial evidence retained.
No runtime, frozen runner, policy, oracle or workload was repaired or modified, and no final evaluator ran.

## Identity and lifecycle

- Runtime: `c00c556405198f60adc42f8bb2a7cee03689a60c`.
- Protocol: `final-evaluation-protocol-v3.0`, commit `398fd99a5c83d50ea51f521b74c328fe57185a36`.
- Branch: `feat/final-evaluation-v3-run`.
- Opened: `2026-11-02T08:52:13.774462+00:00`.
- Stop/status recorded: `2026-11-02T08:59:52.811957+00:00`. Final completion timestamp: **N/A**.
- Run state: **BLOCKED_ENVIRONMENT_DEVIATION / INCOMPLETE_INVALID_FOR_FORMAL_EFFECTIVENESS**.
- The immutable protocol bundle keeps its original frozen/unopened declaration; the separate opening
  and status receipts record this attempted opening and failure. Do not represent the run as unopened.
- Evidence manifest freezes failure evidence, **not COMPLETED / FROZEN RESULTS**.

## Freeze verification

Before opening and again after stopping: frozen validator PASS, exact 200/40/160/140 structure,
all 39 manifest-listed artifact hashes unchanged, clean exact-runtime checkout.

| Artifact | Verified SHA-256 |
|---|---|
| Protocol manifest | `08d83a43eaa6fa0cbd1ca8ff049c7cea52f9979cb8038d490e0ea0b6a435db37` |
| Workload | `63d8f2d3e5c9dc300acbce54cd6ad3cb1395ddb7267bb67fbd743e45bee9ff6e` |
| Oracle | `a5d882a8f9f7331ba0195f32851b53f35892e59c13a6eda86a1405dbab24d056` |

All policies/configs, generator, runners, worker, evaluator and methodology hashes remain unchanged.
V2 remains unchanged and unopened; neither database contains a prospective collection run.
**Hash verification does not establish interpreter-version compliance.**

## Execution evidence, not official effectiveness results

The first Baseline process was blocked by the Windows sandbox's asyncio socketpair restriction,
before any alert admission or decision. A minimal independent TestClient reproduced this failure;
the same probe outside the sandbox passed. That empty attempt is preserved under `baseline/`.
The unchanged runner then completed Baseline under `baseline-execution-2/`, using the original opening
and a fresh DB. Adaptive used a separate clean DB under `adaptive/`.

| Arm | Durable decisions | Learning | Holdout | Verdicts | Completed receipt |
|---|---:|---:|---:|---:|---|
| Initial sandbox Baseline | 0 | 0 | 0 | 0 | No |
| Baseline host execution | 160 | 0 | 160 | 0 | Yes, but environment noncompliant |
| Adaptive interrupted | 98 | 40 | 58 | 40 | No |

Adaptive DB contains 99 inbox rows; the last in-flight alert
has no completed durable decision and must not be counted as an assessed alert. Raw SQLite DB and
rollback-journal files are preserved locally, with checksums in `validation.json`, and are not committed.
The captured learning-end snapshot is retained as partial evidence, not an official Memory result.

## Requested metrics and tables

| Requested result | Status |
|---|---|
| Baseline / Adaptive primary review and No Immediate Review counts | Official values N/A: paired formal run incomplete/noncompliant |
| Primary denominator / split | Frozen design 140; Learning 40 / Holdout 160 unchanged |
| Reduction count/rate, total/safe/unsafe deferrals and unsafe rate | N/A; no final evaluator executed |
| Benign coverage and outcome completeness | Final N/A; captured outcome-to-decision hashes verified |
| Audit samples, human overrides, FP support gate, reason distribution | No official aggregates; partial raw events retained |
| Lessons, Active/Candidate, auto activations, support/conflicts | No official results; learning snapshot retained |
| Primary, stratum and Memory results tables | Not generated as final results |
| Drift timeline and post-contradiction safety | Not reached; cannot assess |
| Tier 2 safety controls | Full Adaptive controls not reached; cannot assess |
| R02 vs external unsafe deferrals | No paired comparison; baseline raw runtime metrics retained |
| Repeatability | Not performed; frozen methodology does not explicitly authorize a second completed formal run |

The pre-registered FP distinction remains support 3 for activation and support 5 for review reduction.
No extra examples or threshold changes were introduced. Deterministic audit sampling remains 10%.
No final charts are appropriate for this interrupted attempt.

## Validation and safety boundaries

Captured decisions have unique IDs and valid snapshot hashes. Each captured outcome refers to its
already durable decision hash. Baseline receipt hashes verify. The runtime's oracle-open guard remains
unchanged and the Baseline isolation probe passed. Adaptive passed the same mandatory probe before
writing decisions, but has no completion receipt. This is scoped evidence, not a claim that an incomplete
formal experiment passed every invariant. Learning-end one-alert-one-vote violations:
`[]`; no full-run safety certification.
No response actions were executed: preserved DB response recommendation/decision counts are zero;
runner action paths contain admission, review, claim and Verdict only. No collection runs exist.
No product code or protocol parameters changed. No merge or PR. No broad product tests were rerun.

## Reproducibility and next decision

See `../evaluation/protocol-v3-run-001/environment.json`, `commands.txt`, `validation.json`,
`startup-environment-incident.json`, `status.json`, `files.txt` and `evidence-manifest.json`.
The manifest records canonical text/JSON hashes and excludes itself; DB byte hashes are separately recorded.
No evidence was overwritten. Do not combine partial outcomes or restart silently under this opening.
Changing the frozen validator to enforce Python 3.11, or amending the allowed interpreter, requires a
separately versioned V3.x freeze and a documented reason before a newly authorized formal run.
This does not require a product-runtime change unless a separate review identifies a product defect.

**Assessor-ready conclusion:** This attempt was opened but halted because its Python interpreter did
not satisfy the frozen methodology. It provides no valid final paired estimate of review requirement
reduction or safety. Human-feedback effectiveness and final safety targets remain unassessed.
It is not ready for Final Report/Slides/Demo as successful evaluation evidence; it is ready only as a
transparent failure/deviation record. No detector accuracy, human-time, productivity, or significance
claims are supported.
