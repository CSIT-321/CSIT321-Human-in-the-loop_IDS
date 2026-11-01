# Tier 2 Case Resolution / Closure V1

Base: `feat/tier2-conclusion-memory-integration` at
`ed600e198bd833e4b7c76857d928929bd44f68af`.
Feature branch: `feat/tier2-case-resolution`.

## Final Case lifecycle

**Open → Investigating → Resolved**.

Resolution is an explicit human statement that active investigation is complete enough
to close the Case. It does not delete evidence, execute a response, change classifications,
assign an owner or change the underlying alert's routing/priority. All history remains
readable. V1 has no Reopen action.

The primary alert may remain historically routed to `tier2_case` with its existing
operational workflow/review state, while the Case is `resolved`. This distinction is
intentional: closure is a Case lifecycle event. The existing open-Case KPI excludes
Resolved cases; historical Tier 2 routing counts and effective review disposition do not
change merely because a Case closes.

## Resolution contract and prerequisites

`POST /api/v2/tier2/cases/{caseRef}/resolve` accepts the existing `CaseCommand`:

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "expectedRevision": 5,
  "reason": "Investigation completed; the response plan is approved but has not been executed."
}
```

The Case must be Open or Investigating, have a latest Investigation Conclusion/Finding,
and have a nonblank resolution reason. All four Findings are supported:
`confirmed_malicious`, `suspicious`, `inconclusive`, `expected_activity`.
Inconclusive may be closed with an explicit monitoring/insufficient-evidence explanation.
Historical Findings remain usable without fabricating a missing human category.

The normal journey explicitly starts investigation. For compatibility with existing Case
semantics, a Case that already has a conclusion can also resolve from Open; V1 does not
invent an additional mandatory Start action.

The server resolves Case, actor, latest conclusion and response state. Caller-supplied
Finding, category, actor or decision source is rejected. Existing active analyst/admin
authorization applies. Evaluators can read but cannot resolve; system policy cannot
resolve or manufacture an analyst actor.

## Exact response rule

**Every existing response recommendation must have a human Approve or Reject decision
before resolution.** Pending recommendations block closure, including stale proposals.
An old stale proposal can be explicitly rejected using the existing response workflow.

No response recommendation is required when none exists. There is no forced containment
for Expected Activity, Suspicious or Inconclusive. A response is never automatically
generated, approved, rejected or executed by closure.

Existing terminal decisions are preserved, not reassessed against a new response policy.
Their original proposal Case revision is retained in the resolution snapshot. If a human
has corrected the conclusion since a decision, that original decision remains historical;
resolution does not silently rewrite it or force another recommendation. The analyst's
resolution reason records why investigation can close.

The response chain remains:

`Human Finding → Response Recommendation → human Approve / Reject → Approved - Not Executed`.

Execution is never a prerequisite or an action. After closure, new response proposals and
new decisions are blocked, while history and exact idempotent retries remain available.
The response policy itself is unchanged.

## State, immutable event and idempotency

Migration **19** rebuilds only `tier2_case_state` and `tier2_case_events` to extend their
status/action checks. It preserves all rows, IDs, timestamps, request payloads, JSON
snapshots and system/analyst attribution, including null system-create actors. Dependent
conclusion-memory foreign keys are preserved. The normal migration framework disables
foreign keys only during the locked rebuild, runs `foreign_key_check` before commit and
restores the original foreign-key setting. GET never performs this migration.

Resolution updates only mutable Case status/revision/update time and appends one
`V2_TIER2_CASE_RESOLVED` event with action `resolve`. Existing Case snapshots and event
append-only protections remain. A unique resolution index prevents multiple resolution
events for one Case. Resolved state updates and new normal investigation event inserts
also have database guards.

The resolution event's immutable after-state stores:

- actual resolver display name, with actor ID in the event row;
- latest typed Investigation Conclusion, including its event/request ID and human category;
- every terminal response recommendation reference/type, proposal Case revision, approval
  status, decision actor/time and `not_executed` execution status.

`CaseView.resolution` and `CaseEvent.resolution` expose typed `CaseResolution`, which also
contains Case/event identity, reason, time, request ID, Case revision and previous/new status.
Creation attribution and owner remain unchanged; a system-created Case is still shown as
system-created even when a human resolves it.

The existing immediate transaction and optimistic revision check serialize writers.
Exact resolution retry replays the same event/result without another revision increment.
Reusing a request ID with different payload/actor/action is rejected. A second new resolve
request is rejected after closure. A previously committed note/start/response command may
still replay with its exact old request identity; this is a nonmutating retry, not permission
to add a new investigation action. Failed event insertion rolls back the status update.

## Behavior after Resolved

New notes, links, Findings, conclusions and Start Investigation are rejected. The legacy
Finding endpoint is covered as well. New response proposals/decisions are rejected.
There is no Reopen endpoint or ownership/SLA workflow.

Case, notes, linked alerts, conclusions, original/system and human classifications,
Investigation Brief, Related Alerts, response history, Human Learning provenance and audit
timeline remain readable through existing read-only endpoints. Case list retains all
historical cases and shows Resolved status; no extra filtering/dashboard is added.

The Case page disables/hides investigation, linking, response and learning write controls
once resolved, while keeping their read views. It shows a prominent Resolved status and a
Case Resolution section with resolver, timestamp, reason, conclusion reference and response
approval snapshots. Timeline shows **Case Resolved**, actor, reason, time and status transition
directly, rather than only in raw JSON.

The resolution form shows latest Finding, human final category and current response approval
state. It fetches all existing response pages, and response proposals/decisions refresh this
display. The server rechecks all prerequisites under the write lock, so concurrent response
or Case changes cannot bypass closure requirements. The UI retains retry identity on error.

## Shared human learning remains intact

**Tier 1 Analyst Verdict and Tier 2 Expert Conclusion are two human-evidence sources
feeding the same Triage Memory.**

For the same alert, the latest Tier 2 expert conclusion supersedes the earlier Tier 1
Verdict learning evidence. **One Alert = One Current Learning Vote.**

Resolution does not add a Finding or supersede one. It does not delete a contribution,
change effective evidence, change a Memory revision, activate/withdraw guidance or modify
Selective Review. Legitimate current expert evidence remains current under existing
precedence, expiry and conflict rules. Its source Case can be Resolved.

The Memory service and its authorization rules are unchanged. Although the closed Case UI
is read-only, separately authorized explicit Memory contributions through the existing
Memory API continue to follow its existing latest-conclusion/scope/version rules; they do
not reopen or mutate the Case. No additional learning feature is introduced.

## Validation

Final validation: **589 backend regression tests passed, 1 existing ML-artifact test
skipped**. The final expanded Resolution suite passed **26 tests**, including three
subsequently added checks for open-Case KPI/history counts, Monitor response behavior and
legacy/nonmutating retry compatibility. **252 frontend tests passed across 35 files**.
TypeScript, OpenAPI/schema freshness, production build and whitespace checks passed.
All **four real-browser tests** passed: the new closure journey, expert learning,
human reclassification, and Investigation Assistance/response regression. Six required
width/theme combinations passed. Existing dependency deprecation messages and Vite's
bundle-size advisory remain; no browser runtime errors were reported.

The dedicated resolution suite covers all Findings, missing conclusion, nonblank reason,
server-derived facts, roles/auth/system-actor rejection, exact replay/conflicts, concurrent
resolution, closed investigation and response guards, rollback, legacy readability,
nonmutating old-command retries, historical routing/open-case counts, non-containment
Monitor responses, complete non-lifecycle-table snapshots and current Memory preservation.
The populated version-18 → 19 migration test retains exact state/event/response/Memory rows
and IDs, validates all foreign keys and verifies resolution after upgrade.

Regression includes Tier 2 Cases/direct escalation/conclusions, Response, Tier 2 → Memory,
Verdict → Memory, Triage Memory, Selective Review, Investigation Assistance, Analyst Verdict,
Protocol V2 freeze, API/read-only inspection, schema and migration compatibility. Migration
expectations append version 19; no existing assertions are removed or weakened.

Real disposable Chromium scenarios:

1. Unknown → auto Expert Case → start → note/link → Confirmed Malicious/Web Attack →
   recommendation → pending closure blocked → human approval → Approved - Not Executed →
   expert Memory contribution → explicit Resolve → terminal/readable history and current Memory.
2. Expected Activity → explicit Resolve without forcing a response/containment recommendation.
3. Resolved UI hides writes; server rejects a new Note; Case list, timeline, Brief, linked
   evidence, conclusions, response approval and Memory provenance stay readable.

Resolution controls are checked at 1440, 1024 and 390 pixels in dark/light themes, with no
page horizontal overflow. Screenshots under ignored `apps/web/test-results/` were visually
inspected. Existing expert-learning, human reclassification and Assistance/response browser
journeys are also regressed using their current disposable synthetic fixtures.

From `apps/web`, with `HITL_PYTHON` pointing to the installed interpreter:

```text
node node_modules/@playwright/test/cli.js test --config playwright.resolution.config.ts
node node_modules/@playwright/test/cli.js test --config playwright.conclusion-memory.config.ts
node node_modules/@playwright/test/cli.js test --config playwright.reclassification.config.ts
node node_modules/vitest/vitest.mjs run
node node_modules/typescript/bin/tsc -b
node node_modules/openapi-typescript/bin/cli.js ../api/openapi.json -o src/api/schema.d.ts --check
node node_modules/vite/bin/vite.js build
```

The new browser fixture uses temporary synthetic data on 8023/5193, preserves existing
previews, never uses demo.db, and starts no prospective collection. API schema freshness
is checked with `python scripts/build_openapi.py --check` from `hitl-ids`.

## Limits and core-feature completion

No Reopen, automatic resolution, ownership assignment, SLA, ITSM integration, response
execution, additional learning feature, guided tour, independent review or detection change
is included. Pending response decisions must be completed explicitly. Historical missing
human categories remain missing; closure does not fabricate them. Production version-18
databases require the standard explicit writable migration before read-only inspection.

**This completes core product feature development.** The next project phases are final
end-to-end validation, real Suricata validation, evaluation, integration and documentation.
Further core HITL feature development is out of scope after this increment. This feature
does not merge branches, create a PR or open prospective collection. Protocol V2 stays
unchanged and unopened.

## Exact changed files

Paths relative to `hitl-ids`:

```text
apps/api/contract/openapi.py
apps/api/openapi.json
apps/api/tier2_case_routes.py
apps/web/e2e/case-resolution.spec.ts
apps/web/playwright.resolution.config.ts
apps/web/src/api/schema.d.ts
apps/web/src/pages/analyst/CaseResolution.test.tsx
apps/web/src/pages/analyst/CaseResolution.tsx
apps/web/src/pages/analyst/ResponseRecommendations.tsx
apps/web/src/pages/analyst/Tier2CasesPage.test.tsx
apps/web/src/pages/analyst/Tier2CasesPage.tsx
docs/tier2-case-resolution.md
packages/contracts/db.py
packages/contracts/tier2_case_resolution.sql
packages/detection/response_approval.py
packages/detection/tier2_cases.py
tests/test_api_contract.py
tests/test_canonical_api.py
tests/test_tier2_case_resolution.py
tests/test_triage.py
tests/test_triage_policy.py
tests/test_verdict_memory.py
```
