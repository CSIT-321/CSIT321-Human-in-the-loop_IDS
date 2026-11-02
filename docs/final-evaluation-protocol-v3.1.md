# Final Evaluation Protocol V3.1 — minimal environment amendment

**Version:** `final-evaluation-protocol-v3.1`. **Final status:** FROZEN / UNOPENED.
Runtime: `c00c556405198f60adc42f8bb2a7cee03689a60c`.
Branch: `feat/final-evaluation-protocol-v3-1`.

## Amendment reason and immutable history

The initial V3.0 formal run was stopped because the execution interpreter was Python 3.12.14 while
the frozen methodology required Python 3.11. No final effectiveness metrics were produced or reused.
Protocol V3.1 was therefore issued as a narrow methodological amendment that added explicit
environment enforcement. The evaluated runtime, 200-alert workload, oracle, policy thresholds,
chronology and metric definitions remained unchanged.

V3.0 protocol commit: `398fd99a5c83d50ea51f521b74c328fe57185a36`.
V3.0 blocked-run commit: `1d6c8ffd8f6c461bdd6f481ff006a803ae4c5c6e`, branch
`feat/final-evaluation-v3-run`. Run 001 remains **BLOCKED_ENVIRONMENT_DEVIATION / INVALID FOR FORMAL
EFFECTIVENESS RESULTS**. It is not a failed effectiveness result; it produced no valid final estimate.
The opening, Baseline, partial Adaptive, incident, status, hashes and failure report remain unchanged.
No result, database or partial decision from that attempt may be reused or combined with V3.1.

## Unchanged methodology

The [V3.0 methodology](final-evaluation-protocol-v3.md) remains normative for effectiveness design,
subject only to the explicit environment enforcement and separately named V3.1 artifacts below.
The old document's lifecycle declaration describes its original freeze, not the subsequent failed run.
The new bundle copies workload, trusted context, oracle, expected structure and result schema byte for
byte. The amendment comparison validates every original protocol field except protocolVersion, with
one new environmentRequirement field. Worker code is unchanged; evaluator arithmetic is identical.

| Dimension | V3.0 → V3.1 |
|---|---|
| Runtime SHA, runtime trees and policy/config hashes | Identical |
| Evaluation question, metrics and denominators | Identical |
| Workload, identities, chronology and human outcomes | Identical |
| Total / Learning / Holdout / primary | 200 / 40 / 160 / 140 |
| Learning | 24 stable benign, 6 drift benign, 10 negative controls |
| Holdout | 80 stable, 20 unseen benign, 40 unsafe, 10 Unknown/Tier 2, 10 drift |
| Baseline | Fresh DB, 160 Holdout, no learned Memory; product learning code remains enabled |
| Adaptive | Fresh DB, 40 learning then 160 Holdout; same three authenticated Analysts |
| Claim and Verdict | Real canonical actions, unchanged 750 ms arbitration |
| Outcome isolation | Durable decision first; oracle reveal second; unchanged worker file-open guard |
| Holdout feedback | None except the two predefined first drift contradictions |
| Memory | Exact benign only, support 3, agreement 0.67, conflicts 0, fixed 30 days |
| Selective Review | False Positive support 5; deterministic audit 10% |
| Expiry | No sliding renewal or post-expiry auto-reactivation |
| Drift, Tier 2, R02 and limitations | Identical |
| Protocol identity and bundle/tool paths | Separately identified V3.1 |
| Environment validation and receipt | Explicit fail-closed guards and version evidence added |

No alert identity regeneration, threshold tuning, metric redesign or product source change occurred.

| Frozen input | Canonical SHA-256, equal in both versions |
|---|---|
| Workload | `63d8f2d3e5c9dc300acbce54cd6ad3cb1395ddb7267bb67fbd743e45bee9ff6e` |
| Oracle | `a5d882a8f9f7331ba0195f32851b53f35892e59c13a6eda86a1405dbab24d056` |

The [machine comparison](../evaluation/protocol-v3.1/amendment-diff.json) supplies exact policy/tree
hashes, input equality and unchanged protocol fields. The new manifest binds tools, documentation,
requirements and the original frozen dependencies. V3.0 evidence hashes are checked separately.

## Environment contract and enforcement

Require `sys.version_info.major == 3` and `sys.version_info.minor == 11`. Any 3.11.x patch is allowed.
Python 3.10, 3.12 and other major/minor versions fail with a nonzero exit and:
`FAIL — ENVIRONMENT REQUIREMENT NOT SATISFIED: Protocol V3.1 requires Python 3.11.x; current interpreter is Python ...`.

