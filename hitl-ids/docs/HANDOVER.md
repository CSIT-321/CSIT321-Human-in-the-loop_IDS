# HANDOVER — read this first in a new session

**Purpose.** Carry the full state of this project into a fresh session with zero loss of context
and minimal token cost. Everything a new session needs is here or one link away.

**Last updated:** 2026-09-16 (rev 23 — ranking provenance resolved, four stale claims corrected;
see §0b item 7) · **Branch:** `feat/demo-build` — tracking
`origin/feat/demo-build`, in sync with `origin/feat/demo-build` (**0 ahead, 0 behind** — verified 2026-09-16; the
R4→showcase-v9 work was pushed after rev 22, so the old "11 commits ahead" is stale) · `feat/s2-contracts` and `feat/s6-fusion` pushed earlier as view-only progress
branches ·
**Phases 2–5 DONE · the S16 demo gate PASSED** (S12, S13, S14, S16 in changelog v1.21) ·
**Console rebuild** (user request, `docs/console-rebuild-proposal.md`): R1–R6 DONE, **complete** ·
**S18a account separation landed** (user request): real sign-in — the seeded accounts
`g.ang`/`analyst-demo`, `admin`/`admin-demo`, `evaluator`/`evaluator-demo` (one per view); bcrypt +
8-hour JWT bearer; `X-Demo-Role` and the role dropdown/chips are gone; next is the plan's S17 (the
S18 remainder equally unblocked — confirm the order with the user) —
changelog v1.31 · **The queue now ranks by severity, and the band is a label (v1.31):**
`db.QUEUE_ORDER_BY` was `queue_priority, combined_score, id`. The band's first key put Tier 2 candidates
that are not severe at the top — **the whole top 50 was `Medium`** — so the queue now orders by
**severity worst-first, then operational score**. The order is defined once, in `db.queue_order(alias)`,
and the queue, the API, the metrics module, the scenario module and `cef.queue_key` all derive from it;
it had been written out in five places. **Invariant I5 is retired** (a disputed rule no longer outranks
a more severe finding; I2 still review-flags every override). `queue_class`/`queue_priority` remain as
the Tier 2 escalation label and the band tabs. **The three-arm evaluation was re-baselined** (run
`20260916T063856Z`): under the new order **feedback no longer costs a top-50 place** — precision@50
holds at 1.000 with **zero** false positives in the top 50 in every arm, where the band order fell to
0.980 and pushed a benign alert to **rank 1** (now rank 186). Remaining deltas are small and still
negative (precision@200 −0.010, mean rank −0.515) and are reported as measured. **Caveat, and the
measurement behind it:** six candidate orders were compared on both databases. **`data/demo.db` cannot
judge an order** — every candidate scores precision 1.000 at every cut-off, because its 996 flagged
alerts hold only 2 false positives and both sit far down, so the test is saturated. **`data/stress.db`
can**, and it prefers **evidence-first**, which with Tier 2 as a label reaches precision@100 **1.000**
against **0.770** for the band order it replaced. Severity carries no signal there (flat: Critical
0.447, Medium 0.661) because every injected false positive lands in `ml_only` — the degradation copies
a real attack's record onto a benign flow. It is a paired comparison, so the *relative* result is sound
even though the absolute precision is not. **Response:** severity-first stays the default (triage is
urgency, and it costs nothing on the real detector), and the contract gains an **`evidence` sort** so
the suspect-model case is one click away. Also in v1.29–v1.30: severity capped by the attack class's
ceiling read from `config/severity-chart.json`; ingest applying a family's stored learning; the
`unjudged` queue filter with a **Judged** control; 23 annotation callouts over the showcase screenshots;
and a showcase section on what "Rule" means · **User-testing prep batch landed (2026-09-15/16, in the unpushed commits):** PUM
v0.3 with the real sign-in section, `docs/tier1-analyst-workflow.md`,
`docs/workflow-test-cases.md` (the A–L hand-test protocol for the tester), showcase v8/v9
(`docs/ids-console-showcase.html`), and the **model bake-off** `notebooks/07_model_bakeoff.ipynb`
(LR collapses to 0.51 macro F1 at 78.7% accuracy; RF 0.962; XGBoost 0.966 ± 0.015 vs HistGB
0.969 ± 0.011 — a tie; XGBoost retained on the native-TreeSHAP tiebreak; decisions B1–B3; the
notebook is still untracked) · **Two 2026-09-16 demo features (uncommitted unless noted below): the
login password eye (hold-to-peek, auto-hides when the pointer leaves) and the queue's
`detectionMinScore`/`detectionMaxScore` filters** — the "not saturated" preset
(`evidence=ml_only + detectionMaxScore=99.999` → exactly 21 alerts) exists because 975 of 996
flagged alerts sit at exactly 100.0 and a confirming verdict there clamps; `AL-00576` (81.30 → 91.30,
Model only → Tier 2 by E2) is the demo beat, rehearsed as step 4. **Corrected 2026-09-16:** the beat
used `AL-02717` (88.48 → 98.48), which is **benign** in the capture and not even the first row under
an ascending detection-score sort — `AL-00576` at 81.30 is. Confirming a false positive as a True
Positive would have had the demo assert something false. `AL-02717` is the right alert for a
*dismissal*, which is how `system-workflow.md` already recorded it. Run
`python scripts/list_false_positives.py` before presenting to see both lists · **The queue's
inspection-sort tie-break fixed (v1.28):** it was a direction-blind `a.id ASC`, so a page whose
scores all tied came back identical ascending and descending — and 4,789 of 5,000 alerts (95.8%)
tie on their score. It now orders by evidence class, review flag, capture time and id, each
following the requested direction ·
**445 tests, 0 skipped** (Python, in `.venv`) + **132 web tests** (`apps/web`, `npm test`) +
the browser narrative (`npm run e2e`, passes with three real sign-ins) ·
**Python runs from `hitl-ids\.venv` (3.11) — see §0b before running anything** ·
`python scripts/run_detection.py` builds the demo database · `python -m uvicorn apps.api.main:app`
serves the API on :8000 · `cd apps/web && npm run dev` serves the console on :5173
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

