# Slice 9 — Evaluation package and scripts

Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.

OUTPUT FILE: `analysis/codebase-review/slice-9.md` (the only file you may write).

FOCUS: Separate (a) scripts a final-product operator needs, (b) research/one-off scripts to archive, (c) dead scripts. Check the frozen-protocol checks that fail on every commit (fact 6) and propose the fix that keeps the frozen evidence verifiable without blocking development.

FILES (59). Read every one of these. Do not search the tree for other files to review; you may open another file only to trace a caller or a symbol, and you must say so.

- `hitl-ids/packages/evaluation/__init__.py`
- `hitl-ids/packages/evaluation/context_protocol.py`
- `hitl-ids/packages/evaluation/harness.py`
- `hitl-ids/packages/evaluation/metrics.py`
- `hitl-ids/packages/evaluation/prospective_recorded.py`
- `hitl-ids/packages/evaluation/scenario.py`
- `hitl-ids/packages/evaluation/selective_review.py`
- `hitl-ids/packages/evaluation/temporal_fixture.py`
- `hitl-ids/packages/evaluation/temporal_review.py`
- `hitl-ids/packages/evaluation/temporal_source.py`
- `hitl-ids/packages/evaluation/truth.py`
- `hitl-ids/scripts/build_demo_detection.py`
- `hitl-ids/scripts/build_openapi.py`
- `hitl-ids/scripts/build_protocol_v3_workload.py`
- `hitl-ids/scripts/build_samples.py`
- `hitl-ids/scripts/build_stress_detection.py`
- `hitl-ids/scripts/build_user_manual.py`
- `hitl-ids/scripts/check_protocol_v2_freeze.py`
- `hitl-ids/scripts/download_dataset.py`
- `hitl-ids/scripts/evaluate_protocol_v3.py`
- `hitl-ids/scripts/evaluate_protocol_v3_1.py`
- `hitl-ids/scripts/evaluate_recorded_collection.py`
- `hitl-ids/scripts/evaluate_selective_review.py`
- `hitl-ids/scripts/evaluate_temporal_review.py`
- `hitl-ids/scripts/freeze_protocol_v3.py`
- `hitl-ids/scripts/freeze_protocol_v3_1.py`
- `hitl-ids/scripts/fusion_demo_summary.py`
- `hitl-ids/scripts/import_suricata_eve.py`
- `hitl-ids/scripts/inspect_alert_v2.py`
- `hitl-ids/scripts/list_false_positives.py`
- `hitl-ids/scripts/make_diagrams.py`
- `hitl-ids/scripts/materialize_flow_queue.py`
- `hitl-ids/scripts/open_protocol_v3.py`
- `hitl-ids/scripts/open_protocol_v3_1.py`
- `hitl-ids/scripts/preview_triage_policy.py`
- `hitl-ids/scripts/ranking_experiment.py`
- `hitl-ids/scripts/rehearse_demo.py`
- `hitl-ids/scripts/retune_rules.py`
- `hitl-ids/scripts/run_detection.py`
- `hitl-ids/scripts/run_evaluation.py`
- `hitl-ids/scripts/run_ml_inference.py`
- `hitl-ids/scripts/run_protocol_v3_1_adaptive.py`
- `hitl-ids/scripts/run_protocol_v3_1_baseline.py`
- `hitl-ids/scripts/run_protocol_v3_adaptive.py`
- `hitl-ids/scripts/run_protocol_v3_baseline.py`
- `hitl-ids/scripts/scan_labels.py`
- `hitl-ids/scripts/serve_rehearsal.py`
- `hitl-ids/scripts/serve_routing_rehearsal.py`
- `hitl-ids/scripts/serve_s16_rehearsal.py`
- `hitl-ids/scripts/smoke_protocol_v3.py`
- `hitl-ids/scripts/smoke_protocol_v3_1.py`
- `hitl-ids/scripts/summarize_real_suricata.py`
- `hitl-ids/scripts/train_model.py`
- `hitl-ids/scripts/validate_protocol_v3.py`
- `hitl-ids/scripts/validate_protocol_v3_1.py`
- `hitl-ids/scripts/validate_real_suricata.py`
- `hitl-ids/scripts/validate_rule_set.py`
- `hitl-ids/scripts/write_rule_set.py`
- `hitl-ids/scripts/run_real_suricata.ps1`
