# HANDOVER — read this first in a new session

**Purpose.** Carry the full state of this project into a fresh session with zero loss of context
and minimal token cost. Everything a new session needs is here or one link away.

**Last updated:** 2026-09-12 (rev 10) · **Branch:** `feat/s7-feedback` (local) ·
`feat/s2-contracts` and `feat/s6-fusion` **pushed to origin** as view-only progress branches ·
**Phase 2 DONE (S2, S5 + S4b, S6, S7a, S7b, S8) · Phase 3: S9 DONE · Phase 5: S15 DONE** —
changelog v1.18 · **342 tests, 0 skipped** · `python scripts/run_detection.py` builds the demo
database · `python scripts/run_evaluation.py` runs the three-arm evaluation
**Iteration 1 (Evidence & Direction) complete** · the ranking formula and the agreement gate were
chosen by experiment (Q29, Q30) · collaborator's `origin/main` merged ·
**NFR-01 explainability satisfied** · **NFR-05 proven at evaluation level**

---

## 0. Paste this to start the next session

> Read `hitl-ids/docs/HANDOVER.md` **and the *Step status* table in
> `plans/hitl-ids-demo-build.md`**, then confirm you have the state loaded by telling me (a) the
> current phase and the next step **as the plan's status table names it**, (b) the two findings that
> were reversed and why, and (c) what I have told you never to delegate. Do not re-derive any
> settled decision. Then begin that step, reading **its section in the plan** before you write
> anything.

The confirmation is not ceremony — if a new session cannot answer those three, it has not loaded
the state and will re-litigate settled ground.

> **Read the plan's step section before implementing, not just this file.** This handover is an
> *entry point*; `plans/hitl-ids-demo-build.md` is **canonical** for what a step contains, and it
> carries the context brief a delegated worker is given. Working from §7 alone is how the plan went
> eleven changelog versions without an update, while still instructing a reader to retire the
> project's most productive signature rule. `tests/test_plan_sync.py` now fails if the two
> documents disagree about what is done — but a test cannot tell you to *read* the step, so read it.

**The next step is S10b** — the plan's *Step status* table is the authority, and it marks S10b
`NEXT`. S10a's contract and `apps/api/openapi.json` are the target to implement against. Read
[`the plan's S10a/S10b section`](../../plans/hitl-ids-demo-build.md) before writing anything — it
says what a delegated worker gets and what is withheld. Then confirm the ground you are standing
on:

```
python -m pytest                      # expect 342 passed, 0 skipped
python scripts/run_detection.py       # rebuilds data/demo.db: 5,000 flows -> 5,000 alerts, ~21 s
python scripts/run_evaluation.py      # the three arms over that database, ~3 s
python scripts/build_openapi.py --check   # the committed API contract is in step with the models
```

Use `C:/ProgramData/miniconda3/python.exe` for all three — see §6 on the two interpreters. The
databases are gitignored, so a fresh checkout has to rebuild them; everything else is committed.

**Read [`evaluation-report.md`](evaluation-report.md) before quoting any number about feedback.**
S15 did not find the result the project wanted, and the honest version is the one to present:
similar-alert learning works and does not leak, but on this sample it *lowered* precision, because
the control queue was already perfect and the mechanism promoted a false positive to rank 1.

---

## 1. What this project is

**FYP-26-S3-13**, CSIT321 final-year project: a **Human-in-the-Loop Intrusion Detection Dashboard**.
Network-based IDS over recorded flow data, combining signature rules and an ML classifier, where an
analyst reviews alerts and their feedback adjusts scoring within safety guardrails.

Repo: `github.com/CSIT-321/CSIT321-Human-in-the-loop_IDS` · working tree `hitl-ids/`

---

## 2. User's standing instructions — do not re-ask

