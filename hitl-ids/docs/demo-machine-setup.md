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
| `.venv` (the Python environment) | `py -3.11 -m venv`, ~550 MB |
| `apps/web/node_modules` | `npm ci`, ~196 MB, ~8 s |

The repository is about 810 MB cloned, most of it the frozen `stage-1`…`stage-5`
research record and the document images. On a slow connection, clone it the
night before rather than on the morning.

---

## What the machine needs first

| Requirement | Why, and what goes wrong without it |
|---|---|
| **Python 3.11** | **Assume the machine does not have it** — step 2 installs it. Non-negotiable: The pinned FastAPI 0.136 / Starlette 1.6 set is tested on 3.11 only. On 3.12 the API fails at import with `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'`. |
| **Node 20 or newer** | Verified on Node 22.12.0 with npm 10.9.0. Vite 8 requires a current LTS; do not assume an older Node will do. |
| **Ports 8000 and 5173 free** | The API and the console. Nothing else may be listening. |
| **git** | To clone. |

**On Windows, `py -0p` usually does not list a 3.11** — it shows 3.12, 3.8, 3.7.
That is the trap that has already cost this project a session, so step 2 installs
one before anything else and step 3 names it explicitly.

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

### 2 · Get Python 3.11 onto the machine  (~5 minutes)

**Assume it is not there.** A current Windows machine typically has 3.12 or
nothing, and 3.12 does not work — see the table above. Check first:

```
py -0p                                :: lists every Python the launcher knows
```

If no `3.11` line appears, install one. Any 3.11.x will do; the project was
built on 3.11.11 and the pinned set installs on any of them.

**Route A — the python.org installer. Use this one unless you have a reason
not to.** Download the latest **Python 3.11** Windows installer from
<https://www.python.org/downloads/> (open "Looking for a specific release?" —
3.11 is no longer the newest, so it is not the big yellow button; 3.11.9 is the
last 3.11 with a Windows installer). In the installer:

- Tick **"Install launcher for all users"** — this is what makes `py -3.11` work
  afterwards. It is on by default.
- You do **not** need "Add python.exe to PATH", and leaving it off avoids
  displacing the machine's existing Python.
- A per-user install needs no administrator rights.

Then confirm the launcher can see it:

```
py -0p                                :: a 3.11 line must now appear
py -3.11 --version                    :: Python 3.11.x
```

**Route B — Miniconda, if the machine already has it.** Conda can create a 3.11
without touching the system Python:

```
conda create -y -n hitl311 python=3.11
conda env list                        :: note the path printed for hitl311
```

The interpreter is `<that path>\python.exe`, and you use it in step 3.

**Route C — `winget`, only if it exists.** Not all machines have it (the one
this was written on does not):

```
winget install Python.Python.3.11
```

> **Do not use `python -m venv` or `py -m venv` without a version.** Both pick
> the machine's default, which is where the 3.12 failure comes from. Always name
> the interpreter: `py -3.11 -m venv` or the full path.

### 3 · Build the environment  (~2 minutes)

```
py -3.11 -m venv .venv                :: or: <full path to a 3.11>\python.exe -m venv .venv
.venv\Scripts\activate
python --version                      :: MUST print Python 3.11.x - stop here if not
python -m pip install -r requirements.txt
```

Verify the three that matter:

```
python -c "import fastapi, xgboost, pandas; print(fastapi.__version__, xgboost.__version__, pandas.__version__)"
```

Expect `0.136.0 3.2.0 2.3.3`.

### 4 · Build the demo database  (~26 seconds)

```
python scripts/run_detection.py
```

Expect `5,000 flows -> 5,000 alerts` and `"tier2_candidates": 644`.

> **If `data/demo.db` already exists, delete it first.** The script **appends** a
> detection run to whatever database it finds. Run it twice and you get 10,000
> alerts across two runs, with every old verdict still in place.

### 5 · The console's dependencies  (~10 seconds)

```
cd apps\web
npm ci
cd ..\..
```

`npm ci` — not `npm install` — so the pinned lockfile is honoured exactly.

### 6 · Start it  (two terminals, both from `hitl-ids/`)

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
| `(.venv)` shows but `python --version` says 3.12 | Created with `py -m venv` or bare `python`, both of which take the default | Delete `.venv`, recreate with `py -3.11 -m venv .venv` |
| `py -0p` lists no 3.11 at all | The machine has never had it | Step 2 — install it before going further |
| `py: can't find a suitable Python` after installing | The launcher was not installed with it | Use the interpreter's full path instead: `C:\Users\&lt;you&gt;\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv` |
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
