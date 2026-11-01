# Tier 2 Human Attack Reclassification + Investigation Conclusion V1

Base branch: `feat/tier2-investigation-assistance`.
Exact base: `2af33be1f5903ede6b29190f4ae10dc423ed339e`.
Feature branch: `feat/tier2-human-reclassification`.

## Meaning and workflow

System Attack Classification is the automation result at triage/admission time.
Human Final Attack Classification is the expert's explicitly chosen interpretation after
investigation. Finding is the human security conclusion about the event. These concepts
are separate; a human category never overwrites the system category or determines response
by itself.

Primary example:

`Suricata → System Unknown / Needs Expert → automatic Expert Tier 2 Case → Investigation Assistance → explicit Start Investigation → Human Finding Confirmed Malicious + Human Final Attack Classification Web Attack`.

The Case continues to show **System Attack Classification: Unknown / Needs Expert**.
An expert may likewise retain or correct a known category: system Brute Force can coexist
with human Infiltration or Reconnaissance / Port Scan. No detector output, native evidence,
classification-v3 snapshot, priority, system route, creation attribution or alert routing
history is rewritten. Conclusions do not start or close the Case automatically.

## Contract and validation

`POST /api/v2/tier2/cases/{caseRef}/conclusions` accepts `InvestigationConclusionRequest`:

```json
{
  "requestId": "a UUID identifying this logical command",
  "expectedRevision": 2,
  "finding": "confirmed_malicious",
  "finalAttackCategory": "web_attack",
  "reason": "The expert's evidence-based investigation reason"
}
```

`finding` retains exactly `confirmed_malicious`, `suspicious`, `inconclusive`,
`expected_activity`. The final-category enum retains the existing concrete normalized
taxonomy: `brute_force`, `botnet_c2`, `dos`, `ddos`, `web_attack`, `infiltration`,
`reconnaissance_port_scan`, `malware_exploit`, `other_known_attack`.

| Finding | Human final category |
|---|---|
| Confirmed Malicious | Required, explicitly selected concrete category |
| Suspicious | Optional concrete category, otherwise unresolved/null |
| Inconclusive | Optional concrete category, otherwise unresolved/null |
| Expected Activity | Must be null / not applicable |

Unknown / Needs Expert is a system escalation category, never a human final option.
Benign, false_positive and expected_activity are not attack categories. False Positive
remains a Tier 1 Verdict concept. `other_known_attack` is available for confirmed malicious
activity that cannot be mapped more specifically; a nonblank investigation reason remains
mandatory for it and every other conclusion. No category is inferred from automation.

Existing Case mutation authentication and active security analyst / system administrator
authorization apply. Evaluators can read but cannot write. The actor comes from the
authenticated principal; clients cannot submit `actorId` or `decisionSource`. No system
policy actor or fabricated analyst may record a human conclusion.

## Append-only storage and compatibility

No database migration is necessary. The existing immutable `tier2_case_events` ledger
already supports Finding events and JSON snapshots. A new conclusion is a Finding action
with event type `V2_TIER2_INVESTIGATION_CONCLUSION_RECORDED`. Its existing row stores
Case identity, actor, finding, reason, request ID/payload, timestamp and state revision.
Its `after_state.investigationConclusion` stores the explicit human category, immutable
system classification visible when recorded (or null if unavailable), and the previous
Finding/conclusion event ID being superseded. The event and Case creation tables retain
their existing update/delete/replace protections.

`CaseView` exposes `systemAttackClassification` and `latestConclusion`.
`CaseEvent.conclusion` exposes a typed `InvestigationConclusion`, containing:

- `eventId`, `caseRef`, `finding`, nullable `finalAttackCategory`;
- `actorId`, `reason`, `createdAt`, `caseRevision`, `requestId`;
- nullable `systemClassification`, nullable `supersedesEventId`;
- `recordKind`: `investigation_conclusion` or `legacy_finding`.

These references allow a future learning feature to reference a specific immutable
conclusion. No learning integration is implemented here.

Corrections append another event, increment the Case revision once, and identify the prior
event; history remains intact. Latest means the most recent Finding action in event order.
Exact request retry returns the same event ID with `replayed=true`, without another event
or revision increment; the response Case is the current Case, consistent with existing
Case mutation semantics. Reusing a request ID with another payload, actor or action is
rejected. Existing optimistic revision checks and immediate write transaction serialization
protect concurrent submissions.

Historical Finding events are decoded without fabricating a final category, a historical
system-classification snapshot, or supersession metadata. They display **Not recorded
(historical Finding)**. The old `/findings` endpoint retains its legacy contract, including
historical confirmed-malicious Findings with no category, for compatibility. The current
UI uses only `/conclusions`; its required-category rule applies to that new contract.

## Case UI, assistance and response