| Instruction | Detail |
|---|---|
| **No deadlines** | The PRD's 14-week schedule is discarded. Sequence by dependency only. Never produce a Gantt or date estimate. |
| **Documents are reference-only** | PRD, URS, TDM (in the parent `FYP/` folder) are **not to be amended**. Log divergences in `docs/plan-changelog.md` instead. |
| **Team is out of scope** | The 6 members / 3 pairs are irrelevant here. This workplan is **the user + Claude + delegated workers** only. |
| **Delegate for token efficiency** | Use the `delegate-providers` skill for bulk work. See §6 for what may and may not be delegated. |
| **Old repo structure is ignored** | `stage-1/`…`stage-5/`, `dashboard/`, `prototype-demo/`, `docs/` are **frozen research record**. Never modify them. New work lives in `hitl-ids/`. |
| **Demo first** | Full backend, PostgreSQL, real auth and the flow exporter are all deferred until the demo gate (S16) passes. |

---

## 3. Current state

**Iteration 1 (Evidence & Direction) is COMPLETE and committed.** 35 files, 209,205 insertions.

> **Phase numbering — no ambiguity permitted.** `plans/hitl-ids-demo-build.md` is canonical:
> Phase 0 Foundation (S1–S2) · Phase 1 Data & model (S3–S4) · Phase 2 Detection core
> (S5, S4b, S6, S7, S8) · Phase 3 Persistence + API (S9–S10) · Phase 4 Interface (S11–S14) ·
> Phase 5 Evaluation + demo gate (S15–S16) · Phase 6 Post-demo (S17–S18).
>
> The completed evidence work is **Iteration 1** — a *work iteration* spanning plan Phase 1 plus
> S4b. It is **not** "Phase 1". Never use a bare phase number for it.
>
> **Actual status:** Phase 0 **PARTIAL** (S1 scaffold incomplete — Python slice only; **S2 DONE**) ·
> Phase 1 **DONE** · Phase 2 **DONE** (S5, S4b, S6, S7a, S7b, S8) · Phase 3 **S9 DONE**, S10a/S10b
> remain · Phase 5 **S15 DONE**, S16 (the demo gate) remains · **next: S10a** ·
> Phases 4, 6 not started.

```
hitl-ids/
  data/raw/       CSECICIDS2018_improved.zip   10.4 GB, GITIGNORED, must be re-downloaded
  data/processed/ label_scan · demo_sample(5,000) · train_sample(250,655) · manifests
  data/demo.db    the populated demo database, 42 MB, GITIGNORED - rebuild:
                  python scripts/run_detection.py   (5,000 flows -> 5,000 alerts, ~21 s)
  models/         8-class XGBoost + metrics + port ablation
  notebooks/      01-06, all execute with ZERO errors (05 = ranking runs 1-2, 06 = run 3, the gate)
  config/severity-chart.json           Q28: editable, versioned severity chart
  packages/detection/ranking/          severity chart loader · formulas C0-C3, M1/M2 · experiment
  packages/detection/feedback/         S7a service.py (one verdict) · S7b learning.py (its family)
  packages/detection/guardrail/        policy.py - the caps, the floors and I3
  packages/detection/pipeline/         S9: source.py (the S3 seam) · predictor.py (TreeSHAP in the
                                       run) · store.py (repositories) · runner.py (run_detection)
  packages/detection/ml/inference.py   vendored+adapted TreeSHAP inference (see sec. 8)
  packages/evaluation/                 S15: truth.py (the one ground-truth join) · scenario.py (the
                                       pre-registered sequence) · metrics.py · harness.py (3 arms)
  apps/api/contract/                   S10a: common · alerts · operations · openapi. NO FastAPI
                                       import - pure Pydantic, so S11 can start before S10b
  apps/api/openapi.json                S10a published: 13 operations, 37 schemas. COMMITTED;
                                       rebuild/verify: python scripts/build_openapi.py [--check]
  evaluation/ranking/                  history.jsonl + runs/<id>/{config,results}.json, METHOD.md
  evaluation/three-arm/                S15's record, same layout + METHOD.md
  packages/contracts/  S2: models.py · schema.sql (12 TDM tables + alert_families) · db.py (codec,
                       QUEUE_ORDER_BY - queue_priority since S7b)
  tests/   342 tests in 13 files, 0 skipped - run: python -m pytest  (pyproject sets pythonpath)
           test_plan_sync.py fails if the plan, this file and the changelog disagree
  tests/fixtures/legacy/   8 FROZEN files - never regenerate
  scripts/        15 scripts, all runnable; run_detection.py builds the demo database (S9),
                  run_evaluation.py runs the three arms (S15), build_openapi.py publishes
                  the API contract (S10a)
  rules/rule-set-s4b-1.json            7 rules, 2 enabled (FTP + SSH brute force)
  docs/           HANDOVER · system-workflow (start here) · plan-changelog (v0.1-v1.16) ·
                  ranking-and-escalation-design · evaluation-report (S15, read before quoting
                  any feedback number) · deviations (the register the plan mandates) ·
                  iteration-report · iteration-2-report ·
                  feasibility-study · rule-retuning-report · finding-infiltration-mislabelling
                  · img/ (15 rendered PNGs, regenerate: scripts/make_diagrams.py)
plans/hitl-ids-demo-build.md    18-step build plan (S1-S18), v1.1 - CANONICAL for the next step;
                                its *Step status* table is the authority, not this file's §7
```

