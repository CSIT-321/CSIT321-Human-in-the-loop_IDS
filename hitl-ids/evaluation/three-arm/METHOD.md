# Three-arm evaluation — method (plan step S15)

What is kept here, and how to read it. The findings themselves are in
[`../../docs/evaluation-report.md`](../../docs/evaluation-report.md).

## The design

| Arm | Feedback | Guardrails | Purpose |
|---|---|---|---|
| A — control | none | on | what the system does unaided |
| B — treatment | scripted | on | the claim being tested |
| C — guardrail probe | the same scripted | **off** | what the guardrails prevented |

Each arm is a **byte copy of one detection database**, so dataset, model version, rule-set version
and seed are identical by construction. The feedback sequence and `guardrails_active` are the only
variables. "Guardrails off" is `GuardrailPolicy(active=False)`; only the 0–100 score range still
binds.

Ground truth is never in the schema. It is reached by exactly one join —
`alerts.id → flow_data.alert_id → flow_data.source_record_id → demo_ground_truth.json` — and never
through a detector's own output.

## Pre-registration

The feedback sequence is derived by a rule fixed **before any arm runs**, never chosen after seeing
a result. Rule `s15-preregistration-1`:

| | |
|---|---|
| Domain | flagged alerts (every queue band but `none`), in contract queue order |
| Subset | ≤ `max_per_family` (5) per family; families of ≥ `min_family_size` (8) only |
| Size | the first `size` (40) alerts satisfying both |
| Category | from ground truth — an oracle analyst: benign → `mark_false_positive`; severity ≥ 7.0 → `escalate`; else `confirm_true_positive` |
| Order | queue order; verdict *n* is timestamped `2026-01-01T00:00:00Z + n s` |

`max_per_family` must be ≥ the agreement gate's `min_feedback_count` (3), or no family could open
its gate and the treatment arm would be inert by construction. Families must retain untouched
members, or an effect on *similar* alerts is unmeasurable.

Changing the rule means changing its identifier and logging it in `plan-changelog.md`. A rule
changed to improve a result is the v0.2 exit criterion returning by the back door.

## Exit criterion (plan v0.3)

Whatever arm C shows is recorded **as measured**. A suppression count of zero means the guardrails
did not bind on that sequence: a publishable result, never grounds for re-sampling. The *guarantee*
that a floor binds lives in S7's unit tests, not here.

## Layout

```
history.jsonl                one line per run: arms, deltas, what the guardrails prevented
runs/<UTC run id>/
    config.json              the pre-registration, the pinned run config, the full sequence
    results.json             every metric for every arm, plus deltas B-A, C-A, C-B
```

Arm databases are written as `data/eval-<arm>.db` and are gitignored; they are regenerable in
seconds and are not the record.

## Reproducing

```
python scripts/run_detection.py        # only if data/demo.db is absent
python scripts/run_evaluation.py       # all three arms, ~3 s
python scripts/run_evaluation.py --dry-run     # print the sequence, run nothing
python -m pytest tests/test_evaluation.py
```

Use `C:/ProgramData/miniconda3/python.exe` — see HANDOVER §6 on the two interpreters.

## Reading the metrics

- **Ranks are 1-based** positions in the contract's queue order
  (`queue_priority ASC, combined_score DESC, id ASC`).
- **MRR** is the mean of 1/rank over *every* true positive, not the classic first-relevant-hit MRR:
  the analyst works the whole queue.
- **`adjusted` vs `rank_changed`.** `adjusted` means the system changed an alert's score or band.
  `rank_changed` includes alerts that merely drifted because others moved past them. Leakage is
  measured by `adjusted` in the `unrelated` group — never by rank, which is relative.
- **`saturation`** reports how many flagged alerts sit at the maximum score. Where a band is
  saturated the ranking formula has no headroom, and order inside it falls to the `id ASC`
  tie-break; every other number must be read in that light.
- **`signature_override` preservation is reported separately** (invariant I3), including when the
  database holds no such alert — in which case the rate is `null` with a note, not a flattering 100%.
