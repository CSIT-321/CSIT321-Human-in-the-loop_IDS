# Phase C — status

## C7 claim release (decision D5) — done, backend only (2026-11-07)

- `POST /api/v2/alerts/{alertRef}/work/release` (`apps/api/work_routes.py`), command `analyst_work.release`.
  - The owner releases their own claim (reason optional).
  - An administrator releases any claim; a reason is required (400 without one).
  - Any other user: 409 (another analyst) or 403 (evaluator role).
  - Idempotent by requestId; a stale `expectedRevision` is refused.
- Idle expiry: a claim older than `claimIdleExpiryMinutes` (`config/analyst-work-expiry-v1.json`, 15) is released
  by the system when another analyst claims the alert, or by `analyst_work.expire_idle_claims` (a sweep). A read
  never releases a claim; the read only shows `canClaim` and "...'s claim is idle".
- Every release writes one `WORK_RELEASED` event (who, from whom, when the claim started, why). Migration 24
  (`packages/contracts/work_release.sql`) allows in_review -> available only when that event exists first.
- The current audit feed shows the release ("X released Y's claim on alert ... Reason: ...").

Checks: `tests/test_work_release.py` (10). Red check `analysis/phase-c/red_check_c7.sh`: 7 planted defects each fail
a test. Live API check `analysis/phase-c/c7_live_check.py` on the routed demo copy: claim 200, second analyst 409,
admin without reason 400, admin with reason 200, audit line present, second analyst then claims 200.

Found on the way: the hand-written API contract tests only compared the document with itself, so the new route was
missing from `openapi.json` with every test green. New test `test_every_real_api_route_is_in_the_published_contract`
compares it with the routes FastAPI serves (`/api/health` was already missing before; listed as known).

Limits:
- "Activity" is the claim time only. An owner who works on an alert for 15 minutes without a verdict can lose the
  claim to another analyst's claim attempt. Tier 1 notes (C6) or a heartbeat would need to reset the clock.
- No scheduler runs the sweep. Expiry happens only on a new claim attempt.
- No screen yet (the release button is Phase C UI work, needs supervisor approval).

## Queue order rule, D4 condition 2 — done (2026-11-07)

`apps/api/operational_queue.py`: `QUEUE_ORDER` = unflagged last, then Operational Priority, then newest, then ref.
"Unflagged" = a legacy flow alert with `evidence_class = 'none'` (no rule, no model flag). External NIDS alerts and
flagged groups stay in the upper tier. Both queue paths (plain and review-filtered) use the same order.

Before this, the rule held only because of the scores. Trusted context can add up to +25, so a single could
outscore a group. Now it is a rule.

Checks:
- New test `test_a_high_scoring_unflagged_item_still_ranks_below_every_group`: a single at score 100 outscores the
  two Tier 1 groups (99); it ranks right after the groups on both paths and across pages. Failed before the change.
- `test_operational_queue.py` fixture gained the two columns the order reads (no expected order changed).
- Red check `analysis/phase-c/red_check_queue_order.sh`: 4 planted defects, each fails a test.
- 14 queue test files: 460 passed. Web: 98 passed, tsc clean.
- `analysis/phase-c/queue_order_probe.py` on a copy of the routed demo.db: 0 of 4,085 positions change (groups 1-81,
  singles 82-4,085 before and after). stress.db copy not found, so not measured there.

Cost: first page of 50 on 4,085 items, 3 runs each: old 107-291 ms, new 180-410 ms (timings on this PC vary a lot).
A join instead of the sub-query gives the same order and no clear gain; kept the sub-query.

Screen: the queue subtitle now says "Flagged first · Operational Priority ↓ · newest first on ties". Text only, no
layout change. Condition 3 (show groups and singles apart in the count) is still a screen decision for supervisors.

## C9 severity-first queue (settled decision 8) — done (2026-11-07)

Found: the served queue did not meet decision 8. On the routed demo copy, a Critical group (score 99.6) sat at
rank 80, below 35 High/Medium groups at 99.86-100 (`c9_order_check.py`).

User decisions:
- Severity is the FIRST key for EVERY source. A severe Suricata alert must never rank lower because of its source.
- A Suricata classtype not in the approved chart uses its rule priority: 1 = High, 2 = Medium, 3 = Low,
  else Informational. Never Critical without a chart entry.

