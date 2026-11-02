# Final Legacy Cleanup & Current Product Surface Freeze

Base: `24d43c5bd6d95131978bfbb77aba21efb0fdaab8` (`feat/shared-analyst-work-claim`).
Candidate branch: `feat/final-legacy-cleanup`. No merge or PR; no prospective collection opened.
The resulting commit is the commit containing this report (use `git log -1` on this branch).

## Decision

**PASS — FINAL CURRENT PRODUCT SURFACE CLEAN.** One operational Analyst Workstation remains.
The runtime is ready to be frozen as a candidate for Final Evaluation Protocol V3. This does not
register, open, collect under, or otherwise change either evaluation protocol.

No BLOCKER or MAJOR findings remain in the cleanup scope. Non-blocking limitations: the production
build retains its existing large-chunk advisory (about 548 kB before compression); backend tests
report existing Starlette/httpx and AnyIO deprecations. These do not change runtime behavior.
Earlier standalone Playwright suites are historical increment-specific harnesses; this validation
runs the current whole Golden Path plus shared-work and role-surface suites, not every old demo.

## Route and navigation decisions

| Surface | Decision / current purpose |
|---|---|
| `/analyst`, `/analyst/operations` | Current home: Analyst Workstation |
| `/analyst/workstation` | Redirect to `/analyst/operations`; no legacy page or child UI |
| `/analyst/v2-triage` | Redirect to `/analyst/operations`; one current identity |
| Both redirects | Preserve `alertRef` only; discard obsolete query parameters |
| `/analyst/overview`, `/queue`, `/alerts/:alertRef`, `/entities/ip/:ip`, `/investigations`, `/feedback-impact`, `/dashboard` | Removed pages; normal Analyst not-found with a Workstation link |
| `/analyst/tier2-cases`, `/analyst/tier2-cases/:caseRef` | Formal Case list, investigation, response decisions, resolution |
| `/analyst/triage-memory` | Human knowledge, policy activation, provenance and history |
| `/analyst/selective-review` | Current safe review projection, explanation and override |
| `/analyst/external-admission` | Incoming Alerts, eligibility and admission |
| `/admin/v2-triage`, `/evaluator/v2-triage` | Retained role-scoped current operational inspection; visible name Alert Triage |
| Admin Status / Guardrails / Audit / IP reports | Retained service diagnostics, historical configuration/audit and evidence inspection; historical scoring diagnostics explicitly distinguished from current Suricata operation |
| Evaluator Scenarios / Runs / Metrics | Retained historical research replay and evaluation evidence, explicitly labelled historical; operational inspection remains in current pages |

Final Security Analyst navigation, in order: **Analyst Workstation · Tier 2 Cases · Triage Memory ·
Selective Review · Incoming Alerts**. No Dashboard nav item, Advanced / Historical menu, historical
queue, feedback impact, investigations or overview shortcut remains.

```text
Analyst Workstation
├── Shared Active Queue
├── Available / In Review / Completed / Escalated
├── Evidence
├── Classification
├── Priority
├── Routing
├── Verdict
└── Human Learning

Tier 2 Cases
├── Investigation Assistance
├── Investigation Conclusion + Human Final Attack Classification
├── Expert Learning
├── Response Recommendation + Human Decision
└── Resolution (resolved cases read-only)

Triage Memory → learned human operational knowledge
Selective Review → review-reduction safety projection
Incoming Alerts → intake/admission
```

## Deletions and terminology

Eight exclusively legacy Analyst pages removed: WorkstationPage, OverviewPage, QueuePage,
AlertDetailPage, IpEntityPage, InvestigationsPage, FeedbackImpactPage and DashboardPage.
Exclusively legacy children removed: workstation AlertPane/ContextRail/KpiStrip/QueuePane;
FamilyPanelCard/FeedbackHistoryCard/FlowPanelCard; SimilarAlerts; FeedbackPanel,
ScoreAdjustmentChain, feedback category presentation and useLastGood. The unused old planning
StepPlaceholder is removed. Their obsolete UI tests are removed. Shared Meter, detector evidence
cards and current tests remain because current Admin/Evaluator or audit views use them.

Top-level `dashboard/` was a superseded standalone React app with no current runtime, test,
deployment or build dependency. It is deleted, not redesigned. `.github/workflows/pages.yml`
builds the separate informational `hitl-ids/site`. The three dashboard data snapshots were copied
unchanged into `docs/history/dashboard-data/` before deletion; the alert sample differs from the
later stage-5 export and is intentionally preserved. Stage 1–5 research is untouched.

Candidate approval/rejection/admission and Complete Earlier Escalation controls are removed from
the shared RoutingDetail UI. Current manual escalation still calls the same compound
`tier2/escalate-case` endpoint. Historical candidate state is labelled as a historical routing
record, not a waiting stage or workflow instruction. Immutable raw events still retain their values.

The Tier 2 form already submits Investigation Conclusion, not the obsolete standalone Finding
endpoint. It is preserved. Remaining current help text now says Investigation Conclusion.
Historical Finding events remain readable in the Case history.

The old independent Human Memory outcome/reason/scope contribution form is removed. Current
Exact learning stays automatic; Narrow remains an explicit extension. The Verdict navigation
button now says **View Human Learning**, avoiding an implication that clicking it creates Exact
evidence. No normal manual Exact action exists. Manual activation is shown only for historical /
manual or Narrow lessons and labelled **Activate historical / manual lesson**; current automatic
Exact lessons do not show it. A separate **Memory governance reason** remains for legitimate
governance decisions, not as a second human Verdict. The page explains System Policy Auto Activation.

Current Suricata evidence no longer displays an irrelevant unavailable-XGBoost row. No operational
parallel-detector claim was introduced. Current Analyst cross-links now target `/analyst/operations`
directly; old supported alert bookmarks redirect there.

