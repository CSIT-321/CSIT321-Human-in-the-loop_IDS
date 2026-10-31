# Conservative Analyst UI refinement

Base: `2019e298f149240fdd52d28c0a704321afaceebb` (`feat/prospective-protocol-v2-freeze`).
Branch: `feat/analyst-ui-refinement`. The modernization branch remains at
`944445b88bf84f8b930a996d45bd7c1e695934b6`; no modernization changes were merged or copied.

## Preserved

The original dark SOC palette, typography, square cards, navigation order, Dashboard cards/charts,
Workstation queue/alert/context columns, full-page evidence grid, and all five alert tabs remain.
Existing routes, deep links, API contracts, queue ranking and backend business logic are unchanged.
Mobile retains the existing horizontal navigation approach; the Workstation panes stack only on small screens.
The final UI still visually resembles the original application.

## Necessary corrections

- Sidebar: an accessible native button switches between original labels and compact abbreviations with
  accessible names/tooltips. `hitl-ids.sidebar-collapsed` persists the preference locally. Mobile links scroll within the navigation.
- Theme: Dark remains the default with its original token values. Light overrides semantic colors;
  native forms, charts and tables use those tokens. The keyboard-operable toggle stores `hitl-ids.theme`.
- Terminology: Incoming Alerts replaces Suricata Admission; Analyst Workspace replaces V2 Triage Routing.
  `/external-admission` and `/v2-triage` routes are retained for every existing role.
- Detector evidence: Suricata shows its source, actual signature, native severity and supplied confidence
  (or Not provided), without historical fusion, XGBoost or TreeSHAP panels. XGBoost shows its supplied
  model/version, structured prediction and confidence; attribution panels appear only when provided.
  `current_flow` remains Legacy Flow Detector with all historical signature/model/fusion evidence intact.
  Older responses without canonical provenance retain their historical evidence. Unknown sources are not presumed fused.
- Dashboard: the same composition card is now Legacy Detector Composition, with the subtitle
  “Historical Signature + XGBoost flow detector results.” The page also scopes all cards to historical flow metrics.
  No metrics were invented, removed or recalculated.
- Tier 1 → Tier 2: a status callout says “Escalated to Tier 2 Candidate” and explains that a formal case
  has not been created. The next-step button scrolls to and focuses the existing case-title field.
  Case title, Tier 1 handoff summary and creation reason remain required; successful creation opens the case.
  The server transition remains `tier1_review → tier2_candidate → tier2_case`, without automatic case creation.
- Research: existing collection controls remain available inside collapsed Advanced / Research & Evaluation
  disclosures. No collection was opened. Existing explicit No Immediate Review and Approved — Not Executed semantics remain.
- Responsiveness: cards contain chart/table scrolling, long identifiers wrap, mobile filter/tab rows scroll,
  and the shell permits content to shrink without page-level horizontal overflow. Focus outlines and text state labels remain.

## Validation and screenshot review

Run from `hitl-ids/apps/web` after installing the existing lockfile dependencies:

```text
node node_modules/vitest/vitest.mjs run --maxWorkers=4
node node_modules/typescript/bin/tsc -b
node node_modules/openapi-typescript/bin/cli.js ../api/openapi.json -o src/api/schema.d.ts --check
node node_modules/vite/bin/vite.js build
node node_modules/@playwright/test/cli.js test --config playwright.refinement.config.ts
```

Also run `python scripts/build_openapi.py --check` from `hitl-ids`.
`HITL_PYTHON` may select a Python environment with the repository's existing API dependencies.
On this Windows host, TEMP/TMP were set to the ignored `test-results/tmp` directory for test workers.

Results: 212 frontend tests across 29 files; TypeScript, generated API schema and OpenAPI checks;
Vite build; nine Chromium E2E tests. The build retains its advisory about a bundle larger than 500 kB.
Browser coverage includes existing admission, escalation, case creation/navigation, response approval
without execution, memory and selective-review workflows. Collection-opening browser suites were not run.
Their selectors were updated so the controls remain discoverable when those suites are explicitly requested.

The new fixture runner initializes the existing pristine synthetic fixture in a temporary database,
then reuses routing-fixture setup. It never reads or writes `data/demo.db` (absent in this checkout).
Standalone Suricata/XGBoost alert-detail screenshots use explicitly synthetic intercepted canonical responses;
the admission/routing/workflow tests use the real API on the disposable database. This is UI validation,
not new detector integration or detector-performance evidence.

Screenshots are local, ignored artifacts under `hitl-ids/apps/web/test-results/`:

- `refinement-dashboard-{1440,1024,390}-{dark,light}.png`: original card layout in both themes.
- `refinement-collapsed-*`, `refinement-Incoming-Alerts-*`, `refinement-Analyst-Workspace-*`:
  sidebar states, unchanged deep links, both themes and all three widths.
- `refinement-workstation-dark.png`, `refinement-workstation-*`: original panes, legacy evidence and mobile tabs.
- `refinement-suricata-*`, `refinement-xgboost-*`, `refinement-xgboost-shap.png`: detector-specific evidence.
- `refinement-tier2-candidate.png`, `refinement-tier2-case-form.png`: candidate explanation and explicit case form.