**Also merged:** the collaborator's `stage-3/` and `stage-5/` work (their model is INVALIDATED -
see sec. 9). Their `dashboard/` still runs but displays old 6-class data.

**Start here:** [`system-workflow.md`](system-workflow.md) — the whole system end to end, each
part marked built / next / planned.
[`iteration-2-report.md`](iteration-2-report.md) — what Iteration 2 built, with the
fusion diagrams and calculations. [`iteration-report.md`](iteration-report.md) — Iteration 1's
evidence and direction change. Diagrams regenerate with `scripts/make_diagrams.py`.
[`plan-changelog.md`](plan-changelog.md) has every decision and its evidence.

---

## 4. Settled facts — never re-derive these

Everything below is measured, verified, and reproducible from the notebooks.

### Dataset (corrected CSE-CIC-IDS2018, Engelen et al. IEEE CNS 2022)
- **63,195,145 flows**, 10 capture days, 93.9% benign
- **Infiltration was never one class** — 99.6% is `NMAP Portscan`; true infiltration = **317 flows**
- **FTP brute force is 100% `Attempted`** — never succeeded
- **Web Attack = 283 successful flows** in 63.2M; the old sample held 29% of the entire class
- Schema is **91 columns**, not 79; `CWE Flag Count` → `CWR Flag Count` fixed a typo

### Decisions (all confirmed by the user)
| ID | Decision |
|---|---|
| Q18 | Attempted attacks are **malicious**, flagged via `is_attempted` |
| Q19 | **Port Scan** is an 8th class, split out of Infiltration |
| Q20 | Disjoint **train (250,655)** + **demo (5,000)** samples, seed `20260911` |
| Q21 | Signature layer = **trust/explainability**, not coverage |
| Q22 | Queue order = `corroborated` → `signature_override` → `ml_only` → `none`, then score (2026-09-11) |
| Q23 | S6 combination **accepted for the demo** at current defaults; tuning deferred to realistic traffic (2026-09-11) |
| Q24 | Feedback moves an alert into a **higher queue class**; review flag is an extra feature (2026-09-11) |
| Q25 | Automatic tier escalation **post-demo**; the demo shows which alerts **would** go to Tier 2 (2026-09-11) |
| Q26 | The ranking formula is **chosen by testing** game-inspired candidates (2026-09-11) |
| Q27 | False positives **drop a class**, scaled by an **attack-type severity chart** (2026-09-11) |
| Q28 | The severity chart is **configuration**: `config/severity-chart.json`, versioned (`sev-1`) and validated on load; change values there, never in code (2026-09-11) |
| Q29 | Ranking **formula C1** (severity-weighted), chosen in run 3 by the pre-registered rule sel-3. **Movement M1** stands pending the project lead: sel-3's M2 pick rests on internal class changes. History: `evaluation/ranking/`; read notebooks 05 (runs 1–2) and 06 (run 3) (2026-09-11) |
| Q30 | The collaborator's **agreement gate** is adopted for similar-alert learning: ≥ 3 learning verdicts, no tie, ≥ 0.67 agreement, and only learning in the dominant direction applies (2026-09-11) |