The existing Findings tab becomes **Investigation Conclusion** on the same Case page.
It displays the original system classification, Human Investigation Finding, Human Final
Attack Classification, Investigation Reason, and Record Investigation Conclusion.
Confirmed Malicious requires explicit category selection before submission. Expected
Activity clears/disables the category. System classification is never copied into the
human selection. Case Summary shows the latest human conclusion alongside the preserved
system classification. Conclusion history and Audit Timeline show categories, actor,
reason, time, revision and supersession directly, without requiring raw JSON inspection.

Investigation Assistance continues to show its unchanged historical system classification,
case creation snapshot and uncertainty. Tier 1 Verdict remains separate and unchanged.
Related alerts are not reclassified, linked or otherwise propagated by a conclusion.
Suggested steps stay advisory; no suggestion is retrospectively marked completed.

Response recommendations refresh when the Case revision changes. Existing response logic
still reads the latest Finding action; no response-policy implementation changed:

- Confirmed Malicious plus a valid source target can suggest Block Source IP.
- Suspicious + Infiltration produces Monitor, not confirmed-malicious containment.
- Expected Activity produces Monitor.
- Inconclusive produces Further Investigation.

A recommendation is still an explicit subsequent action, followed by human Approve /
Reject. Approval ends at **Approved - Not Executed**. New conclusions make older proposal
snapshots stale under the existing revision checks. No response is generated or executed
merely by recording a conclusion.

## Validation

- Requested backend regression run: **417 passed** across Case, direct escalation,
  conclusion, assistance, response, Verdict, Verdict Memory, Triage Memory, Selective
  Review, routing, Protocol V2 freeze, OpenAPI contract and read-only inspection tests.
- Final conclusion suite rerun: **30 passed**, including two subsequently added tests
  for exact taxonomy consistency and anti-spoof/inactive-user rejection.
- Complete frontend suite: **242 passed**, 33 files. TypeScript, OpenAPI/schema freshness,
  production build and diff whitespace checks passed.
- Real disposable Chromium feature/assistance suite: **2 passed**. The feature journey
  covers Unknown → Web Attack, known Brute Force → Suspicious/Web Attack → corrected
  Confirmed Malicious/Infiltration, preserved Tier 1 Verdict, visible history, Expected
  Activity/null, Finding-based response recommendations, and approval without execution.
  The second journey regresses the complete Assistance/start/note/link/audit/response path.
- Conclusion controls were exercised at 1440, 1024 and 390 pixels in dark and light themes,
  with explicit category selection remaining usable and no page horizontal overflow.
  Screenshots are in ignored `apps/web/test-results/` and were visually inspected.

The complete backend-table comparison permits changes only to Case state/event ledger
and its sequence; immutable Suricata/system classification, routing/priority, Tier 1
Verdict, Memory/Selective Review, linked alerts and collection remain identical. Tests
also cover legacy readability, append-only SQL protections, reason validation, role/auth,
request replay/conflicts, stale revisions and concurrent same/different requests.

Reproduce the feature browser suite from `apps/web`, with `HITL_PYTHON` set to the installed
interpreter: `node node_modules/@playwright/test/cli.js test --config playwright.reclassification.config.ts`.
It uses the real API and a temporary synthetic database on 8020/5190; no demo database or
prospective collection is opened. Other existing previews are preserved.

An additional attempt to launch the three older Case/response/workstation browser scripts
was blocked before tests by their pre-existing rehearsal fixture: it omits the current
mandatory capture scope and supplies caller context to bundled admission, which now
requires persisted trusted facts. Their UI labels/category selection steps were updated,
without weakening assertions; that older fixture was not redesigned in this feature.
The new feature and Assistance browser suite above is independently runnable and passed.
Existing dependency deprecation messages and Vite's bundle-size advisory remain.

## Scope and limitations

There is no Tier 2 conclusion → Memory integration, related-alert propagation, model
retraining, final human category override of system data, Case closure workflow, task
engine, response execution or ownership workflow. Historical missing final categories
remain missing. No independent review, merge or PR is performed. Protocol V2 configuration
is unchanged and unopened; no prospective collection is started.

## Exact changed-file manifest

Paths below are relative to `hitl-ids`:

```text
apps/api/contract/openapi.py
apps/api/openapi.json
apps/api/tier2_case_routes.py
apps/web/e2e/human-reclassification-fixture.py
apps/web/e2e/human-reclassification.spec.ts
apps/web/e2e/investigation-assistance.spec.ts
apps/web/e2e/response-approval.spec.ts
apps/web/e2e/tier2-case.spec.ts
apps/web/e2e/unified-workstation.spec.ts
apps/web/playwright.reclassification.config.ts
apps/web/src/api/schema.d.ts
apps/web/src/pages/analyst/InvestigationConclusion.tsx
apps/web/src/pages/analyst/Tier2CasesPage.test.tsx
apps/web/src/pages/analyst/Tier2CasesPage.tsx
docs/tier2-human-reclassification.md
packages/detection/tier2_cases.py
tests/test_api_contract.py
tests/test_tier2_human_reclassification.py
```