**The demo gate (S16) has passed; the next step is S17** — the plan's *Step status* table is the
authority, and it marks S17 `NEXT`: the prefix flow exporter. **S18 (the full backend) is equally
unblocked** and may run in parallel; S17 is marked `NEXT` only because it comes first in the graph —
confirm the order with the user before starting either. To present the demo, follow
[`demo-script.md`](demo-script.md). Read the plan's S16 landed note and the S17 section before writing
anything. Then confirm the ground you are standing on:

```
cd hitl-ids && .venv\Scripts\activate  # every terminal; python --version must print 3.11.x (§0b)
python -m pytest                      # expect 445 passed, 0 skipped (sandbox blocking the temp
                                       # dir? add -p no:cacheprovider --basetemp=<scratchpad>)
python scripts/run_detection.py       # rebuilds data/demo.db: 5,000 flows -> 5,000 alerts, ~21 s
python scripts/rehearse_demo.py       # the S16 narrative through the API on a copy: 46 checks
cd apps/web && npm test && npm run e2e && cd ../..   # 128 web tests; the narrative in a browser
python scripts/run_evaluation.py      # the three arms over that database, ~3 s
python scripts/build_openapi.py --check   # the committed API contract is in step with the models
```

`npm run e2e` needs `HITL_PYTHON` pointing at a 3.11 interpreter (it starts its own API):
`set HITL_PYTHON=%CD%\.venv\Scripts\python.exe` from `hitl-ids` first. The databases are gitignored, so a
fresh checkout has to rebuild them; everything else is committed.

**Read [`evaluation-report.md`](evaluation-report.md) before quoting any number about feedback.**
S15 did not find the result the project wanted, and the honest version is the one to present:
similar-alert learning works and does not leak, but on this sample it *lowered* precision, because
the control queue was already perfect and the mechanism promoted a false positive to rank 1.

---

## 0b. Starting a debugging session — read before touching anything

**The last session (changelog v1.23) ended mid-debugging with the user.** Everything below was verified
on 2026-09-14 unless marked otherwise.

### Run the system (two terminals, both from `hitl-ids`)

