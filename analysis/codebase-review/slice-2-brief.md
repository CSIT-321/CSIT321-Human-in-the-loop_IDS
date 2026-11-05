# Slice 2 — Detection core: fusion, signature, ML, pipeline, ranking, feedback, guardrail, audit

Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.

OUTPUT FILE: `analysis/codebase-review/slice-2.md` (the only file you may write).

FOCUS: The approved engine. The feedback/guardrail logic must be reachable from the final Tier 1 view for flow alerts. Find what the V2 changes broke or bypassed here (runner.py, store.py were modified).

FILES (25). Read every one of these. Do not search the tree for other files to review; you may open another file only to trace a caller or a symbol, and you must say so.

- `hitl-ids/packages/detection/fusion/__init__.py`
- `hitl-ids/packages/detection/fusion/cef.py`
- `hitl-ids/packages/detection/signature/__init__.py`
- `hitl-ids/packages/detection/signature/engine.py`
- `hitl-ids/packages/detection/signature/observable.py`
- `hitl-ids/packages/detection/signature/rule_set.py`
- `hitl-ids/packages/detection/ml/__init__.py`
- `hitl-ids/packages/detection/ml/inference.py`
- `hitl-ids/packages/detection/pipeline/__init__.py`
- `hitl-ids/packages/detection/pipeline/predictor.py`
- `hitl-ids/packages/detection/pipeline/runner.py`
- `hitl-ids/packages/detection/pipeline/source.py`
- `hitl-ids/packages/detection/pipeline/store.py`
- `hitl-ids/packages/detection/ranking/__init__.py`
- `hitl-ids/packages/detection/ranking/experiment.py`
- `hitl-ids/packages/detection/ranking/formulas.py`
- `hitl-ids/packages/detection/ranking/severity.py`
- `hitl-ids/packages/detection/feedback/__init__.py`
- `hitl-ids/packages/detection/feedback/learning.py`
- `hitl-ids/packages/detection/feedback/service.py`
- `hitl-ids/packages/detection/guardrail/__init__.py`
- `hitl-ids/packages/detection/guardrail/policy.py`
- `hitl-ids/packages/detection/audit/__init__.py`
- `hitl-ids/packages/detection/audit/writer.py`
- `hitl-ids/packages/detection/triage.py`