**The project goal (confirmed 2026-09-11):** analyst feedback on past alerts **reorders future
alerts** to raise triage efficiency, inside the guardrails. S7b (similar-alert learning) is its core.
Design: [`ranking-and-escalation-design.md`](ranking-and-escalation-design.md).

### Model
- 8 classes, macro F1 **0.9882**, weighted F1 0.9997, 82 features
- **The 0.99 F1 is a testbed artefact.** Port-shortcut hypothesis tested by ablation and
  **rejected** (−0.0011). Cause is single-tool attack generation giving each class a constant flow
  fingerprint. **Never present as a real-world capability claim.**

### Explainability (NFR-01) - SATISFIED
`scripts/run_ml_inference.py` produces a native TreeSHAP explanation for **5,000/5,000** demo
alerts, **5,000/5,000 additivity checks passed** (max deviation 1.13e-5, tolerance 1e-4).
Output: `data/processed/demo_ml_predictions_shap.json` (gitignored, 16 MB, regenerable).

### Rule thresholds - VALIDATED on held-out data
Re-tested on `train_sample.csv` (250,655 rows the rules never saw, 50x the tuning set), now
reproducible via `scripts/validate_rule_set.py` through the production engine. 30,025 hits. Not overfit.
- **Any-attack scoring** (a hit is right if the flow is an attack): precision **0.9999**, recall
  **0.1993**, 2 false positives — the figures originally reported.
- **Class-correct scoring** (the flow's class is the rule's class): precision **0.9992**, recall
  **0.1991** — 23 NMAP probes of TCP/21 are labelled FTP brute force. Always say which scoring.

Rule set: `rules/rule-set-s4b-1.json`. FTP = TCP + port 21 + `totalFwdPackets ≥ 1` + its other
original clauses; SSH = `flowPacketsPerSecond ≥ 10.66689` + its other clauses. Five rules retired.
Rules use the camelCase **observable view** (`packages/detection/signature/observable.py`).

### Detector relationship (the crux)
```
1,000 malicious flows:  ml_only 794 · both 200 · signature_only 0 · missed_by_both 6
```
Retuned signature rules: **precision 1.000, recall 20%**, but **zero unique coverage**.

### Data contracts (S2) - `packages/contracts/`
- `schema.sql` is canonical. **After S9 consumes it, changes need a migration, not an edit.**
- Every TDM departure is marked `DEVIATION` inline and logged in changelog **v1.5**; a test fails
  on any unlogged column.
- `combined_score` = operational score feedback moves; `detection_score` = immutable original.
- Ground truth is **not** in the schema; evaluation joins on `flow_data.source_record_id`.
- `audit_log` and `feedback_events` are append-only, including against `INSERT OR REPLACE`.
- Timestamps are fixed-width UTC text `YYYY-MM-DDTHH:MM:SS.ffffffZ` so text order is time order.
  Encode query bounds with `db.format_timestamp`; timezone-less datetimes are refused.

---

## 5. Reversed and rejected — do not resurrect

These were believed, then disproved. Re-proposing them wastes a cycle.

