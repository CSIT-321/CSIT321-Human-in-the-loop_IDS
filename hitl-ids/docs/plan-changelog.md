# Plan Changelog

A versioned record of every change to the project plan, with the evidence that forced it.

**Read this file before the plan itself.** The plan states what we are building; this file states
what we *stopped* believing, and why. Entries are append-only — superseded reasoning is marked
withdrawn, never deleted, because a rejected option that is silently removed gets re-proposed.

Conventions: `ADD` new commitment · `CHG` changed commitment · `DEL` withdrawn commitment ·
`FIX` correction of an error in a previous version.

---

## v0.1 — Inherited baseline (as of 2026-09-10, before review)

The plan implied by the approved documents (PRD, URS, TDM) plus four weeks of implementation.
Never written down as a plan; reconstructed here so later changes have a baseline.

| Commitment | Source |
|---|---|
| Dataset: CICIDS2017 | PRD §6.4, URS Constraint 3 |
| Hybrid detection: signature rules + XGBoost, fused by weighted sum | TDM §6.2.7 |
| `Combined = (Sig_Severity × W_sig + ML_Prob × W_ml) × 100`, weights 0.50/0.50 | TDM §6.2.7 |
| "Signature + ML agreement is the strongest evidence case" | PRD §1.3.3 |
| Stack: React + Vite + Tailwind + Recharts / FastAPI / PostgreSQL | PRD §6.1–6.3 |
| 3 roles, 48 use cases, 13 tables, ~40 endpoints | URS §3, TDM §3.3.3, §7.4 |
| Guardrails: −30 cap, floor 70, critical ≥ 80, exception 3×/60% | PRD §3.4, TDM §6.2.8 |
| 14-week Scrum schedule, 6 members in 3 pairs | PRD §5, §8 |

**Known state of the code at this point:** CSE-CIC-IDS2018 (not 2017), no backend, no database,
no authentication, Node.js detection engines, React dashboard reading static JSON, 6-class model.

---

## v0.2 — Post-grilling (2026-09-10)

Three rounds of structured interrogation resolved the documents-vs-code divergence. Ten decisions
locked (D1–D10 in the plan). Produced `plans/hitl-ids-demo-build.md` — 18 dependency-ordered
steps, no dates.

| | Change | Rationale |
|---|---|---|
| CHG | Dataset → **CSE-CIC-IDS2018**, then → **corrected** release (Engelen et al., IEEE CNS 2022) | Code was weeks ahead on 2018; the corrected release costs one retrain and pre-empts dataset-validity challenge |
| CHG | Documents become **reference-only**, not amended | User decision; deviations logged instead |
| ADD | Retrain to **7 classes incl. Infiltration** | 83/1000 demo rows unpredictable by the 6-class model |
| CHG | Backend → batch detection writes SQLite; minimal API for the demo path only | Demo-first; grows to full FastAPI without schema rewrite |
| CHG | Detection logic → **Python**; Node engines become the specification | Single-language pipeline, as the PRD's own rationale demands |
| ADD | New tree `hitl-ids/`; `stage-*/` frozen as research record | User decision |
| CHG | Prefix module → **flow exporter**, post-demo. Suricata **rejected** | Suricata emits flow totals, not the ~79 CICFlowMeter features the model consumes |
| ADD | SHAP precomputed top-5 at detection time | Protects the ~2 s NFR-04 budget |
| CHG | Evaluation → **three seeded arms** (control / treatment / guardrails-off) | Two arms cannot demonstrate what the guardrails prevented |
| DEL | 14-week schedule, dates, team allocation — **withdrawn** | User: dependency ordering only; workplan is user + Claude + delegated workers |

---

## v0.3 — Post-adversarial-review (2026-09-10)

An independent adversarial review of v0.2 returned 28 findings (5 critical). All were verified
against source before acceptance.

| # | Finding | Evidence verified |
|---|---|---|
| FIX | **S6's golden test was impossible.** The plan demanded the TDM weighted formula *and* a byte-match against `fusion-engine.js`, which implements no weighted sum — it is an 8-branch decision tree with `+10`/`+5`/`−10` adjustments | `grep` for weights across 667 lines returns only `weightedF1` (an evaluation metric). Severity map is `Low:40 Medium:60 High:80 Critical:95` |
| FIX | **Critical threshold was wrong.** Plan said ≥ 80; code bands Critical at **≥ 90** | `getFusionConfidenceLevel` thresholds `[90, 70, 40]` |
| FIX | **S2 omitted four tables** later steps write to: `ml_models`, `evaluation_scenarios`, `users`, `signature_rules` — and S2 was declared expensive to change after S9 | S4's rollback names `ml_models.status`; `audit_log.actor_id` FKs `users` |
| FIX | **S5 depended on S3**, so a cold agent would golden-test the ported engine against the *new* dataset | S5 needs a frozen fixture, not new data → dependency changed to S2 only |
| FIX | **Missing edge S15 → S10**, invalidating the `S15 ∥ S11` parallelism claim; "start once OpenAPI is frozen" was circular since FastAPI *generates* OpenAPI from implemented handlers | S10's endpoint list contains `GET /api/evaluation/*`, which S15 defines |
| FIX | **S15's exit criterion instructed tuning the experiment until it produced the desired result** ("if zero, strengthen the sequence") | Inverted D9's own rationale; replaced by pre-registration of the feedback sequence |
| ADD | Legacy fixtures frozen to `hitl-ids/tests/fixtures/legacy/` (8 files) | Done — prevents the golden tests dissolving when the dataset changes |
| FIX | Third guardrail `infiltration_floor_75` had been silently dropped from the plan | `feedback-engine.js:65-69` |
| FIX | Plan listed 6 feedback categories; the engine implements 5 (`duplicate` is new) | `feedback-engine.js:81-112` |
| FIX | S7's flagship determinism property test **cannot fail** — a pure function of two immutable inputs | Real determinism check is S9's same-seed run |

---

## v1.0 — Evidence-driven redirection (2026-09-11)

Notebooks `01`–`03` were built to test v0.3's assumptions against the actual data. They
invalidated the project's central technical claim. This is the largest change so far.

### The evidence

| Finding | Value | Notebook |
|---|---|---|
| Signature engine recall | **0.016** — 8 of 500 malicious flows | 01 |
| Signature engine precision | **0.533** — 7 of 15 hits are benign | 01 |
| Rules that never fire | **5 of 7** (FTP, DoS, DDoS, Botnet, Infiltration) | 01 |
| Alerts with **both** signature and ML evidence | **0** | 01 |
| `SIG-WEB-ATTACK-FLOW` precision | **0.000** — all 4 hits benign | 02 |
| Best achievable precision for DoS/DDoS/Botnet/Infiltration on the 17 observable features | **0.14 – 0.37** | 02 |
| Malicious flows caught by ML only / signature only / **both** | 403 / 8 / **0** | 02 |

### The changes

| | Change | Rationale |
|---|---|---|
| DEL | "Signature + ML agreement is the strongest evidence case" — **withdrawn** | Occurs **zero** times. No weighting can create it (notebook 01 F7: ρ = 1.0000 across all weight settings — the weights rescale two *disjoint* populations) |
| DEL | Weighted-sum fusion (TDM §6.2.7) — **withdrawn** | The two scores are not commensurable. Notebook 03's weight sweep is a see-saw: at `W_sig ≥ 0.7` signature alerts reach rank 4 only by crushing all 403 correct ML detections |
| ADD | **Complementary Evidence Fusion (CEF)** — evidence classes `corroborated` / `signature_override` / `ml_only` / `none`; signature hits override rather than average | Notebook 03. Preserves the complementary signal that averaging destroys |
| ADD | **Queue ordering is part of the fusion contract**: `ORDER BY evidence_priority, score DESC` | See FIX below — a review flag alone was not enough |
| FIX | **CEF's own first design failed.** Flagging `signature_override` for review and sorting that queue by score ranked the 8 key detections **#414 of 417 — worse than the weighted sum**. Cause: comparing a precision-1.000 rule's score of 60 against an ML probability of 85 is the original error in a new costume | Fixed by ordering on evidence class first: the 8 move to positions **1–8**. Invariant **I5** added to prevent regression. The failed attempt is preserved in notebook 03 |
| CHG | Project's central claim → **complementary coverage**, not agreement | The retuned SSH rule catches 8 real brute-force attacks the ML model labels Benign at **0.75–0.80 confidence**. A stronger and demonstrably true claim |
| ADD | New step **S4b — signature rule tuning** (after S3, before fusion) | Notebook 02 proves the SSH rule reaches **precision 1.000** at any threshold in 20–110 (currently `min: 10`) with no loss of true positives |
| CHG | Retire rather than tune the 5 inert rules | Their best single-feature precision is 0.14–0.37 — unusable for a high-precision posture |
| CHG | Fusion step becomes a **re-specification**, not a port; golden test deleted, replaced by CEF invariants I1–I5 | Consequence of the v0.3 FIX plus CEF |
| CHG | Demo centrepiece → *"the signature layer caught an attack the model confidently called benign, and the human decides"* | The former centrepiece has no instances in the data |
| ADD | `hitl-ids/scripts/download_dataset.py` for the corrected dataset | **BLOCKED** — no Kaggle credentials on this machine. Run `kaggle auth login`, then re-run |

### Rejected alternatives (recorded so they are not re-proposed)

- **Retune the fusion weights to de-emphasise signature.** Mathematically inert while
  co-occurrence is zero — notebook 01 F7. It would hide the problem, not fix it.
- **Demo on a curated slice where both detectors fire.** No such slice exists (co-occurrence is
  zero), and concealing 1.6% recall would not survive examiner questioning.
- **Keep the rules as-is and reframe them as deliberately high-precision.** The *posture* was
  adopted; the claim as-stated could not be, because precision was 0.533, not high. It had to be
  earned first, which is what S4b does.

---

## v1.1 — Corrected dataset acquired (2026-09-11)

`CSECICIDS2018_improved.zip` (10.43 GB, 10 capture days, 36.04 GB uncompressed) was downloaded
from the authors' own server and a full label scan run over all **63,195,145 flows**. The
corrected data changes the class taxonomy, not just the numbers.

### Findings

| Finding | Evidence |
|---|---|
| **Infiltration was never one class.** 89,374 of 89,691 Infiltration flows (99.6%) are `Infiltration - NMAP Portscan`. True infiltration is 317 flows in 63M | This is *why* Infiltration is notorious as unlearnable — the label conflates a port scan with post-compromise activity |
| **FTP brute force never succeeded.** All 298,874 FTP-BruteForce flows are marked `Attempted`; zero successful | Makes the attempted/benign decision worth 76% of the Brute Force class |
| **Web Attack barely exists.** 283 successful flows in 63.2M (0.0004%) | The old 1,000-row sample contained 83 of them — **29% of the entire class population** |
| Overall imbalance | 93.9% benign / 6.1% attack |
| **Schema changed: 91 columns, not 79** | Six new: `Fwd RST Flags`, `Bwd RST Flags`, `ICMP Code`, `ICMP Type`, `Total TCP Flow Time`, `Attempted Category` |
| `CWE Flag Count` → `CWR Flag Count` | The original misspelled the TCP *Congestion Window Reduced* flag. The trained model carries the typo |

### Changes

| | Change | Rationale |
|---|---|---|
| ADD | `scripts/column_map.json` — **all 78/78** model features resolve to the corrected schema, verified, no duplicate targets | Closes the column-name seam the adversarial review flagged as unowned. A silent mismatch here is train/serve skew |
| CHG | **Q18: attempted attacks are MALICIOUS**, flagged via `is_attempted` | A failed brute force is still an attack a SOC must see; calling it benign would make the IDS "correct" to ignore an in-progress intrusion. Also preserves FTP as a class. The flag keeps the sensitivity analysis available |
| ADD | **Q19: `Port Scan` becomes an 8th class**, split out of Infiltration | Keeping the portscan inside Infiltration is the mislabelling that broke the class. Splitting yields a learnable 89,374-flow class and an honest "true Infiltration has only 317 examples — too few to model" |
| CHG | **Q20: two disjoint datasets** — `train_sample.csv` (per-class caps) and `demo_sample.csv` (~5k at 80/20) | The old 1,000-row 50/50 sample was 15× more attack-dense than reality. Separating the two lets the demo look alive without the training set inheriting a fake prior |
| ADD | `scripts/scan_labels.py`, `scripts/build_samples.py` | Streaming from the zip; 36 GB never written to disk. Fixed seed; leakage assertion between demo and train |
| CHG | Model retrain target is now **8 classes**, not 7 | Consequence of Q19 |