Actual captures were inspected against the existing `hitl-ids/docs/img/demo-guide/01b-workstation.png`.
Checks at 1440, 1024 and 390 pixels cover both themes, keyboard collapse, persistence, navigation,
queue/selective-review tables, long IDs, reachable actions and no document/main horizontal overflow.
The mobile filter overflow found during validation was corrected within the existing queue.

## Exact changed-file inventory (34 files)

14 production UI files, 19 test/configuration files, and this document. Every file serves a requested refinement.

| Repository-relative file | Why necessary |
| --- | --- |
| `docs/analyst-ui-refinement.md` | Requested preservation, scope, verification and file inventory. |
| `hitl-ids/apps/web/src/components/layout/AppShell.tsx` | Reuse mobile navigation on all existing pages; allow content to shrink. |
| `hitl-ids/apps/web/src/components/layout/Sidebar.tsx` | Accessible persisted collapse with original navigation order. |
| `hitl-ids/apps/web/src/components/layout/TopBar.tsx` | Accessible persisted Dark/Light toggle in the original top bar. |
| `hitl-ids/apps/web/src/index.css` | Semantic Light tokens, native color scheme and targeted overflow/mobile rules. |
| `hitl-ids/apps/web/src/session/roles.ts` | Correct navigation labels for existing role routes. |
| `hitl-ids/apps/web/src/features/alert/DetectorProvenance.tsx` | Source-specific evidence and shared conditional rendering without API changes. |
| `hitl-ids/apps/web/src/features/alert/MlPanelCard.tsx` | Only describe TreeSHAP when attribution data exists. |
| `hitl-ids/apps/web/src/features/workstation/AlertPane.tsx` | Apply provenance gating and honest confidence labels while preserving tabs. |
| `hitl-ids/apps/web/src/pages/analyst/AlertDetailPage.tsx` | Apply the same evidence correction to existing full-page deep links. |
| `hitl-ids/apps/web/src/pages/analyst/DashboardPage.tsx` | Scope historical metrics without rebuilding Dashboard cards. |
| `hitl-ids/apps/web/src/pages/analyst/ExternalAdmissionPage.tsx` | Correct page title and workspace-link wording. |
| `hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.tsx` | Correct title and highlight explicit candidate-to-case action. |
| `hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.tsx` | Make collection controls secondary while retaining all controls and warnings. |
| `hitl-ids/apps/web/src/pages/analyst/WorkstationPage.tsx` | Two CSS hooks for small-screen pane stacking; desktop grid unchanged. |
| `hitl-ids/apps/web/src/test/shell.test.tsx` | Keyboard, persistence and unchanged navigation-route regression checks. |
| `hitl-ids/apps/web/src/features/alert/DetectorProvenance.test.tsx` | Source/confidence separation, legacy retention and conditional SHAP checks. |
| `hitl-ids/apps/web/src/pages/analyst/__tests__/dashboard.test.tsx` | Assert legacy scope labels alongside existing count checks. |
| `hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx` | Assert candidate callout, required fields and absence of automatic case POST. |
| `hitl-ids/apps/web/src/pages/analyst/ExternalAdmissionPage.test.tsx` | Update the workspace-link assertion without changing its deep link. |
| `hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.test.tsx` | Reach collection controls through the new secondary disclosure. |
| `hitl-ids/apps/web/src/pages/analyst/CollectionPanel.test.tsx` | Preserve evaluator read-only checks through the disclosure. |
| `hitl-ids/apps/web/e2e/analyst-refinement.spec.ts` | Theme/sidebar persistence, responsive tables, old routes and detector screenshot coverage. |
| `hitl-ids/apps/web/e2e/refinement-fixture.py` | Disposable synthetic fixture without touching demo.db. |
| `hitl-ids/apps/web/playwright.refinement.config.ts` | Reproducible relevant browser suite excluding collection-opening journeys. |
| `hitl-ids/apps/web/e2e/detector-foundation.spec.ts` | Update the expected historical detector label. |
| `hitl-ids/apps/web/e2e/external-admission.spec.ts` | Update visible terminology while retaining admission/deep-link checks. |
| `hitl-ids/apps/web/e2e/routing-workflow.spec.ts` | Update workspace navigation/title selectors. |
| `hitl-ids/apps/web/e2e/tier2-case.spec.ts` | Update terminology; verify candidate explanation, focus and explicit case creation. |
| `hitl-ids/apps/web/e2e/response-approval.spec.ts` | Update navigation wording while preserving no-execution assertions. |
| `hitl-ids/apps/web/e2e/triage-memory.spec.ts` | Update workspace selector while preserving memory workflow coverage. |
| `hitl-ids/apps/web/e2e/selective-review.spec.ts` | Update workspace selector while preserving automation/verdict distinctions. |
| `hitl-ids/apps/web/e2e/prospective-collection.spec.ts` | Update wording/disclosure selectors; suite not executed or collection opened. |
| `hitl-ids/apps/web/e2e/prospective-override.spec.ts` | Update wording/disclosure selectors; suite not executed or collection opened. |

No backend algorithms, models, integration, schemas, policies, ranking, routing rules, memory/context rules,
response logic or prospective evaluation logic changed. Protocol V1/V2 files are untouched and Protocol V2
remains unopened. No merge, PR or collection-opening action is part of this change.
