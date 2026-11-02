# Protocol V3 preflight result — not final evaluation results

**PASS. Protocol is FROZEN / UNOPENED and ready for a later explicitly authorized opening.**
No final 200-alert baseline/adaptive experiment, opening receipt or final collection was run.
Runtime base: `c00c556405198f60adc42f8bb2a7cee03689a60c`.
Branch: `feat/final-evaluation-protocol-v3`.

## Frozen artifacts

| Artifact | Canonical SHA-256 |
|---|---|
| Manifest | `08d83a43eaa6fa0cbd1ca8ff049c7cea52f9979cb8038d490e0ea0b6a435db37` |
| Operational workload | `63d8f2d3e5c9dc300acbce54cd6ad3cb1395ddb7267bb67fbd743e45bee9ff6e` |
| Trusted context | `f0556a3ec7f816dd7da94584d95578e21a6ee9184c948e29c598c55c842159c0` |
| External outcome oracle | `a5d882a8f9f7331ba0195f32851b53f35892e59c13a6eda86a1405dbab24d056` |
| Protocol JSON | `c2b1b94cbae968035114ab94ecad0836c00ffd6dcd07a816dd23eba79b2a7960` |

All policy hashes and source hashes are in the
[frozen manifest](../evaluation/protocol-v3/manifest.json). Runtime product/configuration diff is empty.
Protocol V2 retains `collectionOpened=false`; no product policy or migration was modified.

## Tests actually performed

`python -m pytest tests/test_protocol_v3.py tests/test_verdict_memory.py tests/test_conclusion_memory.py tests/test_analyst_work_claim.py tests/test_protocol_v2_freeze.py -q`

**81 passed, 0 failed**, with two existing dependency deprecation warnings (Starlette/httpx, AnyIO).
Of these, **18** are new V3-only generator/preflight/hash/denominator/no-opening/no-leakage tests.
The unchanged product regression suites cover authenticated ownership, revisions, retry deduplication,
cross-scope Exact/Narrow evidence, Tier 2 precedence and canonical corrections without extra votes.

`python scripts/validate_protocol_v3.py` → PASS: 200 alerts, Learning 40, Holdout 160,
primary 140, 90 distinct contexts. The 10 repeat-learning patterns use the actual five configured
Exact identity fields; distinct alert IDs, chronology, 8×3 stable + 2×3 drift, negative controls,
all Holdout strata and oracle/context coverage passed. The generator reproduced all frozen input hashes.
The final workload was parsed/validated only, never admitted or evaluated in a product DB.

Two fresh runs of the **same independent eight-alert DEVELOPMENT fixture** were performed:

```text
python scripts/smoke_protocol_v3.py --runtime-root ../../final-legacy-cleanup --out .pytest-tmp/v3-smoke-1
python scripts/smoke_protocol_v3.py --runtime-root ../../final-legacy-cleanup --out .pytest-tmp/v3-smoke-2
```

Both passed. No development identity overlaps any of the 200 final identities. In both arms the
runtime oracle-open probe was denied. The adaptive development lesson reached support 3 / Active
with three distinct authors through real claim/Verdict APIs. Its predefined contradiction moved it
to conflict_review; the two later development drift records required review. A separate development
Unknown alert created a formal Case. Effective vote violations and prospective collection rows were
zero. The second smoke additionally verified the final append-only feedback journal and final result
schema. Baseline/adaptive semantic decisions matched across fresh replays; random IDs/timestamps
were not compared as if they were research outcomes.

These are tool checks, **not an effectiveness percentage or results from the frozen 200-alert experiment**.
Compact proof is in [validation.json](../evaluation/protocol-v3-preflight/validation.json).
Only the optional formal opening commands in the [methodology](final-evaluation-protocol-v3.md)
should be used next, after authorization. Those commands were not executed in this increment.

## Interpretation and remaining boundaries

No BLOCKER or MAJOR preflight finding remains. The important pre-registered policy interaction is
that false-positive lessons can auto-activate at support 3 while actual Selective Review requires
support 5. Neither the requested workload nor the product policy was changed to improve a future
number. Audit sampling is untouched. First drift deferral is possible and is measured separately;
the critical target concerns unsafe deferrals after authoritative contradictory feedback.

The immutable input bundle and hashes are ready. Formal results, methodology acceptance and safety
acceptance still require the later experiment; this preflight does not claim those results in advance.
No response execution, runtime change, V2 change, merge, PR or final collection occurred.

The [exact file manifest](final-evaluation-protocol-v3-files.txt) lists all changes in this commit.