Order now: severity -> flagged before unflagged (D4) -> Operational Priority -> newest -> ref.
- `packages/detection/queue_severity.py`: one scale. Flow alert = `alerts.severity`. Suricata alert = chart band of
  its classtype (`config/severity-chart.json`), else the priority fallback.
- `config/suricata-classtypes-v1.json` (43 entries, built by `build_classtype_config.py` from the local Suricata
  `classification.config`): EVE `alert.category` is the description; the chart keys on the classtype name.
- `apps/api/operational_queue.py`: `QUEUE_ORDER` uses `queue_severity_rank(...)` as its first key.
- Queue subtitle: "Severity first · flagged first · Operational Priority ↓ · newest first on ties".

Checks:
- `tests/test_queue_severity.py`: 22 tests (per-source severity, Critical above higher-score High, severe Suricata
  above flow alerts, severity beats the flagged tier, D4 inside a level, tie-breaks).
- Red check `red_check_c9.sh`: 6 planted defects, each fails a test. Defect 2 (severity after the flagged tier) first
  passed all tests; a new test closed that gap.
- 16 queue test files: 482 passed. Web 98 passed, tsc clean.
- `c9_effect.py` on the routed demo copy: 38 of 4,085 positions change; severity inversions 36 -> 0; the Critical
  group moves from rank 80 to within 1-44; flagged 1-81 / unflagged 82+ is unchanged. First page ~105 ms vs ~83 ms.
- Real adapter output: fixture 'Potentially Bad Traffic' (priority 2) -> Medium; 'Misc activity' (3) -> Low.

Not checked: no Suricata alert is in the routed demo database (source_kind is legacy_flow_alert for all 4,085), so
the mixed-source order is proven by tests only, not on real data.

## C1 verdict bridge (D1, D2) — done, local (2026-11-08)

Approval rule (user, 2026-11-07): C1 proceeds under D1/D2, which the user owns. Every screen layout still waits
for the user's approval. Earlier replies said C1-C6 needed FYP supervisor approval; the written record does not
say that (REVIEW-AND-PLAN.md 5b).

What C1 does:
- `packages/detection/verdict_bridge.py`: a V2 Tier 1 verdict on a flow alert records the mapped approved verdict
  (D2 table: confirmed_malicious -> confirm_true_positive, suspicious -> needs_investigation, expected_activity ->
  mark_expected_activity, false_positive -> mark_false_positive). A human Tier 2 escalation of a flow alert records
  the approved 'escalate' (+15). Suricata alerts: nothing written (no approved-engine row).
- Group verdict (user): the representative's legacy alert only; approved family learning carries it.
  Measured on the routed demo copy (`c1_facts.py`): 77 of 81 groups have every member in the representative's
  family. The 4 others are Tier 1 groups of 38-57 members across 34-42 families; their other families do not learn.
- One transaction: `feedback/service.py` split into `apply_feedback` (no commit) and `submit_feedback` (commits,
  unchanged behaviour for the approved API). The bridge calls `apply_feedback` inside `record_verdict` and
  `escalate_case`, before their commit.
- Verdict reason -> approved `note` (no length limit on `note`). The approved audit row names the analyst.

### Queue score decision, for final product review

Problem (measured in code): D1 says "the queue re-orders" after a verdict. The V2 queue sorted on
`operational_triage_state_v2.operational_priority`, fixed at routing time from the immutable `detection_score`
(`triage_policy.py:94`). The approved engine writes `alerts.combined_score` and `alerts.severity`. So after a
verdict the V2 queue moved only if the severity level changed.

Options:
1. Queue score = routing `operational_priority` + verdict delta (`combined_score - detection_score`), clamped 0-100.
   Computed when the queue is read; nothing new stored.
2. Keep the score frozen; only severity moves.
3. The bridge also rewrites `operational_priority`, with a triage policy audit row.

Chosen: option 1 (user asked for the recommended option, 2026-11-07). Justification:
- It meets D1: every verdict and every family move changes the queue, not only those that cross a severity level.
  Proven by `test_the_verdict_delta_moves_an_item_inside_its_severity_level` (-15 keeps Critical, still moves).
- One writer, one stored score. The approved engine stays the only writer of the verdict effect (D1); the queue
  reads it. Option 3 would store the same fact twice — the "two stores can disagree" risk D1 option B rejected.
