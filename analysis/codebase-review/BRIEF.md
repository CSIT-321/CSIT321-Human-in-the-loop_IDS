# Final-product codebase review — shared brief (read fully before starting)

SCOPE RULE FIRST: read and edit ONLY files inside this repository
(`C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS`). Never read any
path outside it. You may WRITE exactly one file: your slice's output file named below. Do not edit,
create, move or delete anything else. Do not run `pytest`, `npm`, `git commit`, `git checkout`,
servers or installs. Read-only shell commands (`git log`, `git grep`, `git show`, `rg`, `wc`) are
allowed.

## What the product is

`hitl-ids/` is a Human-in-the-Loop Intrusion Detection console (FYP-26-S3-13), at its final-product
stage. Detection: signature rules + an 8-class XGBoost model, fused by "Complementary Evidence Fusion"
(`packages/detection/fusion/cef.py`) into ranked alerts in SQLite (`alerts` table). Analysts record
verdicts; guardrails bound how far a verdict moves a score; similar-alert families learn from agreeing
verdicts. FastAPI backend (`apps/api`), React + Vite console (`apps/web`), three roles: Security Analyst,
System Administrator, Evaluator.

Two generations coexist in the code — this is the central design problem you must judge:

- **Legacy / flow generation (approved by the supervisor at the demo):** `alerts` table, `/api/alerts*`
  endpoints, the five-category feedback + guardrails (`packages/detection/feedback`, `guardrail`), family
  learning, queue order `db.queue_order`.
- **Operational V2 generation (added later by a teammate, now inherited):** `operational_alerts_v2` +
  `operational_triage_state_v2`, Suricata intake (`packages/detection/adapters`, `external_admission.py`),
  system routing (`system_routing.py`), Tier 2 cases, triage memory, selective review, claim
  arbitration, workspaces, presentation replay, frozen evaluation protocols V3/V3.1. Migrations 2–21 in
  `packages/contracts/db.py`. The V2 web console replaced the legacy analyst pages.

## Facts already measured (do not re-derive; build on them and challenge them)

1. On the approved `data/demo.db` (5,000 flow alerts, 996 flagged), the V2 workstation showed **0
   alerts**: it reads only `operational_alerts_v2`. A new script `scripts/materialize_flow_queue.py`
   now projects the 996 flagged alerts — but they stay `unassigned/staged`, unrouted.
2. `system_routing.admit_system_route` (`packages/detection/system_routing.py:78-150`) routes **only
   Suricata** alerts (it raises without a Suricata bundle, lines 84-86). Flow alerts are never routed,
   cannot be claimed (`analyst_work.py:83-86`) and cannot receive a verdict (`analyst_verdict.py:64-67`).
3. `triage_policy.evaluate_triage` computes `tier2_recommended` + reasons, but `system_routing.py:101`
   hard-codes `tier2_recommended=False`. Measured: 0 of 168 replay alerts recommended.
4. 4 of the 5 system-routing rules need trusted context facts that only an analyst or a synthetic
   fixture writes. In the V3.1 replay only 1 of 165 alerts was auto-escalated.
5. On a flow alert the V2 console drops 13 of 24 analyst-visible items of the approved page: `AL-xxxxx`
   short name, operational score, duration/bytes, 88 flow features, rule condition table, combined
   explanation, rule-and-model agreement, queue band, fusion scheme, family, score-adjustment chain,
   the 5-category verdict form, investigation notes. One value is wrong: confidence on AL-01958 shows
   "Not provided" where the approved page shows 100.0%.
6. The full Python suite at the tip: 1613 passed, 5 skipped, 5 failed. `test_plan_sync` fails (handover
   count). The 4 `test_protocol_v3*.py` tests compare the live git tree SHA of `hitl-ids/apps`,
   `packages`, `config` with the frozen run, so ANY later commit fails them.
7. Safety of automatic escalation rules vs ground truth: E1 (rule AND model agree, score >= 80):
   200 escalated / 0 false positives on demo, 148 / 0 on a degraded-model stress DB. E3 (score >= 90 and
   High): 648 / 342 false positives on the stress DB. Only E1 is safe to automate.

