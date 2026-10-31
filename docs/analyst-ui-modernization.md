# Analyst UI modernization

## Architecture and scope

OLD: Signature + XGBoost fusion-centric console.

NEW: Detector-agnostic HITL operational console:

Detector source → Canonical Alert → Tier 1 → Tier 2 Candidate → Tier 2 Case → Investigation,
with Triage Memory guidance and Selective Human Review.

Suricata is the primary operational IDS source. XGBoost remains a supported secondary / historical
ML detector. The Custom Signature Engine remains legacy compatibility evidence. Nothing in this
change retrains models, changes detector output, or changes operational policy.

Base: `2019e298f149240fdd52d28c0a704321afaceebb` (`feat/prospective-protocol-v2-freeze`).
Implementation branch: `feat/analyst-ui-modernization`.

## Navigation and compatibility

| Group | Pages |
| --- | --- |
| Operations | Dashboard, Incoming Alerts, Analyst Workspace, Tier 2 Cases |
| Learning & Automation | Triage Memory, Selective Review |
| Insights | Analytics |
| Legacy | Legacy Workstation |

Analyst login and role redirects land on `/analyst/dashboard`.
`/analyst/overview` redirects to the Dashboard. The recorded-flow overview is retained at
`/analyst/legacy-overview`, linked from Analytics.

`/analyst/inbox` is the canonical Incoming Alerts route; `/analyst/external-admission` remains usable.
`/analyst/workspace` is the canonical Analyst Workspace route; `/analyst/v2-triage` remains usable,
including alertRef query links. Other existing queue, alert, investigation and feedback routes remain
usable and intentionally accessible from the Legacy Analytics area. Admin/evaluator authorization
and routes remain intact.

## Dashboard data and hierarchy

1. Actionable status: Needs Human Review, Tier 2 Candidates, Open Tier 2 Cases, Incoming Alerts.
2. Review automation: Must Review, Recommended Review, No Immediate Review, recalls and audit samples.
3. Security activity: top detections, categories and source distribution from incoming alert evidence.
4. Human learning: Active Memory, Eligible for Activation, Conflict Review.
5. Trends and Analytics entry point.

Counts use existing typed APIs. List aggregation follows pagination, without sorting operational
queues or changing backend ranking. Incoming Alerts counts non-admitted records, including held
records. Needs Human Review combines must-review and recommended-review metrics. Open cases include
open and investigating cases. Security breakdowns explicitly disclose their incoming-alert scope;
they are not represented as global cross-detector totals. Missing time-series APIs are disclosed,
not replaced with fabricated charts. No legacy fusion metrics appear on the primary Dashboard.

**No Immediate Review is not a human verdict.**

## Sidebar, themes and accessibility

Desktop navigation expands to icons and labels or collapses to labelled icons with native tooltips.
The content grows into the released width. `hitl.sidebar.collapsed` persists locally. Mobile uses
an explicit Navigation disclosure independent of the desktop preference. Controls are native keyboard
buttons; links retain accessible names and aria-current, and toggles expose aria-expanded.

The global Light/Dark toggle persists `hitl.theme`. Semantic CSS tokens cover surfaces, text, borders,
links, primary actions, warning/success/danger states, severity and chart colors. Existing forms,
tables and charts inherit the same tokens. Focus-visible outlines remain available. State is named
in text, rather than indicated only by color. UUIDs and snapshots wrap; wide tables scroll locally.

## Incoming Alerts and Analyst Workspace

The admission journey is Incoming Alert → Eligibility Review → Admit to HITL → Open in Analyst
Workspace. Existing review/admission calls, optimistic concurrency versions and request IDs are
unchanged. Eligibility review and operational admission remain separate decisions.

Workspace prioritizes detection identity, operational urgency, review disposition, workflow stage,
plain-language reasons and a recommended next action. Deep links avoid redundant queue selection
controls. Section links lead to Overview, Evidence & Safety, Memory, Actions and Technical Details.

Native Severity remains detector-native. Operational Priority remains the platform score/band.
Tier is a workflow escalation level. Review Disposition is attention policy, not a verdict.
Confidence appears only when supplied; absent Suricata confidence reads **Not provided**.

The workflow indicator highlights the existing backend route/stage. It does not introduce transitions.
Supplied safety reason codes are translated for primary explanations; original codes and immutable
snapshots remain available in technical/safety evidence. Trusted Context is shown with its provenance.
Review changes refresh the overview; periodic refresh reflects subsequent safety changes.

