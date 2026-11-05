# Slice 3 — V2 intake, routing and escalation

Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.

OUTPUT FILE: `analysis/codebase-review/slice-3.md` (the only file you may write).

FOCUS: This is where automatic Tier 1 -> Tier 2 escalation lives. Judge exactly how a flow alert could be routed through the same path, and what a foolproof auto-escalation (fact 7) must change here.

FILES (20). Read every one of these. Do not search the tree for other files to review; you may open another file only to trace a caller or a symbol, and you must say so.

- `hitl-ids/packages/detection/adapters/__init__.py`
- `hitl-ids/packages/detection/adapters/admission_policy.py`
- `hitl-ids/packages/detection/adapters/current.py`
- `hitl-ids/packages/detection/adapters/operational_v2.py`
- `hitl-ids/packages/detection/adapters/staging.py`
- `hitl-ids/packages/detection/adapters/suricata.py`
- `hitl-ids/packages/detection/adapters/suricata_bundle.py`
- `hitl-ids/packages/detection/external_admission.py`
- `hitl-ids/packages/detection/system_routing.py`
- `hitl-ids/packages/detection/routing.py`
- `hitl-ids/packages/detection/triage_policy.py`
- `hitl-ids/packages/detection/triage_policy_service.py`
- `hitl-ids/packages/detection/attack_classification.py`
- `hitl-ids/packages/detection/tier2_escalation.py`
- `hitl-ids/packages/detection/context_store.py`
- `hitl-ids/packages/detection/trusted_context.py`
- `hitl-ids/config/system-routing-v1.json`
- `hitl-ids/config/operational-triage-v1.json`
- `hitl-ids/config/suricata-classification-v3.json`
- `hitl-ids/config/external-admission.json`
