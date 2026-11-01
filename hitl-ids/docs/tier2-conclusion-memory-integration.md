# Tier 2 Investigation Conclusion → Triage Memory Integration V1

Base: `feat/tier2-human-reclassification` at `9d2f8761127121739a20195b089debafdecdfc23`.
Feature branch: `feat/tier2-conclusion-memory-integration`.

## Human evidence precedence

**Tier 2 Expert Conclusion > Tier 1 Analyst Verdict > historical compatibility evidence**
for the **same primary operational alert**. One alert supplies at most one current human
learning vote per lesson. Different scopes or repeated contributions cannot manufacture
independent support. Contributions still require explicit human action.

The latest Case Finding is an authority barrier as soon as it exists. Earlier Tier 1,
older Tier 2 and compatibility evidence become historical/non-current immediately,
before a replacement is contributed. Only evidence linked to the latest eligible canonical
Investigation Conclusion can count. With no expert Finding, the existing latest-Verdict
behavior is retained. Case conclusions apply only to the Case's primary alert: linked and
suggested alerts never inherit the conclusion.

| Latest canonical Tier 2 Finding | Reusable Memory outcome |
|---|---|
| confirmed_malicious | confirmed_malicious |
| suspicious | suspicious |
| expected_activity | expected_activity |
| inconclusive | Not eligible; zero current reusable evidence from this alert |

Inconclusive still supersedes earlier evidence. It is not mapped to false_positive,
expected_activity or any invented outcome. Historical compatibility Findings are readable
and conservatively block revival of lower-authority evidence, but a current canonical
Investigation Conclusion is required for a new expert contribution.

Example: Tier 1 Expected Activity was contributed. Tier 2 later records Confirmed
Malicious / Web Attack. The old vote immediately stops supporting its lesson. An explicit
expert contribution then supplies a single Confirmed Malicious vote, which may conflict
with that lesson. If Tier 2 instead records Inconclusive, the alert supplies zero current
reusable votes and no contribution button appears.

## API and authorization