## Detector-specific evidence

The shared evidence presentation uses Canonical Alert provenance. Suricata shows native detector
facts and raw source evidence, without Signature/ML panels. XGBoost shows supplied model version,
prediction, confidence and explanation availability. TreeSHAP evidence is retained when supplied.
`current_flow` is labelled **Legacy Flow Detector**. Its Signature and XGBoost panels and immutable
structured evidence remain available under an explicit legacy label. Existing legacy API responses
without canonical provenance retain historical panels for compatibility.

## Tier 1 to Tier 2

Manual escalation still produces a candidate, not a case. The view scrolls back to the overview and
shows **Escalated to Tier 2 Candidate** and **A formal Tier 2 Case has not been created yet**.
A prominent Create Tier 2 Case link leads directly to the adjacent form. Required fields remain:
case title, Tier 1 handoff summary and case creation reason. Helper text explains both narrative
fields. Successful creation navigates directly to the returned case UUID.

Case pages group Case Summary, Tier 1 Handoff, Detector Evidence, Investigation, Response and
Timeline / Audit. Investigation notes, findings and linked alerts retain their original commands.
A case can begin investigation through an explicit reasoned action. Response approval/rejection
retains revision and authorization checks. **Approved — Not Executed** is stated explicitly;
no response execution behavior is added.

## Learning, automation and legacy boundary

Triage Memory remains under Learning & Automation, grouped by Active, Eligible for Activation,
Conflict Review, Candidate, Expired and Rejected (within the loaded page). Human analyst outcomes
and derived memory lessons are explicitly distinguished. Memory does not retrain XGBoost.

Selective Review remains a standalone monitoring page. Per-alert policy, safety evidence, memory
and override controls remain available in Workspace. Research / prospective controls are within
Advanced / Research & Evaluation disclosures, not primary SOC navigation.

Analytics links to **Legacy Flow Detector Analytics**, preserving Signature override, Model only,
Corroborated, Nothing flagged it and the historical fusion distribution. Legacy recorded-flow
analytics and feedback views are not presented as the current architecture.

## Validation and limitations

Browser tests use the real Vite frontend and FastAPI backend with disposable synthetic databases.
The routing rehearsal script gains an opt-in `--pristine` flag using the existing S16 fixture builder;
it does not read or modify `data/demo.db`. This is the only Python file changed, and it is test tooling.
No backend application, contracts, schema, algorithms, policies, routing, response logic or protocol
files change. Protocol V2 remains unopened. No collection is opened, no attack traffic generated,
no real response executed, no merge and no PR created. The independent remnant audit is not part of
this implementation.

Prospective browser scenarios are updated for navigation/disclosures but are not executed because
they open collection runs. Existing Protocol V2 freeze checks run without opening collection.

Known API/UI limits: security activity is scoped to incoming evidence; no operational time-series
endpoint exists; dashboard counts span several reads rather than an atomic snapshot. Dashboard
aggregation may become expensive with very large lists. Legacy workstation remains a dense
historical interface. XGBoost-only provenance has component coverage; the real backend fixture
supplies historical fused/ML evidence, not a standalone XGBoost ingestion path. Production build
retains the existing large-bundle warning. This does not claim a formal accessibility certification.

### Final checks

- Full frontend suite: **213 tests passed across 30 files**.
- TypeScript (`tsc -b`): passed.
- OpenAPI source check (`build_openapi.py --check`): passed.
- Generated TypeScript schema (`openapi-typescript --check`): passed; no schema changes.
- Vite production build: passed (existing >500 kB bundle warning).
- Routing browser suite: **12 passed**, including the modernization journey and responsive matrix.
- S16 browser narrative: **1 passed**, using its pristine synthetic fixture.
- Routing, Tier 2 and Protocol V2 freeze backend checks: **71 passed**.
- Prospective browser collection/override scenarios: not run, to honor the no-collection restriction.
- `git diff --check`: passed.

Browser viewport matrix: 1440, 1024 and 390 pixels, in both Dark and Light themes. Dashboard,
Incoming Alerts, Workspace, Tier 2 Cases, Triage Memory, Selective Review, Analytics and Legacy
Analytics passed document/main overflow assertions. Keyboard collapse/expand and reload persistence
were verified. The end-to-end journey recorded eligibility, admission, manual escalation, explicit
case creation, investigation note and finding on disposable data; it checked old deep links,
Suricata missing confidence and legacy evidence. Response regression verified approval without execution.

