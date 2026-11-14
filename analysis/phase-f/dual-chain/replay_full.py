"""Run the whole Packet Replay (160 steps) on a scratch database and record what the queue holds after each step.

Product code only: apps/api/packet_replay.py build() and advance_one(). No product database is written.
Output: replay_full.json beside this file, and the scratch database path inside it.

    hitl-ids/.venv/Scripts/python.exe analysis/phase-f/dual-chain/replay_full.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HITL = HERE.parents[2] / "hitl-ids"
sys.path.insert(0, str(HITL))

from apps.api import packet_replay  # noqa: E402

TARGET = Path(os.environ["LOCALAPPDATA"]) / "Temp" / "hitl-review" / "packet-replay-full.db"


def census(conn: sqlite3.Connection) -> dict:
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "flows": one("SELECT count(*) FROM alerts"),
        "queue": one("SELECT count(*) FROM (SELECT * FROM operational_alerts_v2 WHERE id NOT IN (SELECT hidden_operational_alert_id FROM cross_chain_links))"),
        "suricataAdmitted": one("SELECT count(*) FROM external_operational_admission"),
        "groups": one("SELECT count(*) FROM alert_groups"),
        "groupMembers": one("SELECT count(*) FROM alert_group_members"),
        "tier2Cases": one("SELECT count(*) FROM tier2_cases"),
    }


def main() -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(str(TARGET) + suffix).unlink(missing_ok=True)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    flows = packet_replay.build(TARGET)
    with sqlite3.connect(TARGET) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
    steps, started = [], time.time()
    for step in range(160):
        t0 = time.time()
        packet_replay.advance_one(TARGET, step, "admin")
        with sqlite3.connect(TARGET) as conn:
            steps.append({"step": step, "seconds": round(time.time() - t0, 2), **census(conn)})
        if step % 20 == 19:
            print(f"step {step + 1}/160  {steps[-1]}  total {time.time() - started:.0f}s", flush=True)
    (HERE / "replay_full.json").write_text(json.dumps(
        {"db": str(TARGET), "flowsInWindow": flows, "seconds": round(time.time() - started, 1), "steps": steps},
        indent=1), encoding="utf-8")
    print("done", steps[-1], f"{time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
