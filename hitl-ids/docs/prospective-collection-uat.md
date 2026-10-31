# Prospective Collection V2 Manual UAT

Status: unexecuted checklist. Not participant results, not a readiness PASS, not production evidence.
Use synthetic fixtures/offline recorded data in a disposable database. No attack generation or real response execution.

## Session record

| Field | Observed value |
| --- | --- |
| UAT session / collection run UUID | |
| Protocol version and hash | |
| Code commit SHA and clean-tree state | |
| Participant pseudonym | |
| Classification: professional analyst OR proxy/student analyst | |
| Relevant professional experience (self-reported, optional) | |
| Facilitator | |
| Data basis: synthetic/demo OR independently validated historical inputs | |
| Role used: Analyst / Admin / Evaluator | |
| Session started (ISO timestamp with timezone) | |
| Session completed (ISO timestamp with timezone) | |
| Total session duration (seconds, stopwatch) | |
| Consent / anonymized results reference | |

Do not combine professional and proxy/student participant results without separate strata.
Do not include passwords, sensitive payloads or participant names in the results artifact.

## Preconditions

- Final readiness review has not yet passed. Do not open a registered research run using this checklist alone.
- For rehearsal, an Admin may create an explicitly synthetic, disposable run with a future start and cutoff.
- For actual collection after final PASS: preregister a new future-dated V2 run; freeze reviewed clean commit,
  policy/configuration hashes, participant classification, targets and outcome cutoff. Preserve V1 unchanged.
- Confirm the database is disposable or explicitly approved for the eventual registered study; preserve its identity.
- All three roles have valid authenticated accounts. Evaluator has read-only access.
- Stage labelled synthetic Suricata evidence; never generate attack traffic. The source occurrence stays unchanged.
- Have at least three separate benign historical reviews for an exact lesson; activate only after human verification.
- Use separate future alert identities for guidance, No Immediate Review, contradiction and override tasks.
- Prepare unknown/conflicting context cases; a deferral is not expected for every alert (including the audit sample).
- Start a stopwatch separately for active analyst investigation time and total task time including navigation/rework.

## Tasks

Record every task separately. The observed-result/time columns are deliberately blank.