## Legacy search classification

Search covered current frontend terms Legacy, Historical, Candidate, XGBoost, Signature, Fusion,
Feedback Impact, old triage/investigation and manual Memory terminology.

| Classification | Remaining / removed hits |
|---|---|
| A — REMOVE | Eight old Analyst pages and children, Dashboard nav, Advanced/Historical menu, top-level dashboard app, Candidate recovery/approval controls, duplicate Memory inputs, old current-product documentation claims |
| B — KEEP historical evidence | DetectorProvenance / OperationalEvidence / SignaturePanelCard / MlPanelCard / EvidencePanelCard render recorded historical detector evidence conditionally; audit history retains raw event types, states, historical Findings and superseded learning |
| B — KEEP research diagnostics | Admin historical Status/Guardrails, Evaluator Scenarios/Run/Metrics, shared design band names for historical run data; these are not Analyst operational queue controls |
| B — KEEP academic artifacts | stage-1–5, prototype-demo, archived manual, labelled older demo/showcase/pipeline documents, screenshots and all final validation evidence |
| C — KEEP current functionality | V2RoutingPage and `/api/v2` identifiers are current contracts; Suricata signatures, signature IDs and classification matches are current detector evidence, not legacy fusion |
| C — KEEP current safety vocabulary | Memory `candidate` is a lesson support status, unrelated to removed Tier 2 Candidate workflow; historical-input provenance is required safety information |

An import reachability pass from `src/main.tsx` found no remaining unreachable non-test TS/TSX
implementation after the exclusively legacy code and StepPlaceholder were removed. Shared schema
types and regression fixtures are intentionally retained.

## Preserved contracts and data

No backend application, contract, service, policy, configuration, migration, or backend test file
changed. Detection, classification, priority, routing, feedback score behavior, canonical Verdicts,
Memory policy, Selective Review and Tier 2/Response/Resolution business logic are unchanged.
Legacy endpoints remain internal compatibility for historical data, replay, migrations, audit and
research diagnostics; deleting them would exceed this frontend cleanup. Old feedback category
values, Candidate transaction/recovery internals and historical Finding/Exact APIs are untouched.

Preserved semantics: exclusive claims; same-round contention gives nobody ownership; owner-only
Tier 1 Verdict; 15-second read-only refresh; One Alert = One Current Vote; Tier 2 > Tier 1;
automatic Exact evidence; safe auto activation; fixed 30-day validity; conflict withdrawal;
R01 canonical Verdict guard; R02 unsafe-suppression metric; human response approval without
execution; case closure with read-only resolved history.

Existing final Golden Path, real Suricata PCAP and shared Analyst evidence and documentation,
raw evidence, historical screenshots, migrations and append-only audit data are unchanged.
Protocol V2's canonical SHA-256 remains
`cfc9539c0b325919a60eb8a5722826affa53e1c253e3b96c15e3a6db41dd2541`;
`collectionOpened` remains false. No response execution, merge, PR or collection occurred.

## Validation

| Check | Result |
|---|---|
| Full current frontend | **209 passed, 27 files** |
| Backend relevant regression | **308 passed**: shared work, Verdict, Verdict/Conclusion Memory, safe activation, canonical review safety, Selective Review, Tier 2 cases/direct escalation/reclassification/resolution, response approval, Suricata routing and Protocol V2 freeze |
| TypeScript | `tsc -b` PASS |
| API / schema | No API changes; generated schema and OpenAPI untouched; freshness regeneration not required |
| Production build | PASS (existing large-chunk advisory only) |
| Final Golden Path | **1 passed**, real API + disposable DB, current routes only; human learning, safe review, expert conclusion, response and resolution assertions retained |
| Shared work + role surface | **2 passed**, three Analysts plus evaluator; Available, ownership, contention, Completed/history, correction, escalation and owner-only Verdict verified |
| Current role navigation | Every Analyst/Admin/Evaluator nav destination rendered; no page exceptions |
| Responsive/theme | 1440 / 1024 / 390 × light/dark; 30 current Analyst route screenshots, 24 shared-work state screenshots, 30 Golden Path screenshots; no page-level horizontal overflow |
| Documentation site | Build and all local references PASS with its existing Markdown dependency |
| Real Suricata | Existing tooling and evidence unchanged; the current Workstation routes used by it remain covered. No repeated external download |
| Preservation | Git diff confirms original backend/config/tests/evidence/migrations and detector integration files unchanged |

Commands, from `hitl-ids/apps/web`: `node node_modules/vitest/vitest.mjs run`,
`node node_modules/typescript/bin/tsc -b`, `node node_modules/vite/bin/vite.js build`,
`node node_modules/@playwright/test/cli.js test --config playwright.final-golden-path.config.ts`,
and `... --config playwright.current-surface.config.ts`.
The latter uses `HITL_WORK_API_PORT=8034` / `HITL_WORK_WEB_PORT=5204` to avoid touching the existing
preview on 8032/5202. Shared test default ports and substantive assertions are unchanged.
Backend: `python -m pytest` on the 14 named suites recorded above; full output is retained locally
in `hitl-ids/.pytest-tmp/backend.log`. Documentation: `python site/build_site.py --check` with output
inside the ignored workspace temporary directory.

New compact proof and representative screenshots are under
[`hitl-ids/docs/evidence/final-legacy-cleanup`](../hitl-ids/docs/evidence/final-legacy-cleanup/validation.json).
Existing evidence is not overwritten. Remaining user-facing historical material is limited to
explicitly identified audit/research records; no competing legacy Analyst workflow remains.

## Exact changed files

The companion [file manifest](final-legacy-cleanup-files.txt) lists every added, modified, deleted
or relocated path in this commit, including this report, the manifest itself and new evidence.