- The routing context stays. Trusted context (up to +25) is in `operational_priority`, not in `detection_score`.
  Sorting on `combined_score` alone would drop it (planted defect 7 in `red_check_c1.sh` proves the test catches it).
- The guardrails stay the limit. The delta is the guardrailed `actual_delta`, so the queue cannot move further
  than the approved engine allowed.
- No verdict, no change: `combined_score == detection_score` for all 5,000 alerts on the routed demo copy
  (`c1_delta_precheck.py`), so the order before any verdict is the same as before C1 (tested).
- Read-only and no migration.
Cost (measured, `c1_live_check.py`, routed demo copy, 4,085 items, 3 runs): first page of 50 took 115-126 ms with
the old key and 123-131 ms with the new key (about +5 to +15 ms; timings vary on this PC).
Limit: the shown "Operational Priority" number on the screen is still the routing-time value; the queue order uses
the adjusted score. A screen change to show both needs the user's layout approval.

### C1 evidence

- Tests: `tests/test_verdict_bridge.py` 19/19 (mapping, representative only, audit actor, rollback when the
  approved write fails, rollback when a later step fails, retry writes once, correction amends, Suricata writes
  nothing, refuses outside a transaction, escalate +15, failed escalate leaves no case, queue moves by severity,
  queue moves by score inside a severity level, routing context kept, no verdict no change).
- Red check `red_check_c1.sh`: 9 planted defects, each fails >= 1 test; restored code passes 19/19. Defect 7
  (sort on combined_score alone) first passed every test; `test_the_queue_score_keeps_the_routing_context` added.
- Hand-made queue test databases (`test_queue_severity.py`, `test_operational_queue.py`) got `detection_score` and
  `combined_score` columns with equal values (delta 0); no expected order changed. C9 red check re-run: 6/6 defects
  still fail, 52/52 pass restored.
- Live check through the real API (`c1_live_check.py`, routed demo copy): g.ang claims the top Tier 1 group, POST
  verdict `false_positive` -> 200. Approved row: `mark_false_positive`, requested -30, actual -30, `applied`, note
  kept, user 1. Approved audit: `FEEDBACK` and `SIMILAR_ALERT_LEARNING`, both actor 1. Legacy score 100 -> 70,
  severity -> High. Queue position 1 -> 75. Family learning gate stayed closed ("1 of 3 required"), so no other
  member moved: approved behaviour, not a defect.
- Web: `AnalystVerdict.tsx` already sends the 4 D2 outcomes; no screen change in C1.

Not covered by C1: the existing approved API `POST /api/alerts/{id}/feedback` still works on its own; a direct
approved verdict does not create a V2 verdict (one direction only, as D1 states).

## Screen layout approvals (user, 2026-11-08)

Pack: `analysis/phase-c/SCREEN-REVIEW-PACK.html`. All approved as shown:
- Q1 C2: add 2 tabs (Tier 2 candidates, Auto-escalated) to the existing 10.
- Q2 D4 condition 3: groups and singles apart in the Tier 1 tab label and the KPI.
- Q3 Release: inline confirm form.
- Q4 C3: Why Tier 2 panel on the Overview tab, above the verdict form.
- Q5 C4: as shown (AL short name, rule conditions, combined explanation, agreement, confidence fix).
- Q6 C5: new Flow & Score tab, flow alerts only.
- Q7 C6: new append-only V2 notes table (option A), owner-guarded.
Build order: C4, Release, C6, C3, C2 + D4 condition 3, C5.

## C4 evidence items — done, local (2026-11-08)

- Header AL short name, rule clause table, combined explanation, rule/model agreement, S7-05 fusion confidence.
- Tests: `OperationalEvidenceFlow.test.tsx` 10/10. Red check `red_check_c4.sh`: 7/7 defects caught. Web 127/127 (18 files). tsc clean.
- Live (demo copy, ports 8011/5181, g.ang): AL-01958 shows `· AL-01958`, Confidence 100.0%, "Rule and model agree", the explanation, and the 5-clause table.
- Open: the Historical XGBoost Evidence card still shows "Supplied confidence: Not provided" for corroborated alerts (canonical confidence is null). It conflicts with 100.0% in the provenance block. Needs a decision.
