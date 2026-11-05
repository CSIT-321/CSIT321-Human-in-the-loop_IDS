# Slice 4 — V2 human workflow: work claim, verdict, Tier 2 cases, memory, selective review, response

Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.

OUTPUT FILE: `analysis/codebase-review/slice-4.md` (the only file you may write).

FOCUS: Check claim arbitration (it sleeps inside claim()), transaction ownership, and whether two verdict systems (legacy 5-category feedback vs V2 4-outcome verdict) can be unified for the Tier 1 view.

FILES (15). Read every one of these. Do not search the tree for other files to review; you may open another file only to trace a caller or a symbol, and you must say so.

- `hitl-ids/packages/detection/analyst_work.py`
- `hitl-ids/packages/detection/analyst_verdict.py`
- `hitl-ids/packages/detection/tier2_cases.py`
- `hitl-ids/packages/detection/investigation_assistance.py`
- `hitl-ids/packages/detection/triage_memory.py`
- `hitl-ids/packages/detection/selective_review.py`
- `hitl-ids/packages/detection/selective_review_policy.py`
- `hitl-ids/packages/detection/response_approval.py`
- `hitl-ids/packages/detection/response_policy.py`
- `hitl-ids/packages/detection/prospective_collection.py`
- `hitl-ids/config/analyst-work-claim-v1.json`
- `hitl-ids/config/triage-memory-v1.json`
- `hitl-ids/config/selective-review-v1.json`
- `hitl-ids/config/safe-memory-auto-activation-v1.json`
- `hitl-ids/config/tier2-assistance-v1.json`
