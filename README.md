# Human-in-the-Loop Intrusion Detection System (FYP-26-S3-13)

A web console for a Security Operations Centre (SOC). Two detectors read the same recorded network
traffic: Suricata signature rules, and an XGBoost classifier on CICFlowMeter flow features. Both
feed one ranked analyst queue. Analyst verdicts re-rank similar alerts (family learning) inside
fixed safety limits. Tier 2 cases, response decisions and case resolution complete the workflow.

All traffic is recorded public data (CSE-CIC-IDS2018). The system does not read a live network and
does not execute responses.

## Repository layout

| Path | Content |
|---|---|
| `hitl-ids/apps/api` | FastAPI back end |
| `hitl-ids/apps/web` | React + Vite web console |
| `hitl-ids/packages` | Detection, ranking, learning and data-contract code |
| `hitl-ids/scripts` | Data build and evaluation scripts |
| `hitl-ids/models`, `hitl-ids/rules`, `hitl-ids/config` | Trained model, signature rules, thresholds |
| `hitl-ids/data` | Committed demo inputs. The databases are built locally (see step 3) |
| `hitl-ids/tests` | Back-end tests |
| `evaluation/` | Frozen evaluation results that the Evaluator pages read |

## Prerequisites

| Tool | Version | Note |
|---|---|---|
| Git | any recent | |
| Node.js + npm | Node 20.19 or later (22 LTS recommended) | Vite 8 does not start on Node 18 |
| Python | 3.11 | `uv` (step 2) installs it for you |

Disk: about 1.5 GB after the build. No dataset download is necessary.

## Set up from a fresh clone

Run every command from the folder that the step names.

1. Clone the repository.

   ```
   git clone https://github.com/CSIT-321/CSIT321-Human-in-the-loop_IDS.git
   cd CSIT321-Human-in-the-loop_IDS/hitl-ids
   ```

2. Install `uv`, then create the Python environment (from `hitl-ids/`).

   ```
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

   uv venv --python 3.11 .venv
   uv pip install --python .venv -r requirements.txt
   ```

   If you already have Python 3.11, `python -m venv .venv` and
   `.venv/bin/pip install -r requirements.txt` also work (`.venv\Scripts\pip` on Windows).

3. Build the two demo databases (from `hitl-ids/`).

   ```
   # macOS / Linux                                   # Windows
   .venv/bin/python scripts/run_detection.py          .venv\Scripts\python scripts\run_detection.py
   .venv/bin/python scripts/build_packet_replay.py    .venv\Scripts\python scripts\build_packet_replay.py
   ```

   `run_detection.py` writes `data/demo.db` (5,000 alerts, about 30 s). `build_packet_replay.py`
   writes `data/packet-replay/` (27,516 flows, about 3 minutes). Both read only committed files.

4. Install the web console (from `hitl-ids/apps/web`).

   ```
   npm ci
   ```

## Run

Use two terminals.

1. API (from `hitl-ids/`):

   ```
   .venv/bin/python -m uvicorn apps.api.main:app --port 8000      # Windows: .venv\Scripts\python
   ```

   Wait for `Application startup complete`. The first start creates the user accounts.

2. Web console (from `hitl-ids/apps/web`):

   ```
   npm run dev
   ```

3. Open http://localhost:5173.

## Accounts

| Role | Username | Password |
|---|---|---|
| System Administrator | `admin` | `admin-demo` |
| Security Analyst (Tier 1 and Tier 2) | `g.ang` | `analyst-demo` |
| Security Analyst (Tier 2 only) | `t2.ang` | `tier2-demo` |
| Evaluator (read-only) | `evaluator` | `evaluator-demo` |

These are fixed demo credentials for an offline demo. Do not expose this server on a network.

## Demo walkthrough

1. Sign in as `admin`. Open **Operational Workspace**. In the Replay card, choose
   **Packet Replay** and select **Prepare Replay**.
2. Select **Activate**, then **Start Arrivals**. Alerts from both detectors arrive step by step.
3. Sign in as `g.ang` in a second browser profile. Open **Analyst Workstation**.
4. Open an alert. Read the Suricata and Flow evidence, then record a verdict with a reason.
5. Record three false-positive verdicts on alerts of the same family (same signature and internal
   host). The other alerts of that family drop in priority. Family learning needs at least three
   agreeing verdicts and never moves a critical alert below its floor.
6. Escalate an alert to Tier 2. Sign in as `t2.ang` and open **Escalated** to work the case.
7. Sign in as `evaluator`. Open **Scenarios**, **Final V3.1 Evaluation** and **Detection Metrics**.
8. As `admin`, select **Reset Replay** to return to an empty queue.

## Tests

```
# from hitl-ids/
.venv/bin/python -m pytest -q

# from hitl-ids/apps/web
npm test            # unit tests
npm run typecheck
npm run build
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| API stops with `No detection database` | Step 3 not done | Run `scripts/run_detection.py` |
| Packet Replay answers `REPLAY_WORKLOAD_UNAVAILABLE` | Replay base not built | Run `scripts/build_packet_replay.py` |
| Sign-in fails right after a rebuild | Accounts are created at API start | Restart the API |
| `npm run dev` fails with a Vite or crypto error | Node is too old | Install Node 22 LTS |
| Every panel shows an error | API not running on port 8000 | Start the API first |

Data sources and file hashes: [`hitl-ids/data/README.md`](hitl-ids/data/README.md).