| Claim | Status | Why |
|---|---|---|
| "Signature + ML **agreement** is the strongest evidence" (PRD) | Partially restored | Was withdrawn on old data; agreement does occur (200×) on corrected data |
| "Detectors are **complementary**" (notebook 02/03) | **WITHDRAWN** | `signature_only = 0` on corrected data |
| "Zero co-occurrence" (notebook 01 F5) | **WITHDRAWN** | Occurs 200 times |
| **Weighted-sum fusion** (TDM §6.2.7) | **REJECTED** | Scores from different evidence classes are not commensurable |
| **Retune the fusion weights** to fix coverage | **REJECTED** | Mathematically inert while co-occurrence is low; hides the problem |
| **Retune rules** to restore complementarity | **TESTED, CLOSED** | Precision reached 1.000 but `signature_only` stayed 0 |
| **Suricata** as the prefix module | **REJECTED** | Cannot emit CIC flow features; use the GintsEngelen CICFlowMeter fork instead |
| **Curated demo slice** where both detectors fire | **REJECTED** | Would conceal real recall; fails viva scrutiny |
| Demo on **static JSON** with no persistence | **REJECTED** | Feedback that dies on refresh cannot demonstrate the thesis |

---

## 6. Working rules learned the hard way

**Delegation (`delegate-providers` skill)**
- ✅ Delegate: bulk analysis scripts, CRUD endpoints, React components from a contract, test
  fixtures, boilerplate, document extraction.
- ❌ **Never delegate:** fusion maths, feedback/guardrail logic, data contracts, or the
  `POST /alerts/{id}/feedback` endpoint (it invokes guardrails).
- ❌ **Never delegate research.** GLM's provider rejects WebSearch and it **silently fabricates** —
  it produced 23 KB citing 29 URLs it never fetched. DeepSeek fails loudly instead. Both are fine
  for read/write/transform work.
- **Read the files a worker wrote.** Never trust its returned `result`; one agent returned only
  "Standing by." while its 28 findings sat in a 1.47 MB transcript.

**Documents**
- **The plan is canonical for what to build; this file is only the entry point.** They drifted for
  eleven changelog versions because every session read §7 here and never opened
  `plans/hitl-ids-demo-build.md`. The plan meanwhile instructed a reader to retire
  `SIG-FTP-BRUTE-FORCE` — one of the two rules that survive — and to rehearse a demo whose own
  stop-condition had fired. **Update the plan's *Step status* table in the same commit that finishes
  a step**; `tests/test_plan_sync.py` fails when the documents disagree.
- **Four files, four jobs.** Plan = what to build next. `plan-changelog.md` = why we changed our
  minds, with evidence. `deviations.md` = the flat register of what differs from the approved
  documents and the plan's original steps. This file = current state for a new session.
- A delegated worker is handed **a step section from the plan**. That is the real reason the plan
  cannot be allowed to go stale.

**Verification**
- **Verification code needs the same scrutiny as the thing it verifies.** A delegated worker was
  wrongly rejected on a coverage figure because the *verification* dropped each rule's other
  clauses. The worker was right. Re-check the checker before disputing a result.
- **Execute notebooks, don't just write them.** Three separate errors were caught only by running
  them — including a fusion design that ranked its own key alerts #414 of 417.

**Environment**
- **GateGuard** intercepts the first Bash command and every new-file Write. It requires a short
  facts preamble (callers, no-duplicate check, schemas, verbatim user instruction) before it
  allows the call. `ECC_GATEGUARD=off` disables it if it becomes obstructive.
- `gh` is **not authenticated** — no PR/CI automation. Git branches work fine.
- Kaggle is **not authenticated** — irrelevant now; the dataset came from the authors' own server.
- The 10.4 GB archive and 142 MB `train_sample.csv` are gitignored. The **frozen fixture CSVs are
  force-added** because they are the reproducibility anchor.
