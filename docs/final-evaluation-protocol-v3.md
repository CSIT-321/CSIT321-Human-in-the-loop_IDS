# Final Evaluation Protocol V3

**Version:** `final-evaluation-protocol-v3.0` · **Status:** FROZEN / UNOPENED.
**Runtime:** `c00c556405198f60adc42f8bb2a7cee03689a60c`, final Legacy cleanup.
**Protocol branch:** `feat/final-evaluation-protocol-v3`.
This is methodology, input generation and preflight, not the final experiment or collection.

## Research question and assessor explanation

“To what extent can accumulated human feedback reduce future immediate analyst review requirements
while maintaining conservative safety controls?” The secondary question asks whether authoritative
contradictory human feedback withdraws guidance before later similar alerts continue to be deferred.

The final evaluation uses a frozen chronological workload with a separate learning phase and unseen
holdout phase. Human outcomes from the learning phase are allowed to build Triage Memory, while
holdout outcomes are kept external until after each review decision is recorded. This prevents label
leakage and allows the same holdout workload to be compared between a clean baseline and the adaptive
HITL system.

Real Suricata integration was validated separately using public PCAPs and an actual Suricata engine.
The controlled V3 workload is used specifically to evaluate repeatable human-learning and
review-reduction behavior, not detector accuracy. See the retained real-PCAP and Golden Path evidence
in `hitl-ids/docs/`. Controlled EVE is deliberately labelled CONTROLLED; it is not represented as fresh
real sensor output. Predetermined external outcomes exercise authenticated human product actions;
three synthetic Analyst identities are provenance, not three recruited research participants.

## Runtime and policy freeze

The exact versions and canonical SHA-256 values are in
[`manifest.json`](../evaluation/protocol-v3/manifest.json), under `runtimePolicies` and `hashes`.
The manifest also hashes source/runner/evaluator versions, requirements, documentation, oracle,
ordered workload, context and schema. Git tree identities pin apps, packages and configuration.
The runner imports a separate **clean exact-runtime checkout**, not the tooling branch's product code.

| Policy | Fixed behavior |
|---|---|
| `triage-memory-v1` | Support 3 distinct alerts, agreement 0.67, conflicts 0, validity 30 days |
| `safe-memory-auto-activation-v1` | Automatic Exact only; expected_activity / false_positive only; no sliding renewal or post-expiry reactivation |
| `selective-review-v1` | Support 3 normally; **false-positive support 5**; deterministic audit sampling 10%; freshness/safety checks unchanged |
| `system-routing-v1` | Current automatic routing rules, no Candidate stage |
| `suricata-classification-v3` | Current deterministic classification, including Unknown / Needs Expert |
| `context-provenance-v1` | Existing provenance/freshness policy |
| `analyst-work-claim-v1` | Real 750 ms arbitration; no shortened window or collision experiment |
| Admission / operational triage / other configs | Included verbatim in the manifest; no evaluation-specific runtime override |

The 3-support false-positive lessons can be Active but still fail the stricter Selective Review gate.
This is pre-registered, not an experimental failure to be repaired by adding labels or lowering a
threshold. Audit-sampled eligible alerts remain recommended_review and count as requiring review.
No attempt is made to choose UUIDs that avoid the audit sampler.

V2 remains historical, frozen and unopened. V3 neither edits V2 nor uses V2's participant/collection
assumptions. It does not use manual Exact contribution, manual activation, historical feedback
scoring, Candidate creation, old Workstation or a parallel Signature/XGBoost operational detector.

## Workload and chronology

Exactly 200 independent operational identities: Learning 1–40, Holdout 41–200. No overlap.
No randomness or post-freeze shuffle. Logical EVE time is 2026-11-03 00:00 UTC plus index minutes.
This is a scenario clock, **not a backdated registration timestamp**. `createdAt` is actual UTC at freeze.
In the isolated subprocess, `models.utc_now` follows the current EVE instant plus elapsed monotonic
processing time. The real work-claim clock and arbitration remain untouched. No behavior or thresholds
are patched. Baseline/adaptive use the same logical event times; all are well within the 30-day window.
Result UUIDs, subsecond timings and JWT timestamps can differ on replay; dispositions, counts, order,
support/conflict, policy reasons and safety outcomes must be semantically reproducible.

