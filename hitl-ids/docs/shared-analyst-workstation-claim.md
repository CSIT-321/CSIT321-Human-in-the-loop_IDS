# Shared Analyst Workstation & Exclusive Alert Claim V1

Base: `feat/real-suricata-pcap-validation`, `1192c10d6cbdd8ca137093446334bb00f8a62de7`.
Candidate branch: `feat/shared-analyst-work-claim`. No merge, PR, or prospective collection.

## Assessor explanation

The Analyst Workstation is shared across analysts, but active Tier 1 work is exclusive per alert. When one analyst successfully claims an alert, other analysts can see that it is in review but cannot modify it. If multiple analysts contend for the same unclaimed alert in the same claim arbitration round, ownership is not assigned to either analyst and both are asked to select again. Once a Verdict is recorded, the Tier 1 work item is completed and leaves the default active workload while all evidence and audit history remain available.

This is a minimal human-work lifecycle, not an enterprise assignment system. There is no SLA, automatic assignment, workload balancing, lease, heartbeat, timeout, release, shift management, or Tier 2 ownership feature.

## Independent work lifecycle and eligibility

| Work status | Meaning |
| --- | --- |
| Available | Current system-routed Tier 1 / triage work requires attention and has no owner. |
| In Review | Exactly one finalized human owner; remains visible to everyone. |
| Completed | First canonical Tier 1 Verdict committed; no active owner. |
| Escalated | Owner transferred active Tier 1 work through the existing atomic Tier 2 Case command; no active owner. |

Routing, priority, classification, review disposition and human work remain separate. Completion does not change review disposition or routing. Review disposition can change independently while an owner works; this does not release ownership. An unowned No Immediate Review alert has no active Tier 1 work projection and cannot be claimed until **Require Human Review** explicitly recalls it. A finalized owner can still record a Verdict after a later policy deferral, preserving canonical safety recognition.

Only active `security_analyst` users and the already-supported operational `system_admin` role can claim. The legacy evaluator compatibility account stays read-only and is not a current product role. Claiming requires the current persisted system-routing projection and current `tier1_review` / `triage` state. Legacy detector/routing history is not silently converted into current Tier 1 work. Auto-routed Unknown / Expert Review alerts retain their automatically created Tier 2 Cases and never require Tier 1 claims.

## Intentional selection and shared UI

An Analyst's intentional click on an eligible Available Tier 1 queue row automatically requests ownership through the existing 750 ms arbitration. Initial/default row display, page load, direct URL, SSE arrival, silent reconciliation, fallback polling, queue refresh, filter change and workspace reconnect never claim. Arrival and background rendering are not user selection. There is no current Start Review control. Success refreshes the queue, detail and KPIs.

The owner sees **In Review — You**. Other analysts see **In Review — Alice**, can inspect the alert, and have no first-Verdict, escalation or Workstation review/context mutation controls. Backend authorization independently enforces ownership, including direct/stale requests. Alert-specific trusted facts, manual memory review and selective-review mutations cannot bypass another analyst's active ownership. Global context/lesson governance and existing Tier 2 collaboration are separate policies.

On a controlled conflict the UI clears the current selection, refreshes the shared queue and asks the analyst to select again. It does not automatically pick another alert or retry ownership. The message is:

> Claim Conflict — Another analyst attempted to claim this alert at the same time. No ownership was assigned. Please select an alert again.

An already-owned alert instead explains that it is currently being reviewed by the named owner. Network uncertainty retains the same request ID for retry. Authenticated SSE signals persisted arrivals and silently reconciles the queue; slower safety reconciliation and temporary polling after disconnect expose other analysts' changes. There are no websockets.