### Consequences still to land

- Notebooks 01–03 must be re-run against the corrected data; **several figures will move.**
- The 1.6% signature recall and the precision-1.000 SSH fix were measured on the *old* sample and are provisional until re-derived.
- `Attempted Category` is **label metadata and must never reach a detector** — a label-leakage vector that did not exist before.

---

## v1.2 — Corrected data reverses v1.0's premise (2026-09-11)

The 8-class model was trained on `train_sample.csv` and the findings re-measured on the disjoint
`demo_sample.csv`. **Both empirical pillars of v1.0 failed.**

### The reversal

| Measure | Old sample (v1.0 basis) | Corrected sample |
|---|---:|---:|
| Signature precision | 0.533 | **0.871** |
| Signature recall | 0.016 | **0.054** |
| Caught by ML only | 403 | 940 |
| **Caught by signature only** | **8** | **0** |
| **Caught by both** | **0** | **54** |
| Missed by both | 89 | 6 |

| | Change | Rationale |
|---|---|---|
| DEL | **F5 "zero co-occurrence" — withdrawn.** Agreement occurs 54 times on corrected data | Was measured on the uncorrected sample |
| DEL | **F8 "complementary coverage" — withdrawn.** `signature_only = 0`; the signature layer is fully subsumed by the ML model | The 8 brute-force flows the old model mislabelled are caught by the new one |
| DEL | **CEF's `signature_override` evidence class has zero instances**, so the v1.0 demo centrepiece does not exist on this data | Notebook 03's design needs rebuilding on the new footing |
| ADD | 8-class model trained: macro F1 **0.9882**, weighted F1 0.9997 (`models/training-metrics.json`) | Replaces the 6-class model that could not emit Infiltration |
| ADD | **Port-shortcut hypothesis tested and REJECTED.** Removing `Dst Port` + `Protocol` costs only −0.0011 macro F1 (`models/ablation-port.json`) | Each attack class was generated by one tool with fixed config, so the flow *shape* is a near-constant fingerprint. The 0.99 F1 is a testbed artefact and will not transfer to real traffic — state this in the report |

### Cause, stated plainly

The reversal is mostly the **new model being far stronger**, not the rules improving. The old
6-class model was trained on mislabelled data and called SSH brute force "Benign" at 0.78
confidence; the corrected 8-class model catches those flows easily. A strong classifier subsumes
weak rules. This also partially vindicates the original PRD claim that v1.0 withdrew — agreement
does occur.

**Process error worth recording:** v1.0's redesign was built on the uncorrected sample while
knowing a corrected one was pending. The frozen fixtures meant nothing was lost, but the design
work was premature. Empirical premises should be established on final data before a design is
committed to.

### Open question this raises

If the signature layer contributes **no unique detections**, what justifies the hybrid? Options
under test: (b) retune against corrected data to find genuine complementarity — **in progress,
delegated**; falling back to (a) reposition the signature layer as the *explainability* half
(a matched rule with a stated condition is verifiable by a human; SHAP values are only
suggestive), making the hybrid's contribution **trust rather than recall**.

---

## v1.3 — Retuning closed on evidence; signature layer repositioned (2026-09-11)

Option (b) — retune the rules against corrected data to recover complementarity — was tested and
**closed negative**. Option (a) adopted.

### (b) Retuning: works, but adds no coverage

Threshold search over each rule's numeric clauses, both directions, requiring precision ≥ 0.90.
Delegated to a DeepSeek worker; **every figure independently re-verified** before acceptance.

| Rule | Tuned threshold | Fires | Precision | Recall |
|---|---|---:|---:|---:|
| `SIG-FTP-BRUTE-FORCE` | `totalFwdPackets ≥ 1` (with TCP + port 21) | 146 | **1.000** | 0.73 |
| `SIG-SSH-BRUTE-FORCE` | `flowPacketsPerSecond ≥ 10.67` | 54 | **1.000** | 0.27 |

Five rules **cannot** reach precision 0.90 — hard ceilings: DoS **0.000**, Botnet **0.000**,
DDoS 0.342, Infiltration 0.250, Web Attack 0.784. They are **retired, not tuned**.

Coverage with the retuned set: `ml_only 794 · signature_only **0** · both 200 · missed_by_both 6`.

> Signature precision rose 0.871 → **1.000** and recall 5.4% → **20%**. Genuine improvement — but
> `signature_only` is still **0**. Retuning made the layer *good*, not *complementary*.

### (a) The repositioning

| | Change | Rationale |
|---|---|---|
| CHG | Signature layer's purpose → **trust and explainability**, not coverage | When it fires it is right 100% of the time, and a human can verify *why*. `SSH on port 22, >10.67 pkt/s, ≥10 fwd packets, <5s` is checkable against the flow record; `Bwd Packet Length Min contributed +0.31` is not — SHAP explains the model, not the traffic |
| CHG | Evidence classes become a **triage-effort allocation** | `corroborated` (200) fast-track · `ml_only` (794) **highest human value**, no checkable reason · `missed_by_both` (6) feeds rule development |
| CHG | Project claim → *the hybrid does not detect more; it tells the analyst where attention is worth spending* | True on this data, unlike both the PRD's "agreement is strongest evidence" and v1.0's "complementary coverage" |
| DEL | `signature_override` retired as a live case (retained as a defensive branch) | Zero instances |
| ADD | `notebooks/04_corrected_findings.ipynb` — full decision record, executes clean | Showcase artifact |
| ADD | Supersession banners on notebooks 01–03 | A reader must not take reversed conclusions at face value; the notebooks are kept unchanged as the record |

### Process notes

- **A delegated worker was right and my verification was wrong.** My first check applied each
  tuned threshold in isolation, dropping the rule's other clauses, so `totalFwdPackets ≥ 1`
  appeared to match all 4,999 rows and I rejected the result. Re-run correctly, the worker's
  figures matched exactly. Verification code needs the same scrutiny as the thing it verifies.
- Rule thresholds were tuned **on the demo sample**; a clean re-test on a held-out slice is
  outstanding and is a real risk of overfitting the thresholds.

---

## v1.4 — Collaborator merge; their model invalidated, ours is truth (2026-09-11)

A collaborator force-pushed 14 commits to `origin/main` (rewriting history past our branch base).
Merged into `feat/corrected-dataset-and-findings`; **our frozen fixtures were unaffected**, which
is exactly why they were frozen.

### What they contributed

| Asset | Lines | Value to us |
|---|---:|---|
| `stage-3/core/ml_inference.py` | 671 | Python inference + **native TreeSHAP with additivity verification** |
| `stage-3/tests/test_ml_inference.py` | 624 | Behavioural spec |
| `stage-5/config/adaptation-config.json` | 94 | Similarity weights, graduated adjustments, guardrails |
| `stage-5/core/similarity-engine.js` | 159 | Weighted similar-alert matching |
| `stage-5/core/feedback-aggregation-engine.js` | 451 | Agreement-gated aggregation |

### Two independent confirmations of our analysis

- **`duplicate` is a workflow action, not a scoring one.** Their config places it in
  `workflowFeedbackTypes`, never `learningFeedbackTypes` — matching the conclusion drawn from
  URS UC-SA-15 before their code was seen.
- **`infiltrationFloor: 75` retained**, confirming the guardrail our plan had dropped.

### Decisions

| | Change | Rationale |
|---|---|---|
| CHG | **Their 6-class model and all its outputs are INVALIDATED.** Our corrected 8-class model is the single source of truth | Theirs is trained on the uncorrected dataset and cannot emit `Infiltration` or `Port Scan` |
| ADD | `packages/detection/ml/inference.py` — vendored, adapted copy of their module | Upstream **hard-asserts 78 features**; ours has 82, so it rejected our model outright |
| FIX | Extended the leakage guard with `Attempted Category`, `attack_class`, `is_attempted` | `Attempted Category` states whether an attack succeeded — a leakage vector that did not exist before the corrected release, so the upstream guard predates it |
| ADD | `models/preprocessing-config.json` (8-class, 82 features) | Required by their loader; supersedes the 6-class version |
| ADD | `scripts/run_ml_inference.py` + `data/processed/ml-explainability-summary.json` | **5,000/5,000 alerts carry a TreeSHAP explanation with verified additivity** (max deviation 1.13e-5, tolerance 1e-4). **NFR-01 is now satisfied on corrected data.** |

Adaptations are marked `ADAPTED:` inline; their TreeSHAP logic, schema validation and provenance
hashing are preserved unchanged. Intent is that our tree eventually supersedes `stage-3/`/`stage-5/`.

**Coordination risk:** the collaborator is actively developing in `stage-3/` and `stage-5/`, which
our plan declared frozen. That convention now conflicts with reality and needs agreeing with them.

---

## v1.5 — S2 data contracts landed (2026-09-11)

Plan step **S2** (keystone) implemented on branch `feat/s2-contracts`: `packages/contracts/`
(`models.py`, `schema.sql`, `db.py`) and `tests/test_contracts.py`. **51 tests pass, 0 skipped** —
including all **5,000 real TreeSHAP records** validating against `MlPrediction`, one of them
persisting through `alerts.shap_attributions` losslessly.

### Departures from the TDM (§7) — every one is marked `DEVIATION` inline

| | Change | Rationale |
|---|---|---|
| ADD | `alerts.evidence_class`, `alerts.evidence_priority` | Plan v1.0 — the queue orders by them |
| ADD | `alerts.detection_score` | The immutable score detection produced. `combined_score` becomes the operational score feedback moves. The engine measures caps and floors against the former (`detectionScore` vs `operationalPriorityScore`); without it the control-vs-treatment comparison (D9) cannot be reconstructed from the database |
| ADD | `alerts.requires_review` | Plan S6 task list; the engine's `forceReview` (S7) |
| ADD | `signature_rules.attack_category`, `signature_rules.rationale` | Corroboration needs the class a rule asserts; the rationale is the human-checkable "why" (v1.3 trust repositioning) |
| CHG | `signature_rules`: `UNIQUE (rule_id)` → `UNIQUE (rule_id, version)` | A detection run must replay against the `rule_set_version` it recorded |
| CHG | `signature_rules.rule_id` 20 → 50 chars | **Caught by a test:** the frozen legacy id `SIG-DOS-HIGH-RATE-FLOW` is 22 chars. Renaming would break traceability to the fixtures and `retune_results.json` |
| ADD | `detection_runs.seed` | S9's `run_detection(..., seed)` must be reproducible from the row |
| ADD | `flow_data.source_record_id` | The only join key to ground truth, which is kept **out of the schema entirely** (label leakage) |
| CHG | `feedback_events.category` CHECK → the engine's five | Resolved in HANDOVER §7. `duplicate` is recorded in `alerts.is_duplicate_of` |
| ADD | `feedback_events` is append-only (triggers) | The TDM's `amended_from_id` already models amendment as a new row |
| ADD | `INSERT OR REPLACE` guard trigger on both append-only tables | SQLite REPLACE deletes the conflicting row **without firing DELETE triggers** unless `recursive_triggers` is on. The TDM's UPDATE/DELETE trigger pair alone leaves the audit log overwritable. A test proves the guard holds on a raw connection with no pragmas |
| ADD | FKs `detection_runs.model_version`, `evaluation_scenarios.model_version` → `ml_models.version` | Every recorded model version resolves |
| CHG | Nullability tightened on structural FKs (`alerts.run_id`, `flow_data.alert_id`, …) | An alert without a run is meaningless |
| KEEP | `detection_runs.fusion_weights` name | Holds the fusion configuration snapshot. Weighted-sum fusion stays rejected; the name is kept for the migration |
| DEFER | `notifications` (the 13th table) | With the full backend, S18 |

### Guardrail seed

TDM five (`max_feedback_reduction 30`, `critical_alert_floor 70`, `critical_alert_threshold 80`,
`learned_exception_min_occurrences 3`, `learned_exception_min_confidence 60`) +
`infiltration_alert_floor 75` + from `adaptation-config.json`: `max_feedback_increase 20`,
`review_threshold 70`, `high_risk_threshold 70`, aggregation `3 / 0.67 / 0.80`. A test pins these
to the collaborator's file. The graduated adjustments (FP −10/−25 …) are feedback maths and belong
to S7, not `guardrail_config`.

### What the contract enforces, and what it leaves to S6

