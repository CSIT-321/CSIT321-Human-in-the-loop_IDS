# Blueprint — Human-in-the-Loop IDS Dashboard

**Version 1.1** · supersedes v1.0, v0.3 (post-adversarial-review) and v0.2 (post-grilling).
**This file is canonical for what to build next** — see *Step status* below. It is re-synchronised
with `plan-changelog.md` at the end of every step; a test (`tests/test_plan_sync.py`) fails if the
two disagree.
**Read [`hitl-ids/docs/plan-changelog.md`](../hitl-ids/docs/plan-changelog.md) first** — it records
every change and the evidence that forced it, including the claims this plan no longer makes.
Deviations register: [`hitl-ids/docs/deviations.md`](../hitl-ids/docs/deviations.md).
Method and limitations: [`hitl-ids/docs/feasibility-study.md`](../hitl-ids/docs/feasibility-study.md).

**Objective:** A presentable, end-to-end working demo of the HITL IDS dashboard, on a foundation that grows into the full specified system without a rewrite.

> ### What changed in v1.1, in one paragraph
> v1.0 was written on the **uncorrected** dataset and two of its claims did not survive the corrected
> one. It said the detectors are *complementary* — that the signature layer catches 8 brute-force
> attacks the model calls Benign. **On corrected data `signature_only = 0`: the signature layer has
> zero unique coverage**, and is justified instead as trust and explainability (Q21). It also said
> co-occurrence is zero; **agreement in fact occurs 200 times**, which is what makes the
> `corroborated` band real. What survives from v1.0 is the part that mattered: the TDM's weighted-sum
> fusion has **mathematically inert** weights and is replaced by **Complementary Evidence Fusion**,
> and **S4b** earns the precision the design depends on. v1.1 also corrects S4b's rule list (v1.0
> would have retired the project's most productive rule), replaces the S16 demo narrative whose own
> stop-condition has triggered, and adds the *Step status* table this plan previously lacked.
> Full register: [`deviations.md`](../hitl-ids/docs/deviations.md) §E.

**Repo:** `github.com/CSIT-321/CSIT321-Human-in-the-loop_IDS` (branch `main`)
**Mode:** git branches, **no `gh` automation** (`gh` not authenticated — run `gh auth login` to enable PR/CI steps)
**Scheduling:** dependency-ordered. **No dates.** A step is ready when its dependencies' exit criteria pass.

---

## Locked decisions (from grilling rounds 1–3)

| # | Decision | Consequence |
|---|---|---|
| D1 | Dataset = **corrected** CSE-CIC-IDS2018 (Engelen et al., IEEE CNS 2022) | Cite as methodological contribution; pre-empts dataset-validity challenge |
| D2 | Retrain XGBoost to **8 classes incl. Infiltration** — `Port Scan` split out of Infiltration (Q19; 99.6% of "Infiltration" was NMAP portscan) | Must land before any evaluation work |
| D3 | Backend = **option (c)**: batch detection writes SQLite; minimal API for feedback/audit path only | Grows into full FastAPI without schema rewrite |
| D4 | All detection logic in **Python** | Node engines are reimplemented, not transliterated |
| D5 | **New structure** `hitl-ids/` inside existing repo; old folders disregarded | `stage-*/`, `dashboard/`, `prototype-demo/` frozen as research record |
| D6 | **All 3 role UIs**, analyst path deepest | Guardrail + evaluation screens are the selling point |
| D7 | Prefix module = **flow exporter** (Engelen CICFlowMeter fork), post-demo | Avoids train/serve skew: same tool produced D1's dataset |
| D8 | SHAP **precomputed** top-5 at detection time | Protects NFR-04 ~2s budget |
| D9 | Evaluation = **3 seeded runs** (control / treatment / guardrails-off) | Only way to demonstrate rather than assert guardrails |
| D10 | Docs (PRD/URS/TDM) are **reference only**, not amended | Deviations logged in `hitl-ids/docs/deviations.md` |

