# Guardrails under a fallible analyst — separate experiment

**Status.** Supporting research on the legacy flow-feedback pipeline. It does not touch the current
Suricata workflow, the V3.1 evaluation or any file under `apps`, `packages` or `config`.
Script: `scripts/evaluate_fallible_analyst.py`. Run `fallible-001`, outputs in
`evaluation/fallible-analyst/`.

## Why

The S15 three-arm evaluation could not test the guardrails (`evaluation-report.md`, findings 5
and 6). Its scripted analyst never makes a mistake, so no verdict pushed a real attack down and
arm C (guardrails off) was identical to arm B. That showed the sequence could not test them, not
that they are unnecessary. This experiment gives them something to do.

## Method (error model fixed before any run)

The S15 oracle sequence (40 verdicts) with one change: every 4th verdict that confirms or
escalates a real attack is replaced by `mark_false_positive`, so the analyst wrongly dismisses
25% of attack verdicts. Verdicts on benign flows stay correct. Deterministic; 25% is a stress
level, not an estimate of how often analysts are wrong. Arms are S15's: A no feedback, B fallible
verdicts with guardrails, C the same verdicts without. Two detection databases: `demo.db`
(the real detector) and `stress.db` (SYNTHETIC degraded detector). An oracle run on each is
included for comparison.

## Measures, and a correction made during the work

S15's `critical_floor_breaches` is not used. It compares a score with `critical_alert_threshold`
(80), not the guardrail's actual floor `critical_alert_floor` (70), and it also counts benign
alerts that were correctly dismissed. A first run reported 10 "breaches" for alerts that sat
exactly on the floor and 37 on a perfect-analyst run, which is a defect of the measure, not of
the guardrails. It was replaced by direct measures on real attacks only, against arm A. The error
model was not changed. S15's own numbers are unaffected because its analyst never pushed a score
down.

## Results

| Run | Arm | Real attacks dropped | Points lost | Below floor 70 | Infiltration below 75 | Dropped, never judged |
|---|---|---|---|---|---|---|
| demo, oracle | B guardrails on | 0 | 0 | 0 | 0 | 0 |
| demo, oracle | C guardrails off | 0 | 0 | 0 | 0 | 0 |
| demo, **fallible** (10 wrong) | B guardrails on | 10 | 290.0 | 0 | 0 | 0 |
| demo, **fallible** (10 wrong) | C guardrails off | 10 | 300.0 | 0 | 2 | 0 |
| stress, oracle | B guardrails on | 5 | 36.3 | 0 | 0 | 5 |
| stress, oracle | C guardrails off | 5 | 37.5 | 0 | 1 | 5 |
| stress, fallible (1 wrong) | B guardrails on | 6 | 61.3 | 0 | 0 | 5 |
| stress, fallible (1 wrong) | C guardrails off | 6 | 67.5 | 0 | 2 | 5 |

On the real detector (`demo`), the oracle moved nothing down. With the 10 wrong dismissals,
every dismissed attack lost points whether or not the guardrails were on.

## What this shows

1. **The guardrails worked as specified and bound only at the Infiltration floor.** In the
   fallible demo run the two wrongly dismissed Infiltration alerts were held at 75 with guardrails
   on (`capped`, `infiltration_alert_floor`, a 25-point drop) and fell to 70 with them off.
   Their measured benefit there was 10 points (290 vs 300 lost) and 2 Infiltration alerts kept
   above their floor.
2. **Nothing else was protected, because nothing needed to be.** Every flagged alert sits at 100
   (975 of 996 in S15). One dismissal subtracts 30, which lands exactly on the critical floor of
   70, so the floor and the 30-point cap coincide with a single dismissal's effect. No real attack
   fell below 70 in either arm. The floor of 70 and the cap of 30 were never separately tested
   because one wrong dismissal cannot exceed them.
3. **A perfect analyst still lowered real attacks on the degraded detector.** In `stress/oracle`,
   5 real attacks lost 36.3 points although every verdict was correct. All 5 were never judged:
   they were adjusted through family learning from other, correct verdicts. The guardrails
   reduced this by only 1.2 points. They limit how far a score moves, not whether a family
   propagation reaches an alert it should not.

## Limits

- 25% is a chosen stress level. It says nothing about how often real analysts are wrong.
- On `stress.db` the rule produced one wrong dismissal because the sequence there is mostly
  benign verdicts. That run has little power for the fallible question, and the pre-registered
  rule was not changed to compensate.
- One wrong dismissal per alert cannot test stacking. A single analyst repeatedly dismissing the
  same family (reaching the three-verdict learning gate) is not covered and would be a separate,
  pre-registered experiment.
- Detection metrics are identical in every arm; this changes the queue order, not the detector.
- This is the legacy flow-feedback pipeline. The final product's Triage Memory has its own
  safeguards and is not tested here.

## Reproduce

```
python scripts/run_ml_inference.py
python scripts/run_detection.py
python scripts/build_stress_detection.py
python scripts/run_detection.py --replay data/processed/stress_ml_predictions.json --database data/stress.db
python scripts/evaluate_fallible_analyst.py --run-id fallible-001
```

Needs SQLite with the NULL-tolerant `json_valid` CHECK constraints (see
`fix/sqlite-null-json-check`) on SQLite 3.38.4.
