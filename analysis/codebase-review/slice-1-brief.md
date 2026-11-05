# Slice 1 — Contracts, schema and migrations

Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.

OUTPUT FILE: `analysis/codebase-review/slice-1.md` (the only file you may write).

FOCUS: The data dictionary. Check every migration in db.py, the append-only triggers, CHECK constraints, and whether legacy and V2 tables model the same concept twice.

FILES (26). Read every one of these. Do not search the tree for other files to review; you may open another file only to trace a caller or a symbol, and you must say so.

- `hitl-ids/packages/contracts/__init__.py`
- `hitl-ids/packages/contracts/canonical.py`
- `hitl-ids/packages/contracts/db.py`
- `hitl-ids/packages/contracts/models.py`
- `hitl-ids/packages/contracts/operational_v2.py`
- `hitl-ids/packages/contracts/suricata_bundle.py`
- `hitl-ids/packages/contracts/analyst_verdict.sql`
- `hitl-ids/packages/contracts/analyst_work.sql`
- `hitl-ids/packages/contracts/conclusion_memory.sql`
- `hitl-ids/packages/contracts/external_inbox.sql`
- `hitl-ids/packages/contracts/external_operational_admission.sql`
- `hitl-ids/packages/contracts/operational_v2.sql`
- `hitl-ids/packages/contracts/prospective_collection.sql`
- `hitl-ids/packages/contracts/response_approval.sql`
- `hitl-ids/packages/contracts/routing_workflow.sql`
- `hitl-ids/packages/contracts/safe_memory_auto_activation.sql`
- `hitl-ids/packages/contracts/schema.sql`
- `hitl-ids/packages/contracts/selective_review.sql`
- `hitl-ids/packages/contracts/suricata_capture_scope.sql`
- `hitl-ids/packages/contracts/suricata_system_routing.sql`
- `hitl-ids/packages/contracts/tier2_case_resolution.sql`
- `hitl-ids/packages/contracts/tier2_cases.sql`
- `hitl-ids/packages/contracts/triage_memory.sql`
- `hitl-ids/packages/contracts/triage_policy_v1.sql`
- `hitl-ids/packages/contracts/trusted_context.sql`
- `hitl-ids/packages/contracts/verdict_memory.sql`
