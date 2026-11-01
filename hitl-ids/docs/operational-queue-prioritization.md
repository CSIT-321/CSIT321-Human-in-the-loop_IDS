# Operational queue prioritization

Base: `feat/suricata-correlation-auto-routing` at `5d0e86f0c1513dc1a51143345009ef36784462c4`.
Stacked branch: `feat/operational-queue-prioritization`.

## Before and after

Before: Unified Workstation → flat current operational queue → database ID order → limited workload overview and page-local search.

After: Operational KPI Strip → current queue tabs → separate Attack Type filter → Operational Priority ordering → selected alert workspace.

The three panes, evidence tabs, authenticated manual escalation, case links and historical tools remain in place. This increment only reads, presents, filters and orders persisted V2 values. It adds no verdict, policy, migration, detection evidence or workflow transition.

- **Priority** = how urgently SOC should act. The number is the existing `operationalPriority`.
- **Route** = who handles it, from the current `handlingRoute`.
- **Attack Category** = the normalized class the platform has already identified.
- **Review Required** = the current operational state's `reviewRequired` flag.

These remain independent. P1 does not imply Tier 2; Unknown does not assert maliciousness; No Immediate Review is not a human verdict.

## Whole-dataset KPI semantics

All counts cover persisted `operational_alerts_v2`, regardless of queue page, search or filters. They do not read legacy `/api/alerts`, raw inbox totals or unmaterialized historical alerts.

| Card / response field | Exact predicate |
| --- | --- |
| Critical / `criticalAlerts` | Current triage band stored as `critical`: P1 under `p1_p4`, or critical under `legacy_labels`. No threshold is recomputed. |
| Tier 2 / `tier2Cases` | Current alert `handlingRoute = tier2_case`. Counts alerts, not case rows. |
| Expert Review / `expertReview` | Persisted system route class `EXPERT_REVIEW_REQUIRED` **or** persisted normalized classification `unknown_needs_expert`; one alert counted once. |
| Needs Review / `reviewRequired` | Current triage `reviewRequired = true`, including unassigned compatibility alerts when that flag is true. |
| No Immediate Review / `noImmediateReview` | Current triage `handlingRoute = no_immediate_review`. |
| Open Tier 2 Cases / `openTier2Cases` | Case rows joined to current case state with status `open` or `investigating`. |
| Tier 1 / `tier1Review` | Current alert `handlingRoute = tier1_review`. |
| Total Alerts / `totalAlerts` | Every persisted operational V2 alert, including unassigned compatibility records. |

Categories intentionally overlap: a P1 Tier 2 alert contributes to Critical, Tier 2 and Needs Review. Expert Review may also be Tier 2. These cards must not be summed. Case count and alert count are different units. The strip states that categories overlap and are whole-dataset counts; each card has a definition tooltip.

**Selective Review boundary:** its existing dynamic disposition can differ from the triage route and review-required flag. The existing Selective Review service records decisions separately and revalidates their evidence on inspection; it does not write those decisions back to `handlingRoute`. This increment uses the explicit route predicate above, not historical deferral events, and does not invoke Selective Review policy evaluation for counts. A separate disposition that has not changed the route is therefore not counted by this KPI. This is deliberate, avoiding stale deferrals or hidden policy recomputation. Inspect the current disposition in Context & Review.

`routeClass` and classification are the persisted system record, not a newly inferred class from priority. Manual overrides preserve their initial system provenance; final Tier 2 membership always comes from the current triage route. Historical records without normalized classification are shown as **Not classified** and match only All attack categories.

## Read API

`GET /api/v2/alerts/summary` returns:

```json
{
  "totalAlerts": 66,
  "criticalAlerts": 54,
  "tier1Review": 9,
  "tier2Cases": 54,
  "expertReview": 2,
  "reviewRequired": 64,
  "noImmediateReview": 2,
  "openTier2Cases": 54
}
```

These are the disposable synthetic test fixture's counts, not production measurements.

The summary and existing list use the repository's `ReadConn` / `ReadPrincipal`: SQLite URI `mode=ro`, `PRAGMA query_only=ON`, shared authenticated connection, then an explicit `BEGIN` for the data snapshot. Analyst, administrator and evaluator retain existing read permissions. Missing/forged/expired/inactive authentication remains denied. Missing DB and noncurrent schema fail with the existing 503 envelopes, without creating or migrating anything.

Summary aggregates and the case count share one read transaction. List total and its page also share one transaction. The two HTTP responses are independently consistent snapshots, not one cross-request snapshot. Refresh updates both; successful in-workstation escalation reloads both. There is no push subscription for changes from other sessions.

The endpoint is included in the authored OpenAPI, generated client types and complete inspection inventory. The list's additive `detectionSummary` contains only source/destination, destination port, occurrence time, related-signature count and evidence types copied from immutable evidence. Full evidence remains a separate center-pane request.

## Server filters, tabs and search

