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