- **Two Python interpreters, and they disagree.**
  - `python` may resolve to **Python 3.12 / pandas 3**, which has no `xgboost`, so one contracts
    test skips.
  - `C:/ProgramData/miniconda3/python.exe` is **3.11 / pandas 2**; the full suite passes there with
    0 skipped.
  - Jupyter's `python3` kernel runs 3.12 even when launched from miniconda's jupyter.
  - Pandas 3 changed date parsing: always parse ISO timestamps with `format="ISO8601"`, never
    `dayfirst` (changelog v1.12).
- **If pytest reports `PermissionError` on its temp folder**, the session sandbox is blocking it,
  and the code is not at fault. Run
  `python -m pytest -p no:cacheprovider --basetemp=<scratchpad>/pytest-tmp`.

---

## 7. Next steps, in dependency order

| # | Step | Owner | Note |
|---|---|---|---|
| ~~1~~ | ~~Held-out re-test of rule thresholds~~ | **DONE 2026-09-11** | precision **0.9999**, recall **0.1993** on 250,655 unseen rows; 2 FPs in 30,025 hits. Not overfit. |
| ~~2~~ | ~~S2 — data contracts~~ | **DONE 2026-09-11** | 12 tables, 51 tests, 0 skipped. Deviations in changelog v1.5 |
| ~~3~~ | ~~S5 + S4b — signature engine and tuned rule set~~ | **DONE 2026-09-11** | Engine delegated (DeepSeek), golden-tested 1,000/1,000. Rule set written; held-out figures reproduced. Changelog v1.6 |
| ~~4~~ | ~~S6 — fusion re-specification~~ | **DONE 2026-09-11** | `packages/detection/fusion/cef.py`; spec in its docstring. Demo: 200 corroborated, 0 override; DB queue order proven. Changelog v1.8 |
| 5 | ~~S7a — direct feedback + guardrails~~ **DONE** (changelog v1.10) · ranking experiment **done** (changelog v1.12–v1.13; Q29 formula C1, Q30 agreement gate) · **NEXT →** S7b: similar-alert learning with the gate, formula C1 and movement M1, as persisted family adjustments. Count agreement by feedback category, as the collaborator's engine does, not by direction as the experiment does. Add plus `queue_class` and the Tier 2 marker as contract additions (`ranking-and-escalation-design.md` §7). Inputs recorded before S7a: invariant I3 is S7's; "Critical" now means score ≥ 80 (Node used ≥ 90) — log the floor-trigger decision. Inputs from v1.9: floors must never *raise* a score; map `uncertain`; feedback cannot cross evidence bands — see `system-workflow.md` §7 | **Claude only** | **Port the collaborator's design** (sec. 8) to Python rather than authoring fresh |
| ~~5b~~ | ~~S7b — similar-alert learning~~ | **DONE 2026-09-12** | `feedback/learning.py` + a rewritten `service.py`: the coarse family key, the category-counted gate, C1 + M1 replayed over each family's effective verdicts, the `alert_families` table, and the `queue_class` contract addition. Changelog v1.14 |
| ~~6~~ | ~~S8 — audit writer~~ · ~~S9 — SQLite persistence + batch detection runner~~ | **DONE 2026-09-12** | `packages/detection/pipeline/`: the S3 ingest seam, the predictor protocol (TreeSHAP in the run, D8), the repository layer and `run_detection`. 5,000 flows → 5,000 alerts in 21 s, reproducible field-for-field. Changelog v1.15 |
| ~~7~~ | ~~S15 — the three-arm evaluation harness~~ | **DONE 2026-09-12** | `packages/evaluation/` + `scripts/run_evaluation.py`; 25 tests. Arms are byte copies of one detection database, so dataset/model/rules/seed are pinned by construction. Pre-registration `s15-preregistration-1`, 40 verdicts. **Detection identical across all three arms.** S7b reached 198 untouched true positives and leaked onto 0 alerts outside judged families — **but promoted a benign alert from rank 639 to rank 1**, and precision fell (P@50 1.000 → 0.980) because the control was already perfect. Arm C = arm B exactly: the sequence had no dismissals, so no guardrail could bind. Changelog v1.16, report `evaluation-report.md` |
| ~~8~~ | ~~S10a — the API contract~~ | **DONE 2026-09-12** | `apps/api/contract/` + `scripts/build_openapi.py`; 26 tests. 13 operations, 37 schemas, published to `apps/api/openapi.json`. Pure Pydantic — no FastAPI import — so S11 can start now. Reading the plan first caught a stale v1.0 instruction to order the queue by `evidence_priority`, which would have made feedback appear to do nothing. Changelog v1.18 |
| 9 | **NEXT →** S10b — the route handlers behind S10a's contract | **delegate + Claude review** | The worker gets `apps/api/openapi.json`, the contract models and `store.py`'s reads. **`POST /alerts/{id}/feedback` is withheld** — it invokes the guardrails. NFR-04 (p95 < 2s) is measured here |
| 10 | S11 — web shell, role switching, typed client | delegate + Claude review | Depends on S10a only, which is done: **this can start in parallel with S10b** |

