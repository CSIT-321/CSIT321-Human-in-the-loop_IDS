# Operational Workspaces and Final V3.1 evidence

The HITL IDS remains one product: one FastAPI service, one frontend, one sign-in system, and the existing detection, classification, routing, Verdict, Triage Memory, Selective Review, and Tier 2 domain logic.

## Operational workspaces

System Admin opens **Admin → Operational Workspace** (`/admin/workspaces`) to select the operational database used by Analysts. The allowlisted choices are:

| Workspace | Purpose | Database |
| --- | --- | --- |
| Operational | Existing configured operational environment | `HITL_IDS_DB` or the project's default `data/demo.db` |
| V3.1 Demo Replay | Interactive demonstration on the frozen V3.1 input workload | `workspaces/v3-1-replay.db` beside the configured Operational database |

The selection and Admin action audit live in `workspaces/control.db`, outside both operational databases. Every API request resolves the selected database on the backend and binds its connection to that database for the request. A request already in progress finishes on its originally selected connection; subsequent requests see the new selection. The Analyst top bar shows the active workspace and refreshes when it changes. No records are copied between workspaces during activation.

Only System Admin can prepare or reset Replay or activate a workspace. Analyst and Evaluator cannot mutate workspace selection. Reset is available only for Replay, and only while Operational is active. If Windows still has an in-flight Replay connection open, reset returns `REPLAY_IN_USE` and can be retried after it closes. Every Admin action records actor, action, workspace, UTC time, and reason.

## Preparing Replay

Admin chooses **Full Replay** or **Presentation Replay** before preparation. Both use the same isolated V3.1 Demo Replay workspace; neither is live network monitoring.

### Full Replay

Preparation reads `evaluation/protocol-v3.1/workload/operational-workload.jsonl` without changing it. Its 200 Suricata-format EVE records are staged through the existing staging/correlation adapter, then each staged inbox alert is reviewed for eligibility and admitted through the current external admission path. Admission applies the current normalized classification, Operational Priority, routing, and automatic Tier 2 handling. A new isolated Replay database is built in a temporary file and published only after all records have been processed and foreign keys checked. Preparation uses no oracle or expected outcome data. The Admin page reports raw records, staged alerts, and resulting operational alert count separately. With the frozen Run 001 workload and current pipeline, those counts are 200, 200, and 200; this is an observed pipeline result, not a forced count.

Full Replay starts before human Verdict and Memory actions. Analysts may then use their normal account to claim work, record Verdicts, build Memory, inspect Selective Review, and investigate Tier 2 Cases. All such changes remain in Replay. Switching back restores the untouched Operational records. Reset removes only the isolated Replay database and its preparation metadata.

### Presentation Replay

Preparation reads the same frozen 200-record EVE workload, its expected identity/phase structure, trusted context, and **only the first 40 Learning feedback lines** from the frozen adaptive feedback journal. Holdout feedback and oracle outcomes are never read by the presentation controller. The 40 Learning alerts pass through current staging, eligibility, admission, Selective Review, exclusive claim, canonical Verdict and automatic Exact Memory commands. Their real checkpoint must be **40 completed decisions, 20 lessons, 10 Active and 10 Candidate** under the current policy; preparation fails if this differs. A new isolated Replay database is published only after the checkpoint and integrity checks pass.

The initial **10 Holdout** alerts then enter through the existing Suricata staging and admission pipeline. The other **150 Holdout** records remain exclusively in the frozen workload file until arrival; they are absent from both `external_alert_inbox` and `operational_alerts_v2`. A newly arrived alert follows normal classification, Operational Priority, system routing and automatic Unknown → Tier 2 Case behavior. Current trusted context is seeded by the same disposable synthetic fact producer used by the official runner; it is not an oracle outcome. No final Memory or Verdict state is directly inserted.

The first 10 Holdout records arrive in frozen index order. The next arrival is the first `unknown_tier2` identity from frozen stratum metadata, to make Tier 2 visible early. The remaining identities follow frozen index order. **Presentation arrival order differs from the official evaluation sequence.** Stratum is used solely for this fixed ordering; it is not exposed to Analysts and does not decide classification or routing.

