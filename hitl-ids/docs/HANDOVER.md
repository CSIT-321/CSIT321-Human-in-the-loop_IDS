# HANDOVER — read this first in a new session

**Purpose.** Carry the full state of this project into a fresh session with zero loss of context
and minimal token cost. Everything a new session needs is here or one link away.

**Last updated:** 2026-09-11 (rev 6) · **Branch:** `feat/s6-fusion` (local) ·
`feat/s2-contracts` **pushed to origin** as a view-only progress branch · **S2, S5 + S4b, S8, S6
DONE** — changelog v1.8
**Iteration 1 (Evidence & Direction) complete** — = plan Phase 1 + step S4b · collaborator's
`origin/main` merged · **NFR-01 explainability satisfied**

---

## 0. Paste this to start the next session

> Read `hitl-ids/docs/HANDOVER.md` in this repo, then confirm you have the state loaded by telling
> me (a) the current phase and next step, (b) the two findings that were reversed and why, and
> (c) what I have told you never to delegate. Do not re-derive any settled decision. Then begin
> the next step.

The confirmation is not ceremony — if a new session cannot answer those three, it has not loaded
the state and will re-litigate settled ground.

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
> **Actual status:** Phase 0 **PARTIAL** (S1 scaffold incomplete — Python slice only; **S2 DONE**, 51 tests) ·
> Phase 1 **DONE** · Phase 2 **S5, S4b, S8, S6 done** (S7 remains) · Phases 3–6 **not started**.

```
hitl-ids/
  data/raw/       CSECICIDS2018_improved.zip   10.4 GB, GITIGNORED, must be re-downloaded
  data/processed/ label_scan · demo_sample(5,000) · train_sample(250,655) · manifests
  models/         8-class XGBoost + metrics + port ablation
  notebooks/      01-04, all execute with ZERO errors
  packages/detection/ml/inference.py   vendored+adapted TreeSHAP inference (see sec. 8)
  packages/contracts/  S2: models.py · schema.sql (12 tables) · db.py (codec, QUEUE_ORDER_BY)
  tests/test_contracts.py   51 tests - run: python -m pytest   (pyproject.toml sets pythonpath)
  scripts/        9 scripts, all runnable
  tests/fixtures/legacy/   8 FROZEN files - never regenerate
  docs/           HANDOVER · iteration-report · plan-changelog(v0.1-v1.4) ·
                  feasibility-study · rule-retuning-report · finding-infiltration-mislabelling
                  · img/ (6 rendered PNGs)
plans/hitl-ids-demo-build.md    18-step build plan (S1-S18), v1.0
```

**Also merged:** the collaborator's `stage-3/` and `stage-5/` work (their model is INVALIDATED -
see sec. 9). Their `dashboard/` still runs but displays old 6-class data.

**Start here:** [`iteration-2-report.md`](iteration-2-report.md) — what Iteration 2 built, with the
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

---

## 7. Next steps, in dependency order

| # | Step | Owner | Note |
|---|---|---|---|
| ~~1~~ | ~~Held-out re-test of rule thresholds~~ | **DONE 2026-09-11** | precision **0.9999**, recall **0.1993** on 250,655 unseen rows; 2 FPs in 30,025 hits. Not overfit. |
| ~~2~~ | ~~S2 — data contracts~~ | **DONE 2026-09-11** | 12 tables, 51 tests, 0 skipped. Deviations in changelog v1.5 |
| ~~3~~ | ~~S5 + S4b — signature engine and tuned rule set~~ | **DONE 2026-09-11** | Engine delegated (DeepSeek), golden-tested 1,000/1,000. Rule set written; held-out figures reproduced. Changelog v1.6 |
| ~~4~~ | ~~S6 — fusion re-specification~~ | **DONE 2026-09-11** | `packages/detection/fusion/cef.py`; spec in its docstring. Demo: 200 corroborated, 0 override; DB queue order proven. Changelog v1.8 |
| 5 | **NEXT →** S7 — feedback + guardrails. Inputs from v1.8: invariant I3 is S7's; "Critical" now means score ≥ 80 (Node used ≥ 90) — log the floor-trigger decision | **Claude only** | **Port the collaborator's design** (sec. 8) to Python rather than authoring fresh |
| 6 | ~~S8 — audit writer~~ **DONE** (delegated, changelog v1.7) · S9 — SQLite repositories + batch runner | Mixed | S9 builds on `db.insert`/`db.get` and `AuditWriter` |

Full detail per step: [`../../plans/hitl-ids-demo-build.md`](../../plans/hitl-ids-demo-build.md).

**Guardrail constants — use the collaborator's `stage-5/config/adaptation-config.json`**, which is
richer than the docs and now merged: max negative **-30**, **max positive +20** (the docs omit a
positive cap entirely — without it repeated "confirm true positive" inflates without bound),
criticalFloor **70**, infiltrationFloor **75**, reviewThreshold **70**, min **3** feedback events,
agreement **0.67 = moderate / 0.80 = strong**, with graduated adjustments
(FP -10/-25 · TP +8/+15 · expected activity -15).

**Feedback categories — RESOLVED.** The engine (`stage-5/core/feedback-engine.js:80-112`) is
authoritative and implements **five**, under different names from the docs:
`confirm_true_positive +10` · `mark_false_positive −30` · `mark_expected_activity −30` ·
`needs_investigation 0` (forces review) · `escalate +15` (forces review).
**`duplicate` needs no delta.** It appears zero times in the engine or dashboard, and URS UC-SA-15
defines it as a *queue action* (link to original, suppress from active queue), not a score
adjustment. The docs' "six categories" miscounts by folding a queue action into the scoring set.

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
   view-only progress branch, with the demo sample. Work continues locally; push again only when asked.
2. ~~Held-out re-test~~ **Done, reported.** ~~S2~~ **Done.** ~~S5 + S4b~~ **Done.** ~~S8~~ **Done.** ~~S6~~ **Done.** Next is S7 (Claude only — the plan's highest-risk step).
3. Review [`finding-infiltration-mislabelling.md`](finding-infiltration-mislabelling.md) — a
   report-ready write-up of the Infiltration finding, drafted and awaiting your edit.
4. **Agree a file-ownership boundary with the collaborator** before the next merge (see sec. 8).
5. When ready, our tree is intended to **supersede** their `stage-3/`/`stage-5/` on push — user
   decision, not yet actioned. Branch is deliberately **local only**; do not push unasked.