```
:: terminal 1 — the API
cd "C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids"
.venv\Scripts\activate
python --version                         :: must print Python 3.11.11
python -m uvicorn apps.api.main:app      :: "Uvicorn running on http://127.0.0.1:8000"; leave it open

:: terminal 2 — the console
cd "C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids\apps\web"
npm run dev                              :: http://localhost:5173 — analysts land on /analyst/workstation
```

Check `http://localhost:8000/api/health` → `{"status":"ok","database":"…\\data\\demo.db","exists":true}`.
From Claude's Bash tool, call the environment directly: `.venv/Scripts/python.exe …` (no activation).

### Traps that already cost a session — check these first

| Symptom | Cause | Fix |
|---|---|---|
| Console loads but every panel errors / buttons do nothing | **API not running on :8000** (this was the whole "features no longer work" report) | Start terminal 1 |
| `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'`, paths show `Python312` | Ran under the user's system Python 3.12.6 (FastAPI 0.115 + Starlette 1.6) | Activate `.venv` |
| `(.venv)` in the prompt but `python --version` is 3.12; `Error importing numpy` | Someone ran `py -m venv .venv` or `python -m venv .venv` — both are 3.12 here; the `py` launcher does not list the miniconda 3.11 | `deactivate`, delete `.venv`, `C:\ProgramData\miniconda3\python.exe -m venv .venv`, activate, `python -m pip install -r requirements.txt` |
| `No module named 'apps'` | uvicorn run outside `hitl-ids` | `cd hitl-ids` |
| KPI strip dashes / Claim, notes, IP panel `NOT_FOUND` | API process older than the R1 endpoints | Restart the API |
| Two Vite servers on :5173 (`127.0.0.1` and `::1`) | A second `npm run dev` left running | Close one terminal |
| A Vitest test fails in the full run but passes alone (seen: `feedback.test.tsx`, `guardrails.test.tsx`) | Timeouts under CPU contention when typecheck/build/e2e run concurrently | Run `npm test` on its own; not a code defect |
| Figma MCP tools vanish mid-session | The Desktop Bridge plugin scans ports **9223–9232**; a server started on 9231 broke it | Never bind 9223–9232; re-run the plugin in Figma Desktop; restart Claude Code with `--continue` if tools stay missing |

### Files and facts the next session needs

- **Environment:** `hitl-ids/.venv` (gitignored) · `requirements.txt` (tested pins: xgboost 3.2.0, fastapi
  0.136.0, starlette 1.6.0, uvicorn 0.37.0) · `pyproject.toml` now lists FastAPI/Uvicorn and
  `packages.find include = ["apps*","packages*"]` (without it `pip install -e .` fails).
- **Console:** analyst home `/analyst/workstation` (`pages/analyst/WorkstationPage.tsx`,
  `features/workstation/`); the old Alert Queue and alert pages still exist and the e2e story uses them.
  Verdict labels are display-only (`features/feedback/categories.ts`); API category values are unchanged.
- **Showcase guide** (published artifact, private):
  https://claude.ai/code/artifact/0696a658-591d-401a-8c25-2adc4fec8882 — its source is a scratchpad file of the
  last session; to update it, read it back with the Artifact tool (`action: read`) and republish to that URL.
  Screenshots: `docs/img/demo-guide/` via `GUIDE_CAPTURE=1 npx playwright test capture-guide`.
- **Figma:** file "Untitled", key `SJ5fC4xzbME46JGrqwgdVO`, via the figma-console MCP. Pages Tokens · Workstation
  · Screens (*proposed* R4/R5 designs, not the product) · Wireframes. `createImageAsync` from localhost is
  refused by the plugin manifest, so screens must be built as vector layers.
- **Never commit or rebuild over** `docs/FYP-26-S3-13_PrelimUserManual.docx` (user's edits; the generated
  `_v0.2.docx` beside it is committed), `docs/FYP-26-S3-13_PUM.pdf` or
  `hitl-ids/Screenshot 2026-09-13 210609.png` (the design reference). All three are uncommitted by design.

### Open now (verified 2026-09-16)

1. **Figma "Product screens" page** — still requested, still blocked: the Desktop Bridge plugin is
   not running (probed 2026-09-16). The user must open Figma Desktop → Plugins → Development →
   Figma Desktop Bridge → Run; then the page can be built from `docs/img/demo-guide/` as vector layers.
