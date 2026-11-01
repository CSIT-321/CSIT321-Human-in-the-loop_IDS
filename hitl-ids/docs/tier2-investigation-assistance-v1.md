# Tier 2 Investigation Assistance V1

Base: `feat/verdict-memory-integration` at `05272930cc71af1d7a0c07d7a42340e7ddcfd868`.
Feature branch: `feat/tier2-investigation-assistance`.

Assistance summarizes recorded evidence, correlates potentially related current alerts,
and suggests investigation steps. It does not decide a Finding, confirm maliciousness,
execute a response, automatically link alerts, or merge cases. No runtime LLM or external
enrichment API is involved. No database migration is required.

## API and provenance

`GET /api/v2/tier2/cases/{caseRef}/assistance` returns `InvestigationAssistance`:

- `caseRef`, `assistancePolicyVersion`, `correlationWindowHours`, `maximumRelated`;
- `brief`: `atCaseCreation`, `classificationAtAdmission`, `systemRoutingAtAdmission`,
  `suricataEvidenceAtCreation`, `currentCaseStatus`, `currentCaseRevision`,
  `currentTier1Verdict`, `tier1VerdictExplanation`, `currentTrustedContext`, `uncertainties`;
- `relatedAlerts`: a bounded shortlist with explicit relationship reasons;
- `suggestedSteps`: ordered advisory template text, without completion status.

The endpoint uses the existing `ReadConn` / `ReadPrincipal` dependency chain and a single
read transaction. Missing cases return 404. Existing active analyst, administrator and
evaluator read permissions apply. Evaluators gain no mutation authority.

**At Case Creation** is the unchanged immutable `CaseSnapshot`: original detector evidence,
priority/band, routing audit and escalation/handoff reasons. Its signatures and native
severity are historical detector evidence. The original system classification and system
route are read from the immutable admission ledger and explicitly labeled **at Admission**;
manual escalation does not rewrite an original `ROUTINE_REVIEW` decision.

**Current Case and Human Context** separately shows current status/revision, latest
canonical Tier 1 Verdict with reason, author, timestamp and revision, and current resolved
trusted context. Verdict data is not presented as part of the creation snapshot.
Automatic cases with no Verdict say “Not recorded / not required for automatic Tier 2
routing.” Manual cases without one do not invent or retrospectively require a Verdict.

Trusted context reuses the platform resolver. Values, status, source type/reference,
fact reference, subject, observation/availability/validity/expiry and reason are available
in the provenance disclosure. Unknown, expired and conflicting values remain unknown;
synthetic facts remain labeled synthetic. No scanner, asset identifier or authorized
schedule is invented from unavailable data. Historical cases without a system ledger
remain readable and explicitly report unavailable normalized classification.

Unknown / Expert cases explain unresolved classification without asserting maliciousness.
Classification reasons, matches, conflicting categories and their signatures are available
in a disclosure. Critical cases show the recorded Critical Escalation reasons, original
priority and actual trusted context. Manually escalated cases show human attribution and
escalation reason plus the latest Tier 1 Verdict when present. Missing optional HTTP,
DNS, TLS or SSH records are evidence limitations, not a benign/malicious conclusion.

## Related-alert policy

`config/tier2-assistance-v1.json` selects policy `tier2-assistance-v1`, an inclusive
**±24-hour event-time window** relative to the primary alert, **maximum 20 results**, and
enabled relationship rules. Update the version when changing policy semantics.

Rules use real existing fields:

1. Same source IP.
2. Same destination IP.
3. Same ordered source/destination pair (an additional explicit reason).
4. Same normalized known attack category. Shared Unknown or informational/null is not
   treated as evidence of a common attack class.
5. Shared Suricata signature ID.
6. Same sensor provenance (a weak reason, not proof of a common incident).

At least one configured non-temporal relationship is required. Every suggestion also
explains that it falls within the time window. There is no probabilistic confidence,
hidden similarity score, or declaration of a campaign.

Selection joins admitted external V2 operational alerts, system-routing records and
current triage state. It excludes the primary, already-linked alerts, resolved alerts,
nonoperational/staged records, legacy-only entities, unclassified historical projections,
unrelated alerts and out-of-window records. Operational UUID uniqueness eliminates
duplicate entities. Existing links are read from the existing case event ledger.

Time selection is bounded in SQL. Both `+08:00` and Suricata `+0800` offsets are normalized
for SQLite, then precise aware datetime comparisons enforce the inclusive boundary.
Unknown/unusable primary event time yields no suggestions and an explicit limitation.