| Task / role | Exact UI steps | Expected result | Observed result | Pass/fail | Started | Completed | Duration s | Confusion/error notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Login / all roles | Open Login; enter assigned account; Sign in | Correct role navigation; no role switching via request payload | | | | | | |
| Admission / Analyst | Suricata Admission; select staged fixture; inspect evidence; Eligibility decision = accepted; enter reason; Record eligibility review; enter admission reason; Admit to HITL Workflow | Human-authorized Tier 1 admission; original severity/confidence/occurrence unchanged | | | | | | |
| Triage inspection / Analyst | Open V2 Routing; inspect route, stage, priority, Review Reasons and latest routing decision | Admission's triage policy snapshot visible; unknown context is stated, not false | | | | | | |
| Trusted context / Analyst | Add Trusted Context; deliberately select each assessed field; set observation/expiry; enter structured reason; Record Safety Assessment | Source = analyst_assessment; server availability/recording; untouched fields stay unknown; facts append | | | | | | |
| Unknown/conflict / Analyst | Leave a required field unknown, or add a contradictory independent fact; inspect Safety Evidence | Unknown/conflict explicit; Must Review; no automatic closure or route change | | | | | | |
| Run registration / Admin | Selective Review; Collection Runs; enter protocol, classification, future dates and final PASS reference; Create Draft Run; inspect hashes; Open Run before start | Frozen identity; no opening without future window and approval reference; non-synthetic requires clean committed source | | | | | | |
| Recorded evaluation / Analyst | V2 Routing; Prospective Collection; select open run; enter reason; Evaluate Review Policy during window | Immutable decision, distinct occurrence/admission/eligibility/decision timestamps, policy, context, disposition and pending outcome visible | | | | | | |
| Human outcome / Analyst | Investigate; choose Human memory outcome; enter evidence-based reason; Record Human Memory Review after decision | Later outcome completed; original decision and inputs unchanged | | | | | | |
| Tier 1 escalation / Analyst | Enter routing reason; Escalate to Tier 2; inspect route and audit | Explicit authenticated transition; priority/detector evidence not silently rewritten | | | | | | |
| Tier 2 case / Analyst | Use Tier 2 case link; create/open case; claim or assign as permitted; inspect evidence | Case ownership/state and linked primary alert recorded | | | | | | |
| Finding / Analyst | On case, select supported finding and enter rationale; record finding | Immutable later finding; no retrospective change to selective decision | | | | | | |
| Response approval / Analyst/Admin | Inspect response recommendations; choose supported recommendation; enter approval reason; Approve | Human authorization only; no firewall, host isolation, account disabling or SOAR execution | | | | | | |
| Memory activation / Analyst | Record three separate matching Expected Activity outcomes; open recorded lesson; inspect support/conflict; enter reason; Activate Lesson | Explicit activation; candidate alone cannot defer alerts | | | | | | |
| Future guidance / Analyst | Open a separate matching alert after activation; inspect memory match and reasons | Guidance references historical lesson; no retroactive application to prior decisions | | | | | | |
| No Immediate Review / Analyst | Collect all explicit safe context on an eligible future alert; select run; Evaluate | Deferral only if unchanged V1 gates pass; audit samples/conflicts still require review | | | | | | |
| Human override / Analyst | On deferred alert, enter reason; Require Human Review; record task observation after recall | Must Review; original deferral retained; override/observed recall exported separately | | | | | | |
| Expired/closed-run override / Analyst | Keep an expired or closed synthetic run selected on a deferred alert; enter reason; Require Human Review; reload; inspect Review decision history | Human review required; explicit not-recorded reason; Must Review and audit survive reload; collection ledger unchanged | | | | | | |
| Workload record / Analyst | Prospective Collection; enter stopwatch Analyst review seconds, Total task seconds, errors, rework and notes; Record Task Observation | Append-only human-reported measurement; no invented zero duration or inferred time savings | | | | | | |
| Closure/export / Admin | Wait until outcome cutoff; Refresh Runs; Close Run; Inspect Export; Download JSON | Early closure rejected; export contains actual decisions, timestamps, inputs, outcomes, routing and overrides | | | | | | |
| Registered evaluation / Evaluator | Selective Review; Collection Runs; inspect closed run; Evaluate Recorded Collection | Read-only recorded mode; reconstruction-only and open-run evaluation rejected | | | | | | |
| Archive integrity / Evaluator | In a disposable exported JSON copy remove one decision or matching raw event, then evaluate that copy offline | Explicit archive-integrity failure, not a report with a smaller cohort; original export/database unchanged | | | | | | |
| Permissions / Evaluator | Inspect context/run/decision; attempt same tasks through available controls | No collection, context, routing, case, feedback or approval mutations offered | | | | | | |

## Per-alert workload worksheet

| Run / alert / decision UUID | Baseline immediate-review count | Actual immediate review? | Deferred? | Disposition | Analyst review seconds | Total task seconds | Later outcome | Outcome available at | Unsafe deferral? | Errors | Rework | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | | | | | |

Baseline review volume is one immediate review per eligible alert. Count the first eligible applied decision
per alert, not repeated Evaluate clicks. Later overrides/recalls remain visible separately.
run.decisionCount counts every immutable collection ledger event, including repeats and in-window overrides.
Do not equate it with eligibleAlerts; completeness reconciliation validates all ledger events.
Later malicious/suspicious truth makes an earlier deferral unsafe; it never rewrites that historical deferral.
Only outcomes strictly after decisionAt and before outcomeCutoff enter the closed report.

Review-volume reduction = deferred eligible alerts / eligible alerts. This is NOT time workload reduction.
Record stopwatch durations even when no alert is deferred. Leave unmeasured time blank, not zero.
Measured analyst-time reduction requires a separately designed paired/counterbalanced baseline experiment;
the application intentionally reports it as unavailable. Do not infer it from alert-count reduction.

## Exit checklist

- Record observed results honestly, including failed tasks, timeouts, confusion and facilitator assistance.
- Keep anonymized participant classification, screenshot references and exact frozen export/report hashes.
- Check actual server timestamps, later outcome ordering, context provenance and unchanged detector evidence.
- Verify no source database was changed by export/evaluation and no real response action occurred.
- A synthetic rehearsal PASS is not the independent final readiness review or production effectiveness evidence.