| Phase / stratum | Count | Construction |
|---|---:|---|
| Learning stable | 24 | 8 Exact patterns × 3; patterns 1–4 Expected Activity, 5–8 False Positive |
| Learning drift | 6 | Patterns 9–10 × 3 Expected Activity |
| Learning negative | 10 | 5 Confirmed Malicious + 5 Suspicious, separate contexts |
| Holdout stable matching benign | 80 | 8 patterns × 10 new instances |
| Holdout unseen benign | 20 | 10 Expected Activity + 10 False Positive, unmatched contexts |
| Holdout malicious | 20 | Confirmed Malicious, separate contexts and predetermined observable indicator risk |
| Holdout suspicious | 20 | Suspicious, separate contexts and predetermined evidence-conflict risk |
| Holdout Unknown / Tier 2 | 10 | Opaque signatures; 5 malicious / 5 suspicious oracle outcomes |
| Holdout drift | 10 | Pattern 9: 5 malicious; pattern 10: 5 suspicious; contradiction first at indices 191 and 196 |

Primary population: stable 80 + unseen 20 + malicious/suspicious 40 = **140 Tier 1 Holdout alerts**.
Unknown/Tier 2 and drift are reported separately, not hidden in that denominator. If actual routing
does not realize the planned Tier 1 population, the evaluator fails the comparison rather than silently
excluding inconvenient alerts. Baseline review count is observed, never assumed to equal 140.

Exact identity uses the actual config fields: detectorSource, detectionTitle, sourceIp, destinationIp,
protocol. Within a pattern, other supplied match fields (ports/category) also agree. Flow IDs are unique;
actual `parse_record` / `build_bundle` identities are validated, not invented by the evaluator.
Independent patterns have distinct titles AND native categories as well as addresses: the product
also retrieves related lessons by title/category, whose unsafe evidence can conservatively veto reuse.
This separation avoids an accidental cross-pattern veto without changing the real matching rules.

Context values are generated and frozen before any experimental decisions. Stable/unseen/drift
contexts are low-risk and complete; malicious/suspicious controls have scenario-defined observable
risk facts. Drift deliberately has no observable new risk flag before the authoritative human audit:
the first contradiction can be deferred and must be reported honestly. The existing synthetic-fact
producer supplies nine scoped facts before evaluation, with four-hour validity. Source is explicitly
synthetic_fixture. No normal context value changes after oracle reveal. No oracle label enters context.

## Oracle isolation and decision capture

Operational JSONL is pure EVE, not an object carrying phase/stratum/label. Structure and outcome files
are evaluator-only. The preflight validates field whitelists, rejects outcome/groundTruth metadata,
and checks that runtime modules have no oracle/tooling dependency. An independent runtime subprocess
has a file-open guard denying oracle paths, including a tested deliberate access attempt.

For each alert: admit → seed frozen context → invoke authenticated Selective Review evaluate → read
current routing/review projection → return decision snapshot → append canonical JSONL and **fsync** →
verify snapshot hash on disk → only then open/join that alert's oracle outcome. The runtime process
does not receive the oracle file, phase, stratum, expected route or future labels. For the permitted
learning/audit actions only, it subsequently receives the single human outcome to submit through
the ordinary canonical Verdict API. Such already-authoritative human history is permitted learning,
not leaked future truth. Pre-outcome decision records never contain an external oracle outcome.

This enforces information flow for these tools; it is not an OS sandbox against a malicious machine
administrator. Inputs, script hashes, decision hashes and append-only journals provide auditable
replay checks. A changed script/input/config invalidates preflight. JSON is canonically hashed with
sorted keys/compact UTF-8; JSONL hashes the ordered parsed array; source/doc hashes normalize LF.

## Baseline and Adaptive procedures

Both arms create new isolated databases and the same three demo accounts; no existing demo DB is
reused. Baseline skips Learning completely, then processes all 160 Holdout alerts with identical
order, source evidence and context. It makes no claims/Verdicts and builds no learning Memory.
Product learning code is present and unmodified, not disabled.

Adaptive processes the 40 Learning alerts using deterministic round-robin Analyst identities.
Each event receives a pre-outcome decision snapshot before label reveal. The assigned Analyst claims
the work via the real authenticated claim API, then records the canonical Verdict. Automatic Exact
evidence and auto activation happen naturally in the product transaction. No runner writes support,
activation, review disposition, work ownership or routing tables. Only schema/accounts and existing
synthetic context prerequisites use direct setup helpers. Real import/admission paths are used.