`POST /api/v2/tier2/cases/{caseRef}/triage-memory/from-conclusion`

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "expectedCaseRevision": 2,
  "conclusionEventId": 15,
  "scope": "exact"
}
```

Only identity/version and scope (`exact` or `narrow`) are accepted. The server resolves
Case, primary alert, latest canonical conclusion, Finding/outcome, investigation reason,
author, human category, detector/context snapshots and operational state version.
Caller-supplied outcome, reason, actor or final category is rejected. Missing/ineligible/
superseded conclusions and stale Case revisions are rejected. No Tier 1 Verdict is required
for automatic Unknown/Expert or Critical cases. Current analyst/admin authorization is
reused; evaluators are read-only and system policy cannot author human learning evidence.

`GET /api/v2/tier2/cases/{caseRef}/triage-memory/conclusion-state` returns
`ConclusionMemoryState`: latest conclusion, eligibility, contribution status, scope,
lesson reference/current Memory view, previous expert supersession and Tier 1 supersession.
It uses `ReadConn` / `ReadPrincipal`; GET never migrates, writes audit or changes evidence.

Mutation returns the existing `MemoryMutation`. Exact retries replay the original
contribution without another vote. Reused request identity with another actor/payload is
rejected. A conclusion event can be contributed once, regardless of contributor or scope.
An old request can replay after correction, but cannot restore its now-superseded evidence.
A new attempt to contribute an older event is rejected. Immediate transactions serialize
competing writers and rollback all lesson/evidence/audit inserts on failure.

## Additive storage and immutable provenance

Schema migration **18** adds `conclusion_memory_contributions` and
`conclusion_memory_evidence`, with foreign keys, unique conclusion/request identities,
per-lesson uniqueness and update/delete/replace protections. Existing Verdict-linked and
historical evidence tables are retained unchanged. Normal explicit writable migration
upgrades version 17 databases; read-only endpoints refuse an outdated schema rather than
migrating on GET.

Memory evidence distinguishes `tier2_conclusion`, `analyst_verdict` and
`legacy_memory_review`. Older Verdict snapshots are identified from their existing Verdict
reference, without rewriting stored JSON. New expert evidence preserves:

- primary operational alert and source Case references;
- the immutable typed conclusion, including event/request ID, Case revision, Finding,
  human final category, reason, actor, timestamp, system classification and supersession;
- conclusion author display name captured at contribution time;
- separate contribution actor ID/name and chosen scope;
- immutable detector snapshot, existing Memory context snapshot, source operational state
  version and contribution timestamp.

The contributor is never represented as the conclusion's author when they differ. The
human final category is provenance only: it is not a Memory key, outcome mapping input,
classifier override or routing signal. Existing context_for, Exact/Narrow identity fields,
matching rules, thresholds, expiry and human activation requirements remain intact.

## Effective evidence, audit and safety

The effective-evidence projection includes the new evidence table, selects only the latest
authoritative source for each alert, and deduplicates by operational alert reference.
Supersession changes the projected Memory revision even before replacement contribution,
so stale activation/Selective Review snapshots cannot keep trusting withdrawn evidence.

Recording a canonical expert conclusion captures earlier current evidence and appends
`V2_TRIAGE_MEMORY_EXPERT_SUPERSEDED` audit entries in the **same Case transaction**.
These retain the old evidence and identify the superseding event; they do not create new
reusable evidence or a lesson. Read-time Current/Superseded labels remain dynamic, while
historical audit payloads stay immutable. Exact Case-command retries do not duplicate audit.

Explicit contribution reuses the existing candidate/support/conflict machinery. Three
distinct compatible expert sources can produce support 1 → 2 → 3 and eligibility, but
never automatic activation. Positive Exact evidence cannot broaden Narrow support;
contradictions still reach every compatible lesson. Conflicts use the existing
conflict_review gate. Expert authority does not bypass agreement, minimum support,
freshness or human approval.

An immutable past activation decision remains in history. If current evidence loses its
threshold, projected status becomes candidate and guidance is withdrawn; conflicts cause
conflict_review. Existing Selective Review recomputes current guidance and effective
disposition. KPI, queue filters and detail views stop presenting stale No Immediate Review.
No old Review event is destructively updated. Existing review version invalidation remains
conservative, including after other learning mutations.

## UI

The existing Case page gains **Human Learning** after investigation controls. It shows
the latest expert Finding, final category and canonical reason. Only scope is selectable;
there are no duplicate outcome/reason/category inputs. Eligible current conclusions can
be explicitly contributed. The result shows contribution scope, linked lesson, projected
Memory status and support/conflict counts. Corrections identify prior expert evidence as
superseded. Tier 1 replacement has a separate brief explanation. Inconclusive offers no
contribution control. Evaluators see read state without mutation controls.

The standalone Memory page preserves Verdict evidence and adds explicit expert source,
Finding, final category, investigation reason, conclusion author, Memory contributor,
Case/alert links, scope and Current/Superseded status. Timeline supersession is visible
without reading raw JSON. Tier 1 learning tells users to use the Case when expert
investigation has superseded earlier Verdict evidence.

## Validation

Final results: **566 backend tests passed, 1 existing ML-artifact test skipped**;
**247 frontend tests passed across 34 files**. TypeScript, OpenAPI/schema freshness,
production build and whitespace checks passed. The comprehensive expert-learning browser
journey passed all five scenarios and six width/theme combinations; both existing
human-reclassification and Assistance browser journeys also passed (**3 browser tests**).
Existing dependency deprecation messages and Vite's bundle-size advisory remain.

The dedicated backend suite covers direct mapping, absence of automatic learning,
separate authorship, complete non-Memory table isolation, read-only state, immediate
Tier 1/Inconclusive withdrawal, expert correction, history, replay/conflicting identity,
concurrent retry, three-source activation/conflicts, Exact/Narrow boundaries, Critical
automatic Case/admin contribution, provenance tampering, stale/missing sources, roles,
transaction rollback, immutable storage, and Selective Review/KPI/queue consistency.

Regression includes Tier 2 conclusions/Cases/direct escalation, Triage Memory,
Verdict → Memory, Selective Review, Investigation Assistance, Response, Analyst Verdict,
Protocol V2 freeze, read-only inspection, schema contracts and additive migrations.
Migration expectations/inventories add version 18 and its two tables; existing assertions
are retained. The ML-generated fixture test remains skipped when its gitignored artifact
is absent; no classifier inference or retraining is initiated.

Real browser scenarios use the real API and a disposable synthetic database:

- automatic Unknown → eligible expert conclusion → explicit Exact → candidate/provenance;
- Tier 1 Expected Activity → contribution → escalation → expert supersession → replacement;
- Inconclusive → old Tier 1 evidence withdrawn and no new contribution;
- expert correction → old evidence immediately superseded → explicit current replacement;
- initial active expected-activity lesson loses one of three sources → support 2,
  inactive guidance and No Immediate Review 3 → 0.

The active-guidance baseline is tested before other learning mutations, since the existing
review version policy conservatively invalidates old Review snapshots after learning changes.
Human Learning is checked at 1440/1024/390 widths in dark/light themes without page-level
horizontal overflow; screenshots in ignored `apps/web/test-results/` were visually inspected.
Existing independently runnable human-reclassification and Assistance/response browser
journeys also pass. Existing obsolete legacy rehearsal fixtures were not redesigned.

From `apps/web`, set `HITL_PYTHON` to the installed interpreter and run:

```text
node node_modules/@playwright/test/cli.js test --config playwright.conclusion-memory.config.ts
node node_modules/@playwright/test/cli.js test --config playwright.reclassification.config.ts
node node_modules/vitest/vitest.mjs run
node node_modules/typescript/bin/tsc -b
node node_modules/openapi-typescript/bin/cli.js ../api/openapi.json -o src/api/schema.d.ts --check
node node_modules/vite/bin/vite.js build
```

New browser fixture ports are 8022/5192, separate from existing user previews. It asserts
zero prospective runs and the browser asserts no response/collection mutation. Backend
logs and browser artifacts are kept under ignored test-results.

## Scope and limitations

System Classification, Human Final Classification event, source priority/routing,
Case state/ownership, Tier 1 Verdict, detector evidence and Response records are unchanged
by contribution. Conclusion recording adds only the described legitimate supersession audit
when earlier Memory evidence exists. Response remains Finding-based and approval never
executes an action. Investigation Assistance is unchanged.

No classifier retraining, category propagation to linked/future alerts, automatic lesson
activation, Case closure, response execution, guided tour or independent review is added.
Protocol V2 is unchanged/unopened; no operational prospective collection is started.
No merge or PR is created. Effective evidence is computed on read using FYP-scale queries;
this increment adds no large-volume indexing/service redesign. Historical Findings need a
canonical current conclusion before expert contribution. Human category remains provenance,
not a policy for classifying future traffic.

## Exact changed files

Paths relative to `hitl-ids`:

```text
apps/api/contract/openapi.py
apps/api/memory_routes.py
apps/api/openapi.json
apps/web/e2e/conclusion-memory-fixture.py
apps/web/e2e/conclusion-memory.spec.ts
apps/web/playwright.conclusion-memory.config.ts
apps/web/src/api/schema.d.ts
apps/web/src/features/alert/VerdictLearning.tsx
apps/web/src/pages/analyst/ConclusionLearning.test.tsx
apps/web/src/pages/analyst/ConclusionLearning.tsx
apps/web/src/pages/analyst/Tier2CasesPage.tsx
apps/web/src/pages/analyst/TriageMemoryPage.test.tsx
apps/web/src/pages/analyst/TriageMemoryPage.tsx
docs/tier2-conclusion-memory-integration.md
packages/contracts/conclusion_memory.sql
packages/contracts/db.py
packages/detection/tier2_cases.py
packages/detection/triage_memory.py
tests/test_api_contract.py
tests/test_canonical_api.py
tests/test_conclusion_memory.py
tests/test_contracts.py
tests/test_inspection_readonly.py
tests/test_operational_v2.py
tests/test_triage.py
tests/test_triage_policy.py
tests/test_verdict_memory.py
```
