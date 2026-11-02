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

Preparation reads `evaluation/protocol-v3.1/workload/operational-workload.jsonl` without changing it. Its 200 Suricata-format EVE records are staged through the existing staging/correlation adapter, then each staged inbox alert is reviewed for eligibility and admitted through the current external admission path. Admission applies the current normalized classification, Operational Priority, routing, and automatic Tier 2 handling. A new isolated Replay database is built in a temporary file and published only after all records have been processed and foreign keys checked. Preparation uses no oracle or expected outcome data. The Admin page reports raw records, staged alerts, and resulting operational alert count separately. With the frozen Run 001 workload and current pipeline, those counts are 200, 200, and 200; this is an observed pipeline result, not a forced count.

Replay starts before human Verdict and Memory actions. Analysts may then use their normal account to claim work, record Verdicts, build Memory, inspect Selective Review, and investigate Tier 2 Cases. All such changes remain in Replay. Switching back restores the untouched Operational records. Reset removes only the isolated Replay database and its preparation metadata.

## Official Evaluation evidence

**Admin → Evaluation → Final V3.1** and **Evaluator → Final V3.1** use the same read-only API projection and frontend component. It reads committed artifacts from `evaluation/protocol-v3.1/` and `evaluation/protocol-v3.1-run-001/`; it never opens those files for writing or reruns the experiment. The projection validates the 200 workload identities, 160 Holdout results, adaptive outcomes, feedback, Memory table, and drift timeline before serving results. Learning records show their human feedback and do not invent a Baseline/Adaptive comparison. Admin and Evaluator can read the summary, records, individual records, and Memory Impact. Analyst requests to those endpoints are denied.

The interactive Replay shares the frozen workload's input provenance with the official controlled evaluation. It does **not** automatically reproduce the official result. Official effectiveness claims come only from the frozen Run 001 artifacts. The Evaluation module preserves both initial unsafe drift deferrals and the later withdrawal evidence.

The project has validated real offline PCAP → Suricata → EVE intake. Neither Operational nor Replay is described as continuous live network monitoring.

## Browser verification

The focused browser journey is `apps/web/e2e/operational-workspaces.spec.ts`. Start the API with `HITL_IDS_DB` pointing to a freshly schema-created disposable Operational database, and start Vite with `HITL_API_TARGET` pointing to that API. Set `HITL_WORKSPACES_DB` to the same disposable database path, then run `playwright test --config playwright.workspaces.config.ts` from `apps/web`. The test resets only its disposable Replay when re-run, checks the Operational database fingerprint before and after Replay preparation and Analyst activity, and checks the Admin, Analyst, and Evaluator flows at desktop and mobile widths in both themes.