Learning-end snapshot contains all lessons, outcome/scope/support/conflicts/status, activation source,
validFrom/expiresAt, effective votes and evidence author distribution. Ten benign Active lessons are
the planned expectation, not a forced result. Negative lessons cannot auto-activate as benign guidance.
Lesson count alone is not effectiveness. Activation rate = auto-activated / all created learning-end
lessons, explicitly including negative lessons in the denominator.

Normal Holdout events receive **no Verdict or learning injection**, regardless of oracle outcome.
Only the first contradiction per drift pattern receives feedback: capture/freeze its initial decision,
reveal external outcome, explicitly audit it, issue Require Human Review if ownership is blocked by
deferral, claim, then record the canonical contradictory Verdict. Capture immediate Memory withdrawal
and the remaining four alert decisions. There are exactly two planned Holdout feedback injections.
The baseline receives neither. Initial deferral is never retroactively overwritten by recall.
Actual authenticated overrides are recorded separately from policy-generated Must Review.

## Metrics and denominators

For primary paired records let B = baseline immediate review count, A = Adaptive immediate review count.
Immediate review means disposition other than no_immediate_review, including audit recommended_review.

| Metric | Definition |
|---|---|
| Reduction count | B − A (negative values retained) |
| Reduction rate | (B − A) / B; B=0 → N/A |
| Deferral | Baseline reviewRequired AND Adaptive no_immediate_review; baseline-already-deferred alerts excluded |
| Safe deferral | Deferral with external Expected Activity or False Positive |
| Unsafe deferral | Deferral with external Suspicious or Confirmed Malicious |
| Unsafe deferral rate | Unsafe / total deferrals; zero deferrals → N/A, **not unsafe/all alerts** |
| Benign deferral coverage | Safe / baseline-review-required primary benign alerts; zero → N/A |
| Outcome completeness | Valid oracle outcomes / assessed population: primary 140, supplementary all Holdout 160; target 100% |
| Human overrides | Distinct evaluated alerts with a real explicit authenticated Require Human Review action; count/rate by population; drift audit overrides separate |
| Audit samples | DETERMINISTIC_AUDIT_SAMPLE reason; remain review-required |
| Memory | Created, auto-activated, activation rate, support distribution, conflicts, expired lessons, activation source, effective vote violations |
| Drift withdrawal | Active lessons entering test, first disposition/deferral, actual conflict withdrawal count and later matching dispositions |
| Post-contradiction unsafe deferrals | Later matching drift alerts with Adaptive no_immediate_review after authoritative feedback, regardless of baseline; target 0 |
| Tier 2 safety | Unknown controls missing formal Case, wrong route or No Immediate Review in either arm; count each violating alert once; target 0 |
| Runtime R02 | Record actual unsafeSuppressionCount in each arm as supplementary observed-runtime metric, never substitute for oracle-based rate |

Missing outcomes are listed explicitly and deferred records with missing truth remain unassessed.
They are not counted safe; completeness failure invalidates methodology. No positive reduction
percentage is required. Methodological success requires a valid paired comparison, no leakage,
complete outcomes, correct denominators and reproducible semantic behavior. Critical safety targets
are zero vote violations, zero Tier 2 violations, zero post-contradiction unsafe deferrals and zero
oracle leakage. Any violation is a failure to report, not a reason to tune the frozen workload.

## Output contract and report tables

Each arm emits `decisions.jsonl`, `outcomes.jsonl`, `learning-end.json`, `feedback.json` where applicable,
`final-memory.json`, `runtime-metrics.json`, the disposable `run.db`, and a hash-bound completion receipt.
The evaluator accepts only paired completed arms and verifies record identities, source hashes,
chronology, unchanged route/classification/priority, decision hashes and permitted Holdout feedback.
The [paired result schema](../evaluation/protocol-v3/result-record.schema.json) specifies each alert's
index/stratum, baseline/adaptive dispositions and review flags, decision timestamps/hashes, Memory
matches/status, reason codes, route/classification/priority, Case reference, human override and
post-decision oracle outcome with safe/unsafe/not-deferred/unassessed classification.