The standard-library environment guard is checked by the validator before product imports, and at
the start of the callable validator. The opener independently checks before validation or creating
any output directory/receipt. Both runner entry points and their shared run function check before
reading workload or starting a worker/DB. A formal runner also verifies the opening's V3.1 version,
recorded Python 3.11 major/minor, environment fields and requirements hash, followed by the existing
manifest/runtime/output-root checks. Opening with 3.11 and executing an arm with 3.12 is rejected.
The evaluator also checks the interpreter; its metric logic is unchanged.

The opening receipt includes: pythonFullVersion, pythonMajor, pythonMinor, pythonPatch,
executablePath and platform under `environment`; plus protocolVersion, runtimeSha, manifestHash,
requirementsHash, openedAt, status, outputRoot and operatorAcknowledgement. Full patch/version and
OS evidence are recorded on the actual opening. The original immutable manifest remains frozen;
lifecycle is represented by the separate future receipt, as in V3.0.

This amendment prevents an incompatible interpreter from creating a formal opening receipt,
ensuring future runs fail before any experimental data are generated.

## Actual preflight and development evidence

Actual interpreter: **Python 3.11.18**.
Executable used:
`C:\Users\cheek\OneDrive\Documents\fyp_website\final-evaluation-protocol-v3-1\hitl-ids\.venv311\Scripts\python.exe`.
It is a new isolated virtual environment, installed using the unchanged `pip install -r requirements.txt`
contract. Exact pinned packages were retained. Unpinned/transitive requirements resolved within that
existing contract; installed versions are recorded, rather than claiming they are all pinned or equal
to the old 3.12 environment. No existing environment was upgraded.

92 focused tests passed (11 environment-amendment cases plus the original 81 protocol, canonical
vote-integrity, shared-claim and V2 freeze tests), with two upstream deprecation warnings.
Actual Python 3.12.14 executions of validator, opener and both runners rejected with nonzero exits
and no output directory/receipt/data. Unit tests cover 3.11 patch acceptance, 3.10/3.12 rejection,
independent opener enforcement when standalone validation is skipped, runner rejection, and opening
version/environment/requirements mismatch. No successful real formal opening is used as a test.

The existing independent 8-alert development fixture passed under 3.11.18: real admission, three
Analyst claims, four canonical Verdicts, support 1→2→3, automatic Exact learning and activation,
Selective Review, conflict withdrawal and Unknown Tier 2 Case. The fixture has no final-workload
identity overlap and creates no collection run. It is development evidence, not final effectiveness.

Actual 3.11 structural preflight, byte/hash equality, unchanged worker/evaluator proof, runtime-tree
and policy checks passed. [Validation evidence](../evaluation/protocol-v3.1-preflight/validation.json)
records exact versions, commands, 3.12 failures and smoke boundaries. Frozen input parsing in
preflight does not admit/process the final workload against a product database.

## Future commands — ONLY after new explicit authorization

From this branch's `hitl-ids` directory, use the verified 3.11 virtual environment explicitly.
The guard rejects a wrong environment even if `python` accidentally resolves elsewhere.
Use a clean exact-runtime checkout and a **new** output directory. Do not reuse V3.0 output.

```powershell
$py311 = (Resolve-Path .venv311/Scripts/python.exe).Path
$env:PYTHONUTF8 = '1'
& $py311 --version
& $py311 scripts/validate_protocol_v3_1.py
& $py311 scripts/open_protocol_v3_1.py --runtime-root ../../final-legacy-cleanup --out ../evaluation/protocol-v3.1-run-001 --ack OPEN-FINAL-V3.1
& $py311 scripts/run_protocol_v3_1_baseline.py --runtime-root ../../final-legacy-cleanup --opening ../evaluation/protocol-v3.1-run-001/opening.json --out ../evaluation/protocol-v3.1-run-001/baseline
& $py311 scripts/run_protocol_v3_1_adaptive.py --runtime-root ../../final-legacy-cleanup --opening ../evaluation/protocol-v3.1-run-001/opening.json --out ../evaluation/protocol-v3.1-run-001/adaptive
& $py311 scripts/evaluate_protocol_v3_1.py --baseline ../evaluation/protocol-v3.1-run-001/baseline --adaptive ../evaluation/protocol-v3.1-run-001/adaptive --out ../evaluation/protocol-v3.1-run-001/report
```

Use an execution environment that permits Windows asyncio socketpair (the sandbox blocked the old
attempt before admission). This is an OS execution permission, not a product or methodology patch.
Verify each command succeeds before continuing. Each arm creates a fresh DB and refuses overwrite.
Both arms must complete and the paired evaluator must pass before final metrics can be reported.
Do not change parameters, fix frozen code or overwrite a failed run after opening.

V3.1 is ready for a **newly authorized** final formal run after successful freeze. This amendment did
not open/run the final 200-alert experiment and generated no final effectiveness metrics. V2 remains
unchanged/unopened. No merge, PR, final collection or response execution occurred.