`GET /api/v2/alerts` accepts explicit, composable AND filters before `LIMIT` / `OFFSET`:

| Tab | Query | Whole-dataset count |
| --- | --- | --- |
| All | none | `totalAlerts` |
| Tier 2 | `handlingRoute=tier2_case` | `tier2Cases` |
| Tier 1 | `handlingRoute=tier1_review` | `tier1Review` |
| Expert Review | `routeClass=EXPERT_REVIEW_REQUIRED` | `expertReview` |
| Critical | `priorityBand=P1` | `criticalAlerts` |
| Needs Review | `reviewRequired=true` | `reviewRequired` |
| No Immediate Review | `handlingRoute=no_immediate_review` | `noImmediateReview` |

The Expert query uses the same OR predicate as its KPI, including the normalized Unknown category. Priority-band queries map P1–P4 to existing storage labels; `critical` and P1 select the same displayed critical group. `reviewRequired=false` and other existing route/band/class enum values are also valid. Unknown enum/sort values and invalid limits are rejected. There is no arbitrary query language.

Attack Type independently sends `attackCategory=` using the existing taxonomy: Brute Force, Botnet / C2, DoS, DDoS, Web Attack, Infiltration, Reconnaissance / Port Scan, Malware / Exploit, Other Known Attack, Unknown / Needs Expert.

`q` now searches the full matching dataset (title, detector name, operational UUID and source/destination IP), case-insensitively with a literal substring. It is bound as a SQL parameter; wildcard characters are literal. The maximum is 200 characters. The UI never filters or re-sorts the returned page.

## Ordering and pagination

The sole supported sort is `sort=priority_desc`, also the API/UI default:

1. Existing `operationalPriority` descending.
2. `occurredAt` instant descending, normalized only for comparison, with microsecond precision and timezone offsets respected.
3. Operational UUID/reference ascending for a deterministic final tie.

Null/unassigned priorities sort after all assigned scores, including zero. Historical compatibility projections stay unassigned; no confidence, severity, native Suricata priority, XGBoost probability or legacy combined score is substituted. Invalid numeric values cannot outrank valid scores: the read-order expression accepts only numeric 0–100; the current schema/DTO validation still rejects corrupt state rather than silently inventing a score. Invalid occurrence times sort last within a priority; timezone-unspecified old captures retain their wall-clock time interpreted as UTC for comparison only. No evidence timestamp is rewritten.

Pagination displays the selected query's range and total, e.g. **51–54 of 54** for the second Tier 2 page in the fixture. Each page is 50 alerts. Tabs, Attack Type and search reset offset and selection. Empty/out-of-range pages display 0–0 of the filtered total and retain Previous navigation.

URL state is the single source for `view`, `attackCategory`, `sort`, `q`, `offset` and `alertRef`. Defaults work when parameters are absent; unknown UI view/category/sort values fall back safely to All/all categories/priority order. Reload and back/forward preserve valid filters and selection. Deep-linked alert references can still load outside the current page. `j` / `k` select returned rows; `/` focuses search. Tabs support arrow/Home/End navigation.

Filter navigation is committed synchronously so a rapid tab → Attack Type change cannot reuse the previous tab's URL. The application and test harness supply ReactDOM's `flushSync` implementation to their existing RouterProvider to support this; no routes are changed.

KPI shortcuts change the queue view while preserving the separate attack/search filters, resetting offset/selection. Open Tier 2 Cases links to the existing case list. Tab counts remain whole-dataset counts even when search/Attack Type narrow the page total.

## Visual structure

Queue items show band and current route first, a large right-aligned numeric **Operational Priority** with accessible label and explanatory tooltip, then detection title, normalized category, source → destination and compact detector/signature/evidence context. Expert and routine/critical routing labels are concise. Compatibility candidates use **Recovery pending**, never a normal current Tier 2 Candidate tab.

The KPI strip uses eight columns on desktop, four at 1024, and a locally scrolling row on mobile. Queue tabs wrap on desktop and scroll locally on mobile. The three panes retain the existing responsive behavior; the mobile queue has room for its extra controls and scrollable alert rows. Dark/Light use the existing theme tokens.

## Validation and visual evidence

Final validation:

| Check | Result |
| --- | --- |
| Complete backend `pytest -q` | **1289 passed, 5 skipped** in 530.43s. Includes queue/summary, inspection read-only, historical routing/scoring, correlation and Protocol V2 freeze regressions. |
| Full frontend Vitest suite | **230 passed / 31 files**. |
| Final focused frontend after the RouterProvider callback type adapter | **36 passed / 4 files**: queue, Selective Review panel, Suricata routing and shell. |
| TypeScript `tsc -b` | Passed. |
| Authored OpenAPI and generated TypeScript freshness | Passed; 72 paths, 76 operations, 141 schemas. |
| Production Vite build | Passed; 900.54 kB JS / 252.53 kB gzip. Existing >500 kB chunk advisory remains; no bundling redesign. |
| Real Chromium E2E | **1 passed**, 15.5s total (7.3s flow); real API/frontend, no HTTP mocks. |
| Diff whitespace / scope | Passed; no changes under policy/config/detection packages or production data. |