2. **User-testing prep batch (5 commits).** PUM v0.3 (`FYP-26-S3-13_PrelimUserManual_v0.3.docx`,
   guide recaptured 2026-09-15), `docs/tier1-analyst-workflow.md`, `docs/workflow-test-cases.md`,
   showcase v8/v9 (`docs/ids-console-showcase.html`). Uncommitted **by design**: the user's edited
   `.docx`, `PUM.pdf`, the design-reference screenshot. **Correction (2026-09-16):** this item used
   to list `notebooks/07_model_bakeoff.ipynb` and the showcase's bake-off paragraph as "untracked,
   pending a decision". Both were **already committed** — `git ls-files` confirms the notebook is
   tracked and clean, and the paragraph landed in `54e067d`. Nothing exists only on this machine.
3. **`ruff` — first run 2026-09-16:** ~140 findings, mostly style (RUF100 44, F811 18, I001 17,
   B008 10 — FastAPI `Depends`, a known false positive for this pattern). Nothing blocking; no
   cleanup pass has been done.
4. **Plan tracking unchanged:** the rebuild and the prep batch are not S-steps; the plan's S17
   `NEXT` stands. S18 is equally unblocked — confirm the order with the user before starting either.
5. **Verified this session on the working tree:** 445 Python tests passed (the sandbox blocks the
   default pytest temp dir — use `-p no:cacheprovider --basetemp=<scratchpad>`), `rehearse_demo.py`
   holds end to end, `npm test` and `npm run e2e` pass, and `data/demo.db` is pristine (5,000
   alerts, 0 verdicts, 3 seeded users, 1 run) — ready for a tester pass or a demo as-is.
