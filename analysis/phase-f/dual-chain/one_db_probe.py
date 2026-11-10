"""Can ONE database hold the routed flow lane AND admitted Suricata alerts? Scratch copy only.

Control : admit one real Suricata alert into a copy of the routed flow database, product code as is.
Trial   : the same, with system_routing._version_guard replaced IN THIS PROCESS ONLY by a guard that checks
          only rows of external (non-flow) alerts. No product file is changed.

Usage: python one_db_probe.py
Writes one_db_probe.json beside this file.
"""
from __future__ import annotations

import collections
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3] / "hitl-ids"
sys.path[:0] = [str(ROOT)]
from packages.contracts import db  # noqa: E402
from packages.detection import system_routing  # noqa: E402
from packages.detection.external_admission import (  # noqa: E402
    AdmissionRequest, EligibilityRequest, admit_external, review_eligibility)

TMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
SOURCE = TMP / "p2w-flow.db"          # routed flow lane (4,085 queue items)
EVE = ROOT / "data/spike/Wednesday-14-02-2018/suricata-172.31.69.25/eve.json"
INFO_PREFIX = ("ET INFO", "GPL ")
OUT = Path(__file__).resolve().parent / "one_db_probe.json"


def window() -> Path:
    path = TMP / "dual-probe.jsonl"
    kept = 0
    with path.open("w", encoding="utf-8") as out, EVE.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"event_type":"alert"' not in line:
                continue
            e = json.loads(line)
            if e.get("event_type") == "alert" and not e["alert"]["signature"].startswith(INFO_PREFIX):
                out.write(json.dumps(e) + "\n")
                kept += 1
    print("window alerts", kept, flush=True)
    return path


def fresh(name: str, win: Path) -> Path:
    target = TMP / name
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(target) + suffix)
        if p.exists():
            p.unlink()
    shutil.copyfile(SOURCE, target)
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_suricata_eve.py"), "--input", str(win),
                          "--sensor-id", "capture-set", "--capture-scope", "wed-14-02-2018",
                          "--database", str(target)], capture_output=True, text=True, cwd=ROOT)
    if run.returncode != 0:
        raise SystemExit(run.stdout + run.stderr)
    print(name, "import", json.loads(run.stdout)["staged"], "staged", flush=True)
    return target


def admit_all(target: Path, limit: int | None = None) -> dict:
    with db.connect(target) as c:
        actor = c.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        ids = [r[0] for r in c.execute("SELECT id FROM external_alert_inbox ORDER BY id")]
    ids = ids[:limit] if limit else ids
    admitted, errors = 0, collections.Counter()
    for inbox_id in ids:
        try:
            with db.connect(target) as c:
                review = review_eligibility(c, inbox_id, actor_id=actor, request=EligibilityRequest(
                    request_id=uuid4(), expected_review_id=None, reason="One-database probe.", decision="accepted"))
                admit_external(c, inbox_id, actor_id=actor, request=AdmissionRequest(
                    request_id=uuid4(), expected_review_id=review["id"], reason="One-database probe."))
                admitted += 1
        except Exception as exc:
            errors[f"{type(exc).__name__}: {str(exc)[:110]}"] += 1
    return {"tried": len(ids), "admitted": admitted, "errors": dict(errors)}


def census(target: Path) -> dict:
    c = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    kinds = dict(c.execute("SELECT source_kind, count(*) FROM operational_alerts_v2 GROUP BY 1"))
    routes = [list(r) for r in c.execute(
        """SELECT o.source_kind, t.handling_route, count(*) FROM operational_alerts_v2 o
           JOIN operational_triage_state_v2 t ON t.operational_alert_id = o.id GROUP BY 1, 2 ORDER BY 1, 2""")]
    cases = dict(c.execute(
        """SELECT o.source_kind, count(*) FROM tier2_cases k JOIN operational_alerts_v2 o
           ON o.id = k.primary_operational_alert_id GROUP BY 1"""))
    c.close()
    return {"alertsBySource": kinds, "routesBySource": routes, "tier2CasesBySource": cases}


def scoped_guard(conn, column, policy):
    """Same rule as the product guard, applied only to rows written for external (non-flow) alerts."""
    for row in conn.execute(
            f"SELECT s.{column} FROM operational_system_routing s JOIN operational_alerts_v2 o "
            "ON o.id = s.operational_alert_id WHERE o.source_kind != 'legacy_flow_alert'"):
        old = type(policy).model_validate_json(row[0])
        if old.version == policy.version and old != policy:
            raise ValueError("changed configuration requires a new policy version")


def main() -> None:
    win = window()
    control_db = fresh("dual-probe-control.db", win)
    before = census(control_db)
    control = admit_all(control_db, limit=3)
    print("CONTROL (product guard):", control, flush=True)

    trial_db = fresh("dual-probe-trial.db", win)
    original = system_routing._version_guard
    system_routing._version_guard = scoped_guard
    try:
        trial = admit_all(trial_db)
    finally:
        system_routing._version_guard = original
    after = census(trial_db)
    print("TRIAL (scoped guard, this process only):", trial, flush=True)
    print("before", json.dumps(before), flush=True)
    print("after ", json.dumps(after), flush=True)
    OUT.write_text(json.dumps({"source": str(SOURCE), "control": control, "trial": trial,
                               "before": before, "after": after, "trialDb": str(trial_db)}, indent=1),
                   encoding="utf-8")


if __name__ == "__main__":
    main()