Exact sort: number of matched relationship reasons descending, current operational
priority descending (unassigned last), UTC event time descending, UUID ascending.
The window explanation is present once for every candidate and has no effect on their
relative order. Detector confidence is never used. Result size is bounded; V1 has no
pagination, persisted suggestion state, or campaign engine. SQL scans within the bounded
event-time predicate and Python orders eligible results; this is an FYP-scale implementation,
not an indexed large-volume correlation service.

## Human linking and investigation

Open an alert using its title. “Review link to Case” preselects its UUID in the existing
**Linked Alerts** form and prompts for a human reason. It performs no mutation itself.
The existing **Link alert** action submits
`POST /api/v2/tier2/cases/{caseRef}/alerts` with `operationalAlertRef`, nonblank `reason`,
`expectedRevision` and stable retry `requestId`. There is no second linking implementation.
Success updates the Case revision, refreshes linked-event history and assistance, removes
the suggestion, and preserves the existing `V2_TIER2_ALERT_LINKED` audit event.
Existing stale-revision, duplicate and replay protections are unchanged.

Reading assistance leaves an open Case open. **Start investigation** remains an explicit
human action under **Audit Timeline**. Investigation Notes document actual human work.
Finding taxonomy remains `confirmed_malicious`, `suspicious`, `inconclusive`,
`expected_activity`. System category stays read-only; no human category override is added.

Suggested steps use versioned templates for Unknown, brute force, web attack,
reconnaissance/port scan, generic known attacks and informational/policy signals.
Open-case and Critical-route steps are conditional, as are missing trusted context,
missing optional evidence and available related alerts. All text is advisory; no step
claims to have been executed. There is no task-management or acknowledgment workflow.

The preserved response chain is:

`Human Finding → deterministic Response Recommendation → human Approve / Reject → Approved - Not Executed`.

No execution integration, case ownership flow, memory contribution, routing mutation or
automatic Finding is introduced. Detection, Classification, Routing, Verdict → Memory,
Selective Review and Protocol V2 remain unchanged. No collection is opened.

## Verification and reproducibility

Final validation: **381 backend tests passed** (including 24 assistance tests), **240
frontend tests passed** across 33 files, TypeScript passed, OpenAPI and generated schema
freshness passed, and production build passed. The single comprehensive Chromium E2E
passed all five feature scenarios and six width/theme combinations. The directly affected
six frontend tests were also rerun successfully after correcting a test-only TypeScript
option. Existing dependency deprecation messages and Vite's large-bundle advisory remain;
there were no failing checks or browser runtime errors. No production data was used.

Backend tests: `tests/test_investigation_assistance.py`, Tier 2 Cases/direct escalation,
routing/Suricata routing, Analyst Verdict/Verdict Memory, response approval, Protocol V2
freeze, API contract and complete read-only inspection dependency tests. Assistance tests
cover Expert/Critical/manual briefs, snapshot/current separation, Verdict absence/presence,
all six independent relationship rules, Unknown/time-only exclusions, bounds, ordering,
both timezone offset formats, linking/replay/staleness/audit, template determinism and roles.
Populated assistance GETs preserve the complete database dump and database fingerprint,
including schema, content, file bytes and modification time.

Frontend: complete Vitest suite plus TypeScript, generated OpenAPI/schema freshness and
Vite production build. `Tier2CasesPage.test.tsx` checks advisory rendering and that selecting
a suggestion makes no write before the existing reasoned/revisioned link command.

Real Chromium E2E uses `playwright.assistance.config.ts` and the existing disposable
`pre-freeze-fixture.py`, on separate ports 8019/5189. It exercises Unknown automatic Case,
explicit start, note, related link and audit, human Finding, deterministic recommendation
and human approval without execution; then Critical Case provenance and manual escalation
after a Suspicious Tier 1 Verdict. The fixture never opens collection or uses demo.db.
It checks 1440/1024/390 widths in dark/light themes, readable assistance regions and no
page-level horizontal overflow, with screenshots under ignored `apps/web/test-results/`.

Run commands from `hitl-ids` (select the installed Python interpreter as appropriate):

```text
python -m pytest tests/test_investigation_assistance.py tests/test_tier2_cases.py tests/test_tier2_direct_escalation.py tests/test_routing_workflow.py tests/test_suricata_correlation_routing.py tests/test_analyst_verdict.py tests/test_verdict_memory.py tests/test_response_approval.py tests/test_protocol_v2_freeze.py tests/test_inspection_readonly.py tests/test_api_contract.py -q
python scripts/build_openapi.py --check
```

From `apps/web`:

```text
node node_modules/vitest/vitest.mjs run
node node_modules/typescript/bin/tsc -b
node node_modules/openapi-typescript/bin/cli.js ../api/openapi.json -o src/api/schema.d.ts --check
node node_modules/vite/bin/vite.js build
node node_modules/@playwright/test/cli.js test --config playwright.assistance.config.ts
```