**Known deviations from approved docs** (log, don't hide): dataset is 2018-corrected not CICIDS2017; SQLite before PostgreSQL; fusion may become 3-way if a third detector is added later.

---

## Target structure

```
hitl-ids/
  apps/
    api/            FastAPI service
    web/            React + Vite + Tailwind + Recharts
  packages/
    detection/
      pipeline/     FlowSource seam + predictor + repositories + run_detection (S9)
      signature/    custom flow rule engine
      ml/           model load, predict, SHAP
      fusion/       combined scoring
      feedback/     category deltas, exception memory
      guardrail/    caps, floors, trust gates
      audit/        append-only writer
    evaluation/     S15 three-arm harness: truth, pre-registration, metrics, arms
  data/             versioned datasets
  models/           model artifacts
  evaluation/       experiment RECORDS only (ranking/, three-arm/) — code lives in packages/
  notebooks/        training
  tests/
  docs/deviations.md
```

---

## Ownership and delegation policy

**Claude (me) — never delegated:** architecture, data contracts, fusion maths, feedback maths, guardrail logic, evaluation design, every review gate.

**GLM / DeepSeek workers:** scaffolding, CRUD endpoints, React components from a given contract, test fixtures, docstrings, type stubs, migration boilerplate, doc drafting.

**Provider constraints (verified this session):** DeepSeek **cannot** use WebSearch (`unrecognized_model` on `web_search_tool`); GLM likewise failed web search and answered from training knowledge instead. **All research stays with Claude.** Every worker output is verified by reading the files it wrote — never its self-report.

---

## Dependency graph

```
S1 ──> S2 ──┬──> S3 ──> S4 ───────────────┐
            │                             │
            ├──> S5 ──> S4b ──> S6 ──> S7 ─┴──> S9 ──> S15 ──> S10a ──> S10b ──> S11 ──┬──> S12 ──┐
            │                                                                          ├──> S13 ──┤
            └──> S8 ───────────────────────────────────────────────────────────────────┴──> S14 ──┴──> S16 ──┬──> S17
                                                                                                             └──> S18
```

**Parallel opportunities:** S5 ∥ S8 · S3/S4 ∥ S5/S4b/S6 · S12 ∥ S13 · S17 ∥ S18

**Progress along that graph (v1.1):** everything from `S1` to `S15` inclusive is built —
`S2 → S3 → S4`, `S5 → S4b → S6 → S7a → S7b`, `S8`, `S9`, `S15`. The frontier is **S10a**, and from
there the graph is a straight run of user-facing work to the S16 gate.

> **v0.3 FIX — two dependency errors corrected.**
> **(a)** `S15 → S10` was missing. S10's endpoint list includes `GET /api/evaluation/*`, whose response schemas cannot be specified until S15 defines the metrics. The v0.2 claim `S15 ∥ S11` was **false** and is withdrawn.
> **(b)** "S11 may start once OpenAPI is frozen" was circular — FastAPI *generates* OpenAPI from implemented route handlers, so the document does not exist until S10 is substantially built. **S10 is therefore split:** **S10a** (contract — Pydantic response models, hand-authored OpenAPI; Claude) and **S10b** (handlers; delegable). S11 depends on S10a only, which restores real parallelism instead of asserting it.
>
> **v1.0 CHANGE.** **S4b** (rule tuning) inserted between S5 and S6. S6 no longer depends on S4, because the golden test that created that dependency is deleted — decoupling fusion from the retrain.

---

## Step status

**Canonical.** This table is the answer to "what do I build next". Update it in the same commit that
finishes a step; `tests/test_plan_sync.py` fails if it disagrees with `HANDOVER.md` §7 or with the
changelog's current version. Status is one of `DONE` · `PARTIAL` · `NEXT` · `TODO`.

<!-- PLAN-STATUS:BEGIN -->

| Step | Name | Status | Landed |
|---|---|---|---|
| S1 | Scaffold structure and tooling | PARTIAL | — |
| S2 | Canonical data contracts ⭐ KEYSTONE | DONE | v1.5 |
| S3 | Corrected dataset + FlowSource ingestion | DONE | v1.15 |
| S4 | Retrain XGBoost to 8 classes + SHAP | DONE | v1.2 |
| S5 | Signature engine to Python | DONE | v1.6 |
| S4b | Signature rule tuning | DONE | v1.6 |
| S6 | Fusion re-specification (CEF) | DONE | v1.8 |
| S7a | Direct feedback + guardrails | DONE | v1.10 |
| S7b | Similar-alert learning | DONE | v1.14 |
| S8 | Append-only audit writer | DONE | v1.7 |
| S9 | SQLite persistence + batch runner | DONE | v1.15 |
| S15 | Three-arm evaluation harness | DONE | v1.16 |
| S10a | API contract | DONE | v1.18 |
| S10b | API handlers | DONE | v1.19 |
| S11 | Web shell, role switching, design system | NEXT | — |
| S12 | Analyst path (deep) ⭐ DEMO CORE | TODO | — |
| S13 | Admin path (thin) | TODO | — |
| S14 | Evaluator path (thin) | TODO | — |
| S16 | Demo assembly and rehearsal ⭐ GATE | TODO | — |
| S17 | Prefix flow-exporter module | TODO | — |
| S18 | Full backend (D3 complete) | TODO | — |

<!-- PLAN-STATUS:END -->

**Where that leaves us, in plain terms.** Every part of the system that runs *before a human sees
anything* is built and tested: flows in, rules and model score them, fusion ranks them, an analyst
verdict reshapes the queue inside guardrails, all of it persisted, audited, reproducible and now
measured against a control. **Nothing a human can see is built** — there is no API and no UI. The
remaining seven steps to the demo gate are the entire user-facing half of the project.

**S1 is PARTIAL, deliberately.** The Python slice (`packages/`, `tests/`, `scripts/`, `config/`) is
real and complete; `apps/api/` and `apps/web/` do not exist yet and are created by S10 and S11.

---

# PHASE 0 — Foundation

## S1 — Scaffold structure and tooling

**Deps:** none · **Owner:** delegate (GLM) · **Branch:** `feat/s1-scaffold`

**Context brief.** New greenfield tree `hitl-ids/` inside an existing repo whose other top-level folders are a frozen research record and must not be touched. Python 3.11, Node 22. Backend FastAPI, frontend React + Vite + TypeScript + Tailwind + Recharts.

**Tasks.** Create the target structure above. `pyproject.toml` with ruff + pytest + FastAPI + xgboost + shap + pandas + scikit-learn. Vite app in `apps/web` with Tailwind and Recharts configured. `.gitignore` for data/models/venv. A `README.md` stating this tree supersedes `stage-*/`.

**Verify.** `python -m pytest -q` (0 tests, exits clean) · `cd apps/web && npm run build` succeeds · `ruff check .` clean.

**Exit criteria.** Both toolchains build from a clean clone. No file outside `hitl-ids/` and `plans/` modified.

**Rollback.** Delete `hitl-ids/`; nothing else is touched.

## S2 — Canonical data contracts ⭐ KEYSTONE

**Deps:** S1 · **Owner:** **Claude** · **Branch:** `feat/s2-contracts`

**Context brief.** Every later step depends on these types. The TDM defines 13 tables; the demo needs a coherent subset that can grow to all 13 without migration pain. Guardrail defaults are fixed and consistent across all three source documents: max reduction **30**, critical floor **70**, critical threshold **80**, exception min occurrences **3**, min confidence **60%**.

**Tasks.** Pydantic models: `FlowRecord`, `SignatureMatch`, `MlPrediction`, `ShapAttribution`, `Alert`, `FeedbackEvent`, `GuardrailOutcome`, `AuditEntry`, `DetectionRun`, `EvaluationRun`. SQLite DDL for the demo subset — **twelve** tables: `users`, `datasets`, `signature_rules`, `ml_models`, `detection_runs`, `alerts`, `flow_data`, `feedback_events`, `audit_log`, `guardrail_config`, `evaluation_scenarios`, `evaluation_runs` — with TDM column names preserved so the Postgres migration is mechanical. Append-only `audit_log` enforced by trigger. Seed `guardrail_config` with the five defaults above **plus `infiltration_floor_75`** (a third guardrail present in `feedback-engine.js:65-69` that v0.2 of this plan had dropped).

> **v0.3 FIX.** Four tables were missing from v0.2 and are now mandatory: `ml_models` (S4's rollback names `ml_models.status`), `evaluation_scenarios` (FK parent of `evaluation_runs`; holds S15's `feedback_sequence` and `guardrails_active`), `users` (FK parent of `audit_log.actor_id`; S16's narrative opens with login), `signature_rules` (S9 takes `rule_version`; NFR-08 requires admin-configurable rules).

**Alert schema addition (v1.0).** `alerts` gains `evidence_class` (`corroborated | signature_override | ml_only | none`) and `evidence_priority` (int). These are load-bearing, not decorative — the queue orders by them (see S6).

**Verify.** `pytest tests/test_contracts.py` — round-trip every model; assert an `UPDATE`/`DELETE` on `audit_log` raises; **enumerate `PRAGMA foreign_key_list` for every table and assert zero dangling references**.

**Exit criteria.** Schema instantiates on a fresh SQLite file; append-only proven by a failing-write test; column names match TDM; every FK resolves within the schema.

**Rollback.** Schema is not yet consumed — drop and redefine freely. **After S9 this becomes expensive: get it right here.**

---

# PHASE 1 — Data and model

## S3 — Corrected dataset + FlowSource ingestion

**Deps:** S2 · **Owner:** Claude (acquisition) + delegate (transforms) · **Branch:** `feat/s3-ingest`

**Context brief.** Replace the original CSE-CIC-IDS2018 with the Engelen corrected release. Define the seam D7 depends on: a `FlowSource` protocol whose only implementation now is `CsvReplaySource` (streams rows in timestamp order to simulate a sensor). The existing 1,000-row `AL-XXXX` sample is **verified sound** — its 78 model features align exactly with `feature-columns.json`, extras are `Flow ID`, `Src IP`, `Dst IP`, `Src Port`, `Timestamp`, `id` — so it may be carried over as an interim fixture.

**Tasks.** Acquire corrected dataset; record provenance and citation in `docs/deviations.md`. Implement `FlowSource` protocol + `CsvReplaySource`. Stratified sampler producing a versioned demo sample **including Infiltration**. Register into `datasets` with `class_distribution`. Emit a held-out split with an explicit leakage check.

**Verify.** `pytest tests/test_ingest.py` — schema validation, no train/test id overlap, all 8 classes present in both splits.

**Exit criteria.** Versioned dataset row in DB; leakage test passes; `CsvReplaySource` yields records in timestamp order.

**Rollback.** Keep old sample as `data/legacy/`; ingestion is additive.

## S4 — Retrain XGBoost to 8 classes + precompute SHAP

**Deps:** S3 · **Owner:** Claude (design) + delegate (notebook boilerplate) · **Branch:** `feat/s4-model`

**Context brief.** Current model has **6** classes — `Benign`, `Botnet`, `Brute Force`, `DDoS`, `DoS`, `Web Attack`. **Infiltration is absent while 83 of 1,000 demo rows are Infiltration**, so 8.3% of the demo set is unclassifiable by construction and every per-class metric is currently invalid. Infiltration is known to be near-unlearnable in this dataset; a poor-but-honest per-class score is a legitimate finding, a missing class is not.

**Tasks.** Retrain on corrected data, 8 classes, `imbalanced-learn` for skew. Export model + `feature-columns.json` + `label-mapping.json` + `preprocessing-config.json`. TreeSHAP top-5 per record, persisted to `alerts.shap_attributions` at detection time (D8). Record per-class precision/recall/F1 to `ml_models`.

**Verify.** `pytest tests/test_model.py` — label map has 8 classes including Infiltration and Port Scan; feature order matches training; SHAP contributions sum to (prediction − base value) within tolerance.

**Exit criteria.** 7-class model loads and predicts; SHAP additivity assertion passes; per-class metrics recorded, Infiltration included even if weak.

**Rollback.** Model artifacts are versioned; `ml_models.status` flips back to the prior version.

---

# PHASE 2 — Detection core (Python port)

> **Port strategy for S5–S7:** the Node engines are the **specification**, not the source. Reimplement in Python, then assert the Python output matches the existing Node JSON outputs on the same 1,000-row input (golden tests). This proves the port preserves behaviour before any new logic is added.

## S5 — Signature engine to Python

**Deps:** S2 **only** · **Owner:** delegate (DeepSeek) + Claude review · **Branch:** `feat/s5-signature` · ∥ S8

> **v0.3 FIX.** v0.2 declared `Deps: S2, S3`, scheduling this step *after* the dataset swap — so an agent reading it cold would golden-test the port against the **new** data and get a total mismatch. This step needs a frozen fixture, not new data. The dependency on S3 is removed.

**Context brief.** Port `stage-2/core/signature-engine.js` (296 LOC). Rules are flow-feature predicates in `flow-signatures.json`, AND-combined, each emitting normalised severity 0–1. **Hard rule: `attackType` and `groundTruth` are labels, never detection inputs** — the original project already had to correct this once.

**Fixtures are already frozen** at `hitl-ids/tests/fixtures/legacy/` (done during the feasibility study): `flow-feature-sample.csv`, `flow-feature-full.csv`, `ground-truth.json`, `flow-signatures.json`, `signature-output.sample.json`, `ml-predictions.sample.json`, `fusion-alerts.sample.json`, `feedback-adjusted-alerts.sample.json`. **Never regenerate these.**

**Reference implementation.** Notebook `02` already contains a working clause evaluator that reproduces the Node engine's 15 hits exactly. Port from it rather than from scratch.

**Tasks.** Python rule engine reading the same JSON rule format. Rules enable/disable without code change (NFR-08). Golden test against the **frozen** `signature-output.sample.json`.

**Verify.** `pytest tests/test_signature.py` — golden match; a test asserting label fields are absent from the feature vector reaching a rule.

**Exit criteria.** Equivalent verdicts to Node on the 1,000-row sample; label-leakage test passes.

**Rollback.** Isolated package; delete and retry.

## S4b — Signature rule tuning ⭐ NEW IN v1.0

**Deps:** S5 (needs the Python rule engine) · **Owner:** **Claude** · **Branch:** `feat/s4b-rules`

**Context brief.** Notebook `02` proved the rule set barely functions: recall **0.016**, precision **0.533**, and **5 of 7 rules never fire**. The inert rules are not selective, they are **inverted** — `SIG-DDOS-HIGH-RATE-FLOW` demands `flowPacketsPerSecond >= 900` while actual DDoS flows sit at 0.07–8.94 and *benign* traffic reaches 23,529. Every rule is marked `"validationStatus": "prototype-heuristic"`; none was ever calibrated against data.

**Tasks.**
> **v1.1 CORRECTION — v1.0's rule list was derived on uncorrected data and is withdrawn.** It told
> you to retire `SIG-FTP-BRUTE-FORCE` and to set SSH's threshold to 20. Both are wrong on corrected
> data: FTP is one of the **two rules that survive**, and SSH's re-derived threshold is
> **10.66689**. A worker following v1.0 would have disabled the project's most productive rule.
> Logged as [`deviations.md`](../hitl-ids/docs/deviations.md) C1 and C2.

**Tasks — as actually settled (changelog v1.3, v1.6).**
- **Keep and retune the two brute-force rules.** `SIG-FTP-BRUTE-FORCE` = TCP + port 21 + `totalFwdPackets >= 1` + its other original clauses. `SIG-SSH-BRUTE-FORCE` = `flowPacketsPerSecond >= 10.66689` + its other clauses. Both reach precision **1.000** on held-out data.
- **Retire the other five** — `SIG-DOS-HIGH-RATE-FLOW`, `SIG-DDOS-HIGH-RATE-FLOW`, `SIG-BOTNET-BEACON-FLOW`, `SIG-WEB-ATTACK-FLOW`, `SIG-INFILTRATION-LONG-FLOW`. Best achievable single-threshold precision on the observable features is **0.14–0.37** — unusable for a high-precision posture. They stay in `rule-set-s4b-1.json` with `enabled: false`; **do not delete them**.
- Thresholds re-derived against the corrected dataset, then **validated on 250,655 held-out rows** through the production engine (`scripts/validate_rule_set.py`).

**Measured.** 30,025 hits. Any-attack scoring: precision **0.9999**, recall **0.1993**, 2 false positives. Class-correct scoring: precision **0.9992**, recall **0.1991** (23 NMAP probes of TCP/21 are labelled FTP brute force). **Always state which scoring is meant.**

**Verify.** `pytest tests/test_rules.py` — retuned SSH rule yields precision 1.000 on the frozen fixture; no retired rule remains enabled; overall signature precision **>= 0.9**.

**Exit criteria.** Signature precision >= 0.9 with recall in the 5–20% band. **This is deliberately low recall** — the layer is a high-precision oracle, not a detector of everything.

**Rollback.** Rules are JSON; revert the file.

> **Note on the goal.** v0.2 assumed tuning would restore signature+ML co-occurrence. It does not — notebook `02` shows co-occurrence stays **0** even after retuning. That is not a failure; §S6 explains why it is the point.

---

## S6 — Fusion re-specification (Complementary Evidence Fusion) ⭐ REWRITTEN IN v1.0

**Deps:** S5, S4b · **Owner:** **Claude (never delegated)** · **Branch:** `feat/s6-fusion`

> **v0.3 FIX.** v0.2 demanded the TDM weighted formula **and** a golden match against `fusion-engine.js` — impossible, because that file implements no weighted sum. It is an 8-branch decision tree (`clampScore(base + 10)`, `+5`, `-10`) over a severity map `Low:40 Medium:60 High:80 Critical:95`, and it bands Critical at **>= 90**, not the 80 v0.2 assumed. **The golden test is deleted.**
>
> **v1.0 CHANGE.** The weighted formula is *also* deleted. Notebook `01` F7 proved the weights inert: with zero co-occurrence they rescale two **disjoint** populations, ρ = 1.0000 across every weight setting. Notebook `03` showed the weight sweep is a see-saw — at `W_sig >= 0.7` signature alerts reach rank 4 only by crushing all 403 correct ML detections. **This step is a re-specification, not a port, and the deviation is logged in `docs/deviations.md`.**

**Context brief.** Implement **Complementary Evidence Fusion** exactly as specified in notebook `03`. Governing principle: *a high-precision detector is never averaged away by a disagreeing one.* Fusion scope stays **signature-record-scoped** — unmatched ML predictions are reported out-of-scope, never unioned (the real bug that produced 1000 + 2186 = 3186 phantom alerts). Note **996 of 1000** flows have an ML prediction; the 4 missing must be handled explicitly, not silently dropped.

**Tasks.** Evidence classification (`corroborated` / `signature_override` / `ml_only` / `none`). Score per class. `requires_review`. **Queue ordering by `evidence_priority` then score** — this is part of the contract, not a UI concern. Explanation generator = matched rules + top SHAP features. Delete the Infiltration special-case hack (it is dead code: `infiltrationMlLimitationCount: 0`).

**Verify.** `pytest tests/test_fusion.py` — the five invariants:
- **I1** a signature hit can never lower an alert below `sig_severity × 100`
- **I2** `signature_override` alerts are always review-flagged, whatever the score
- **I3** feedback cannot decay a `signature_override` alert; it routes to the administrator
- **I4** scoring is a pure function of its inputs
- **I5** **no `signature_override` alert may rank below any `ml_only` alert**

Plus: alert count equals signature scope exactly.

> **v1.1 CORRECTION.** v1.0 also required that "the 8 known complementary detections occupy
> review-queue positions 1–8". **No such alert exists** — `signature_only = 0` on corrected data, so
> the criterion is unsatisfiable and is withdrawn ([`deviations.md`](../hitl-ids/docs/deviations.md)
> E3). What replaces it: the queue's top band is `corroborated` (200 alerts, where rule and model
> agree), and **I5 still binds** — it is simply vacuous until a `signature_override` alert exists.

> **Why I5 exists.** CEF's own first design flagged those alerts for review and then sorted the queue by score — ranking them **#414 of 417**, *worse* than the weighted sum it replaced. Comparing a precision-1.000 rule's 60 against an ML probability's 85 is the original error in a new costume. The failure is preserved in notebook `03`.

**Exit criteria.** All five invariants pass. Alert count == signature record count. `AGREEMENT_BONUS` and `CRITICAL_THRESHOLD` configurable (these replace the inert weights and genuinely change behaviour on data that exists).

**Rollback.** Revert branch; S5 output unaffected.

## S7a / S7b — Feedback + guardrails to Python (split in v1.1)

**S7a — direct feedback.** One verdict, on one alert, inside the guardrails. Changelog v1.10.
**S7b — similar-alert learning.** That verdict carried to the alert's *family* behind the agreement
gate, using formula C1 and movement M1. Changelog v1.14. **This is the project's core claim.**

**Deps:** S6 · **Owner:** **Claude (never delegated)** · **Branch:** `feat/s7-feedback`

> **v1.1 — the split is recorded, not proposed.** Two separable claims with different risk profiles;
> S7b is where "feedback on past alerts reorders future alerts" actually lives
> ([`deviations.md`](../hitl-ids/docs/deviations.md) B4).

**Context brief.** Port `stage-5/core/feedback-engine.js` (437 LOC). Deterministic category deltas — **no Bayesian model** (`docs/tech-stack.md` claims Beta-Bernoulli; the code does not implement it and the TDM does not specify it — the doc is stale). Score guardrails and exception trust-gates are **separate mechanisms** and must not be conflated in metrics.

> **v0.3 FIX — three corrections to v0.2.**
> **(a) Categories.** v0.2 listed six; the engine implements **five** (`feedback-engine.js:81-112`) and `duplicate` is genuinely new. Specify all six deltas explicitly — the existing five are `confirmed_malicious +10`, `false_positive −30`, `expected_activity −30`, `uncertain 0`, `escalate +15` — and **decide `duplicate` deliberately**. Do not let an implementer invent a number.
> **(b) A third guardrail was dropped.** `infiltration_floor_75` exists at `feedback-engine.js:65-69` and was absent from v0.2's five defaults. Keep it or remove it, but **log the decision** in `docs/deviations.md`.
> **(c) The floor trigger changes semantics.** Node fires the floor when `fusionConfidenceLevel === 'Critical'`, which is score **≥ 90**. v0.2 said "critical floor 70 for alerts ≥ 80", widening coverage substantially. Defensible as a decision — but it is a behaviour change presented as a port, so log it.

**Guardrails.** Max reduction 30; critical floor 70; `infiltration_floor_75`; exceptions require ≥ 3 occurrences at ≥ 60% confidence. Every outcome records `applied | capped | rejected` with a reason.

**v1.0 addition — invariant I3.** Feedback **cannot decay a `signature_override` alert**; such feedback routes to the administrator as a possible rule regression. A precision-1.000 rule contradicted by an analyst is either a genuine regression worth escalating or analyst error, and in neither case should the score quietly erode.

**Tasks.** Category delta table (all six, explicit). Guardrail service returning `GuardrailOutcome`. Exception memory with occurrence/confidence gate. Every event written to append-only audit.

**Verify.** `pytest tests/test_guardrail.py` —
- the TDM worked example: score 92, requested −40, actual −22, final 70, floor enforced
- a critical alert can never be driven below 70 under **any** category or sequence
- **a `signature_override` alert's score is unchanged by any feedback category (I3)**
- `capped` ≠ `rejected` in counters
- *(secondary)* same alert + same feedback ⇒ identical delta

> **v0.3 FIX.** v0.2 billed that last check as the flagship NFR-05 test. It is a pure function of two immutable inputs — **it cannot fail**, and it says nothing about the run-level reproducibility NFR-05 actually requires (model inference, ordering, `PYTHONHASHSEED`). The real determinism test is S9's same-seed run. Demoted accordingly.

**Exit criteria.** Determinism property holds. Floor unbreakable by any sequence. Audit entry per event.

**Rollback.** Revert branch. **Highest-risk step in the plan — this is the safety claim.**

## S8 — Append-only audit writer

**Deps:** S2 · **Owner:** delegate + Claude review · **Branch:** `feat/s8-audit` · ∥ S5

**Context brief.** NFR-02/NFR-03: every detection, feedback, adjustment and config change logged with actor, timestamp, rationale; tamper-evident. The DB trigger from S2 is the enforcement; this is the typed writer over it.

**Tasks.** `AuditWriter` with typed event constructors (`LOGIN`, `FEEDBACK`, `DETECTION_RUN`, `RULE_CHANGE`, `GUARDRAIL_REJECTION`, `CONFIG_CHANGE`). Query/filter by actor, type, range. CSV export.

**Verify.** `pytest tests/test_audit.py` — write-then-read; `UPDATE` and `DELETE` both raise; filters correct.

**Exit criteria.** Immutability proven by test, not by assertion.

**Rollback.** Isolated package.

---

# PHASE 3 — Persistence and API

## S9 — SQLite persistence + batch detection runner

**Deps:** S6, S7, S8 · **Owner:** Claude · **Branch:** `feat/s9-persistence`

**Context brief.** D3's core: detection is an **offline batch** that writes a real database; the API never runs detection inline. One command takes a registered dataset to a populated `alerts` table.

**Tasks.** Repository layer over the S2 schema. `run_detection(dataset_id, model_version, rule_version, seed)` → ingest → signature → ML + SHAP → fusion → persist alerts + flow_data + shap → audit. Snapshot `fusion_weights` and `guardrail_config` into `detection_runs`.

**Verify.** `pytest tests/test_run.py` — end-to-end run over the sample yields alert count == signature scope; re-running with the same seed produces identical scores; run row snapshots config.

**Exit criteria.** A single command produces a fully populated demo DB, reproducibly.

**Rollback.** DB file is disposable; regenerate.

## S10a / S10b — Minimal API surface (split in v0.3)

**S10a — contract. ✅ DONE (changelog v1.18).** Deps: S9, S15 · Owner: **Claude** · Branch: `feat/s10a-contract`
Pydantic request/response models plus a **hand-authored** OpenAPI document. This is what S11 builds its typed client against.

> **Landed 2026-09-12.** `apps/api/contract/` (common · alerts · operations · openapi) +
> `scripts/build_openapi.py`, 26 tests. **13 operations over 12 paths, 37 schemas**, published to
> `apps/api/openapi.json` and committed so S11 can generate a client from a checkout.
>
> **Paths hand-authored, schemas generated.** Hand-typing the schemas would be a second copy of the
> Pydantic models, free to drift — the failure this project has already paid for once in its own
> planning documents. `--check` and a test keep the committed document in step with the models.
>
> **Decisions the contract carries:** `alertRef` (UUID) is the public identity, row ids are never
> exposed · both score columns in every queue row · the adjustment chain
> (`original → requested → bound → actual → final`) so the guardrails are visible rather than
> silent · `duplicate` is absent from the feedback categories · evaluation deltas may be negative,
> and the schema says so · camelCase on the wire, for a generated TypeScript client.
>
> **A leakage test guards the boundary**: no wire model may expose `attackClass`, `groundTruth`,
> `isAttempted` or a label. The API is the first component that *could* leak the answers.
>
> **Two gaps the contract tests caught while being written**: `AuditQuery` was declared but never
> wired to `/api/audit-log`, which therefore had no filters at all though S13 needs them; and
> query-parameter models were being emitted as unreferenced component schemas.

**S10b — handlers. ✅ DONE (changelog v1.19).** Deps: S10a · Owner: **Claude** · Branch: `feat/s10b-handlers`
Route implementations behind the S10a contract.

> **Landed 2026-09-12.** `apps/api/{deps,mappers,routes,main}.py`, 34 tests. Every contracted
> operation implemented; `uvicorn apps.api.main:app` serves the 5,000-alert demo database.
>
> **NFR-04 measured at real scale, not on the fixture**: `GET /api/alerts` p95 **19.3 ms**,
> `GET /api/alerts/{ref}` p95 **6.2 ms**, against a 2,000 ms budget. Deep paging (offset 4,900)
> does not degrade — `queue_page` issues two queries per page, never one per row.
>
> **Not delegated after all.** The plan allowed a delegate for the handlers with the feedback path
> withheld. In the event the write path, the mappers and the repository reads were too entangled to
> split cleanly, and two of the three bugs found were in exactly the shared part. Delegation would
> have cost more review than it saved.

> **What a delegated worker gets**: `apps/api/openapi.json`, the contract models, and
> `packages/detection/pipeline/store.py`, which already has the reads (`queue`, `counts_by`,
> `alert_by_source_record`). **`POST /api/alerts/{id}/feedback` is excluded from delegation** — it
> invokes the guardrails and the family learning, and it is Claude's, per the plan's own
> anti-pattern list. FastAPI's generated OpenAPI must match the committed document; a difference is
> the handlers failing the contract, not the contract being stale. NFR-04 (p95 < 2s on the two read
> endpoints) is measured here, since this is where code first runs.

> **v0.3 FIX.** v0.2 had a single S10 depending only on S9, and told S11 to start "once OpenAPI is frozen" — circular, because FastAPI generates OpenAPI *from* implemented handlers. Splitting the contract out lets S11 start for real. S10a also depends on **S15**, because `GET /api/evaluation/*` response schemas cannot be written before S15 defines the metrics.

**Context brief.** Only endpoints the demo path exercises. Auth is a **role-switch stub** — real JWT/bcrypt is S18. Deliberately narrow; the other ~25 TDM endpoints are S18.

**v1.0 addition.** `GET /api/alerts` must return `evidence_class`. The feedback write path — `POST /api/alerts/{id}/feedback` — invokes guardrail logic and is therefore **Claude's, not delegated**, per the plan's own anti-pattern list.

> **v1.1 CORRECTION — the ordering in v1.0 is withdrawn.** It said order by
> `evidence_priority, combined_score DESC`. That predates S7b. The queue's contract order is
> **`db.QUEUE_ORDER_BY` = `queue_priority ASC, combined_score DESC, id ASC`**, and the API must use
> it verbatim rather than restate it. Ordering by `evidence_priority` would ignore Q24 — feedback
> moves an alert between *queue bands*, never across evidence classes — so the endpoint would
> render the re-ranking invisible, which is the one thing the demo exists to show. `evidence_class`
> is still returned; it is reported, not sorted on. Logged as
> [`deviations.md`](../hitl-ids/docs/deviations.md) C13.
>
> **Both score columns are required in the list response**: `detection_score` (immutable, what
> detection produced) and `combined_score` (operational, what feedback moves). The dashboard's
> second score column is the demo's point; an API that returns one number cannot show it.

**Tasks.**
- `GET /api/alerts` (rank, filter, sort, search, paginate)
- `GET /api/alerts/{id}` (flow + signature + ML + SHAP + explanation)
- `POST /api/alerts/{id}/feedback`
- `GET /api/alerts/{id}/score-adjustment`
- `GET /api/alerts/{id}/feedback-history`
- `GET /api/dashboard/summary`
- `POST /api/detection/run`
- `GET /api/audit-log`
- `PUT /api/config/guardrails`
- `GET /api/evaluation/*` (S15)
- OpenAPI published.

**Verify.** `pytest tests/test_api.py` — contract test per endpoint; role stub blocks analyst from `PUT /api/config/guardrails`; **p95 latency < 2s on `GET /api/alerts` and `GET /api/alerts/{id}` (NFR-04)**.

**Exit criteria.** All demo-path endpoints green; OpenAPI generated; NFR-04 measured, not assumed.

**Rollback.** Revert; detection core unaffected.

---

# PHASE 4 — Interface

## S11 — Web shell, role switching, design system

**Deps:** S10 (contract only — may start once OpenAPI is frozen) · **Owner:** delegate (GLM) + Claude review · **Branch:** `feat/s11-shell` · ∥ S15

**Tasks.** App shell, routing, login screen, role switcher (analyst/admin/evaluator), Tailwind tokens, typed API client generated from OpenAPI, loading/error/empty states.

**Verify.** `npm run build` · `npm test` component smoke tests · each role lands on its correct default view (analyst → queue, admin → system status, evaluator → scenario list).

**Exit criteria.** All three shells reachable; API client typed; no `any` in the client.

**Rollback.** Revert branch.

## S12 — Analyst path (deep) ⭐ DEMO CORE

**Deps:** S11 · **Owner:** delegate (components) + **Claude (score-adjustment + guardrail messaging)** · **Branch:** `feat/s12-analyst` · ∥ S13

**Context brief.** The demo's spine, and the only path built to full depth (D6). Deduped, the analyst's 24 use cases collapse to roughly 6 real interactions.

**Tasks.** Ranked queue (sort/filter/search/paginate). Alert detail with four evidence panels — flow details, signature evidence, ML prediction, combined explanation — plus empty states ("no rule matched (ML-only alert)" / "signature-only alert"). Investigation notes. Feedback form, **5 scoring categories** (`confirm_true_positive` +10 · `mark_false_positive` −30 · `mark_expected_activity` −15 · `needs_investigation` 0 · `escalate` +15); `duplicate` is a **queue action** (link to original, suppress from the active queue), not a score change — the documents' "six categories" folds a queue action into the scoring set (`deviations.md` A6). **Score-adjustment visualisation: original → requested Δ → guardrail bound → actual Δ → final.** Feedback history. Dashboard summary with Recharts.

**Verify.** Component tests per panel; **end-to-end: submit false-positive feedback on a critical alert → UI shows the cap → refresh → adjusted score persists.**

**Exit criteria.** Full loop works and survives reload. Guardrail intervention is visible to the user, not silent.

**Rollback.** Revert branch.

## S13 — Admin path (thin)

**Deps:** S11 · **Owner:** delegate + Claude review · **Branch:** `feat/s13-admin` · ∥ S12

**Tasks.** System status (run history, service health). Trigger detection run. Guardrail configuration form with the five settings and validated ranges. Guardrail rejection log. Audit log viewer with filters + CSV export.

**Verify.** Component tests; guardrail form rejects floor ≥ ceiling; audit export downloads.

**Exit criteria.** An admin can trigger a run and inspect what guardrails blocked.

**Rollback.** Revert branch.

## S14 — Evaluator path (thin)

**Deps:** S11, S15 · **Owner:** delegate + Claude review · **Branch:** `feat/s14-evaluator`

**Tasks.** Scenario list + config. Detection metrics (overall, per-class including Infiltration, confusion matrix). Baseline comparison with deltas. Guardrail test results. Export.

**Verify.** Component tests; metrics view renders all 8 classes; comparison renders three-arm results.

**Exit criteria.** Evaluator can run a scenario and read the deltas without touching a terminal.

**Rollback.** Revert branch.

---

# PHASE 5 — Evaluation and demo

## S15 — Three-arm evaluation harness ✅ DONE (changelog v1.16)

**Deps:** S9 · **Owner:** **Claude** · **Branch:** `feat/s15-evaluation` · ∥ S11

> **Landed 2026-09-12.** `packages/evaluation/` + `scripts/run_evaluation.py`, 25 tests.
> Report: [`evaluation-report.md`](../hitl-ids/docs/evaluation-report.md) · method:
> [`evaluation/three-arm/METHOD.md`](../hitl-ids/evaluation/three-arm/METHOD.md).
>
> **Result, as measured.** Detection metrics identical across all three arms, so feedback reordered
> the queue and did not touch the detector. S7b reached **198 untouched true positives** and leaked
> onto **0** alerts outside judged families. **But** it promoted a benign alert from rank 639 to
> **rank 1**, and precision@50 fell 1.000 → 0.980 — the control queue was already perfect
> (2 false positives in 996 flagged alerts), so feedback could only break it. **Arm C is identical
> to arm B**: the pre-registered sequence produced no dismissals, so no guardrail could bind.
> Recorded as measured per the v0.3 exit criterion; it means *this sequence could not test the
> guardrails*, not *the guardrails are unnecessary*.
>
> **Still open, and not to be silently resolved:** the efficiency stress test with a weaker or
> drifting detector (`ranking-and-escalation-design.md` §8), and a second pre-registered rule
> covering the dismissal direction so arm C has power. Both need the project lead's go-ahead —
> changing a rule after seeing its result is what the v0.3 FIX forbids.

**Context brief.** D9. Every headline claim is a delta against a control.

| Run | Feedback | Guardrails | Purpose |
|---|---|---|---|
| A — control | none | on | What the system does unaided |
| B — treatment | scripted | on | The claim being tested |
| C — guardrail probe | same scripted | **off** | What guardrails prevented |

Dataset, model version, rule version and seed are pinned identically across all three — the feedback and the guardrail flag are the only variables. Scripted feedback must cover a **subset**, so effects on untouched similar alerts are measurable.

> **v0.3 FIX — the exit criterion was corrupt.** v0.2 said: *"run C shows ≥ 1 critical suppression that run B prevents (if zero, the scripted sequence is too weak — strengthen it)."* That instructs tuning the experiment until it yields the desired result, inverting D9's own rationale. An examiner asking "how did you choose the feedback sequence?" would get "so the result would appear." **Replaced by pre-registration below.**

**Tasks.**
1. **Pre-register the feedback sequence before any arm runs.** Define it deterministically from a fixed seed — e.g. the 40 highest-scoring alerts by `combined_score`, category assigned from ground truth — and write it to `evaluation_scenarios.feedback_sequence`. It must cover a **subset**, so effects on untouched similar alerts remain measurable.
2. Runner executing all three arms with dataset, model version, rule version and seed pinned identically. The feedback and the `guardrails_active` flag are the **only** variables.
3. Metrics: per-class precision/recall/F1/FPR/FNR; ΔFP in top-50; Δ mean reciprocal rank of true positives; critical preservation rate; guardrail cap/reject counts. **Report `signature_override` preservation separately** — v1.0's core claim is that these survive feedback (invariant I3).
4. Baseline comparison writer; report export.

**Verify.** `pytest tests/test_evaluation.py` — **re-running a scenario reproduces identical metrics (NFR-05)**; the pre-registered sequence is byte-identical across runs; run C's suppression count is recorded **as measured**.

**Exit criteria.** Three arms reproducible. Deltas computed. **Run C's suppression count is reported as-measured — zero is a publishable result** meaning the guardrails did not bind on this sequence. Record it; do not re-sample. The *guarantee* that the floor binds belongs in S7's unit tests, not in the evaluation.

**Rollback.** Read-only over existing runs; safe to re-run.

## S16 — Demo assembly and rehearsal ⭐ GATE

**Deps:** S12, S13, S14 · **Owner:** Claude · **Branch:** `feat/s16-demo`

**Tasks.** Seed script producing a known-good demo DB from scratch. Written demo narrative:

> login → queue → **open `AL-00478`** (`ml_only`, 99.89, a Tier 2 candidate) → read the evidence panels: no rule matched, the model calls it a **Web Attack**, and TreeSHAP shows which features drove that → **ground truth says benign** → the analyst dismisses it as a false positive → watch the −30 cap apply and the queue re-rank → open `AL-03086` (36.94, bottom band), the attempted Web Attack **both detectors missed**, and confirm it → watch it climb → show that four *similar* alerts nobody touched moved with it (S7b) → refresh (persistence holds) → admin views the guardrail log → evaluator shows the three-arm deltas, **including the one that went the wrong way**

> **v1.1 CHANGE — the centrepiece moved a second time, because v1.0's own stop-condition fired.**
> v0.2 opened on a *fused* alert with both detectors agreeing; v1.0 replaced it with the top
> `signature_override` alert and added the precondition *"if S3's corrected dataset yields zero, the
> demo narrative breaks — stop and re-plan"*. **The corrected dataset yields exactly zero**
> (`signature_only = 0`), so that condition has triggered and the v1.0 narrative cannot be performed.
> v1.1: the 8 alert ids it named (~~`AL-0509 … AL-0574`~~) are from the frozen *uncorrected*
> fixture and must not be used as demo data.
>
> The replacement is the case that does exist, and it is a better demonstration: **the model is
> confidently wrong, a human overrules it, and the correction spreads to the alerts like it.** That
> is the thesis — a human in the loop — rather than two detectors nodding at each other.
> Logged as [`deviations.md`](../hitl-ids/docs/deviations.md) E4.

**Demo-data precondition (v1.1).** The seed script must guarantee, in the corrected demo sample:
one high-scoring `ml_only` **false positive** (`AL-00478`), one attack **both detectors missed**
(`AL-03086`), and a **family with untouched members** so S7b's spread is visible. All three are
present in `data/demo.db` as built by `scripts/run_detection.py`. **Do not curate a slice where both
detectors fire** — that is on the anti-pattern list and would conceal real recall.

**Honesty requirement (v1.1).** The evaluator view must show S15's result **as measured**, including
that precision@50 fell from 1.000 to 0.980 under feedback and that a benign alert reached rank 1.
Presenting only the favourable deltas would fail the same scrutiny the v0.3 FIX was written to
prevent. See [`evaluation-report.md`](../hitl-ids/docs/evaluation-report.md).

Rehearse end-to-end from a clean clone. Record known limitations honestly.

**Verify.** Clean clone → seed → run → full narrative executes with no manual DB fixes.

**Exit criteria.** **This is the "presentable demo" gate. S17/S18 do not start until this passes.**

**Rollback.** n/a — assembly only.

---

# PHASE 6 — Post-demo

## S17 — Prefix flow-exporter module

**Deps:** S16 · **Owner:** Claude · **Branch:** `feat/s17-exporter` · ∥ S18

**Context brief.** D7. [GintsEngelen/CICFlowMeter](https://github.com/GintsEngelen/CICFlowMeter) — the same tool that produced the corrected dataset (D1), which eliminates train/serve skew. It is a **flow exporter, not an IDS**; the signature engine remains the IDS logic. Java + Npcap on Windows is painful — run offline over PCAP via WSL/Docker.

**Tasks.** `ExporterSource` implementing `FlowSource` from S3. PCAP → CIC features → pipeline. Column-name and dtype reconciliation against `feature-columns.json`. Documented setup. ~~**Optional:** Suricata as a third evidence stream.~~ **v1.1: REJECTED** — Suricata cannot emit CIC flow features, so it cannot feed the model (`deviations.md` D-1). Do not re-propose.

**Verify.** Features from the exporter on a sample PCAP match the training schema exactly; a flow processed end-to-end produces an alert.

**Exit criteria.** Live-ish flows enter the pipeline with zero downstream change. **If schema reconciliation fails, stop and report — do not silently coerce columns.**

**Rollback.** `CsvReplaySource` remains default; exporter is opt-in.

## S18 — Full backend (D3 complete)

**Deps:** S16 · **Owner:** Claude + delegate · **Branch:** `feat/s18-backend` · ∥ S17

**Tasks.** SQLite → PostgreSQL (schema was written for it in S2). Real JWT + bcrypt + RBAC replacing the S10 stub. Remaining TDM endpoints: user management, rule manager, model version management, fusion weight config, bulk feedback, exports, notifications. Re-verify append-only triggers under Postgres.

**Verify.** Full API contract suite; RBAC matrix test per role per endpoint; audit immutability re-proven on Postgres.

**Exit criteria.** Feature parity with the TDM's specified surface.

**Rollback.** Postgres migration is reversible while SQLite artifacts are retained.

---

## Invariants — checked after every step

1. `pytest` green; `ruff check` clean; `npm run build` succeeds.
2. **No label leakage** — `attackType`/`groundTruth` never reach a detector.
3. **Alert count == signature scope** — no phantom alerts.
4. **Audit is append-only** — `UPDATE`/`DELETE` raise.
5. **Guardrails hold** — no critical alert below floor 70 under any feedback sequence.
6. **Determinism** — identical inputs produce identical scores (NFR-05), verified at *run* level (S9) **and at evaluation level (S15: two runs of a scenario produce byte-identical metrics)**.
7. **Nothing outside `hitl-ids/` and `plans/` is modified** — the research record is frozen.
8. **(v1.0)** **No `signature_override` alert ranks below any `ml_only` alert** (I5). **(v1.1: vacuous but retained — the corrected dataset produces no such alert. Note the queue *bands* reuse the evidence-class names, so an alert may sit in a band called `signature_override` while its `evidence_class` is `ml_only`; I5 is about the evidence class.)**
9. **(v1.0)** **Frozen fixtures are never regenerated** — `tests/fixtures/legacy/` is immutable.
10. **(v1.0)** **Signature precision ≥ 0.9** once S4b lands. A low-precision "high-confidence oracle" is a contradiction that destroys the layer's purpose.

## Anti-patterns to reject

- Transliterating Node to Python instead of reimplementing against frozen fixtures.
- Delegating fusion or guardrail maths — plausible-looking wrong answers are costly and hard to spot. **This includes `POST /api/alerts/{id}/feedback`, which invokes them.**
- Building evaluation before S4 — metrics over a 6-class model are invalid.
- Computing SHAP on demand — blows NFR-04.
- Conflating guardrail caps with exception trust-gate rejections in metrics.
- Accepting a worker's self-report without reading its files. **Research is never delegated at all** — GLM fabricated 29 citations it never fetched.
- Adding endpoints "while we're here" — S10 is deliberately narrow.
- **(v1.0) Averaging scores from different evidence classes.** A precision-1.000 rule's 60 is not "worse than" an ML probability of 85; they are not commensurable. This error killed the weighted sum *and* CEF's own first draft.
- **(v1.0) Tuning an experiment until it produces the desired result.** Report as measured.
- **(v1.0) Ignoring `dashboard/src`.** Freezing it as a research record does not mean refusing to *read* it — 2,368 lines of working components and typed models are a legitimate source for S11/S12. Port structure; never modify the originals.

## Plan mutation protocol

Steps may be split, inserted, reordered or abandoned. Record the change and its reason in
[`hitl-ids/docs/deviations.md`](../hitl-ids/docs/deviations.md) — **created 2026-09-12; it had been
mandated since v0.1 and never existed**, which is how v1.0's withdrawn claims survived in this file
for eleven changelog versions. **S2 is the exception:** after S9 consumes it, schema changes require
a migration path, not an edit.

**And update the *Step status* table above in the same commit that finishes a step.**
`tests/test_plan_sync.py` fails if this plan, `HANDOVER.md` and `plan-changelog.md` disagree about
which steps are done — the drift that produced v1.1 is now a test failure rather than a discovery.