Full detail per step: [`../../plans/hitl-ids-demo-build.md`](../../plans/hitl-ids-demo-build.md).

**Guardrail constants — use the collaborator's `stage-5/config/adaptation-config.json`**, which is
richer than the docs and now merged: max negative **-30**, **max positive +20** (the docs omit a
positive cap entirely — without it repeated "confirm true positive" inflates without bound),
criticalFloor **70**, infiltrationFloor **75**, reviewThreshold **70**, min **3** feedback events,
agreement **0.67 = moderate / 0.80 = strong**, with graduated adjustments
(FP -10/-25 · TP +8/+15 · expected activity -15).

**Feedback categories — RESOLVED.** The engine (`stage-5/core/feedback-engine.js:80-112`) is
authoritative and implements **five** scoring categories, under different names from the docs:
`confirm_true_positive +10` (forces review) · `mark_false_positive −30` ·
`mark_expected_activity −15` · `needs_investigation 0` (forces review) · `escalate +15` (forces review).
*(Corrected in changelog v1.9 — this line previously said −30 for expected activity.)*
**`duplicate` needs no delta.** The engine lists it with no score change, alongside `uncertain`
(no change, forces review — map it in S7); URS UC-SA-15 defines `duplicate` as a *queue action*
(link to original, suppress from active queue), not a score adjustment. The docs' "six categories" miscounts by folding a queue action into the scoring set.

---

## 8. The collaborator's work — what to use, what to ignore

A collaborator force-pushed 14 commits to `origin/main`, merged into our branch. **Their 6-class
model and every output derived from it are INVALIDATED** — trained on the uncorrected dataset,
cannot emit `Infiltration` or `Port Scan`. **Our 8-class model is the single source of truth.**
Their *code*, however, is good and largely reusable.

| Their asset | Status | Use |
|---|---|---|
| `stage-3/core/ml_inference.py` | **ADAPTED, IN USE** | Vendored to `packages/detection/ml/inference.py` |
| `stage-3/evaluation/ml-explainability-summary.json` | **INVALIDATED** (6-class) | Superseded by `data/processed/ml-explainability-summary.json` |
| `stage-5/config/adaptation-config.json` | **ADOPT** | The similarity + adjustment + guardrail design for S7 |
| `stage-5/core/similarity-engine.js` | **PORT to Python** | Weighted similar-alert matching, needed by S7 and evaluation |
| `stage-5/core/feedback-aggregation-engine.js` | **PORT to Python** | Agreement-gated aggregation |
| `stage-5/tests/*`, `stage-3/tests/*` | **USE AS SPEC** | 1,237 lines of behavioural tests to port |
| `dashboard/` | Component source only | Displays invalidated 6-class data |

**The three adaptations already made** (marked `ADAPTED:` inline in our vendored copy):
1. Removed their hard **78-feature assertion** — it rejected our 82-feature model outright.
2. Extended `FORBIDDEN_PREDICTION_FIELDS` with **`Attempted Category`**, `attack_class`,
   `is_attempted`. `Attempted Category` states whether an attack succeeded and is a leakage vector
   introduced by the corrected release, so their guard predates it.