## Claim API and exact arbitration

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v2/alerts/{alertRef}/work` | Read-only current work projection, revision, owner, provenance and permissions. |
| `GET /api/v2/alerts/{alertRef}/work/events?limit=50&offset=0` | Read-only immutable event history, newest first; limit at most 200. |
| `POST /api/v2/alerts/{alertRef}/work/claim` | Explicit arbitration command: `{requestId: UUID, expectedRevision: integer >= 0}`. |

The versioned `config/analyst-work-claim-v1.json` policy uses **750 ms** (`analyst-work-claim-v1`). Each round persists the version and actual window used; changing configuration never changes a pending round's deadline. The backend validates a bounded 1–5000 ms setting.

1. Under SQLite `BEGIN IMMEDIATE`, authenticate the actor, validate the actor/payload-bound request identity, current eligibility and work revision. Lazily create an Available row only on POST. Create or join the alert's one pending round and append a human intent.
2. The first registered intent starts the server-clock window. `closes_at = started_at + 750 ms`. Registration under the database write lock before this deadline defines membership. Client timestamps, alphabetical order, actor IDs, role seniority, score and random priority never choose a winner.
3. Commit the intent and release the write lock before waiting. Separate requests/connections/processes can join the same persisted round. There is no process-local ownership mutex.
4. At/after the deadline, a POST worker takes `BEGIN IMMEDIATE` and finalizes once. One distinct eligible actor receives ownership; two or more distinct actors yield **no owner** and an Available item. Recheck eligibility at finalization. Persist the result and audit in the same transaction.
5. Single-actor success returns 200. Every contender in a contended round receives 409 `CLAIM_CONTENTION`, including the round identity and Available/no-owner projection. Ineligible, stale, or already-owned requests receive controlled conflicts. SQLite busy/locked uncertainty returns `WORK_RETRY` with the same-request retry instruction.

Distinct actors are counted, not HTTP attempts. The same `requestId` and identical actor/payload replay the existing result without another intent/audit. Reusing it with another actor, alert or revision is rejected. Different request IDs from the same actor still represent one distinct contender. Reopening as the finalized owner does not replace ownership or create another round; a new request identity is bound in the retained intent table without another claim-finalization event.

An intent registered after a prior round's deadline first finalizes that old round. It does **not** join it retroactively. If that round assigned an owner, the late other actor is rejected and the owner remains. This is a finite server-registration window, not a promise that all human clicks close in wall-clock time will conflict under arbitrary network or scheduling delays.

If a worker dies after registration, the round remains durable. GETs do not finalize it. A subsequent explicit POST/retry finalizes the overdue round before processing a new attempt. This recovery concerns **pending arbitration only**, not expiring an owned work item.

## Integrity, audit and attribution

Migration 21 adds only `analyst_work`, `analyst_claim_rounds`, `analyst_claim_intents`, and `analyst_work_events` plus their constraints/triggers/index. The work primary key allows one current row/owner per operational alert. A partial unique index allows one pending round per alert. Request UUIDs are unique; foreign keys link alerts, real users, rounds and Verdicts. Revision/transition checks prevent owner replacement and terminal reopening; a claimed owner update must match its finalized round. Round finalization is one-way. Intent and audit records reject update, delete and replacement.

Events distinguish human `CLAIM_INTENT` (real actor ID/name/request ID) from `CLAIM_ROUND_STARTED`, `CLAIM_FINALIZED`, `CLAIM_CONTENTION` and `CLAIM_INELIGIBLE` (system policy, null actor; contenders/final owner in detail). `WORK_COMPLETED` and `WORK_ESCALATED` identify the real human and Verdict/Case. Owner name, claim time, round and revision are retained for provenance. No fake human actor represents arbitration.

## Verdict, completion, correction and escalation

The first normal Tier 1 Verdict requires the current owner inside the existing serialized command transaction. Canonical Verdict, automatic Exact Memory contribution, work completion and completion audit commit together. Injected terminal-audit failure rolls all of them back, retaining the In Review owner. No extra contribution click is introduced.

Completion records time, completing actor/name and the completing Verdict reference. Active owner ID becomes null. The first completion provenance stays fixed; the projection separately shows the latest Verdict outcome. Explicit historical corrections remain append-only and revision/state-version protected, may be performed by the existing authorized operator roles, and never reopen Completed work. Retries do not duplicate completion or votes.

Owner manual escalation uses the existing atomic Case command. Routing, Case creation, Escalated work and handoff audit commit or roll back together. No new visible Candidate step is introduced. An explicit later handoff of previously Completed history preserves the existing supported escalation behavior while keeping that earlier Tier 1 work Completed. No Tier 2 assignment system is added.

Canonical R01/R02 recognition, unsafe-suppression accounting, expert authority, one-alert-one-current-vote, withdrawal and correction remain authoritative independently of work status. `safe-memory-auto-activation-v1` is unchanged: Exact only, eligible benign outcomes, support >= 3, agreement >= 0.67, zero conflicts, fixed 30-day validity, no sliding renewal or automatic post-expiry reactivation.

## Queue and KPI semantics

The Workstation defaults to **Active**, implemented as `workScope=active`. Completed and Escalated Tier 1 work is excluded before pagination; claimed work remains visible. **Completed**, **Escalated** and **All** preserve access to retained records. API callers omitting `workScope` retain the previous all-alerts behavior. Deep links can inspect completed history even while the queue is Active. Priority/time/reference ordering is unchanged.

`activeAlerts` / **Active Alerts** counts all operational records without terminal Tier 1 work; it is deliberately not a claim-eligibility count. It retains other workflows, including system Tier 2, deferred attention and legacy history. `tier1Review` / **Active Tier 1** now excludes Completed/Escalated work from the Tier 1 route. `availableWork` counts current system-routed, unowned, non-deferred Tier 1/triage items; `inReviewWork`, `completedWork`, `escalatedWork` expose the separate work lifecycle. Completed detail shows reviewer, finishing time and current Verdict outcome.

Other existing counts remain whole-dataset projections, including **Needs Review** and **No Immediate Review**. The UI explicitly explains this distinction. These attention/research metrics are not relabeled as unhandled work, and no Selective Review research calculations change.

## Populated database upgrade

No old migration is edited. Migration 21 marks existing canonical Verdict history Completed using the latest authentic pre-upgrade Verdict author/reference/time, with no invented claim. Historical analyst-created Cases without a Verdict become Escalated; auto-created system Cases receive no Tier 1 ownership. When both histories exist, Completed retains the canonical Verdict provenance. Other alerts derive availability without a read-side insert.

`WORK_HISTORY_MIGRATED` has null actor and `historical_migration` attribution, with the actual historical human in detail. All old records remain unchanged. Tests construct realistic schema-20 Verdict/Memory/Case data, prove whole-upgrade rollback on injected SQL failure, verify preservation of every old table after 20→21, check repeat migration is a no-op, and run foreign-key/integrity checks. Older migration fixtures reproduce their historical command semantics only during fixture creation; current production owner checks are not bypassed.

Upgrade through the existing explicit writable initialization/migration path (`db.migrate`). Read endpoints continue rejecting unsupported old schemas rather than migrating on GET. Back up a deployed database before applying a forward migration; no production database was used for validation.

## Validation method and boundaries

`tests/test_analyst_work_claim.py` sends two simultaneous actual FastAPI HTTP requests from independent clients/connections/threads. A start barrier and a barrier after both committed registrations ensure genuine same-round overlap; this is not a sequential second request against an already-owned item. Assertions check both 409 responses, one common round, distinct actors, Available/null owner, subsequent single retry and later claimant rejection.

`apps/web/e2e/shared-work.spec.ts` signs Alice, Bob and Carol into separate browser contexts against a real temporary SQLite/FastAPI backend; a fourth evaluator context verifies 403. Browser requests are released together, with test-only server scheduling barriers before registration and after both real commits for the one contention scenario. The harness does not replace policy, time, domain outcomes or database writes. Other claims use ordinary real timing. Evidence includes the request/response bodies and persisted rounds, work and events in `test-results/shared-work/**/multi-user-proof.json`.

The browser scenario covers read-only DB fingerprints, owner reload, other-user refresh/read-only controls, contention/reselect, retry, late rejection, Verdict→Completed, Completed filter/history, explicit correction, owner escalation/Case creation, automatic Unknown Case, evaluator rejection and no collection. Responsive Light/Dark checks at 1440/1024/390 create 24 screenshots across Available, other-owner In Review, conflict and Completed history, with overflow assertions. The current Golden Path uses intentional eligible row selection to trigger Auto-Claim before active Tier 1 handling; its learning, R01/R02, response/closure assertions are retained.

Detection, real PCAP→Suricata→EVE/import, classification, route transitions, score/priority policy, Tier 2 assistance/conclusions/expert learning, response recommendation/approval/**Approved — Not Executed**, and resolution behavior are unchanged. Only authorization and atomic human-work bookkeeping surround the existing supported operations. Protocol V2 stays historical, frozen and unopened; no prospective collection was opened. This implementation does not perform a new detection tuning or broad redesign.

## Limitations and evaluation readiness

Abandoned finalized claims have **no automatic timeout or recovery in V1**. An owner who leaves or becomes inactive can strand work; there is intentionally no release/reassignment endpoint. A network-lost successful claim remains owned; the same actor's retry/reload recovers its state. Pending arbitration recovery needs a later explicit POST. Stream disconnection and fallback polling can temporarily show stale permissions, but backend checks reject unauthorized writes. Short arbitration windows cannot compensate for arbitrary transport delay.

Completed-history correction follows existing operator authorization rather than an exclusive historical editor. Tier 2 remains collaborative under its existing policy. These are explicit V1 boundaries, not hidden leases or assignment features. Final V3.1 Run 001 has since completed and frozen; this document's earlier validation predates that official evaluation and does not change its results.

## Recorded validation results

- Final consolidated backend regression: **597 passed, 1 skipped** (missing gitignored ML inference artifact), 185.18 seconds. It includes claim/concurrency, Verdict/correction, R01/R02, safe automatic learning, queue/KPI, all migration/schema failures found by the full scan, read-only inspection, Tier 2 and Protocol freeze.
- Frontend: **258 passed**, 36 files.
- TypeScript: `tsc -b` passed. OpenAPI JSON freshness and generated TypeScript schema freshness passed. Production build passed (existing large-chunk advisory only).
- Real multi-user browser E2E: **1 passed**; three analysts plus evaluator, 24 responsive/theme screenshots.
- Historical Final Golden Path browser E2E: **1 passed** under the former explicit review-start UX; the current Auto-Claim path requires separate regression validation.
- Migration 20→21: populated data preserved, injected migration failure rolled back, repeated migration no-op, foreign-key and integrity checks passed.
- Protocol V2 canonical SHA-256: `cfc9539c0b325919a60eb8a5722826affa53e1c253e3b96c15e3a6db41dd2541`; `collectionOpened=false`.

An exploratory full backend scan produced 1507 passed / 5 skipped / 10 failed before all schema inventories and historical fixtures had been updated. Every failing module was included in final regression; this is not a claim that the entire unrelated full suite was rerun green. Skips require gitignored inference/sample artifacts. Existing assertions were retained; historical fixtures gained explicit claim prerequisites or isolated pre-feature setup, and expected schemas gained migration 21.

Observed unrelated minor setup issue: simultaneous first login into a partially seeded disposable database raced in existing lazy demo-account initialization. The browser harness now seeds those existing accounts before concurrent login; production authentication logic is unchanged.

Reproduction (from `hitl-ids`, with project Python/dependencies installed):

```text
python -m pytest tests/test_analyst_work_claim.py -q
python scripts/build_openapi.py --check
cd apps/web
npm run check:api
npx tsc -b
npx vitest run
npm run build
npx playwright test --config playwright.shared-work.config.ts
npx playwright test --config playwright.final-golden-path.config.ts
```

Set `HITL_PYTHON` for Playwright when the project interpreter is not `python` on PATH. Both browser configurations own disposable databases; they never use or open collection in a live database.

## Exact changed files

All paths below are relative to the repository root. Generated API contracts and existing schema/test inventories are included.

```text
hitl-ids/apps/api/contract/openapi.py
hitl-ids/apps/api/contract/routing.py
hitl-ids/apps/api/main.py
hitl-ids/apps/api/openapi.json
hitl-ids/apps/api/operational_queue.py
hitl-ids/apps/api/routing_routes.py
hitl-ids/apps/api/work_routes.py
hitl-ids/apps/web/e2e/final-golden-path.spec.ts
hitl-ids/apps/web/e2e/shared-work-fixture.py
hitl-ids/apps/web/e2e/shared-work.spec.ts
hitl-ids/apps/web/playwright.shared-work.config.ts
hitl-ids/apps/web/src/api/schema.d.ts
hitl-ids/apps/web/src/features/alert/AnalystVerdict.tsx
hitl-ids/apps/web/src/features/alert/AnalystWork.test.tsx
hitl-ids/apps/web/src/features/alert/AnalystWork.tsx
hitl-ids/apps/web/src/features/alert/OperationalQueue.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/OperationalWorkstationPage.tsx
hitl-ids/apps/web/src/pages/analyst/SelectiveReviewPage.tsx
hitl-ids/apps/web/src/pages/analyst/Tier2CasesPage.test.tsx
hitl-ids/apps/web/src/pages/analyst/V2RoutingPage.test.tsx
hitl-ids/config/analyst-work-claim-v1.json
hitl-ids/docs/shared-analyst-workstation-claim.md
hitl-ids/packages/contracts/analyst_work.sql
hitl-ids/packages/contracts/db.py
hitl-ids/packages/detection/analyst_verdict.py
hitl-ids/packages/detection/analyst_work.py
hitl-ids/packages/detection/context_store.py
hitl-ids/packages/detection/routing.py
hitl-ids/packages/detection/selective_review.py
hitl-ids/packages/detection/tier2_escalation.py
hitl-ids/packages/detection/triage_memory.py
hitl-ids/tests/pre_freeze_fixture.py
hitl-ids/tests/test_analyst_verdict.py
hitl-ids/tests/test_analyst_work_claim.py
hitl-ids/tests/test_api_contract.py
hitl-ids/tests/test_canonical_api.py
hitl-ids/tests/test_contracts.py
hitl-ids/tests/test_external_staging.py
hitl-ids/tests/test_inspection_readonly.py
hitl-ids/tests/test_investigation_assistance.py
hitl-ids/tests/test_operational_queue.py
hitl-ids/tests/test_pre_freeze_review_fixes.py
hitl-ids/tests/test_safe_memory_auto_activation.py
hitl-ids/tests/test_suricata_correlation_routing.py
hitl-ids/tests/test_tier2_case_resolution.py
hitl-ids/tests/test_triage.py
hitl-ids/tests/test_triage_policy.py
hitl-ids/tests/test_verdict_memory.py
hitl-ids/tests/work_claim_fixture.py
```