6. **Full data + presentation validation (2026-09-16, commit 54e067d):** a fresh
   `run_detection.py` rebuild is **content-identical** to the previous database (same hash over all
   5,000 alerts' semantic fields); `run_evaluation.py` reproduced the pre-registered run
   **metric-for-metric** (new record `20260916T032933Z` beside `20260912T032022Z` in
   `history.jsonl`; the only differences are run id, commit and the UUID-bound `sequence_digest` —
   the 40-verdict sequence is semantically identical, so the digest proves same-database fidelity
   only); `build_openapi.py --check` clean; **all seven notebooks execute with zero errors** in
   `.venv` after adding dev-only tooling (`nbclient`, `ipykernel`, `matplotlib`, `shap` —
   `requirements.txt` untouched; the notebooks previously ran only in the user's miniconda Jupyter);
   every headline figure quoted in the docs matches the data (644 Tier 2 candidates, 200
   corroborated, 0 signature overrides, 4,004 not flagged; showcase bake-off numbers match
   notebook 07's stored outputs exactly). Fixed: PUM expected-test count 411 → 445 (this line said 426 until 2026-09-16;
the suite is 445 — see §0b item 5). Known cosmetic:
   the showcase HTML has no `<!DOCTYPE html>` (quirks mode) — it has always been styled that way;
   do not add a doctype without re-checking every section.
7. **Ranking provenance — resolved 2026-09-16, and a defect fixed.** The formula question has a
   deterministic answer: **sel-3 selected C1**, and the code has always run C1. The `"formula": "C2"`
   that appeared in every `evaluation/ranking/runs/*/config.json` was a **serialisation artefact**:
   `experiment.py` wrote `asdict(RankingParams())` — the dataclass's own *defaults* (C2/M1) — under a
   key named `params`, which read as "the parameters used" while describing nothing that ran. The
   arms executed are enumerated in the same file (`for formula in FORMULAS` → C0/C1/C2/C3), each
   records its own values in `runs[]`, and the winner is `selection[0]`. **Fixed:** the key is now
   `candidate_space` (`{formulas, movements, family_keys, chosen_by_rule}`); nothing anywhere read
   the old key, so no consumer changed. The three 2026-09-11 runs are left untouched as history;
   a fresh run `20260916T073135Z` carries the corrected record and **reproduced run 3 exactly** —
   identical ordering and identical values — so the selection is stable, not a seed artefact.
   **How thin C1's win is, which the docs must not overstate:** C1 beat C2 on
   `mean_attack_position` by **0.0001** (0.0828 vs 0.0829) — the *only* metric separating them;
   demotions, Tier 2 precision and precision@100 tie exactly. The **control (no feedback) is
   0.0829**, so C1's feedback improves triage position over doing nothing by 0.0001. **C0 would
   rank #1 on raw performance** (same 0.0828, and the lowest class churn of any arm at 13.00) and is
   disqualified *only* by `meets_q27` — its fixed steps do not scale with attack severity. The
   selection is therefore policy-driven at the top, not evidence-driven, and the honest claim is
   "chosen by a pre-registered rule", never "measured best".
   **Movement is a deliberate lead override, and must be recorded as one:** sel-3's #1 pick is
   **C1+M2+coarse**; the code runs **C1+M1**. M2's sole advantage is `class_changes` (13.00 vs
   25.33) — internal band churn, not a triage outcome; every metric ranked above it ties. The
   evidence supports retaining M1 on risk grounds: in run 2, **before the agreement gate existed,
   M2 scored Tier 2 precision 0.7418 against M1's 1.0000 and doubled Tier 2 load (504 vs 243)**.
   M2 is safe only because the gate contains it; M1 does not depend on the gate to be safe.
   **Arm C's explanation corrected:** §0b item 6 and the S15 narrative said "the sequence had no
   dismissals, so no guardrail could bind". The mechanism is better stated: no guardrail *policy*
   bound — the **100 ceiling** did. 975 of 996 flagged alerts sit at exactly 100.0 and the
   pre-registered sequence emits only positive verdicts, so every one of the 40 verdicts clamped at
   the top of the range. That clamp is active in **both** arms, which is *why* arm C could not
   diverge from B (`C_minus_B` is all zeros, `extra_breaches_without_guardrails: 0`).

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
> Phase 1 **DONE** · Phase 2 **DONE** (S5, S4b, S6, S7a, S7b, S8) · Phase 3 **DONE** (S9, S10a,
> S10b) · Phase 4 **complete** (S11–S14) · Phase 5 **complete** (S15, and the S16 demo gate passed) ·
> Phase 6 not started — **next: S17**, with S18 equally unblocked.

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
  tests/   376 tests in 15 files, 0 skipped - run: python -m pytest  (pyproject sets pythonpath)
           test_plan_sync.py fails if the plan, this file and the changelog disagree
  tests/fixtures/legacy/   8 FROZEN files - never regenerate
  scripts/        15 scripts, all runnable; run_detection.py builds the demo database (S9),
                  run_evaluation.py runs the three arms (S15), build_openapi.py publishes
                  the API contract (S10a)
  rules/rule-set-s4b-1.json            7 rules, 2 enabled (FTP + SSH brute force)
  docs/           HANDOVER · system-workflow (start here) · plan-changelog (v0.1-v1.16) ·
                  ranking-and-escalation-design · evaluation-report (S15, read before quoting
                  any feedback number) · deviations (the register the plan mandates) ·
                  preliminary-user-manual (+ img/wireframes/: 16 generated screens,
                  rebuild with scripts/make_wireframes.py) ·
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
- **Workers stall silently.** In v1.21 a GLM worker and a DeepSeek worker both stopped making tool calls
  for 11+ minutes with no error. Wrap every worker in `timeout 1500`, run at most two at once, and check
  progress in its transcript (`~/.claude/projects/<cwd-slug>/*.jsonl`), not its output file — the output
  is only written at the end. **Stopping the shell does not stop the `claude` child** on Windows: find
  it by command line (`claude-glm` / `claude-deepseek` settings path) and kill it by process id.
- **GLM's main query logs `unrecognized_model`**; prefer DeepSeek for code workers until that is resolved.

**Verification that finds what tests miss**
- **Run the browser end-to-end test** (`npm run e2e`) after any API or page change. In v1.21 it found a
  SQLite cross-thread 500 that 381 passing Python tests, `TestClient` and `curl` all missed, because only
  a browser fires an alert's three reads at once.
- **Rehearse on copies, never on `data/demo.db`.** Verdicts and the audit trail are permanent.

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
- **Use the project environment `hitl-ids/.venv`** (Python 3.11.11, built from
  `C:/ProgramData/miniconda3/python.exe`, installed from `requirements.txt`). The full suite passes there with
  0 skipped. From Bash: `.venv/Scripts/python.exe`.
  - The machine's `python` and `py` are **Python 3.12.6 / pandas 3** with an incompatible FastAPI 0.115 +
    Starlette 1.6 and no `xgboost`. `py -0p` lists 3.12, 3.8, 3.7 only — never create the environment with
    `py` or bare `python` (§0b).
  - Correction (v1.23): 3.12 *can* install xgboost (3.4.1); the project stays on 3.11 because that is the
    tested set, not because 3.12 is impossible.
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
| ~~10~~ | ~~S10b — the route handlers~~ | **DONE 2026-09-12** | `apps/api/{deps,mappers,routes,main}.py`; 34 tests. Every contracted operation implemented; `uvicorn apps.api.main:app` serves the 5,000-alert database. **NFR-04 measured for real: queue p95 19.3 ms, detail p95 6.2 ms** against a 2,000 ms budget. Three bugs caught by running it — changelog v1.19. Not delegated: the write path and the shared mappers could not be split cleanly |
| ~~11~~ | ~~S11 — web shell, role switching, design system, typed client~~ | **DONE 2026-09-13** | `apps/web/`: client generated from `openapi.json` (`npm run check:api` guards it), design tokens in Tailwind, three role shells with per-role nav, stub role switch labelled on screen. 30 web tests. Architecture by Claude, components by a DeepSeek worker, reviewed file by file. Changelog v1.20 |
| ~~12~~ | ~~S12 — analyst path · S13 — admin path · S14 — evaluator path~~ | **DONE 2026-09-13** | Components by DeepSeek workers, reviewed file by file; the verdict form, the score-adjustment chain and the guardrail messaging by Claude. Contract additions: `sourceRecordId` + search, `GET /api/evaluation/runs`. Changelog v1.21 |
| ~~13~~ | ~~S16 — demo assembly and rehearsal (the gate)~~ | **DONE 2026-09-13** | Narrative corrected to the `Port Scan / 445` family (deviations E6). `rehearse_demo.py` 41/41 on a copy and on a freshly seeded database; `npm run e2e` passed in Chromium. Three defects found by the browser run, all fixed with tests. Script: `docs/demo-script.md`. Changelog v1.21 |
| ~~14~~ | ~~S18a — account separation: real login (JWT, bcrypt, RBAC)~~ | **DONE 2026-09-15** | `apps/api/auth.py`: bcrypt, 8-hour HS256 bearers, `current_user` + `require_role` on the real role, `/api/auth/login` + `/api/auth/me`, `last_login`. Three seeded accounts (`g.ang`, `admin`, `evaluator`) self-heal on first sign-in; `_acting_user` gone — writes attribute to the signed-in account. `X-Demo-Role`, the TopBar role dropdown and the login role chips deleted end to end. 15 new tests (`tests/test_auth.py`); `rehearse_demo.py` and the e2e narrative sign in per account. Changelog v1.27 |
| 15 | **NEXT →** S17 — prefix flow exporter (post-demo) | Claude | S18 (full backend) is equally unblocked and may run in parallel; confirm the order with the user first. Read the plan's S17 section: schema reconciliation against `feature-columns.json` must stop and report, never silently coerce |

Full detail per step: [`../../plans/hitl-ids-demo-build.md`](../../plans/hitl-ids-demo-build.md).

**Console rebuild (user request, off the S-step graph)** — tracked in
[`console-rebuild-proposal.md`](console-rebuild-proposal.md) §6, not in the table above: R0–R3 **DONE**
(changelog v1.22 backend, v1.23 design system + workstation) · R4 **DONE** (v1.24, Overview + IP entity) ·
R5 **DONE** (v1.25, admin + evaluator) · R6 **DONE** (v1.26, gate, guide, showcase, PUM v0.2). **The rebuild is
complete**; the plan's S17 is next (S18 equally unblocked — confirm the order with the user). Open items: §0b.

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