### Screenshot review

Screenshots are generated under `hitl-ids/apps/web/test-results/` (local QA artifacts, not source).
The following were opened and visually inspected, not just DOM-asserted:

| View | Artifact |
| --- | --- |
| Dark Dashboard, expanded | `modern-dark-dashboard.png` |
| Dark Dashboard, collapsed | `modern-collapsed-dashboard.png` |
| Light Dashboard | `modern-light-dashboard.png` |
| Incoming Alerts | `modern-incoming.png` |
| Suricata Workspace | `modern-suricata-workspace.png` |
| Tier 2 Candidate | `modern-tier2-candidate.png` |
| Tier 2 Case | `tier2-case-desktop.png` |
| Legacy XGBoost / signature evidence | `modern-legacy.png` |
| 390px Dark Workspace | `modern-mobile-workspace.png` |
| 390px Light Workspace | `modern-light-mobile.png` |
| 390px Light Dashboard | `modern-light-dashboard-390.png` |
| 1024px Dark Dashboard | `modern-dark-dashboard-1024.png` |

Review fixes included translating technical reasons, removing redundant deep-link queue controls,
making case creation prominent, improving muted-text contrast, and keeping numeric scores together.
No obvious page-level overflow or theme/readability defect remained in the reviewed operational views.

### Exact changed-file inventory

All paths below are repository-relative. No generated runtime dependencies or databases are committed.


- `docs/analyst-ui-modernization.md`
- `hitl-ids/apps/web/e2e/analyst-modernization.spec.ts`
- `hitl-ids/apps/web/e2e/demo.spec.ts`
- `hitl-ids/apps/web/e2e/detector-foundation.spec.ts`
- `hitl-ids/apps/web/e2e/external-admission.spec.ts`
- `hitl-ids/apps/web/e2e/prospective-collection.spec.ts`
- `hitl-ids/apps/web/e2e/prospective-override.spec.ts`
- `hitl-ids/apps/web/e2e/response-approval.spec.ts`
- `hitl-ids/apps/web/e2e/routing-workflow.spec.ts`
- `hitl-ids/apps/web/e2e/selective-review.spec.ts`
- `hitl-ids/apps/web/e2e/tier2-case.spec.ts`
- `hitl-ids/apps/web/e2e/triage-memory.spec.ts`
- `hitl-ids/apps/web/playwright.config.ts`
- `hitl-ids/apps/web/playwright.prospective.config.ts`
- `hitl-ids/apps/web/playwright.routing.config.ts`
- `hitl-ids/apps/web/src/App.tsx`
- `hitl-ids/apps/web/src/components/layout/AppShell.tsx`
- `hitl-ids/apps/web/src/components/layout/Sidebar.tsx`
- `hitl-ids/apps/web/src/components/layout/TopBar.tsx`
- `hitl-ids/apps/web/src/features/alert/DetectorEvidence.tsx`
- `hitl-ids/apps/web/src/features/alert/DetectorProvenance.test.tsx`
- `hitl-ids/apps/web/src/features/alert/DetectorProvenance.tsx`
- `hitl-ids/apps/web/src/features/workstation/AlertPane.tsx`
- `hitl-ids/apps/web/src/index.css`
- `hitl-ids/apps/web/src/pages/admin/__tests__/ipSecurityReport.test.tsx`
- `hitl-ids/apps/web/src/pages/analyst/AlertDetailPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/AnalyticsPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/DashboardPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/ExternalAdmissionPage.test.tsx`
- `hitl-ids/apps/web/src/pages/analyst/ExternalAdmissionPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/LegacyAnalyticsPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/Modernization.test.tsx`
- `hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.test.tsx`
- `hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/Tier2CasesPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/TriageMemoryPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx`
- `hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/WorkstationPage.tsx`
- `hitl-ids/apps/web/src/pages/analyst/__tests__/dashboard.test.tsx`
- `hitl-ids/apps/web/src/pages/analyst/__tests__/overview.test.tsx`
- `hitl-ids/apps/web/src/pages/analyst/reviewLanguage.ts`
- `hitl-ids/apps/web/src/session/roles.test.ts`
- `hitl-ids/apps/web/src/session/roles.ts`
- `hitl-ids/apps/web/src/test/setup.ts`
- `hitl-ids/apps/web/src/test/shell.test.tsx`
- `hitl-ids/scripts/serve_routing_rehearsal.py`
