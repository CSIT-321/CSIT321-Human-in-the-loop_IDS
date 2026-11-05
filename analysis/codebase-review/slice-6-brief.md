# Slice 6 — API: V2 routes and the published contract

Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.

OUTPUT FILE: `analysis/codebase-review/slice-6.md` (the only file you may write).

FOCUS: Check that handlers and the hand-authored contract (contract/openapi.py) agree, N+1 query paths (operational_queue.summary computes effective_review per alert), and which endpoints the final Tier 1 / Tier 2 views need versus which are research-only.

FILES (25). Read every one of these. Do not search the tree for other files to review; you may open another file only to trace a caller or a symbol, and you must say so.

- `hitl-ids/apps/api/routing_routes.py`
- `hitl-ids/apps/api/verdict_routes.py`
- `hitl-ids/apps/api/work_routes.py`
- `hitl-ids/apps/api/tier2_case_routes.py`
- `hitl-ids/apps/api/memory_routes.py`
- `hitl-ids/apps/api/selective_review_routes.py`
- `hitl-ids/apps/api/context_routes.py`
- `hitl-ids/apps/api/external_admission_routes.py`
- `hitl-ids/apps/api/response_routes.py`
- `hitl-ids/apps/api/collection_routes.py`
- `hitl-ids/apps/api/operational_queue.py`
- `hitl-ids/apps/api/current_audit.py`
- `hitl-ids/apps/api/final_v3_routes.py`
- `hitl-ids/apps/api/final_v3_records.py`
- `hitl-ids/apps/api/contract/__init__.py`
- `hitl-ids/apps/api/contract/admin_current.py`
- `hitl-ids/apps/api/contract/alerts.py`
- `hitl-ids/apps/api/contract/auth.py`
- `hitl-ids/apps/api/contract/common.py`
- `hitl-ids/apps/api/contract/current_audit.py`
- `hitl-ids/apps/api/contract/external_admission.py`
- `hitl-ids/apps/api/contract/openapi.py`
- `hitl-ids/apps/api/contract/operations.py`
- `hitl-ids/apps/api/contract/responses.py`
- `hitl-ids/apps/api/contract/routing.py`
