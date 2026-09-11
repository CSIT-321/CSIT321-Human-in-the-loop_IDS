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

## v1.12 — Severity chart made configuration; ranking formula selected by experiment (2026-09-11) ← **current**

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