Enforced in Pydantic **and** again as DB `CHECK`s, so raw-SQL writers cannot bypass them:
`evidence_class ∈ {corroborated, signature_override}` ⇔ a signature matched; `corroborated` and
`ml_only` ⇒ a non-Benign ML class. These are necessary conditions only — how classes and
priorities are *assigned* is S6's re-specification. The queue order is fixed as
`db.QUEUE_ORDER_BY = evidence_priority ASC, combined_score DESC, id ASC`.

Also enforced: flow features refuse every label field (`LEAKAGE_FIELDS`, pinned as a superset of
the inference guard); an `available` SHAP explanation must carry a passed additivity check
(NFR-01); non-finite floats are refused because JSON columns cannot store them.

### Process notes

- **My own verification constant was wrong.** I hand-counted 19 foreign keys; the schema has 17.
  The test now asserts the explicit edge set rather than a count, so a mismatch names the edge.
- **S1 remains partial.** S2 added only the `pyproject.toml` pytest/ruff slice it needed. Still
  outstanding (delegable): Vite scaffold, `README.md`, and `ruff` itself, which is not installed.
- **Open for S5:** legacy rule conditions key on camelCase (`flowPacketsPerSecond`) while corrected
  flows use CIC names (`Flow Packets/s`). The tuned rule file must choose one namespace and map the other.

---

## v1.6 — S5 + S4b landed: engine ported, rule set written, held-out figures reproduced (2026-09-11)

Branch `feat/s5-signature`. `feat/s2-contracts` was pushed to `origin` as a view-only progress
branch for collaborators, carrying the 5,000-row demo sample and `data/README.md`.

| | Change | Evidence |
|---|---|---|
| ADD | `packages/detection/signature/engine.py` — Python port of `stage-2/core/signature-engine.js`. **Delegated** to a DeepSeek worker; accepted on reading its code and re-running every test | Golden test: all **1,000** legacy records reproduce the JS verdict, rule id and readable conditions exactly |
| ADD | `observable.py` — the single projection from corrected-release columns to the 16 camelCase fields rules test | Identical on all 5,000 demo rows to `demo_detection_input.csv`, the view S4b was tuned on |
| DEC | Rules stay in the observable (camelCase) namespace. Closes the open question in v1.5 | The thresholds were tuned and validated there; translating them to CIC names would re-open verified figures |
| ADD | `rules/rule-set-s4b-1.json`, written by `scripts/write_rule_set.py` | FTP and SSH enabled with their **full** retuned conditions; the other five retired (`enabled: false`), not deleted. The SSH threshold is exactly **10.66689** — the handover's 10.67 was rounded |
| ADD | `scripts/validate_rule_set.py` — the held-out re-test, now committed and run through the production engine | The original held-out run was ad hoc and never committed |
| CHG | The engine returns **every** match (`match_all`); the JS engine kept only the first | `match_all(...)[0]` equals the JS verdict; the contract stores a list |
| KEEP | Four deliberate divergences from the JS, marked `DIVERGENCE` in `engine.py` | Each makes text or non-finite values fail a threshold instead of silently passing it |

### Held-out figures: reproduced, with the scoring made explicit

Through the production engine on `train_sample.csv` (250,655 rows): **30,025 hits**, exactly the
handover's count. Two scorings are now reported side by side:

