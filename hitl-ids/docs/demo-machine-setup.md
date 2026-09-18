# Setting up the demo on a different machine

**Every step below was run end to end on 2026-09-18**, from a bare clone of
`feat/demo-build` at `413cb77`, in a directory that had never held this project.
The timings are what it actually took, not estimates.

The console guide (`ids-console-showcase.html`) assumes the system is already
running. This document is how you get there on a machine that has never seen it.

---

## What a clone gives you, and what it does not

A clone **is** enough to rebuild everything. Nothing is missing, and nothing has
to be copied by hand from the original machine.

| Present in the clone | Size |
|---|---|
| `data/processed/demo_sample.csv` — the 5,000 flows the demo runs on | 2.9 MB |
| `models/xgboost_ids_model.json` — the trained 8-class model | 3.2 MB |
| `rules/rule-set-s4b-1.json` · `config/severity-chart.json` | small |
| `requirements.txt` · `apps/web/package-lock.json` — the pinned versions | small |

| **Absent by design — you create these on the new machine** | Built by |
|---|---|
| `data/demo.db` (the demo database) | `scripts/run_detection.py`, ~26 s |
| `.venv` (the Python environment) | `python -m venv`, ~550 MB |
| `apps/web/node_modules` | `npm ci`, ~196 MB, ~8 s |

The repository is about 810 MB cloned, most of it the frozen `stage-1`…`stage-5`
research record and the document images. On a slow connection, clone it the
night before rather than on the morning.

---

## What the machine needs first

| Requirement | Why, and what goes wrong without it |
|---|---|
| **Python 3.11** | Non-negotiable. The pinned FastAPI 0.136 / Starlette 1.6 set is tested on 3.11 only. On 3.12 the API fails at import with `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'`. |
| **Node 20 or newer** | Verified on Node 22.12.0 with npm 10.9.0. Vite 8 will not run on Node 18. |
| **Ports 8000 and 5173 free** | The API and the console. Nothing else may be listening. |
| **git** | To clone. |

**On Windows, `py -0p` usually does not list a 3.11.** It shows 3.12, 3.8, 3.7 —
which is exactly the trap that has cost this project a session before. Install
Python 3.11 explicitly (python.org or miniconda) and create the environment with
that interpreter's **full path**, never with bare `python` or `py`.

---

## The setup, in order

Run everything from `hitl-ids/`. Each block is one terminal.

### 1 · Clone

```
git clone https://github.com/CSIT-321/CSIT321-Human-in-the-loop_IDS.git
cd CSIT321-Human-in-the-loop_IDS
git checkout feat/demo-build
cd hitl-ids
```

### 2 · The Python environment  (~2 minutes)

```
<full path to python 3.11> -m venv .venv
.venv\Scripts\activate
python --version                      :: MUST print Python 3.11.x - stop here if not
python -m pip install -r requirements.txt
```

Verify the three that matter:

```
python -c "import fastapi, xgboost, pandas; print(fastapi.__version__, xgboost.__version__, pandas.__version__)"
```

Expect `0.136.0 3.2.0 2.3.3`.

### 3 · Build the demo database  (~26 seconds)

```
python scripts/run_detection.py
```

Expect `5,000 flows -> 5,000 alerts` and `"tier2_candidates": 644`.

> **If `data/demo.db` already exists, delete it first.** The script **appends** a
> detection run to whatever database it finds. Run it twice and you get 10,000
> alerts across two runs, with every old verdict still in place.

### 4 · The console's dependencies  (~10 seconds)

```
cd apps\web
npm ci
cd ..\..
```

`npm ci` — not `npm install` — so the pinned lockfile is honoured exactly.

### 5 · Start it  (two terminals, both from `hitl-ids/`)

```
:: terminal 1 - the API
.venv\Scripts\activate
python -m uvicorn apps.api.main:app

:: terminal 2 - the console
cd apps\web
npm run dev
```

Open <http://localhost:5173>. Sign in as `g.ang` / `analyst-demo`.

**The three accounts seed themselves on first sign-in** — `g.ang`/`analyst-demo`,
`admin`/`admin-demo`, `evaluator`/`evaluator-demo`. A freshly built database has
no `users` rows until someone signs in; that is expected, not a fault.

---

## Prove it before the audience arrives

```
curl http://localhost:8000/api/health
```

`{"status":"ok", ... "exists":true}`. Then on the Workstation, check the KPI strip:

| Reads | Meaning |
|---|---|
| **5,000** total alerts | the database built correctly |
| **644** Tier 2 candidates | the severity chart and fusion ran |
| **0** verdicts | nobody has judged anything — a clean board |
| **1** detection run (System Status) | you did not run `run_detection.py` twice |

If verdicts is not 0, or the run count is 2, delete `data/demo.db` and rebuild.

Optional, and worth it if you have ten minutes:

```
python -m pytest                    :: 466 passed
python scripts/rehearse_demo.py     :: 47 checks, on a copy - never touches demo.db
cd apps\web && npm test             :: 157 passed
```

---

## What will actually go wrong

| Symptom | Cause | Fix |
|---|---|---|
| `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'` | The environment is Python 3.12 | Delete `.venv`, recreate with a 3.11 interpreter's full path |
| `(.venv)` shows but `python --version` says 3.12 | Created with `py -m venv` or bare `python` | Same fix — the `py` launcher does not list 3.11 |
| `No module named 'apps'` | uvicorn started outside `hitl-ids/` | `cd` to `hitl-ids` first |
| Console loads, every panel says "Cannot reach the API" | The API is not running on :8000 | Start terminal 1 |
| KPI strip reads 10,000 alerts | `run_detection.py` ran over an existing database | Delete `data/demo.db`, rebuild |
| Strip shows verdicts before anyone judged | The database carries a previous session's work | Delete `data/demo.db`, rebuild |
| `Port 5173 is already in use` | A dev server is already running | Close it, or let Vite pick the next port and use that URL |
| Pages load but styling is wrong | `npm ci` did not finish | Re-run it from `apps/web` |

---

## Rehearse on the demo machine, not only on yours

The console is identical, but the machine is not. Before the audience:

1. Run the full narrative once, following [`demo-runbook.md`](demo-runbook.md).
2. **Then delete `data/demo.db` and rebuild it**, so the board is clean again.
3. Check the strip reads 5,000 / 644 / 0 verdicts / 1 run.

Screen resolution is the one thing that differs and cannot be tested from here:
the workstation is a three-column layout, and below about 1280 px wide the
context rail drops. Open it on the actual projector resolution once.