Five backend skips are the existing absent gitignored sample/inference artifacts (`test_contracts`, `test_fusion`, `test_observable`, `test_rule_set`, `test_run`), not skipped safety or queue checks. HTTP-library deprecation notices and jsdom's existing external-document-navigation notices are non-failing.

The new backend tests prove whole-dataset counts and intentional overlap, read-only transaction/bytes/schema/mtime preservation, all filters and combinations, filtered pagination beyond 50, literal search, default ranking, exact 95/95/72/60/40 scores, microsecond/offset/UUID ties, null/invalid ordering, authentication and empty datasets. The expanded inspection inventory covers missing and old databases without migration.

The browser flow verifies login, KPI values, 50-row ALL page, its mixed-priority second page, Tier 2 page 2 (**51–54 of 54**), Expert, Tier 1, Needs Review, No Immediate Review, Web Attack filtering (**1–50 of 52**), rapid consecutive filters, URL reload and selected alert, evidence and assistance panes, historical unassigned search, and all six viewport/theme combinations. Only login POST occurs in the browser; no queue operation writes or calls routing/collection APIs. There are no page JavaScript errors. A desktop assertion also prevents hidden accessibility text from creating a blank page-level vertical scroll region.

Nine local screenshots are generated under `apps/web/test-results/` (gitignored test artifacts):

- `queue-all-1440-dark.png`, `queue-all-1440-light.png`
- `queue-all-1024-dark.png`, `queue-all-1024-light.png`
- `queue-all-390-dark.png`, `queue-all-390-light.png`
- `queue-tier2.png`, `queue-expert.png`, `queue-attack-filter.png`

Visual review: workload is immediately readable across the top; 30px priority values align at the right of queue items and carry the visible Operational Priority label. Route tabs, selected styling and filtered range give the queue operational grouping. The Expert queue shows **EXPERT / Unknown / Needs Expert**, while Tier 2 uses the final current route. No historical detector-fusion categories or verdict KPIs appear. At 1440 all three panes remain side by side; at 1024 the KPI strip wraps into two rows and assistance remains in the existing lower area; at 390 KPIs and queue tabs scroll locally while queue/detail stack. Dark and Light retain clear labels, readable scores and selected-row contrast. All six sizes/themes pass the page-width overflow assertion. The local screenshots were visually inspected for desktop, wrapped layout, mobile Dark/Light, Tier 2, Expert and Attack Type filtering.

The shared test fixture has 66 persisted V2 alerts, including 52 automatically routed critical cases, two expert cases, nine routine Tier 1 alerts, two explicit synthetic no-review current-state examples and one unassigned historical compatibility projection. Detections and cases use real staging/admission. The two no-review records are intentionally seeded read-model states; this is not evidence that the unchanged Selective Review policy writes routes. One real case is started so both open/investigating statuses are covered. No prospective run is created.

## Limits and unchanged behavior

- No new scoring, severity mapping, classification, correlation, bundle, auto-routing, case-creation, Selective Review, Triage Memory, XGBoost or evidence-write behavior.
- No Tier 1 Analyst Verdict and no TP/FP/Expected Activity/Escalation Recommended actions in the current queue.
- No Rule + Model / Rule Only / Model Only / Not Flagged tabs, Verdict KPI or False Positives KPI.
- No migration or new persisted index. Aggregate/filter/sort reads scan the current dataset; this increment does not introduce production-scale indexing or cursor pagination.
- Only one sort is offered. Filters are URL-composable; there is no saved-view system or automatic polling of the workload strip.
- Protocol V2 is unchanged/unopened. No merge, PR or prospective collection. Only the requested branch is eligible for push after validation.

## Exact file manifest

Paths are relative to the repository root:

```text
hitl-ids/apps/api/contract/openapi.py
hitl-ids/apps/api/contract/routing.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/api/operational_queue.py
hitl-ids/apps/api/routing_routes.py
hitl-ids/apps/web/e2e/operational-queue-fixture.py
hitl-ids/apps/web/e2e/operational-queue.spec.ts
hitl-ids/apps/web/playwright.operational-queue.config.ts
hitl-ids/apps/web/src/App.tsx
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/features/alert/OperationalQueue.tsx
hitl-ids/apps/web/src/features/alert/SuricataRouting.test.tsx
hitl-ids/apps/web/src/index.css
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.tsx
hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx
hitl-ids/apps/web/src/test/renderApp.tsx
hitl-ids/docs/operational-queue-prioritization.md
hitl-ids/docs/prospective-readiness-final-integrity-fixes.md
hitl-ids/tests/operational_queue_fixture.py
hitl-ids/tests/test_api_contract.py
hitl-ids/tests/test_inspection_readonly.py
hitl-ids/tests/test_operational_queue.py
```