| Export | Columns / use |
|---|---|
| `records.json/csv` | All paired Holdout records, no manual join/arithmetic required |
| `primary-table.json/csv` | Metric, Baseline, Adaptive, Difference/Rate; immediate/NIR counts, reduction count/rate, total/safe/unsafe deferrals, unsafe rate, coverage, overrides, audit samples, completeness |
| `stratum-table.json/csv` | Stable, unseen, malicious, suspicious, Unknown/Tier2, drift: count, baseline/adaptive review, NIR, safe/unsafe deferrals and denominators |
| `memory-table.json/csv` | Lesson ref, outcome, scope, support, conflicts, status, activation source, validFrom, expiresAt, pattern, Holdout exact matches |
| `drift-timeline.json/csv` | Pattern/index, disposition/outcome, feedback injected, before/after support/conflicts/status, guidanceActive, next-alert behavior |
| `learning-timeline.json/csv` | Actual stepwise human actions and Memory snapshots for support 1→2→3→Active illustration |
| `metrics.json`, `report.md` | Primary, per-stratum and supplemental safety/Memory/R02 results and formatted assessor tables |

These exports feed the five later charts: B vs A immediate review; safe vs unsafe deferrals;
disposition by stratum; support-to-activation; drift withdrawal. No polished final chart or final
200-alert result is created on this design branch.

## Preflight and boundaries

Read-only preflight proves counts/strata/coverage/chronology, unique actual adapter IDs, disjoint phases,
configured Exact groups, isolation of unrelated patterns, frozen policies/runtime and all hashes.
Generator regeneration must reproduce all workload bytes semantically/canonically. Mutation tests
reject oracle fields, missing labels, duplicate identity, bad order and wrong phase. Runner guards
reject the final bundle as a development fixture and require a separate explicit opening receipt.

An **independent eight-alert development fixture**, different capture scope/UUIDs, tests real admission,
three real Analyst claims/Verdicts, automatic Exact/activation, decision-before-reveal journal, explicit
drift recall, conflict withdrawal, future review and automatic Unknown Case. It runs no final alert.
Vote-regression preflight also uses existing isolated tests for retries/revisions/Exact+Narrow and
Tier 2 authority. No policy is patched to make this pass. See the separate preflight record for results.

All product source, detector/correlation/classification, priority/routing, claim, Verdict, Case workflow,
Memory/activation/review policies, response/resolution, migrations and original evidence are unchanged.
No firewall/account/host/SOAR execution. No prospective runtime collection row is created. V2 untouched.
Historical protocol claims are not inherited. No merge or PR.

## Limitations registered before results

Controlled scenarios are not production SOC traffic or a random population sample. Exact patterns
are intentionally repeated. 200 alerts is an FYP-scale controlled workload. There is no human time,
productivity, cognitive-load, usability or staffing study. No detector accuracy, precision/recall/F1,
p-values or statistical significance is claimed. External truth is evaluation metadata, not runtime
evidence. No sliding renewal, post-expiry automatic reactivation or response execution. A previously
safe pattern's first contradiction can be deferred before the system receives authoritative evidence;
the safety question is whether that evidence withdraws guidance for subsequent matching events.

## NEXT — only after explicit authorization to open the final experiment

Do not execute these opening/running commands during protocol design. Use a clean exact-base checkout
separate from this tooling checkout, an available Python 3.11 environment with pinned requirements,
and a **new** output directory. Below commands run from this branch's `hitl-ids` directory; replace
paths with absolute local equivalents. Git worktree creation is a checkout, not a merge.

```text
git worktree add --detach ../../v3-runtime c00c556405198f60adc42f8bb2a7cee03689a60c
python scripts/validate_protocol_v3.py
python scripts/open_protocol_v3.py --runtime-root ../../v3-runtime --out .pytest-tmp/final-v3-run-001 --ack OPEN-FINAL-V3
python scripts/run_protocol_v3_baseline.py --runtime-root ../../v3-runtime --opening .pytest-tmp/final-v3-run-001/opening.json --out .pytest-tmp/final-v3-run-001/baseline
python scripts/run_protocol_v3_adaptive.py --runtime-root ../../v3-runtime --opening .pytest-tmp/final-v3-run-001/opening.json --out .pytest-tmp/final-v3-run-001/adaptive
python scripts/evaluate_protocol_v3.py --baseline .pytest-tmp/final-v3-run-001/baseline --adaptive .pytest-tmp/final-v3-run-001/adaptive --out .pytest-tmp/final-v3-run-001/report
```

The future opening receipt records actual UTC and the frozen manifest hash outside this bundle.
The immutable protocol manifest retains its freeze-time status; lifecycle lives in the separate receipt
and arm completion receipts. Failed/partial runs are retained, not overwritten. Diagnose methodology
failures and report them; do not tune policy/workload after seeing effectiveness. Any necessary amendment
requires a separately versioned protocol and a documented reason before a new final run.
