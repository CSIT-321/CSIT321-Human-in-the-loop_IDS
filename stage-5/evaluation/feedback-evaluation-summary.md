# Stage 5 Feedback Evaluation Summary

Stage 5 applies append-only analyst feedback events to Stage 4 fused alerts through deterministic similarity matching, historical aggregation, eligibility gates, and guardrails.

The current evaluation uses a frozen calibration / held-out split. It does not claim chronological temporal evaluation because the current sample is not ordered by reliable operational time.

Ground truth is joined only after detection, fusion, feedback aggregation, and priority adaptation for evaluator-only records. It is not written to the analyst-facing alert artifact and is not used as adaptation input.

This is a prototype workload and priority evaluation, not production IDS performance.

## Overall Counts

- Total alerts: 995
- Evaluation split: frozen_calibration_held_out
- Calibration alert ids: 5
- Held-out alerts ranked: 995
- Held-out feedback ignored during ranking: 0
- Manual exception memory enabled: false
- Alerts adjusted: 0
- Alerts unchanged: 995
- Direct feedback applied count: 0
- Unmatched direct feedback count: 0
- Historical feedback adaptation count: 0
- Exception memory applied count: 0
- Ignored exception count: 0
- Guardrail applied count: 0
- Score adjustment guardrail count: 0
- Exception rejected by trust gate count: 0
- Low confidence exception ignored count: 0
- Insufficient feedback exception ignored count: 0

## Guardrail Metric Clarification

`guardrailAppliedCount` is a broad combined count. It includes both score-limiting guardrails and exception trust-gate rejections.

`scoreAdjustmentGuardrailCount` counts cases where a risk score adjustment was actually limited by a safety rule, such as maximum reduction, Critical alert floor, or Infiltration floor.

`exceptionRejectedByTrustGateCount` counts exception memory matches that were ignored because they did not meet trust requirements. This includes low confidence exceptions and exceptions with insufficient feedback evidence.

Trust-gate rejections do not change the risk score. For report writing, use the split metrics when describing whether feedback changed priority or whether an exception was rejected before adjustment.

## Adaptation Coverage

- Similarity match count: 204
- Similarity match coverage: 0.205
- Adaptation eligible count: 0
- Adaptation eligibility coverage: 0
- Actual adaptation count: 0
- Actual adaptation coverage: 0
- Generated historical memory count: 3
- Low evidence coverage rejection count: 0
- Low similarity rejection count: 995

## Risk Before And After Feedback

- Average risk before feedback: 43.4
- Average risk after feedback: 43.4
- Average risk change: 0
- High-risk threshold: 70
- High-risk alerts before: 421
- High-risk alerts after: 421

## Review Queue Before And After Feedback

- Review queue before: 421
- Review queue after: 421
- Reviewed benign before: 63
- Reviewed benign after: 63
- Reviewed malicious before: 358
- Reviewed malicious after: 358

## Ground Truth Evaluation

- Evaluated with ground truth count: 995
- Benign high-risk before: 63
- Benign high-risk after: 63
- Malicious high-risk before: 358
- Malicious high-risk after: 358
- True positive suppression count: 0
- Infiltration adjusted count: 0
- Infiltration guardrail count: 0

## Count By Analyst Feedback Status

- unchanged: 995

## Count By Adaptation Source

- none: 995

## Count By Feedback Recorded

- not_recorded: 995

## Notes

- Analyst feedback events are the source of truth. Generated historical feedback memory is derived data and should not be manually authored.
- This evaluation uses a frozen calibration / held-out split. It should not be described as temporal evaluation until reliable chronological ordering metadata is used.
- Ground truth is joined only after detection, fusion, feedback aggregation, and priority adaptation for evaluator-only records. It is not written to the analyst-facing alert artifact and is not used as adaptation input.
- Full evaluator-only records are reproducible from the runner and are not required as the primary committed evidence.
- Detection score is preserved as detectionScore/fusionRiskScore. Historical feedback affects operationalPriorityScore for ranking.
- Manual exception memory is disabled for formal adaptive evaluation so improvements can be attributed to analyst feedback events.
- This is a prototype feedback evaluation, not production IDS performance.