## Settled decisions — do NOT recommend reversing these

8 model classes; `signature_only = 0`; 2 enabled rules (FTP, SSH); weighted-sum fusion rejected (CEF
instead); 0.9882 macro F1 is a testbed artefact; ranking formula C1, movement M1, agreement gate 3
verdicts / 0.67; ground truth is NOT in the schema; queue order severity-first via `db.queue_order`;
PRD/URS/TDM documents are reference-only; SQLite, not PostgreSQL; offline demo with committed demo
passwords is intentional.

## The goal of the final product (what your review serves)

- **Tier 1 analyst view:** all incoming alerts plus Tier 2 candidates, each with the reason it should
  be escalated; the analyst can escalate, keep in Tier 1, or record a verdict.
- **Tier 2 analyst view:** only Tier 2 work, showing who escalated it (rule or analyst) and why.
- **Automatic escalation**, foolproof: E1 auto-escalates; uncertain candidates wait for Tier 1 review;
  any error or missing data falls back to human review; idempotent and audited.
- **Restore the lost analyst information** (fact 5) for flow alerts.
- **A documentable design:** clear module boundaries, one name per concept, no dead generations,
  so the design documents (architecture, data dictionary, API, UI) can be rewritten after the fix.

## What to look for, in priority order

1. **BUG** — wrong result, crash, data corruption, race, transaction misuse. Prove it.
2. **SECURITY** — auth/RBAC bypass, injection (note: f-string SQL with a column name from a fixed
   tuple is not injection; trace the value), secrets, unsafe path handling, info leakage.
3. **DESIGN** — duplicated concepts across the two generations, two sources of truth for one policy,
   a module doing two jobs, naming that will be impossible to document, coupling that blocks the
   final-product goal above.
4. **GOAL-BLOCKER** — anything that prevents or complicates the Tier 1 / Tier 2 / auto-escalation /
   info-restore goal. Say exactly what would have to change.
5. **DEAD-CODE** — code, routes, configs, tables, scripts no current path uses. Prove "unused" with a
   `git grep` of the symbol (name the command and count).
6. **DOC-DRIFT** — docstring or comment that states something the code does not do.
7. **TEST-GAP** — risky behaviour in your slice with no test (name the behaviour, check `tests/`).

## Evidence rules — a finding without these is dropped

- Cite `path:line` for every finding. Open the file and confirm the line before you write it.
  Never invent a line number. Use repository-relative paths starting with `hitl-ids/`.
- State the concrete trigger and the bad outcome. "Could be a problem" is not a finding.
- Report only findings you are more than 80% sure of. Zero findings in a category is a valid answer.
- HIGH or CRITICAL needs: the snippet, the trigger/state/outcome, and why existing guards miss it.
- Do not manufacture style nits. No "consider adding docs" findings.

## Output — write the file FIRST, then reply

Write your output file IMMEDIATELY when you have findings, and update it as you go — do not hold the
report until the end. Format exactly:

```
# Slice <N> — <name>
Files read: <n> of <m> listed  (list any listed file you could not read)

## Findings
| ID | Sev | Category | Location | Finding (trigger -> outcome) | Proposed action | Phase |
|---|---|---|---|---|---|---|
| S<N>-01 | HIGH | BUG | hitl-ids/x.py:12 | ... | FIX: ... | B |

## Module map (for the design documents)
One line per file: path — its single responsibility — the generation it belongs to (legacy / V2 / shared).

## Challenges to the team's assumptions
Bullet list: anything in the "facts" or "goal" sections above that the code contradicts, with evidence.
```

Sev is one of CRITICAL, HIGH, MEDIUM, LOW. Proposed action starts with FIX, CHANGE, ADD, REMOVE or
KEEP. Phase is one of: A (data into the queue), B (routing + auto-escalation), C (Tier 1 view),
D (Tier 2 view), E (tests + documents), X (outside these phases).

End your final chat message with exactly one line: `WROTE <output path> FINDINGS <count>`.
