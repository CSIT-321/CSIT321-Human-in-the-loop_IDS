# Slice 7 — Web: analyst console

Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.

OUTPUT FILE: `analysis/codebase-review/slice-7.md` (the only file you may write).

FOCUS: The Tier 1 / Tier 2 views will be built here. Map what exists, what each component shows, and what must be added to restore the 13 lost items (fact 5). The deleted legacy components are in git at commit f1b74b6 (`git show f1b74b6:hitl-ids/apps/web/src/features/feedback/FeedbackPanel.tsx`) - judge whether restoring them is simpler than rebuilding.

FILES (31). Read every one of these. Do not search the tree for other files to review; you may open another file only to trace a caller or a symbol, and you must say so.

- `hitl-ids/apps/web/src/pages/analyst/CaseResolution.tsx`
- `hitl-ids/apps/web/src/pages/analyst/CollectionPanel.tsx`
- `hitl-ids/apps/web/src/pages/analyst/ConclusionLearning.tsx`
- `hitl-ids/apps/web/src/pages/analyst/ExternalAdmissionPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/InvestigationAssistance.tsx`
- `hitl-ids/apps/web/src/pages/analyst/InvestigationConclusion.tsx`
- `hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/ResponseRecommendations.tsx`
- `hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/Tier2CasesPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/TriageMemoryPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/TrustedContextPanel.tsx`
- `hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.tsx`
- `hitl-ids/apps/web/src/features/alert/AnalystVerdict.tsx`
- `hitl-ids/apps/web/src/features/alert/AnalystWork.tsx`
- `hitl-ids/apps/web/src/features/alert/DetectorProvenance.tsx`
- `hitl-ids/apps/web/src/features/alert/EvidencePanelCard.tsx`
- `hitl-ids/apps/web/src/features/alert/MlPanelCard.tsx`
- `hitl-ids/apps/web/src/features/alert/OperationalEvidence.tsx`
- `hitl-ids/apps/web/src/features/alert/OperationalQueue.tsx`
- `hitl-ids/apps/web/src/features/alert/SignaturePanelCard.tsx`
- `hitl-ids/apps/web/src/features/alert/SuricataEvidence.tsx`
- `hitl-ids/apps/web/src/features/alert/SystemRouting.tsx`
- `hitl-ids/apps/web/src/features/alert/VerdictLearning.tsx`
- `hitl-ids/apps/web/src/features/alert/EffectiveReview.ts`
- `hitl-ids/apps/web/src/features/workstation/Meter.tsx`
- `hitl-ids/apps/web/src/App.tsx`
- `hitl-ids/apps/web/src/components/layout/AnalystTour.tsx`
- `hitl-ids/apps/web/src/components/layout/AppShell.tsx`
- `hitl-ids/apps/web/src/components/layout/Sidebar.tsx`
- `hitl-ids/apps/web/src/components/layout/TopBar.tsx`
