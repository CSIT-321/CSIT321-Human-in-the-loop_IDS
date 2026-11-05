# Slice 8 — Web: admin, evaluator, shared client and session

Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.

OUTPUT FILE: `analysis/codebase-review/slice-8.md` (the only file you may write).

FOCUS: Check role gating on the client (never the only guard), token handling, error states, and which admin/evaluator pages a final product should keep versus label as research.

FILES (23). Read every one of these. Do not search the tree for other files to review; you may open another file only to trace a caller or a symbol, and you must say so.

- `hitl-ids/apps/web/src/pages/admin/AuditPage.tsx`
- `hitl-ids/apps/web/src/pages/admin/CurrentAuditPage.tsx`
- `hitl-ids/apps/web/src/pages/admin/EvaluationAuditPage.tsx`
- `hitl-ids/apps/web/src/pages/admin/GovernancePage.tsx`
- `hitl-ids/apps/web/src/pages/admin/GuardrailsPage.tsx`
- `hitl-ids/apps/web/src/pages/admin/IpSecurityReportPage.tsx`
- `hitl-ids/apps/web/src/pages/admin/OverviewPage.tsx`
- `hitl-ids/apps/web/src/pages/admin/StatusPage.tsx`
- `hitl-ids/apps/web/src/pages/admin/UsersPage.tsx`
- `hitl-ids/apps/web/src/pages/admin/WorkspacesPage.tsx`
- `hitl-ids/apps/web/src/pages/evaluator/FinalV31Page.tsx`
- `hitl-ids/apps/web/src/pages/evaluator/MetricsPage.tsx`
- `hitl-ids/apps/web/src/pages/evaluator/RunPage.tsx`
- `hitl-ids/apps/web/src/pages/evaluator/ScenariosPage.tsx`
- `hitl-ids/apps/web/src/api/alertArrivalStream.ts`
- `hitl-ids/apps/web/src/api/client.ts`
- `hitl-ids/apps/web/src/api/useApi.ts`
- `hitl-ids/apps/web/src/session/roles.ts`
- `hitl-ids/apps/web/src/session/guards.tsx`
- `hitl-ids/apps/web/src/session/SessionContext.tsx`
- `hitl-ids/apps/web/src/components/states.tsx`
- `hitl-ids/apps/web/src/components/ui.tsx`
- `hitl-ids/apps/web/src/main.tsx`