The Admin may use **Start Arrivals**, **Pause**, **Next Alert**, **Next 5**, or **Load Remaining**. Automatic playback adds at most one alert every **5 seconds** while Presentation Replay is active. Manual controls use the same arrival path. Cursor, mode, next due time, and playback state are stored in `workspaces/control.db`; request IDs prevent duplicate manual advances, and existing operational identities make restart recovery idempotent. Switching to Operational automatically pauses playback and records a control action.

The Analyst Workstation receives near-real-time UI notifications of **persisted operational alert arrivals** through the authenticated, read-only `/api/v2/alerts/stream` endpoint. The browser sends its normal Bearer token in an Authorization header, never in the URL. An `alert_arrived` event carries only an event ID, workspace ID, operational alert ref, and timestamp; the operational database remains the source of truth. The browser silently reloads the existing queue and summary APIs after an event and after reconnect. It keeps the current queue, selected alert, tab, and draft visible during background fetches. The stream ends when the selected workspace changes, and the browser reconnects to reconcile against the new workspace. A slow 60-second safety reconciliation runs while connected; temporary 15-second polling applies when disconnected. Arrival does not select or claim an alert. This is UI delivery for Replay or other already-persisted operational alerts; it does not provide continuous live network monitoring.

Presentation Replay is an interactive demonstration from frozen inputs, **not** the official experiment and **not live traffic**. Official effectiveness results remain the immutable controlled V3.1 evaluation. Its limitations are the fixed 10-alert initial set and 5-second rate, one selected operational workspace at a time, and no general scheduling or streaming ingestion service.

## Official Evaluation evidence

**Admin → Evaluation → Final V3.1** and **Evaluator → Final V3.1** use the same read-only API projection and frontend component. It reads committed artifacts from `evaluation/protocol-v3.1/` and `evaluation/protocol-v3.1-run-001/`; it never opens those files for writing or reruns the experiment. The projection validates the 200 workload identities, 160 Holdout results, adaptive outcomes, feedback, Memory table, and drift timeline before serving results. Learning records show their human feedback and do not invent a Baseline/Adaptive comparison. Admin and Evaluator can read the summary, records, individual records, and Memory Impact. Analyst requests to those endpoints are denied.

The interactive Replay shares the frozen workload's input provenance with the official controlled evaluation. It does **not** automatically reproduce the official result. Official effectiveness claims come only from the frozen Run 001 artifacts. The Evaluation module preserves both initial unsafe drift deferrals and the later withdrawal evidence.

The project has validated real offline PCAP → Suricata → EVE intake. Neither Operational nor Replay is described as continuous live network monitoring.

## Browser verification

The focused browser journey is `apps/web/e2e/operational-workspaces.spec.ts`. Start the API with `HITL_IDS_DB` pointing to a freshly schema-created disposable Operational database, and start Vite with `HITL_API_TARGET` pointing to that API. Set `HITL_WORKSPACES_DB` to the same disposable database path, then run `playwright test --config playwright.workspaces.config.ts` from `apps/web`. The test resets only its disposable Replay when re-run, checks the Operational database fingerprint before and after Replay preparation and Analyst activity, and checks the Admin, Analyst, and Evaluator flows at desktop and mobile widths in both themes.

The progressive journey is `apps/web/e2e/presentation-replay.spec.ts` with `playwright.presentation.config.ts`. It requires a **fresh** schema-created disposable Operational database for each run, the same API/Vite setup, and `HITL_PYTHON` for its second-Analyst fixture. It checks the 40/10/150 checkpoint, read-only Analyst refresh after manual arrivals, Unknown automatic Tier 2, exclusive Owner/Viewer access, Current HITL Audit, switch pause, and the unchanged Operational database fingerprint at 1440, 1024 and 390 pixels in dark and light themes. The 40 real Learning decisions take longer to prepare than a normal page load.
