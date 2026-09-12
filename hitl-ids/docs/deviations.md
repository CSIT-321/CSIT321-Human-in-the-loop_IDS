# Deviations register

**What this file is for.** The plan mandates it in two places — decision D10 (*"Deviations logged in
`hitl-ids/docs/deviations.md`"*) and the plan mutation protocol (*"Steps may be split, inserted,
reordered or abandoned. Record the change and its reason in `docs/deviations.md`"*) — and it is
cited by S3, S4b, S6 and S7. It was **never created**; the changelog absorbed its job in practice.
Created 2026-09-12 and back-filled from `plan-changelog.md` v0.1–v1.16.

**Division of labour, so this does not drift again:**

| File | Answers |
|---|---|
| [`plan-changelog.md`](plan-changelog.md) | *Why* we changed our minds, with the evidence, in version order |
| **this file** | *What now differs* from the approved documents and from the plan's own original steps — a flat register, not a narrative |
| [`../../plans/hitl-ids-demo-build.md`](../../plans/hitl-ids-demo-build.md) | What we are building and in what order — **canonical for the next step** |
| [`HANDOVER.md`](HANDOVER.md) | Current state for a new session |

Two entries here can never be closed by editing a document: the PRD, URS and TDM are **reference-only
and are not amended** (D10). A divergence from them is recorded, not fixed.

---

## A. Deviations from the approved documents (PRD / URS / TDM)

| # | Approved documents say | We do | Why | Evidence |
|---|---|---|---|---|
| A1 | Dataset CICIDS2017 | **Corrected CSE-CIC-IDS2018** (Engelen et al., IEEE CNS 2022) | The original labels are wrong in ways that invalidate the headline metrics | D1 · changelog v1.1 |
| A2 | 7 attack classes | **8 classes** — `Port Scan` split out of `Infiltration` | 99.6% of "Infiltration" is NMAP portscan; true infiltration is 317 flows in 63.2M | Q19 · v1.2 · [`finding-infiltration-mislabelling.md`](finding-infiltration-mislabelling.md) |
| A3 | PostgreSQL | **SQLite for the demo**, Postgres at S18 | Schema was written for Postgres in S2, so the migration is a port not a rewrite | D3 · v1.5 |
| A4 | TDM §6.2.7 weighted-sum fusion | **Complementary Evidence Fusion**, weights deleted | Scores from different evidence classes are not commensurable; the weights were provably inert (ρ = 1.0000 across every setting) | v1.0 · v1.8 |
| A5 | Real authentication | **Role-switch stub** until S18 | Demo-first (user's standing instruction) | D3 · plan S10a |
| A6 | "Six feedback categories" | **Five scoring categories**, plus `duplicate` as a *queue action* | `feedback-engine.js:80-112` implements five; URS UC-SA-15 defines `duplicate` as link-and-suppress, not a score change. The docs fold a queue action into the scoring set | v1.9 |
| A7 | Ground truth available to the system | **Ground truth is not in the schema at all** | Label leakage. The evaluation reaches it by one join on `flow_data.source_record_id` | v1.5 · S15 |
| A8 | 91-column schema described as 79 columns | **91 columns**; `CWE Flag Count` → `CWR Flag Count` | Typo in the source documentation, confirmed against the release | v1.1 |
| A9 | ~35 TDM endpoints | **10 demo-path endpoints** at S10; the rest at S18 | Deliberately narrow; "adding endpoints while we're here" is on the anti-pattern list | plan S10a |

## B. Plan mutations — steps split, inserted, moved

| # | Mutation | Reason | Logged |
|---|---|---|---|
| B1 | **S4b inserted** between S5 and S6 | Fusion depends on signature precision, which had to be earned before fusion could be specified | plan v1.0 |
| B2 | **S10 split into S10a (contract) / S10b (handlers)** | "S11 starts once OpenAPI is frozen" was circular — FastAPI generates OpenAPI *from* handlers. S10a restores real parallelism | plan v0.3 |
| B3 | **S15 moved before S10a** | `GET /api/evaluation/*` response schemas cannot be written before the metrics exist | plan v0.3 |
| B4 | **S7 split into S7a (direct feedback) / S7b (similar-alert learning)** | Two separable claims with different risk; S7a is one verdict on one alert, S7b carries it to a family behind a gate | v1.10 · v1.14 |
| B5 | **S3's `FlowSource` seam moved into S9** | It was assumed complete with Phase 1 and was not built at all; found while writing `system-workflow.md` | v1.9 · v1.15 |
| B6 | **S6 decoupled from S4** | The golden test that created the dependency was deleted | plan v1.0 |
| B7 | **Evaluation code lives in `packages/evaluation/`**, not the plan's `evaluation/` | `evaluation/` holds experiment *records* (`ranking/`, `three-arm/`); code belongs beside the other packages | v1.16 |
| B8 | **`packages/detection/pipeline/`** replaces the plan's `packages/detection/ingest/` | It holds the ingest seam *and* the predictor, store and runner — one batch-run package | v1.15 |

## C. Component-level deviations

| # | Deviation | Reason | Logged |
|---|---|---|---|
| C1 | **Five rules retired, two retuned and kept.** Retired: `SIG-DOS-HIGH-RATE-FLOW`, `SIG-DDOS-HIGH-RATE-FLOW`, `SIG-BOTNET-BEACON-FLOW`, `SIG-WEB-ATTACK-FLOW`, `SIG-INFILTRATION-LONG-FLOW`. **Kept and retuned: `SIG-FTP-BRUTE-FORCE` and `SIG-SSH-BRUTE-FORCE`** | Plan v1.0 had listed FTP among the retirements on *uncorrected* data. On corrected data both brute-force rules reach precision 1.000 and are the only rules that fire | v1.3 · v1.6 |
| C2 | `SIG-SSH-BRUTE-FORCE` threshold is **`flowPacketsPerSecond ≥ 10.66689`**, not the plan's 20 | Re-derived on corrected data; the plan's 20 came from the uncorrected sweep | v1.6 |
| C3 | **`infiltration_alert_floor = 75` kept** (the plan asked for an explicit keep-or-remove decision) | It exists at `feedback-engine.js:65-69`, the collaborator independently retained it, and Infiltration is the highest-severity class on the chart (9.5) | v1.10 |
| C4 | **A floor never *raises* a score.** The JS engine lifted a sub-floor alert up to the floor on negative feedback | A "false positive" verdict that raises a score is indefensible | v1.10 |
| C5 | **`signature_override` is frozen entirely (invariant I3)**; the JS engine only preserved its review flag | A precision-1.000 rule the model disputes is either a rule regression or analyst error — both belong with the administrator, not in a score decay | v1.10 |
| C6 | **`uncertain` folded into `needs_investigation`** | Identical effect: no score change, forces review | v1.10 |
| C7 | **`escalate` counts as a confirmation for family learning**; the collaborator's engine treats it as teaching nothing | Design match result S = 1. Reversible in one line | v1.14 |
| C8 | **A dismissal withdraws an alert's "→ Tier 2" marker** but moves it no lower | Clearing an alert is a status change, not a score change. Reversible in one line | v1.14 |
| C9 | **Severity chart is configuration** (`config/severity-chart.json`, versioned `sev-1`), never code | Q27/Q28: values must be changeable without a code change, and every run records the version it used | v1.12 |
| C10 | **TreeSHAP is computed inside the detection run** (D8 said "precomputed") | Precomputing it in a side script left NFR-01's claim outside the pipeline; in-run it still meets the budget | v1.15 |
| C11 | **Every flow becomes an alert**, including the 4,004 no detector flagged | They are the queue's bottom band and the evaluation's denominator; dropping them turns recall into precision | v1.15 |
| C12 | **Schema departures from the TDM** are each marked `DEVIATION` inline in `schema.sql` and enumerated in changelog v1.5; a test fails on any unlogged column | The schema is the keystone; silent drift there is unrecoverable | v1.5 |
| C13 | **The queue is ordered by `db.QUEUE_ORDER_BY` (`queue_priority, combined_score DESC, id ASC`)**, not by `evidence_priority` as plan v1.0's S10a note said | `evidence_priority` predates S7b. Feedback moves an alert between queue *bands* (Q24); sorting on evidence class would make the re-ranking invisible in the API — the one thing the demo exists to show | plan v1.1 |

## D. Rejected, with the reason — do not re-propose

These appear in `HANDOVER.md` §5 as well. Repeated here because the plan cites this file as the
register of record.

| # | Rejected | Why |
|---|---|---|
| D-1 | **Suricata as the prefix module** (plan S17 had listed it as optional) | It cannot emit CIC flow features, so it cannot feed the model. Use the GintsEngelen CICFlowMeter fork |
| D-2 | **Retuning the fusion weights** to fix coverage | Mathematically inert while co-occurrence is low; hides the problem |
| D-3 | **Retuning rules to restore complementarity** | Tested and closed: precision reached 1.000 but `signature_only` stayed 0 |
| D-4 | **A curated demo slice** where both detectors fire | Would conceal real recall; fails viva scrutiny |
| D-5 | **Demo on static JSON** with no persistence | Feedback that dies on refresh cannot demonstrate the thesis |
| D-6 | **Strengthening a feedback sequence until arm C shows a suppression** | Plan v0.3 struck this out: it tunes the experiment until it yields the wanted answer. Replaced by pre-registration |

## E. Withdrawn claims — carried here because a document still asserted them

| # | Claim | Status |
|---|---|---|
| E1 | "The detectors are **complementary** — the signature layer catches 8 brute-force attacks the ML model labels Benign" (plan v1.0 preamble) | **WITHDRAWN.** `signature_only = 0` on corrected data. Corrected in plan v1.1 |
| E2 | "**Zero co-occurrence**" (notebook 01, F5) | **WITHDRAWN.** Agreement occurs 200 times, which is what makes the `corroborated` band real |
| E3 | "The 8 known complementary detections occupy review-queue positions 1–8" (plan S6 exit criterion) | **UNSATISFIABLE.** No such alert exists. Replaced in plan v1.1 |
| E4 | "At least one `signature_override` alert in the queue" (plan S16 demo precondition) | **TRIGGERED THE PLAN'S OWN STOP CONDITION.** The corrected dataset yields zero. The demo narrative is rewritten in plan v1.1 |
| E5 | The 0.9882 macro F1 as a real-world capability claim | **NEVER TO BE MADE.** A testbed artefact: single-tool attack generation gives each class a constant flow fingerprint. The port-shortcut hypothesis was tested by ablation and rejected (−0.0011) |