3. Repointed default paths from `stage-3/` to `hitl-ids/`.

**They independently confirmed two of our conclusions:** `duplicate` sits in their
`workflowFeedbackTypes` (not scoring), and they retained `infiltrationFloor: 75`.

**Coordination risk — needs a human conversation, not a code fix.** They force-push (our branch
base `2209658` was rewritten away) and they actively develop in `stage-3/`/`stage-5/`, which our
plan declared frozen. Our fixtures survived only because they are *copies*. Agree a boundary with
them before the next merge.

---

## 9. Open questions for the user

1. ~~Push the branch?~~ **User decision (2026-09-11):** `feat/s2-contracts` pushed to origin as a
   view-only progress branch, with the demo sample. `feat/s6-fusion` (S2–S6 + docs) pushed on request
   the same day. Work continues locally; push again only when asked.
2. ~~Held-out re-test~~ **Done, reported.** ~~S2~~ ~~S5 + S4b~~ ~~S6~~ ~~S7a~~ ~~S7b~~ ~~S8~~
   ~~S9~~ ~~S15~~ — **all done.** Next is **S10a**. Settled since: feedback moves an alert between
   *queue bands* (Q24), never across evidence classes, which closes the `system-workflow.md` §7
   item 4 question.
   **Open (ranking):**
   - (a) Movement M1 or M2 under the gate. The data cannot separate them; M1 stands unless you
     choose M2. S15 adds one datum: under M1 the class offset **accumulates** one band per
     confirmation and clamps at −5, so five verdicts in a family move its members the full
     distance — M1 and M2 converge once a family is judged five times.
   - (b) Whether to add the fine family key as defence in depth. **S15 gives this a concrete
     cost:** the coarse key promoted a benign alert from rank 639 to **rank 1** because its family
     was dominated by confirmed Web Attacks (`evaluation-report.md`, finding 2).
   - (c) The efficiency gain is still untested, and S15 confirmed why: the control queue is already
     perfect (precision 1.000 to k=200, 2 false positives in 996 flagged alerts), so feedback can
     only break it. The stress test with a weaker or drifting detector
     (`ranking-and-escalation-design.md` §8) remains the only way to answer it. **Not run — it
     needs your go-ahead**, and must be reported as a separate, clearly-labelled experiment.

7. **Two decisions S15 surfaced** (`evaluation-report.md` §6), neither taken:
   - (a) **Arm C has no power as pre-registered.** The oracle analyst over a near-perfect detector
     produced no dismissals, and every guardrail that could bind protects against *downward*
     pressure — so "guardrails off" changed nothing. A second pre-registered rule drawing from the
     queue's false positives would give arm C something to measure. Changing the existing rule
     after seeing the result is what plan v0.3 forbids, so this is yours to call.
   - (b) **The queue bands reuse the evidence-class names.** Five `ml_only` alerts now sit in the
     band named `signature_override` with their evidence class unchanged. Rename the bands, or
     accept the collision knowingly before the viva.
3. Review [`finding-infiltration-mislabelling.md`](finding-infiltration-mislabelling.md) — a
   report-ready write-up of the Infiltration finding, drafted and awaiting your edit.
4. **Agree a file-ownership boundary with the collaborator** before the next merge (see sec. 8).
5. When ready, our tree is intended to **supersede** their `stage-3/`/`stage-5/` on push — user
   decision, not yet actioned. Branch is deliberately **local only**; do not push unasked.
6. **Two S7b judgement calls, each reversible in one line** (changelog v1.14): `escalate` counts as a
   confirmation for family learning, where the collaborator's engine treats it as teaching nothing;
   and a dismissal withdraws an alert's "→ Tier 2" marker. Both are logged and either can flip.
