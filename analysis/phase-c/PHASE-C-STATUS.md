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