| Scoring | Precision | Recall | Wrong |
|---|---:|---:|---:|
| **Malicious-correct** — the flow is any attack (the handover's figures) | **0.9999** | **0.1993** | 2 |
| **Class-correct** — the flow's class is the rule's class (v1.3's definition) | **0.9992** | **0.1991** | 25 |

| Rule | True class of the misattributed flows | Flows |
|---|---|---:|
| `SIG-FTP-BRUTE-FORCE` | Port Scan | 23 |
| `SIG-SSH-BRUTE-FORCE` | Benign | 2 |

The handover's figures stand; they were measured under the any-attack scoring without saying so.

**Finding — an input for S6.** The FTP rule's tuned clause (`totalFwdPackets ≥ 1`) is loose enough
that NMAP probes of TCP/21 satisfy it. Those flows are attacks, so this is not a false alarm, but
it is a wrong *label* — and the signature layer's value is a checkable reason (v1.3). S6 must not
count a signature whose class disagrees with the model's as corroboration. The collaborator's
engine already has the hook: `signature_ml_disagreement_review_preserved`.

Every class-correct FTP hit (22,797) is an attempted attack, consistent with v1.1's finding that
FTP brute force never succeeded.

### S2 fix — timestamps now sort as text

Found while specifying S8. The contract stored timestamps as variable-width ISO text: Pydantic
writes `12:00:00Z` for a whole second but `12:00:00.5Z` otherwise, and the database default wrote
three decimals. As text, `12:00:00.5Z` sorts **before** `12:00:00Z`, so every `created_at` range
query and the TDM's `created_at` indexes would have ordered events wrongly.

| | Change |
|---|---|
| FIX | One encoding, `db.format_timestamp`: fixed-width UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`; the schema's column defaults emit the same shape |
| FIX | Timestamps without a timezone are refused (`AwareDatetime`) — the encoder cannot place them on UTC honestly |

Caught before S9 consumed the schema, so an edit rather than a migration. Proven by a test that
mixes whole-second, fractional and database-default timestamps and asserts text order equals time
order.

### Delegation record

One DeepSeek worker: the engine and its golden tests. It wrote only its two files. Its JSON
self-report could not be parsed, so acceptance rested entirely on reading its code and running the
suite — the handover's rule, and here the only option.

---

## v1.7 — S8 audit writer landed; S6 queue order decided (2026-09-11)

| | Change | Evidence |
|---|---|---|
| ADD | `packages/detection/audit/writer.py` — the typed, append-only `AuditWriter` (plan S8). **Delegated** to a DeepSeek worker in an isolated git worktree, then accepted on reading its code and running the suite | 45 new tests: every typed constructor round-trips; raw `UPDATE`/`DELETE` refused by the triggers; `since`/`until` edges proven at whole-second and fractional timestamps; injection-shaped filter values are bound, not formatted. 162 pass in the worktree |
| DEC | **Q22 (user, 2026-09-11): the queue order is `corroborated` → `signature_override` → `ml_only` → `none`** | Keeps notebook 03's order, which v1.3 reframed but never revised. The certain, rule-and-model-agree attacks are cleared first and fast; `ml_only` alerts carry review flags and SHAP explanations. "ml_only first" and "two lanes" were considered and declined |
| CHG | The plan's S8 event list names `RULE_CHANGE`; the contract's `RULE_CREATE` / `RULE_UPDATE` are used instead | The contract is canonical |

The v1.5 timestamp fix landed before the worker started, and its tests exercise exactly that edge.

---

## v1.8 — S6 fusion re-specified and implemented (2026-09-11)

`packages/detection/fusion/cef.py` — Complementary Evidence Fusion, re-specified for the v1.3
trust/triage model. **Not delegated**, as the plan requires. The full specification is the module
docstring.

| | Change | Rationale |
|---|---|---|
| KEEP | Notebook 03's four evidence classes, its scores, `AGREEMENT_BONUS` 5, the severity scores, invariants I1, I2, I4 and I5 | They survive the v1.3 reframing; only the justification changed, from coverage to trust |
| CHG | `corroborated` now requires the model to agree on the **class** | v1.6: a rule the model contradicts is not corroboration. That case is `signature_override` — always reviewed, and ranked above `ml_only` (I5) |
| CHG | The model's malicious probability is `1 − P(Benign)` | The notebook used the predicted class's confidence, which understates it when probability is split between attack classes (DoS 0.50 + DDoS 0.45 is 0.95 malicious, not 0.50). The old data had no class probabilities |
| DEC | One critical threshold, `critical_alert_threshold` (80), sets severity "Critical", `is_critical` and the review flag; High ≥ 70 and Medium ≥ 40 come from `fusion-engine.js`; flows no detector flagged are "Informational" | The three can no longer disagree. **Input for S7:** Node triggered the critical floor at ≥ 90; "Critical" now means ≥ 80, which widens the floor's coverage — S7 must log that (plan v0.3 FIX c) |
| DEC | An unavailable model prediction forces review | Such a flow cannot be assessed. All 5,000 demo predictions are available, so this is a defensive branch |
| DEL | The plan's S6 check "the 8 known complementary detections occupy positions 1–8" | Those detections do not exist on corrected data (v1.2). Replaced by the end-to-end demo test below |
| DEF | I3 — feedback cannot decay `signature_override` | A feedback guardrail, so S7 enforces it. Kept in `test_fusion.py` as an explicit skip naming S7, not deleted |
| ADD | `FusionConfig.snapshot()` is what `detection_runs.fusion_weights` stores; `from_snapshot` refuses any other scheme | A run can be replayed, and a weighted-sum configuration cannot be loaded by accident |

### End to end on the demo sample (5,000 flows, the real rule engine, the real model output)

- `corroborated` **200**, every one a real attack — v1.3's "caught by both: 200".
- `signature_override` **0** — no rule is contradicted on the demo sample. The 23 FTP-rule port
  scans (v1.6) exist only in the training sample.
- `ml_only` = every other flow the model flags.
- The queue the database serves (`ORDER BY db.QUEUE_ORDER_BY`) equals the Python `queue_key` order,
  alert for alert.

22 fusion tests pass, 1 skipped (I3 → S7). Full suite: 187 passed, 1 skipped.

---

## v1.9 — Full workflow documented; combination accepted for the demo; three corrections (2026-09-11)

`docs/system-workflow.md` with diagrams 13–15: the path from network traffic to the dashboard and
back, each part marked built / next / planned.

| | Change | Evidence |
|---|---|---|
| DEC | **Q23 (user, 2026-09-11): the signature + ML combination (S6) is accepted for the demo at its current defaults; tuning is deferred until realistic traffic** | On the demo, flagged flows score 81.3–100 and unflagged flows 0–42.77, with **no alert in between** — any critical threshold from 42.78 to 81.3 gives an identical queue, review set and severities. The parameters live in `FusionConfig` and are snapshotted into every detection run, so a later retune is configuration, not code |
| FIX | `mark_expected_activity` is **−15** in `feedback-engine.js`, not −30 as HANDOVER §7 stated | Read from the engine source |
| FIX | The engine also defines `duplicate` and `uncertain`, both with no score change | HANDOVER said `duplicate` appears nowhere in the engine. The decision is unchanged — `duplicate` is a queue action — but `uncertain` must be mapped in S7 |
| GAP | S3's `FlowSource` / `CsvReplaySource` seam was never built | Plan Phase 1 was marked done on the dataset, samples and model. The S9 runner needs the seam, so it is built with S9 |

### Inputs recorded for S7

1. Floors must hold an alert at the floor only if it started above it — the legacy engine lifts a
   sub-75 Infiltration alert up to 75 on negative feedback.
2. "Critical" is now score ≥ 80 (legacy ≥ 90), widening the Critical floor's coverage — log it.
3. Map `uncertain` (behaves as `needs_investigation`) or add it to the contract.
4. Feedback moves a score within its evidence band, never across bands, so a confirmed missed
   attack stays in the bottom band. The dashboard needs a review view — possibly a decision for the
   project lead, as it shapes the demo story.
5. A false positive among Critical alerts cannot fall below 70; clearing it is a status change,
   not a score change.

Illustrated on real demo alerts in `system-workflow.md` §5: `AL-00478` (99.89 → held at 70),
`AL-02717` (88.48 → held at 70), `AL-03086` (36.94 → 46.94).

---

## v1.10 — S7a landed: direct analyst feedback inside the guardrails (2026-09-11)

`packages/detection/guardrail/policy.py` + `packages/detection/feedback/service.py`, on branch
`feat/s7-feedback`. **Not delegated** — feedback and guardrail logic are Claude-only, and this is the
plan's highest-risk step. 23 new tests in `tests/test_guardrail.py`, and the fusion suite's I3
placeholder is now a real test. **211 tests pass, 0 skipped.**

| | Change | Rationale |
|---|---|---|
| KEEP | The engine's values: requested change +10 / −30 / −15 / 0 / +15 per category; cap −30 / +20; Critical floor 70 (a Critical alert, or a Critical-severity matching rule); Infiltration floor 75 | `stage-5/core/feedback-engine.js` is authoritative (HANDOVER §7) |
| KEEP | **Verdicts do not stack.** The current score is `detection_score` + the guarded change of the latest verdict; each verdict supersedes the previous one (`amended_from_id`) | The engine's semantics (`resolveEffectiveFeedbackEvents`; its test "Detection Score remains immutable after repeated adaptation"). A score can never drift further than one capped change |
| CHG | **Floors never raise a score** — a floor protects an alert only if it started at or above the floor | The engine lifted a 60-point Infiltration alert *up* to 75 on a "false positive" verdict |
| CHG | **I3 freezes `signature_override` against every category.** A non-zero change is rejected and logged as `GUARDRAIL_REJECTION` for the administrator | The plan's S7 test wording: "unchanged by any feedback category". The engine only preserved the review flag |
| DEC | "Critical" = score ≥ 80 (from S6), so the Critical floor protects every flagged demo alert — wider than the engine's ≥ 90 | Logged as plan v0.3 FIX (c) requires |
| DEC | `uncertain` is folded into `needs_investigation`; `duplicate` stays a queue action | Identical effect: no change, forces review |
| DEC | The review flag is the category's own flag, a guardrail's, or S6's review rule applied to the new score. The engine's separate `reviewThreshold` (70) is not used | Keeps S6's single-threshold rule |
| ADD | Guardrails can be switched off (`GuardrailPolicy(active=False)`) for the evaluation's third arm (D9); only the 0–100 range still binds | D9 — the only way to demonstrate the guardrails rather than assert them |
| ADD | Guardrail settings load from `guardrail_config`, so an administrator's change takes effect (NFR-08) | Proven by test |
| ADD | `submit_feedback` is one transaction — `feedback_events` row, alert re-score, `FEEDBACK` + `GUARDRAIL_*` audit entries; any failure writes nothing | Proven by test |
| ADD | Two contract codes: `signature_override_feedback_immune`, `score_range_clamped` | Python literal only; the schema is unchanged |
| DEF | Similar-alert learning (similarity + aggregation) → **S7b**. The engine's revert events are not ported | Direct feedback is what the demo path needs first |

**Proven by test:** the TDM worked example (92, −40 → capped −30 → Critical floor → 70, actual −22);
the collaborator's JS guardrail tests, ported; a Critical alert never falls below 70 across a grid of
scores and requested changes; I3 across every category, on real fusion output; non-stacking;
rollback on failure; the guardrails-off arm. The worked examples in `system-workflow.md` §5
(`AL-00478` 99.89 → 70, `AL-03086` 36.94 → 46.94) are now reproduced by the real service.

**Still open for the project lead:** feedback cannot move an alert across evidence bands, so a
confirmed missed attack stays in the bottom band (`system-workflow.md` §7, item 4). Settle before S11.

---

## v1.11 — Goal confirmed; ranking and escalation decisions Q24–Q27 (2026-09-11)

**The goal, confirmed with the project lead:** feedback on past alerts **reorders future alerts** to
raise triage efficiency, inside the guardrails — the approved thesis (URS: "re-ranks similar future
[alerts]"; FR-B03, Must). Consequence: **S7b, similar-alert learning, is the core of the thesis**,
not a follow-on to S7a.

| ID | Decision (project lead) | Consequence |
|---|---|---|
| **Q24** | Feedback moves an alert into a **higher queue class**; a "flagged for review" view is an additional feature; the `AL-03086` case is documented for later | Supersedes the open question in `system-workflow.md` §7 item 4. `evidence_class` stays the detector record; movement is a separate queue class |
| **Q25** | Automatic tier escalation is **post-demo**, but the demo shows the SOC tier model and **which alerts would go to Tier 2** | Escalation criteria E1–E3 proposed; the approved design has no tiers (UC-SA-14 "Escalate" only raises priority), so this is a logged extension |
| **Q26** | How far a confirmed alert moves is **chosen by testing** candidate systems, informed by game ranking design | Candidates C0–C3 (fixed, severity-weighted, Elo-style, Elo + uncertainty) × class-movement variants M1/M2, and a selection experiment on held-out "future" flows |
| **Q27** | Repeated false positives **drop a class**, by an amount set by the **attack type's severity** | A severity chart anchored on Suricata classtype priority, MITRE ATT&CK tactic and the CVSS v3.1 bands; weight `w = severity / 10` drives the formulas |

Design and sources: [`ranking-and-escalation-design.md`](ranking-and-escalation-design.md).
**Awaiting sign-off:** the severity values, the candidate set, and the queue classes.

---

## v1.12 — Severity chart made configuration; ranking formula selected by experiment (2026-09-11)

The project lead signed off all three items v1.11 awaited:
- the severity values, provided they can be changed later;
- all four candidate formulas, to be experimented on, with the history of the tests and their
  methods kept locally;
- the queue classes.

| | Change | Evidence |
|---|---|---|
| DEC | **Q28: the severity chart is configuration, not code.** It lives in `config/severity-chart.json`, version `sev-1`. It is validated on load (every model class exactly once, severity 0–10). Bands are derived from CVSS v3.1. The chart version is recorded with every experiment run | `packages/detection/ranking/severity.py`. A test shows that editing the file changes the weight and band |
| ADD | **`packages/detection/ranking/`:** formulas C0–C3, movements M1/M2, the queue classes, Tier 2 criteria E1/E3, and the selection experiment | 15 new tests, 226 in total. The experiment's scorer is pinned to `apply_guardrails` over a grid |
| ADD | **The experiment record is kept locally.** `evaluation/ranking/history.jsonl` has one line per run. `runs/<id>/` holds `config.json`, `results.json` and `METHOD.md`. Read it in `notebooks/05_ranking_selection.ipynb` | Nothing is overwritten. Each run records the commit, the chart version and the selection rule |
| CHG | **The selection rule went from sel-1 to sel-2 after the results were seen. This is declared, not hidden.** sel-1 ranked on precision in the top 100 first. The no-feedback control already scores 1.0 there, so all eight pairs tied and a class-change tie-break picked C1 + M2. That run, `20260911T111249Z`, is kept. sel-2 ranks by safety, then attacks demoted under analyst error, then Tier 2 precision, then mean attack position, then class changes, then simplicity | Run `20260911T111625Z` |
| DEC | **Q29: movement M1 (one class at a time, shield 2) is selected; the formula is not** | Under M2, one wrong confirmation overrode 13 correct dismissals and put 779 benign flows into Tier 2 (in one seed). Mean Tier 2 precision is 0.74 under M2 against 1.00 under M1. sel-2 names C1, but its deciding metric traces to one family collision; see the FIX below |
| FIX | **Withdrawn before commit: "the Elo form trusts surprises".** It was first written into this entry and the design doc to explain why C2 demoted attacks under analyst error. A trace with the new `experiment.calibrate()` shows every demotion comes from one family, `('Web Attack', 80, 'TCP', '-')`, after a *correct* dismissal of a benign flow the model scored 99.89. C1 avoided it only because its queue order never reached that flow | `notebooks/05_ranking_selection.ipynb` §7 F2 |
| FIX | **`load_flows` parsed the ISO timestamps day-first.** Under pandas 3, `dayfirst=True` read 1 March 2018 as 3 January, which reordered the demo flows and changed the past/future split. Pandas 2 ignores the flag for ISO text, so the recorded runs (pandas 2.3.3) used the correct chronological order. Timestamps are now parsed as ISO 8601, and unparseable text raises. It came to light because notebook 05, executed on a pandas 3 kernel, did not replay the run | All 144 recorded arms replay identically under Python 3.11 / pandas 2.3.3 and under Python 3.12 / pandas 3.0.5. Test `test_timestamps_parse_as_iso_never_day_first`. New runs record their Python, pandas and numpy versions in `config.json`, and notebook 05 re-simulates recorded arms and stops if any differ |

**Finding: the risk is single-verdict family learning, not the formula.**
- One correct dismissal of an ML false positive demoted 59 true attacks out of Tier 2. Their score
  fell from 100 to 82, which is above the Critical floor of 70, so no guardrail fired.
- The collaborator's adopted gate was not in the experiment. It requires at least 3 learning verdicts
  with at least 0.67 agreement (`stage-5/config/adaptation-config.json`, `aggregation`).
- That gate, and a finer family key, come before the formula is chosen.
- C3's results are identical to C2's.

**Limit.**
- The experiment measures the **harm** analyst error does, not an **efficiency gain**.
- The demo sample is already ranked almost perfectly: the mean attack position is 0.0829 with no
  feedback.
- A stress test with a weaker or drifting detector is proposed but has not been run
  (`ranking-and-escalation-design.md` §8).

---

## v1.13 — Run 3: agreement gate adopted, formula C1 (2026-09-11)

The project lead approved the next step: add the collaborator's agreement gate and a finer family
key, rerun all four formulas, and choose one.

| | Change | Evidence |
|---|---|---|
| ADD | **The agreement gate**, in `formulas.effective`, ported from the collaborator's `checkAdaptationEligibility`. It needs at least 3 learning verdicts, no tie, and a dominant share of at least 0.67, rounded to 4 places (so 2 of 3 fails). Only learning pointing the dominant way applies. **The fine family key** adds the destination IP for every flow. Both are experiment dimensions, giving 576 arms | 4 new tests, 230 in total |
| ADD | **sel-3 was committed before the run** (`5269732`). Candidates are guarded, gated arms, and the formula must scale by severity (Q27). They are then ranked by safety, attacks demoted under error, Tier 2 precision, mean attack position, class changes and simplicity | Run `20260911T121013Z` records that commit |
| DEC | **Q30: the agreement gate is adopted for S7b.** Every gated arm, for every formula, movement and key, demoted 0 attacks and kept Tier 2 at load 243 and precision 1.00, the same as the control | The ungated coarse arms reproduce run 2 exactly (48 of 48 aggregates) |
| DEC | **Q29, completed: the formula is C1.** sel-3 names it and it meets Q27. It leads C2/C3 on mean attack position by 0.0001, about a quarter of a queue position | `notebooks/06_ranking_gate.ipynb` |
| KEEP | **Movement M1 stays, pending the project lead.** sel-3 names M2 because of class changes (13 against 25). That metric counts internal family state, including changes the gate withholds. Every metric the analyst would see is identical for M1 and M2 under the gate; they differ by construction only for unflagged families | — |
| FIX | **Notebook 06, which this entry cites, had not been written. It now exists and executes with zero errors, and writing it corrected two findings.** (1) Under the gate the analyst never reviewed the colliding Web Attack flow, so "its gate stayed shut on a single verdict" is not what happened. A counterfactual (the ungated arms' own verdicts, scored with the gate on) shows the gate alone brings the 59 demotions and the 780 benign Tier 2 alerts to 0 in every seed. (2) The attack families that pass the gate have no flows in the future half; they are not "at score 100 in Tier 2" | `notebooks/06_ranking_gate.ipynb` F1, F3. 48 recorded gated arms replay identically under Python 3.12 / pandas 3 |

**Findings.**
- **The fine key alone removes the family collision, but not M2's Tier 2 flood.** AL-00478 goes to
  64.150.178.87, and the 59 attacks go to 172.31.69.28.
- **Under the gate, feedback barely touches the future queue on this data.**
  - Only 4 of 32–34 learned families pass it (the traced arms: 5 % error, first seed).
  - The three attack families among them have no flows in the future half, and the fourth (benign
    DNS) is already at the bottom.
  - C1 moves 10 benign flows down; C2 moves nothing.
- **The gate asks for more evidence, not the right evidence.** Enough agreeing dismissals of ML false
  positives in a coarse family would still demote the true attacks in it. The fine key is the
  defence in depth.

**Limit.** The efficiency question is still untested. The stress scenario, with a weaker or
drifting detector, remains the next experiment.

---

## v1.14 — S7b landed: similar-alert learning behind the agreement gate (2026-09-12)

`packages/detection/feedback/learning.py` (pure) over a rewritten `service.py` (transactions), on
branch `feat/s7-feedback`. **Not delegated.** 33 new tests; **263 pass, 0 skipped.** A verdict now
moves the alerts like it — the thesis's mechanism — inside the same guardrails as S7a.

Written the same day: **notebook 06**, run 3's decision record, which v1.13 cited but which did not
exist. Executing it corrected two of v1.13's findings — see the FIX in that entry.

| | Change | Rationale |
|---|---|---|
| KEEP | The experiment's own functions **are** the production code: `formulas.apply_verdict` with **C1 + M1**, K = 30, shield 2 (Q29), and the gate at 3 verdicts / 0.67 agreement (Q30) | What runs is what was tested. A property test over 500 random verdict sequences pins `learn()` to the experiment's gated C1 + M1 arm wherever a category is a direction |
| ADD | **Families are persisted**: a new `alert_families` table, one row per family, holding the category counts, the gate's decision and its reason, what the family has learned, and what of it reaches the queue | Derived state, recomputed from the family's **effective** verdicts after every verdict, so it is updated in place — and every change is audited as `SIMILAR_ALERT_LEARNING` |
| ADD | **Contract additions**, cheap before S9: `alerts.queue_class` + `queue_priority` (the band — Q24, Q25) and `alerts.family_key`. `QUEUE_ORDER_BY` now orders by `queue_priority` | The queue is the thing feedback reorders, so the band must be a column the queue can order by and an index can serve |
| DEC | **The gate counts by category**, as `feedback-engine.js` does, not by direction as the experiment did: 2 false positives + 1 expected activity is 0.6667 and the gate stays shut | The collaborator's engine is authoritative on the gate (Q30). The experiment's simulated analyst only ever gave two categories, so the difference could not show up there |
| DEC | **`escalate` counts as a confirmation**, where the collaborator treats it as a workflow type that teaches nothing | The ranking design's match result S = 1 (§4). Counting it as its own category would make 2 confirmations + 1 escalation fail a gate that 3 confirmations pass — an escalation would *weaken* agreement |
| DEC | **Expected activity does not propagate**, keeping the collaborator's `enabledForFutureAdaptation: false`; enabling it needs 5 verdicts at 0.9 agreement | It is an organisation-specific exemption ("that scanner is ours"), which is why their own configuration refuses to generalise it |
| DEC | **An alert with its own verdict is placed by that verdict** (direct takes priority, as in `adjustAlertWithFeedback`): E2 — escalate, or confirm on a type of severity ≥ 7 — marks a Tier 2 candidate; any other confirmation promotes one band (M1); a **dismissal withdraws Tier 2 candidacy** but moves the alert no lower | Leaving a dismissed corroborated Critical alert marked "→ Tier 2" would contradict the Tier 1 decision the analyst just made. Clearing it from the queue remains a status change |
| DEC | **A `signature_override` alert neither teaches its family nor learns from it, and never leaves its band** — enforced in the contract and by a schema CHECK | I3, extended from S7a's score freeze to the band. The design already said a disputed rule goes to Tier 3, never automatically to Tier 2 |
| DEC | **The collaborator's weighted similarity (threshold 0.7) is not ported**; the family key is exact | The experiment that chose C1, M1 and the gate grouped by exact family, and an exact family scores 1.0 under their weights — so this is the stricter rule. Porting the looser matcher would ship a grouping no experiment tested |
| CHG | **Invariant I5 is restated.** "No `signature_override` alert ranks below any `ml_only` alert" holds at detection; with feedback a confirmed `ml_only` family can be promoted into the band above it (Q24), while a `signature_override` alert can never be demoted | Q24 (the project lead) makes the band a function of feedback, so the invariant is now about the detection-time queue plus a one-way freeze |
| FIX | `fusion_review` moved from `service.py` to `learning.py`, so placement stays pure; it is still importable from `service` | Family placement needs S6's review rule, and `learning.py` must not import `service.py` |

**Proven by test** (`tests/test_learning.py`, 27 tests, plus 6 in `test_contracts.py`): the third
agreeing verdict opens the gate and moves the family's unjudged members, while the first two do not;
an **amended** verdict counts once, and shutting the gate restores every member to its detection-time
placement exactly; a member's own verdict overrides its family's; a family's learning cannot push a
Critical member below 70 across 60 random verdicts, and no detection score ever changes; a failure
after the members have moved rolls all of it back; `refresh_family` is idempotent; an alert
**arriving after** the verdicts takes the family's learning — the thesis's claim, in one test; the
guardrails-off arm applies the learning raw; and every change to a family's learning is audited.

**Not done here.** The stress test for the efficiency claim and the run on the 250,655-flow training
sample both remain (`ranking-and-escalation-design.md` §8). S7b makes the mechanism real; it does not
re-open the question of how much it gains.

---

## v1.15 — S9 landed: the batch detection run writes a real database (2026-09-12)

`packages/detection/pipeline/` and `scripts/run_detection.py`. 16 new tests; **279 pass, 0 skipped.**
One command now takes the sample to a populated database:

```
python scripts/run_detection.py        # 5,000 flows -> 5,000 alerts, 21 s, 42 MB
```

| | Change | Rationale |
|---|---|---|
| ADD | **The ingest seam S3 never built** (the gap logged in v1.9): `FlowSource`, with `CsvReplaySource` replaying the corrected release **in timestamp order** — the order a sensor delivers (D7) | The demo behaves like a feed without pretending to be one, and S17's flow exporter becomes a second implementation of the same protocol rather than a rewrite |
| ADD | **`Predictor`**: `XgboostPredictor` computes predictions **and native TreeSHAP inside the run** (D8); `ReplayPredictor` reuses an earlier run's predictions, for a machine without xgboost or a test without a model. The summary records which one ran | Computing SHAP on demand would blow NFR-04's ~2 s budget; precomputing it in a side script left the claim outside the pipeline |
| ADD | **The repository layer** (`store.py`): registrations idempotent on the natural key, the queue read in `QUEUE_ORDER_BY` order, and `alert_by_source_record` — the only join from an alert back to ground truth | S10 and S15 need exactly these reads; an ORM would add a layer over contracts that already describe every row |
| ADD | **`run_detection`** is **one transaction**: a failed run stores nothing, so the summary describes what is in the database | A half-populated demo database that looks complete is worse than no database |
| DEC | **Every flow becomes an alert**, including the 4,004 no detector flagged | They are the queue's bottom band and the evaluation's denominator; dropping them would quietly turn recall into precision |
| DEC | **Non-finite CIC values are handled in two places, deliberately.** The model sees `Infinity` exactly as it did in training; `flow_data` stores an explicit `None`, because the contracts refuse non-finite floats; the observable view still reads such a field as 0, as the tuned rules require | The alternative — cleaning at ingest — would change what the model sees and silently invalidate the committed predictions |
| DEC | A run **asserts that S6's score and review flag equal S7b's detection placement** and fails loudly if they ever diverge | Two code paths now compute where an alert sits; an assertion is cheaper than a mismatch discovered on a dashboard |
| FIX | `db.QUEUE_ORDER_BY`'s columns are unqualified, which is ambiguous in a query that JOINs `flow_data`. Noted at the constant; `store.queue` selects from `alerts` alone | Found while writing the verification query for this entry, not in production code |

**Measured on the committed demo sample** (`data/demo.db`, gitignored and regenerable):

| | |
|---|---|
| Flows → alerts | 5,000 → 5,000, 0 predictions unavailable |
| Evidence | `corroborated` 200 · `ml_only` 796 · `none` 4,004 · `signature_override` 0 |
| Queue bands | `tier2_candidate` 644 · `ml_only` 352 · `none` 4,004 |
| The run's own predictions vs the committed `demo_ml_predictions_shap.json` | **5,000/5,000** identical predicted class and TreeSHAP margin |
| Additivity checks passed (NFR-01, now in the pipeline) | **5,000/5,000** |
| NFR-05 at run level | a second run over the same sample differs in **no** scored field, for any of the 5,000 alerts |

The 796 `ml_only` alerts are v1.3's 794 model-only malicious flows plus the two known benign false
positives, and `signature_override` stays 0 as it has on corrected data throughout.

**The demo's opening move is now in the database.** `AL-00060` (corroborated, 100) and `AL-00478`
(model-only, 99.89 — the benign flow the model calls a Web Attack) both arrive as **Tier 2
candidates**; `AL-02717` (88.48) sits in the `ml_only` band; `AL-03086`, the attempted Web Attack both
detectors missed, sits at 36.94 in the bottom band. Dismissing `AL-00478` and confirming `AL-03086` is
exactly the story S7a and S7b were built to tell.

---

## v1.16 — S15 landed: the three-arm evaluation, and what it actually showed (2026-09-12)

`packages/evaluation/` and `scripts/run_evaluation.py`. 25 new tests; **304 pass, 0 skipped.**
Report: [`evaluation-report.md`](evaluation-report.md) · method:
[`../evaluation/three-arm/METHOD.md`](../evaluation/three-arm/METHOD.md) · run `20260912T032022Z`.

```
python scripts/run_evaluation.py       # three arms over data/demo.db, ~3 s
```

| | Change | Rationale |
|---|---|---|
| ADD | **The arms are byte copies of one detection database**, not three detection runs | Dataset, model, rule set and seed are then identical *by construction*; re-running detection would put the pipeline's determinism between the arms and the comparison, making any difference ambiguous |
| ADD | **Pre-registration `s15-preregistration-1`** (v0.3's replacement for the corrupt exit criterion): flagged alerts in queue order, ≤ 5 per family, families of ≥ 8, 40 verdicts, category from ground truth | The rule is fixed before any arm runs and recorded with its SHA-256 digest, so "how did you choose the feedback sequence?" has an answer that is not "so the result would appear" |
| ADD | **Ground truth reaches the evaluation by one join only** (`flow_data.source_record_id`), and `GroundTruth` refuses a record it lacks rather than defaulting to benign | A silent default would count every unmatched alert as a false positive and quietly deflate precision |
| ADD | Metrics: per-class P/R/F1/FPR/FNR, precision@k, MRR, movement split by **judged / untouched family member / unrelated**, and safety | The middle group is the only place S7b's claim is visible; the third is where leakage would show |
| DEC | **`score_range_clamped` is not a guardrail failure.** Clamping a confirmation on an alert already at 100 is the score range working | Counting it as a breach reported a safety failure on every healthy run — caught by re-checking the checker before believing the first result |
| DEC | **`adjusted` (score or band changed) is reported separately from `rank_changed`** | Rank is relative: one promotion re-ranks everything beneath it. Conflating the two made 151 untouched alerts look as though learning had leaked onto them, when 0 were adjusted |
| ADD | `queue.saturation` is a first-class metric | 975/996 flagged alerts sit at exactly 100.0; without that number the other metrics are unreadable |

**Measured, run `20260912T032022Z`** — detection metrics **identical in all three arms**, so feedback
reordered the queue and did not touch the detector:

| | A — control | B — treatment | C — guardrails off |
|---|---|---|---|
| Precision @10 / @50 | 1.000 / 1.000 | 0.900 / 0.980 | 0.900 / 0.980 |
| False positives in top 50 | 0 | 1 | 1 |
| Critical floor breaches · true positives suppressed | 0 · 0 | 0 · 0 | **0 · 0** |

**The four findings that matter.**

1. **S7b works and does not leak.** 8/8 families opened their gate at agreement 1.000; of 805
   untouched family members, 205 were adjusted and **198 true positives promoted**; of 4,155 alerts
   outside any judged family, **0 were adjusted**.
2. **It promoted two false positives, one to rank 1.** Alert 11 — benign, classified `Web Attack` —
   rose from rank 639 to **rank 1** on five `escalate` verdicts given to *other* members of its
   family. Intrinsic to a coarse family key, not a bug. The design's cost, now measured.
3. **Arm C is inert, and the rule is why.** An oracle analyst over a near-perfect detector yields
   **no dismissals**, and every guardrail that could bind (−30 cap, floors 70 and 75) protects
   against *downward* pressure. Recorded as measured per the v0.3 exit criterion — but it means
   *this sequence could not test the guardrails*, not *the guardrails are unnecessary*.
4. **The score is saturated.** 975/996 flagged alerts at exactly 100.0, 13 distinct scores among 996;
   only 1 of 40 judged alerts changed score. Order inside the top band falls to the `id ASC`
   tie-break, not to the analyst. **The 0.99 F1 testbed artefact now has a third consequence**: it
   leaves the feedback loop nothing to correct, which is why precision could only fall.

**Two nomenclature/parameter notes, both reversible.** Five judged `ml_only` alerts now sit in the
queue band *named* `signature_override` while their evidence class is unchanged — the bands reuse the
evidence-class names, and a viva question is easy to ask there. And `max_per_family = 5` happens to be
exactly the number of confirmations that saturates M1's accumulating class offset at its −5 clamp, so
every judged family's members jumped the full distance rather than one band. Both are logged rather
than quietly re-tuned.

**Open, for the project lead** (detail in the report's §6): the efficiency stress test with a weaker
or drifting detector (`ranking-and-escalation-design.md` §8) is still the only way to answer the
efficiency question; a second pre-registered rule covering the dismissal direction is needed before
arm C has any power. Neither is adopted here — changing a rule after seeing a result is exactly what
v0.3 forbids.

---

## v1.17 — The plan was eleven versions stale; the lifecycle documents are resynchronised (2026-09-12)

**Found by the user, not by us.** Asked where we were in the plan "aside from the S values", we
opened `plans/hitl-ids-demo-build.md` for the first time since **2026-09-11 00:12** — before S2
landed. Every step from v1.5 to v1.16 was driven from `HANDOVER.md` §7 while the plan itself went
untouched. The user's diagnosis was exact: *"this lapse … tells me you dont refer to the plan module
for next step implementation and is actually based off the handover purely."*

**Why it matters more than tidiness.** A delegated worker is handed a **step section from the plan**.
Three of those sections would have produced confidently wrong work:

| | The plan said | Reality | Consequence for a worker |
|---|---|---|---|
| S4b | **Retire `SIG-FTP-BRUTE-FORCE`**; set SSH's threshold to **20** | FTP is one of only **two enabled rules**; SSH's re-derived threshold is **10.66689** | Would have disabled the project's most productive rule and mis-set the other |
| S6 | Exit criterion: "the 8 known complementary detections occupy review-queue positions 1–8" | `signature_only = 0` — no such alert exists | An exit criterion that can never pass; work would stall or be faked |
| S16 | Open the demo on the top `signature_override` alert, with the precondition *"if the corrected dataset yields zero, stop and re-plan"* | The corrected dataset yields **exactly zero** | **The plan's own stop-condition had already fired and nobody had noticed** |

| | Change | Rationale |
|---|---|---|
| ADD | **`docs/deviations.md` created.** Mandated by D10 and the mutation protocol, cited by S3, S4b, S6 and S7 — **seven dangling references, never written**. Back-filled from v0.1–v1.16: 9 document deviations, 8 plan mutations, 12 component deviations, 6 rejected options, 5 withdrawn claims | The changelog absorbed its job, which is why a *withdrawn* claim could sit in the plan unnoticed — a narrative records the change, a register records the resulting state |
| ADD | **Plan v1.1** with a `PLAN-STATUS` table — the plan previously had **no status marker of any kind** and could not answer "where are we" | The question the user asked had no answer in the canonical document |
| CHG | Plan preamble rewritten: the **"detectors are complementary"** claim and **"zero co-occurrence"** both corrected inline | Both were withdrawn in v1.2; the plan asserted them for fourteen versions |
| CHG | **S4b's rule list corrected**, S6's unsatisfiable exit criterion withdrawn, **S16's demo narrative rewritten** around `AL-00478` and `AL-03086`, S7 recorded as split into S7a/S7b, S12's "6 categories" corrected to 5 + `duplicate` as a queue action, "7 classes" → 8 throughout, Suricata marked **rejected** rather than optional | Each is a place a worker would have been misled |
| ADD | **`tests/test_plan_sync.py` (12 tests)** — fails when the plan's status table disagrees with HANDOVER §7, when there is not exactly one `NEXT` step, when a `DONE` step cites no changelog version, when the handover's header or test count is stale, or when the plan re-asserts a withdrawn claim | Modelled on `test_contracts.py::test_columns_are_tdm_names_plus_logged_deviations`, which already fails on an unlogged schema column. **This class of drift is now a test failure, not a discovery** |
| DEC | **The plan is canonical for what to build next; HANDOVER is the entry point.** The start-of-session prompt now sends the reader to the plan's status table and to the step's own section | Working from §7 alone is what produced this entry |

**The test earned its keep immediately**: it failed on the first run against a line in our *own*
S16 rewrite that still read as an assertion of the retired fixture ids. Fixed the prose, not the test.

**Also updated.** `system-workflow.md` §8 (S15 done, next is S10a, canonical order delegated to the
plan) and its stale "S3 — not built" node; `ranking-and-escalation-design.md` §8, where S15 answers
four previously-open questions — family learning reaches untouched alerts (198), does not leak (0),
costs two promoted false positives (one to rank 1), and M1 converges with M2 after five
confirmations — and adds the dismissal-direction sequence as newly open.

**Not changed:** no code outside `tests/`, no contract, no measured figure. This entry is
documentation-only; `python -m pytest` and `python scripts/run_evaluation.py` produce exactly what
v1.16 recorded.

---

## v1.18 — S10a landed: the API contract, and the first thing the new process caught (2026-09-12)

`apps/api/contract/` + `scripts/build_openapi.py`. 26 new tests; **342 pass, 0 skipped.**
Published: `apps/api/openapi.json` — **13 operations over 12 paths, 37 schemas**, committed so S11
can generate its client from a checkout without running Python.

```
python scripts/build_openapi.py           # publish
python scripts/build_openapi.py --check   # fail if the committed document is stale
```

**The process introduced in v1.17 paid for itself immediately.** Reading the plan's S10a section
before writing code — rather than working from HANDOVER §7 — surfaced a stale instruction *inside the
step being implemented*:

> v1.0: "`GET /api/alerts` must return `evidence_class` and **order by `evidence_priority,
> combined_score DESC`**"

That predates S7b. The contract order is `db.QUEUE_ORDER_BY` = `queue_priority ASC, combined_score
DESC, id ASC`. **Ordering by `evidence_priority` would have produced an API in which feedback
appears to do nothing** — an alert promoted between queue bands would not move, because the sort key
never changes. The demo's whole point would have been invisible, and the bug would have looked like
a UI problem three steps later. Corrected in plan v1.1; logged as `deviations.md` C13.

| | Change | Rationale |
|---|---|---|
| ADD | **`apps/api/contract/`** — `common` (envelopes, roles, paging, query models) · `alerts` (queue, four evidence panels, the feedback loop) · `operations` (dashboard, runs, audit, guardrails, evaluation) · `openapi` (the document) | S10a is the contract, not the service |
| DEC | **Nothing imports FastAPI.** The contract is pure Pydantic | It can be written, reviewed and tested before `fastapi` is installed, and S11 can start while S10b is still being written — which is the entire reason v0.3 split S10 |
| DEC | **Paths hand-authored, schemas generated** from the models | The plan says "hand-authored" because FastAPI generates OpenAPI *from* handlers. But hand-typing the schemas would be a second copy of the models, free to drift — exactly the failure v1.17 was written about. Paths are decisions; schemas are consequences |
| DEC | **`alertRef` (UUID) is the public identity; row ids are never exposed** | They leak row counts, and S18's Postgres migration is free to renumber them |
| DEC | **Both score columns in every queue row** (`detectionScore` immutable, `combinedScore` operational) | The dashboard's second score column is the demo's point; one number cannot show it |
| DEC | **The feedback response carries the whole adjustment chain**, not the final score | `original → requested Δ → guardrail bound → actual Δ → final`. A response with only the new score makes the guardrails invisible, and they are the safety claim. A rejected adjustment is a 200 with `action: rejected` — the verdict was recorded and the score was protected; that is not an error |
| DEC | **camelCase on the wire, snake_case in Python** | The consumer is a generated TypeScript client, and this repository already uses camelCase at every JavaScript boundary (`ProducerContract`, the observable view) |
| ADD | **A leakage test over the whole contract**: no wire model may expose `attackClass`, `groundTruth`, `isAttempted` or a label. `attackCategory` (what the system *assigned*) is allowed; `attackClass` (what the capture *was*) is not | The API is the first component that could leak the answers. `sourceRecordId` is exposed deliberately — an identifier, not an answer |
| ADD | `duplicate` is **absent** from the feedback categories, and a test says so | The approved documents' "six categories" folds a queue action into the scoring set (`deviations.md` A6) |
| ADD | **Evaluation deltas are typed to allow negatives**, with the schema description saying they must be rendered as measured | S15 measured precision@50 falling 1.000 → 0.980. A contract that could only express improvement would be a contract that lies |

**Two real gaps the contract tests caught while being written**, neither of which was a test
artefact: `AuditQuery` was declared but **never wired into `/api/audit-log`**, which therefore
offered no filters at all though S13's log viewer needs them; and query-parameter models were being
emitted as component schemas nothing referenced. Query models are now flattened into `parameters`
and excluded from components, where a client generator expects them.

**Not done here, deliberately:** NFR-04's p95 < 2s. It is measured in S10b, where code first runs;
asserting a latency budget against a document would be theatre.

---

## v1.19 — S10b landed: the system is reachable over HTTP (2026-09-12)

`apps/api/{deps,mappers,routes,main}.py` plus the repository reads on `pipeline/store.py`.
34 new tests; **376 pass, 0 skipped.**

```
python -m uvicorn apps.api.main:app --reload     # http://localhost:8000/docs
```

**NFR-04 measured on the real 5,000-alert database**, not on the test fixture:

| | p50 | p95 | budget |
|---|---|---|---|
| `GET /api/alerts` (50) | 15.6 ms | **19.3 ms** | 2,000 ms |
| `GET /api/alerts` (deep page, offset 4,900) | 14.8 ms | 20.5 ms | 2,000 ms |
| `GET /api/alerts/{ref}` | 5.3 ms | **6.2 ms** | 2,000 ms |
| `GET /api/dashboard/summary` | 94.0 ms | 99.1 ms | — |

| | Change | Rationale |
|---|---|---|
| ADD | **Repository reads on `store.py`**: `queue_page` (filtered, paged, with a total), `alert_by_ref`, `flows_for_alerts`, `family_by_key`, `feedback_for_alert`, `has_feedback`, `audit_page`, `dashboard_counts`, `latest_run` | `store.py`'s own docstring already promised these to S10 and S15. Two queries per page, never one per row — which is what keeps the deep page as fast as the first |
| DEC | **A blocked adjustment is a 200, not a 4xx.** The refusal travels in `action: rejected` with the guardrail's explanation | The verdict *was* recorded and the score *was* protected — that is the system working. A 4xx would tell the analyst their action failed |
| DEC | **An unknown filter or sort key raises**, rather than being ignored | A filter silently dropped returns a plausible wrong answer, which is worse than an error |
| DEC | **The role check is named `demo_role_stub`** and applied only where a role genuinely gates an action | Sprinkling it everywhere would imply an access-control model the demo does not have. An unrecognised role is refused, never downgraded to analyst |
| DEC | **`POST /detection/run` reports the existing run** rather than launching one | Detection is an offline batch (D3); a 21-second job inside an HTTP request is not a design, it is a timeout |
| ADD | `GET /api/health` names the database being served | In a demo, "which database am I looking at" is the first question when something looks wrong |

**Three bugs, every one found by running the thing rather than by reading it.**

1. **`alertsMovedByFeedback` reported 644 movements on a database with zero verdicts.** It compared
   `queue_class != evidence_class`, but *detection itself* places alerts in the `tier2_candidate`
   band. Now: the score has left its detection score, or a verdict exists, or the alert's family has
   an open gate applying an adjustment. Reads **0** on a clean database and **845** on arm B — which
   matches S15's movement figures exactly (40 judged + 805 family members).
2. **A guardrail sentence stated the wrong number.** *"This alert is Critical, so its score was held
   at the floor of **29.89**"* — the floor is **70**. `feedback_events` stores only the code, and the
   configured value was being inferred from the delta. Now looked up from `guardrail_config`. That
   sentence is the demo's centrepiece, so it has a regression test.
3. **A test asserted the result it wanted.** `membersMoved >= 1` once the gate opened — but the
   fixture's family is already at the top band and at score 100, so nothing *can* move. The
   saturation S15 measured, reappearing. The test now checks what is observable: the gate opens on
   the third verdict, and an unjudged member's family panel carries the applied adjustment and says
   why.

**Delegation reconsidered, and declined.** The plan allowed a delegate for the handlers with
`POST /alerts/{id}/feedback` withheld. In the event the write path, the mappers and the repository
reads were too entangled to split cleanly, and two of the three bugs above were in the shared part.
Delegating would have cost more review than it saved. Recorded rather than quietly ignored.

**Also:** `tests/conftest.py` now owns the synthetic capture that `test_evaluation` and `test_api`
share, instead of one importing from the other.

---

## v1.20 — S11 landed: the first thing a person can look at (2026-09-13)

`apps/web/`: React 19 + Vite 8 + Tailwind 4 + react-router 7, and a client generated from
`apps/api/openapi.json` by openapi-typescript + openapi-fetch. **30 web tests** (Vitest) beside the
Python suite's 376, which is unchanged.

```
cd apps/web && npm install && npm run dev      # http://localhost:5173, /api proxied to :8000
npm run build · npm test · npm run check:api   # check:api fails if the client is stale
```

| | Change | Rationale |
|---|---|---|
| ADD | **Typed client generated, never written.** `src/api/schema.d.ts` comes from the S10a contract; `unwrap()` returns the typed body or throws one `ApiError` | A hand-written client is a second copy of the contract. No `any` anywhere in `src/` (exit criterion) |
| ADD | **Design tokens** (`src/index.css` `@theme`): one dark console palette under semantic names | Components use `bg-surface`, `text-muted`, never raw hex, so the palette changes in one place |
| ADD | **Three role shells**, each landing where the plan's S11 verification names: analyst → queue, admin → system status, evaluator → scenario list. Routes S12–S14 fill are mounted as placeholders that name their step | Every shell reachable and every nav link resolves now, without pretending an unbuilt screen is finished |
| DEC | **Navigation is per role** | An analyst should never see an admin link; switching role visibly changes what the console offers. Documents are updated from the product, not the reverse (user instruction, 2026-09-13), so no deviation is logged |
| DEC | **The role switch is labelled as a stub on screen** ("Demo build · role switch stub"), and the session survives a reload (sessionStorage) | D3: `X-Demo-Role` is trusted as sent. Survival matters because S12's end-to-end check is *refresh, and the adjusted score persists* |
| DEC | **The role header is held in the client module, set synchronously by the session**, not read from React state | A child's first fetch runs before its parent's effects; reading state would send the previous role on the first request after a switch |
| FIX | **`ErrorBody.detail` loosened to optional in the client only** | openapi-typescript marks a defaulted field required, and every response *does* serialise its defaults — except the error envelope, which `deps.py` renders with `exclude_none`. The one place the generated type was untrue |

**A skeleton already existed, and was superseded.** Commit `161b056` had added four config-only files
under `apps/web/` (`package.json`, `index.html`, `tsconfig.json`, `vite.config.ts`, no `src/`), pinned
to React 18 / react-router-dom 6 / Vite 6 / Vitest 2. The plan and this handover still said `apps/web/`
did not exist, so they were overwritten without being read first — caught afterwards in `git status`,
and compared line by line. The intent was identical (same proxy, same Tailwind plugin, same test
setup path); the stack moved to current majors, the client script became `gen:api` writing
`schema.d.ts` plus a `check:api` guard, and the one stricter setting that had been lost,
`verbatimModuleSyntax`, was restored. The originals remain in git.

**Delegation, as the plan intended this time.** Claude wrote the architecture — tokens, roles, session,
guards, client, fetch hook, route table, test harness — and a DeepSeek worker built the components and
their tests from a written brief (54 turns). Its files were read, not trusted. The worker **correctly
refused to edit the protected files** when the build failed on the `ErrorBody.detail` typing above,
and reported the exact cause and both candidate fixes; the defect was Claude's. One review change: its
fixtures invented model and rule-set versions, replaced with the project's real ones.

**Checked against the live API**, not only fixtures: the dashboard preview's endpoint returns the real
5,000-alert summary through the Vite proxy. `GET /api/evaluation/scenarios` returns **no items on
`data/demo.db`** — the three arms live in their own database copies (S15) — so the evaluator's landing
view shows its empty state on the demo database. S14 must choose which database the evaluator reads.
**Not done:** a visual check in a browser (the browser automation extension was not connected).

---

## v1.21 — S12, S13, S14 and the S16 gate: the demo is presentable (2026-09-13)

The three role paths are built, and the demo narrative executes end to end — through the API and in a
real browser — with no manual database fixes. **385 Python tests, 0 skipped · 103 web tests · build
clean · `check:api` clean.**

```
python scripts/rehearse_demo.py        # 41 checks through the real API, on a throwaway copy
cd apps/web && npm run e2e             # the same narrative in Chromium, on its own copy (~45 s)
```

### What landed

| | Change | Rationale |
|---|---|---|
| ADD | **S12 analyst path**: ranked queue (filters, sort, paging, all in the URL), alert detail with the four evidence panels and the family panel, the verdict form, the score-adjustment chain, verdict history, Investigations, Feedback Impact, dashboard charts | The demo core. The verdict form, the chain and the guardrail messaging are Claude's (never delegated); the rest was a DeepSeek worker, reviewed file by file |
| ADD | **S13 admin path**: system status, the guardrail form (floor below threshold, positive caps, a required reason, only changed fields sent), the guardrail log, the audit trail with filters and CSV export | "Check again" reports the latest run; it does not pretend to start one (D3) |
| ADD | **S14 evaluator path**: evaluation runs and pre-registration, the three-arm comparison with every delta **as measured**, who moved, what the guardrails prevented, per-class metrics with the testbed caution | The honesty requirement of plan S16: the banner says precision fell before the reader meets the table |
| ADD | **`sourceRecordId` on every queue row, and search that matches it** | The narrative names `AL-00478`; the public `alertRef` is a UUID no analyst can read aloud or find |
| ADD | **`GET /api/evaluation/runs`** | The three-arm results are committed files, not rows; without a listing the evaluator needed a terminal. Not "an endpoint while we're here": S14 could not be built without it |
| ADD | **`scripts/rehearse_demo.py`, `scripts/serve_rehearsal.py`, `apps/web/e2e/demo.spec.ts`, `docs/demo-script.md`** | The S16 seed-and-rehearse tooling. Every run works on a **copy**: verdicts are permanent, so rehearsing on `data/demo.db` would hand the next audience a queue that has already been judged |
| DEC | **The S16 narrative's S7b step moved to the `Port Scan / 445` family** | `AL-03086`'s family has one member; three confirmations in `Port Scan / 445` move its two unjudged members into the Tier 2 band. Every claim checked against ground truth. `deviations.md` E6 |

### Defects found — four of them only by running the real thing

1. **The chain hid the Tier 2 withdrawal.** `score_adjustment` used the *evidence class* as the "before"
   band, so a dismissed Tier 2 candidate read "Model only → Model only (unchanged)", and an unjudged
   alert read as if it had moved. Now detection's own placement (`detection_placement`, the pure
   function S9 stores at ingest). Found by simulating the narrative before writing it.
2. **A SQLite cross-thread 500 on the demo's centrepiece.** FastAPI enters the connection dependency and
   runs the handler on different threadpool workers; opening an alert fires three reads at once, and
   SQLite refused a connection used off its creating thread. Every sequential test, `TestClient` run and
   `curl` passed; **the browser e2e run caught it**. `db.connect(check_same_thread=...)`, `False` for the
   per-request API connection only. Two regression tests: a deterministic cross-thread use, and 24
   concurrent reads of one alert.
3. **The guardrail log had no sentence.** The audit record stores the intervention's code and configured
   value, never the sentence the analyst saw, so the administrator's log showed a dash. The API now adds
   the explanation when it serves the log, built from the **stored** configured value — a later change
   to a setting cannot rewrite what the log says happened — without modifying the record.
4. **Imports inside a request handler** (introduced with fix 1) moved to module level: a first import can
   race between threads under exactly the concurrency of defect 2.

### Delegation — the record

| Step | Worker | Outcome |
|---|---|---|
| S12 | DeepSeek | 100 turns. Clean work; review found nothing to change in the pages. One test raced a second request under load (fixed: `findBy`) |
| S13 | GLM | **Stalled** after reading ten files, no output for 11 minutes. Stopped, relaunched on DeepSeek with a 25-minute `timeout`: 112 turns, clean |
| S14 | DeepSeek | **Stalled** on first launch (running beside two other workers); relaunched after S12 finished: 77 turns. Review found one factual error — a caption saying a rule-only alert "can be demoted by feedback", which I3 forbids — corrected |

The briefs gave each worker exact files, real data values and a rule against editing shared files. Two
workers correctly **refused** to edit shared files and reported the needed change instead. **Stopping a
worker's shell does not stop its `claude` child process** on Windows: the orphans had to be found and
killed by process id.

### Verification

| Check | Result |
|---|---|
| `python -m pytest` | **385 passed, 0 skipped** |
| `npm run build` · `npm test` · `npm run check:api` | clean · **103 passed** (15 files) · in step |
| `rehearse_demo.py` on a copy of `data/demo.db` | 41/41 |
| `rehearse_demo.py` on a database freshly seeded by `run_detection.py` | 41/41 |
| `npm run e2e` (Chromium, real API, disposable copy) | **1 passed**, ~45 s |

**Honest limits.** The gate ran from the working tree, not a literal clean clone — the work is not yet
committed. `AL-03086` climbs one rank (998 → 997) while leaving the bottom band. The production bundle
triggers Vite's chunk-size warning (Recharts). `features/admin/partialBody.ts` holds one documented cast,
because openapi-typescript marks defaulted request fields required.

---

## v1.22 — Console rebuild R1: the triage backend (2026-09-13)

The user asked for a full redesign of the console, modelled on real SOC/IDS workflows
(`docs/console-rebuild-proposal.md`, `docs/research/soc-console-research.md`). R1 adds the backend that
workflow needs. **411 Python tests · 103 web tests · typecheck and `check:api` clean · rehearsal holds.**

### What landed

| | Change | Rationale |
|---|---|---|
| ADD | **Schema migrations** — `db.MIGRATIONS`, `db.migrate`, `PRAGMA user_version`; applied by `create_schema`, `open_database` and the API's connection | `schema.sql` is consumed; a demo database built earlier must upgrade in place, not be rebuilt |
| ADD | **`alert_notes` table** (migration 1), append-only by trigger, like `audit_log` and `feedback_events` | Every SOC console keeps an analyst notes thread; a correction is a new note. Not a TDM table — logged here, registered in `test_contracts.py` |
| ADD | **`POST /api/alerts/{ref}/status`, `POST /api/alerts/{ref}/assign`** (`packages/detection/triage.py`) | Owner and status are two of the four triage controls. Uses the existing `status`/`owner_id` columns; audited as `ALERT_STATUS_CHANGE`; a refused transition is a 409 |
| ADD | **`GET/POST /api/alerts/{ref}/notes`** | B2 |
| ADD | **`GET /api/dashboard/breakdowns`, `GET /api/entities/ip/{ip}`** | B4, B5: top talkers, verdict and status mix, guardrail codes, capture-time histogram; per-IP view |
| ADD | **Queue: `verdict`, `owner`, `flowFrom`/`flowTo` filters; `flowTime`, `owner`, `familySize` on rows** | B6 |
| DEC | **Status is workflow, not judgement** | A status or owner change never moves a score, touches a family or invokes a guardrail; only verdicts do |
| DEC | **Flow time is the dataset's capture time** (`flow_features.Timestamp`, capture-local text) | `created_at` is the detection run's time and identical for every alert; the histogram shows when traffic happened, not a live rate |

**Honest limits.** `ruff` is not installed in the Python 3.11 environment, so lint was not run. The API
applies migration 1 to `data/demo.db` the first time it serves that file — a schema upgrade, not a data
change.

---

## v1.23 — Console rebuild R2–R3, the "features don't work" report, and a project Python environment (2026-09-14)

The console now looks like the SOC workstation the user asked for, analysts land on it, and the project
has a Python environment that cannot silently pick the wrong interpreter. Committed as `b534db6` on
`feat/demo-build` and **pushed to origin** (the branch did not exist there before).
**411 Python tests (in `.venv`) · 103 web tests · typecheck clean · `npm run e2e` passes.**

### What landed

| | Change | Rationale |
|---|---|---|
| ADD | **R2 design system**: `apps/web/src/index.css` tokens (near-black ground, square panels, 1 px rules), IBM Plex Sans + JetBrains Mono, `.label-mono`, severity as dot + word; restyled `TopBar` (UTC clock, "Recorded flows" badge — not a live feed), `Sidebar`, `ui.tsx` primitives | The user's design reference (a Figma Make screenshot); tokens in `console-rebuild-proposal.md` §1 |
| ADD | **R3 analyst workstation** `/analyst/workstation`, now the analyst home: `features/workstation/` — `KpiStrip`, `QueuePane` (band tabs with counts, search, `j`/`k`), `AlertPane` (Claim · Start work · Resolve · Dismiss · Release · Reopen; meters; tabs Overview · Verdict · Flow record · Notes · History), `ContextRail` (flow diagram, per-IP context from B5, `FamilySummary`, real quick actions only) | Queue beside the alert is the SOC norm (research §4). Nothing invented: no geo, threat intel or response actions |
| DEC | **Industry verdict labels on screen**: True Positive · Escalate to Tier 2 · Needs investigation · Benign Positive · False Positive (`features/feedback/categories.ts`, `categoryLabel()` for audit text). API values unchanged | User decision (proposal §0) |
| FIX | Verdict radio grid sized by container (`@container`) so it fits the workstation column; duplicate "Tier 2 candidate" pill removed; nested family card replaced by `FamilySummary`; remaining `rounded-xl/lg` and old primary buttons restyled across 15 pages | Found by a scripted walk of every screen |
| ADD | `e2e/demo.spec.ts` and `e2e/capture-guide.spec.ts` updated for the workstation home and the new labels; capture adds `01b–01e` workstation shots; all 35 `docs/img/demo-guide/` images recaptured | The S16 gate and the guide follow the product |
| ADD | **Showcase guide** artifact (https://claude.ai/code/artifact/0696a658-591d-401a-8c25-2adc4fec8882): workstation act, run-from folders, architecture section (stack, diagram, module map, one-verdict trace, API surface, config, tests), project-environment setup and troubleshooting | User request |
| ADD | **Project Python environment** `hitl-ids/.venv` (gitignored), created from `C:\ProgramData\miniconda3\python.exe` (3.11.11); `requirements.txt` pins the tested set (XGBoost 3.2.0, FastAPI 0.136.0, Starlette 1.6.0, Uvicorn 0.37.0, pydantic 2.11.9, numpy 2.3.5, pandas 2.3.3, scikit-learn 1.7.1) | The user's `python` and `py` are 3.12 |
| FIX | `pyproject.toml`: declares FastAPI and Uvicorn (never listed), `httpx` in dev, and `[tool.setuptools.packages.find] include = ["apps*", "packages*"]` | `pip install -e ".[dev]"` failed for everyone ("Multiple top-level packages discovered in a flat-layout") and would not have installed the API |

### The "features no longer work" report — diagnosed, not a code defect

1. **Nothing was listening on :8000.** Vite was up on :5173 (twice: `127.0.0.1` and `::1`), so pages loaded and every
   API call failed. A scripted probe of all 28 screens and workstation actions against a fresh API + DB copy found
   0 failed requests and 0 console errors.
2. **The user's `python` is 3.12.6**, whose FastAPI 0.115.11 + Starlette 1.6.0 fail at import:
   `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'`. Its `py` launcher lists only
   3.12, 3.8 and 3.7 — **not** the miniconda 3.11.
3. **`py -m venv .venv` over the 3.11 environment rebased it onto 3.12** (`pyvenv.cfg home = …Python312`) while
   keeping cp311 wheels: `(.venv)` prompt, `python --version` 3.12.6, `Error importing numpy`. Rebuilt from the
   miniconda path; verified 3.11.11, imports, API serves, 411 tests pass.
4. **Correction:** earlier docs said "Python 3.12 has no matching `xgboost` build". False — pip resolves
   xgboost 3.4.1 for 3.12. The project stays on 3.11 because that is the tested set.

### Figma (figma-console MCP, Desktop Bridge plugin) — partial

File **"Untitled"** (key `SJ5fC4xzbME46JGrqwgdVO`): pages **Tokens** (21 colour variables + token sheet),
**Workstation** (hi-fi 1440×900 mock, pre-label-change), **Screens** (hi-fi *proposed* Overview, IP entity, Admin,
Evaluator + a Workstation copy — **these are proposals, not the product**), **Wireframes** (5 greyscale frames).
Requested and **not done**: full-fidelity designs of *every real screen* from login, plus a wireframe for each, on a
"Product screens" page. Blocked: the plugin **disconnected** after a temporary image server was started on :9231,
inside the port range the plugin scans (9223–9232). The plugin also refuses `createImageAsync` from localhost
("does not satisfy the allowedDomains"), so screens must be built as vector layers.

### Open for the next session (debugging)

See HANDOVER §0b. In short: Figma "Product screens" page; R4 (Overview page, IP entity page — endpoints exist, no
UI route yet); R5 is a mechanical restyle only; R6 PUM not regenerated; HANDOVER/plan do not track the rebuild
as S-steps; `ruff` never run (now installed in `.venv`); Vitest tests time out under CPU contention (pass alone).

---

## v1.24 — Console rebuild R4: Overview and the IP entity page (2026-09-14)

The user chose to finish the console rebuild before S17 (the plan still names S17 `NEXT`; the rebuild is off the
S-step graph). R4 gives the B4 and B5 endpoints from v1.22 their screens. No backend or contract change.
**411 Python tests (unchanged) · 120 web tests (103 + 17) · typecheck clean · `npm run e2e` passes.** Not committed.

### What landed

| | Change | Rationale |
|---|---|---|
| ADD | **`/analyst/overview`** (`pages/analyst/OverviewPage.tsx`), in the analyst nav after Workstation: flow volume by capture hour (chart + table), top source / destination addresses and destination ports, alerts by predicted class, verdicts in force, triage status, guardrail interventions | Proposal §4, analyst "Overview". Every figure is `GET /api/dashboard/breakdowns` or `/summary`; charts repeat as tables |
| ADD | **`/analyst/entities/ip/:ip`** (`pages/analyst/IpEntityPage.tsx`): summary, queue bands in contract order, attack classes, verdicts in force, top peers (each a link to its own page), destination ports, and a pivot to the workstation search | Proposal §4 "Entity (IP)". A 404 for an address no alert mentions shows the API's own message |
| ADD | Addresses link to the entity page from the Overview's top-talker tables and from the workstation context rail (`ContextRail.tsx`) | The analyst's next question about an address is "what else did it do?" |
| ADD | `overview.test.tsx` (9) and `ipEntity.test.tsx` (8); `BREAKDOWNS` and `ATTACKER_ENTITY` fixtures from the real demo database (read-only query), with two verdicts and one intervention added to `BREAKDOWNS` because the real database has none | Fixtures typed against the generated contract |
| DEC | Overview card titled **"Alerts by predicted class"**, not "attack classes" | `byAttackCategory` includes Benign |

### How it was built

Routes, nav, fixtures and the rail link by Claude; the two pages and their tests by two DeepSeek workers in
parallel (`timeout 1500`, one page each, no shared files), reviewed file by file. Review changed two things: the
Overview card title above, and the entity test's peer fixture, which claimed to be demo-database values but had
invented bands, classes, first-seen time and port — replaced with the real values. The worker also added empty
states to three cards the brief did not mention; kept, matching `DashboardPage`.

**Honest limits.** The two pages have not been looked at in a browser: `npm run e2e` passes but does not visit
them, and the guide was not recaptured. There is no eslint config in `apps/web`, so no lint ran. The Figma
**Screens** proposals were not compared (plugin unreliable, v1.23). `rehearse_demo.py` still not re-run after R3.

---

## v1.25 — Console rebuild R5: admin and evaluator screens (2026-09-14)

R4 committed as `98697a7`. R5 replaces the mechanical restyle of the admin and evaluator screens with layouts in the
workstation's style. No backend or contract change. **411 Python tests (unchanged) · 126 web tests (120 + 6) ·
typecheck clean · `npm run e2e` passes · all eight R4/R5 screens captured in Chromium at 1440 px, no console errors.**

### What landed

| | Change | Rationale |
|---|---|---|
| ADD | **`StatStrip`** in `components/ui.tsx`: a row of headline figures in the KPI-strip style, columns sized to the figure count | One primitive for both workers; the first version left empty cells on four-figure strips, found in the browser |
| CHG | **System Status** → operations overview: figures row (total, needs review, Tier 2, verdicts, guardrail actions, unresolved), service health and a new **Detector hits** card (a meter per detector evidence class) beside the latest run | Proposal §4 "Operations overview". `none` is left out of Detector hits: nothing flagging an alert is not a hit |
| CHG | **Guardrails**: three-column limits form; Save is the console's primary button (`bg-primary`, as "Record verdict") | A side-by-side layout was tried and reverted: the read-only settings table wrapped unreadably at 1440 px |
| CHG | **Audit Trail**: filter toolbar with Export CSV as the primary button; event types as colour-coded pills whose text is unchanged; pager above the table | Proposal §4 |
| CHG | **Scenarios** → experiment overview: "Newest run at a glance" shows the three arms side by side with precision@50 and its signed change against control (the −0.020 fall is shown) | Proposal §4 "Experiment overview" |
| CHG | **Run**: figures row; comparison and guardrail outcomes side by side; compact arms table (short headers with full-name titles, no wrapping); delta groups side by side | The arms table wrapped "C-guardrails-off" over three lines |
| CHG | **Metrics**: figures row; the uniform F1 bar chart replaced by **small multiples** — a precision / recall / F1 meter per class, amber below 0.99 | Eight bars between 0.93 and 1.0 read as identical; Infiltration's 0.933 now stands out |
| FIX | **Overview (R4)** histogram: one stacked bar per capture hour (flagged + not flagged) at 1080 px, hour table scrolls inside the card | Seen in the browser: paired bars over 108 hours drew as slivers, and the table ran 108 rows |
| ADD | 6 web tests (status 2, audit 1, scenarios 1, run 1, metrics 1); every existing admin and evaluator assertion passes unmodified | The existing tests pin the on-screen wording |

### How it was built

`StatStrip` and Guardrails by Claude — Guardrails holds the guardrail write path, which is never delegated; only its
layout and button changed, not validation or the `PUT`. Status + Audit and the three evaluator pages by two DeepSeek
workers in parallel (`timeout 1500`), each forbidden to edit shared files or existing assertions, reviewed by diff.
Review changed: the admin `BREAKDOWNS` fixture claimed demo-database values but its status mix was invented (the
comment now says synthetic); `none` removed from Detector hits; two ad-hoc primary-button styles replaced with the
existing one. The browser pass then found the histogram, the strip columns and the Guardrails wrap.

**Honest limits.** "Verdicts per analyst" (proposal §4) was not built: no endpoint reports it, and computing it in the
page would break the rule that the API defines every figure. The guide (`docs/img/demo-guide/`) was not recaptured, so
screenshots 21–31 and the published showcase show the pre-R5 screens. `rehearse_demo.py` still not re-run after R3.
Figma plugin still disconnected; proposals not compared.

---

## v1.26 — Console rebuild R6: the gate re-verified, the guide recaptured (2026-09-14) ← **current**

R5 committed as `288d95d`. R6 re-checks the S16 demo gate after the rebuild and brings the presenter's material up to
the product. No application code changed. **411 Python tests (unchanged) · 126 web tests · `npm run e2e` passes ·
`rehearse_demo.py` holds end to end · guide capture passes.**

### What landed

| | Change | Rationale |
|---|---|---|
| VERIFY | **`rehearse_demo.py`** re-run on a throwaway copy after R3–R5: "The demo narrative holds end to end." | Not run since R3 (HANDOVER §0b) |
| ADD | Guide capture takes **`04b-overview`** and **`04c-ip-entity`**, before any verdict changes the mixes | The guide had no shot of either R4 page |
| FIX | Capture spec: the workstation search now waits for the list to narrow to one card before clicking; System Status waits for service health and for both 5,000 figures (summary and breakdowns) | Found by running it: one run opened the wrong alert, and screenshot 21 was taken with the figures row still loading |
| CHG | All guide screenshots re-rendered (`docs/img/demo-guide/`, 37 files; 25 changed, 2 new) | 21–31 showed pre-R5 screens |
| CHG | **Showcase guide republished** (same URL, version 7): Act 2 gains the Overview and one-address walkthrough; Acts 7–8 describe the operations overview, Detector hits, audit pills, the newest-run glance and per-class panels; roles, API surface and feature coverage updated | The guide follows the product |

**Not done — needs the user.** The Preliminary User Manual was **not** regenerated. Its section 4 is 16 wireframes drawn by
`scripts/make_wireframes.py` from the pre-rebuild screens (no workstation, Overview or IP page), and
`scripts/build_user_manual.py` writes straight to `docs/FYP-26-S3-13_PrelimUserManual.docx`, which holds the user's own
edits. Rebuilding would overwrite them, so it waits for the user's decision.

---

## Open items

| Item | Blocker | Owner |
|---|---|---|
| Download corrected dataset | Kaggle credentials — `kaggle auth login` | User |
| Retrain to 7 classes incl. Infiltration | Depends on dataset | Claude |
| Re-run notebooks 01–03 against corrected data | Depends on retrain | Claude |
| Apply v0.3 + v1.0 changes to `plans/hitl-ids-demo-build.md` | none | Claude |
| `gh` PR/CI workflow steps | `gh auth login` not run | User |

## Provenance

Every quantitative claim above is reproducible by executing the notebooks in
`hitl-ids/notebooks/`, which read only the frozen fixtures in `hitl-ids/tests/fixtures/legacy/`.
All three execute with zero errors. Claims originating from delegated workers were re-verified
against source before entry here — see [`feasibility-study.md`](feasibility-study.md) for the
method and where it failed.
