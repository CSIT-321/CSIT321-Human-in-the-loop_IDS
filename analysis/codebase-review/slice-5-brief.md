# Slice 5 — API: legacy routes, auth, deps, mappers, main, workspaces

Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.

OUTPUT FILE: `analysis/codebase-review/slice-5.md` (the only file you may write).

FOCUS: Security focus: RBAC on every route, the JWT secret default, workspace switching (one global database selection for every user), the SSE stream, path handling in workspaces.

FILES (11). Read every one of these. Do not search the tree for other files to review; you may open another file only to trace a caller or a symbol, and you must say so.

- `hitl-ids/apps/api/routes.py`
- `hitl-ids/apps/api/auth.py`
- `hitl-ids/apps/api/deps.py`
- `hitl-ids/apps/api/mappers.py`
- `hitl-ids/apps/api/main.py`
- `hitl-ids/apps/api/read_only.py`
- `hitl-ids/apps/api/workspaces.py`
- `hitl-ids/apps/api/workspace_routes.py`
- `hitl-ids/apps/api/presentation_replay.py`
- `hitl-ids/apps/api/alert_stream_routes.py`
- `hitl-ids/apps/api/admin_current_routes.py`
