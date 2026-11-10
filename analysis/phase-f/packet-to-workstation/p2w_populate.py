"""Populate ONE database entirely from real Suricata alerts, with no flow lane at all.

Population rule (stated, not cherry-picked): every alert in the three Wednesday-14-02-2018 captures whose
signature is not informational (ET INFO / GPL). Informational alerts stay out of the queue but are still
staged in the inbox, so the backlog is real.

Steps: copy data/demo.db to a scratch DB (never written), import the alerts, then review and admit each
staged record with one stated reason. Prints counts per route, class and band; writes data/lane_suricata_full.json.

Usage: python p2w_populate.py [--limit N]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3] / "hitl-ids"
sys.path[:0] = [str(ROOT)]
from packages.contracts import db  # noqa: E402
from packages.detection.external_admission import (  # noqa: E402
    AdmissionRequest, EligibilityRequest, admit_external, review_eligibility)

OUT = Path(__file__).resolve().parent / "data"
TMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
DB = TMP / "review-suri-full.db"
BASE = ROOT / "data/spike/Wednesday-14-02-2018"
CAPTURES = ("suricata-172.31.69.25", "suricata-172.31.65.56", "suricata-172.31.64.80")
INFO_PREFIX = ("ET INFO", "GPL ")
REASON_REVIEW = "Bulk triage of a real capture set: signature is not informational."
REASON_ADMIT = "Admitted for analyst triage from the real capture set."


def build_window(limit: int) -> tuple[Path, dict]:
    window = TMP / "review-suri-full.jsonl"
    kept = 0
    seen = collections.Counter()
    with window.open("w", encoding="utf-8") as out:
        for cap in CAPTURES:
            path = BASE / cap / "eve.json"
            with path.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"event_type":"alert"' not in line:
                        continue
                    e = json.loads(line)
                    if e.get("event_type") != "alert":
                        continue
                    sig = e["alert"]["signature"]
                    if sig.startswith(INFO_PREFIX):
                        continue
                    e["_capture"] = cap
                    out.write(json.dumps(e) + "\n")
                    kept += 1
                    seen[cap] += 1
                    if limit and kept >= limit:
                        break
            if limit and kept >= limit:
                break
    return window, dict(seen)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    t0 = time.time()
    window, seen = build_window(args.limit)
    print(f"window: {sum(seen.values())} alerts {seen}", flush=True)

    for suffix in ("", "-wal", "-shm"):
        p = Path(str(DB) + suffix)
        if p.exists():
            p.unlink()
    shutil.copyfile(ROOT / "data" / "demo.db", DB)

    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_suricata_eve.py"),
                          "--input", str(window), "--sensor-id", "capture-set",
                          "--capture-scope", "wed-14-02-2018", "--database", str(DB)],
                         capture_output=True, text=True, cwd=ROOT)
    if run.returncode != 0:
        raise SystemExit(run.stdout + run.stderr)
    imported = json.loads(run.stdout)
    print(f"import: {imported}", flush=True)

    actor = None
    routes = collections.Counter()
    classes = collections.Counter()
    bands = collections.Counter()
    admitted = 0
    failed = []
    with db.connect(DB) as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT id, display_name FROM users WHERE username='g.ang'").fetchone()
        actor = {"id": row["id"], "name": row["display_name"]}
        ids = [r["id"] for r in c.execute("SELECT id FROM external_alert_inbox ORDER BY id")]
    for i, inbox_id in enumerate(ids, 1):
        try:
            with db.connect(DB) as c:
                review = review_eligibility(c, inbox_id, actor_id=actor["id"],
                                            request=EligibilityRequest(request_id=uuid4(),
                                                                       expected_review_id=None,
                                                                       reason=REASON_REVIEW, decision="accepted"))
                admit_external(c, inbox_id, actor_id=actor["id"],
                               request=AdmissionRequest(request_id=uuid4(),
                                                        expected_review_id=review["id"],
                                                        reason=REASON_ADMIT))
                admitted += 1
        except Exception as exc:  # recorded, not hidden
            failed.append({"inboxId": inbox_id, "error": f"{type(exc).__name__}: {exc}"})
        if i % 250 == 0:
            print(f"  admitted {i}/{len(ids)}  ({time.time()-t0:.0f}s)", flush=True)

    with db.connect(DB) as c:
        c.row_factory = sqlite3.Row
        for r in c.execute("""SELECT t.handling_route, t.priority_band, s.classification
                              FROM operational_alerts_v2 o
                              JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id
                              LEFT JOIN operational_system_routing s ON s.operational_alert_id=o.id"""):
            routes[r["handling_route"]] += 1
            bands[r["priority_band"]] += 1
            raw = r["classification"]
            if raw:
                try:
                    classes[json.loads(raw)["attackCategory"]] += 1
                except Exception:
                    classes["unparsed"] += 1
            else:
                classes["none"] += 1
        counts = {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in
                  ("suricata_eve_records", "external_alert_inbox", "external_eligibility_review",
                   "external_operational_admission", "operational_alerts_v2", "tier2_cases",
                   "operational_system_routing")}
        queue_state = dict(c.execute("""SELECT handling_route, count(*) FROM operational_triage_state_v2
                                        GROUP BY handling_route""").fetchall())
        total_cases = c.execute("SELECT count(*) FROM tier2_cases").fetchone()[0]

    payload = {"db": str(DB), "rule": "every non-informational Suricata alert of the three Wednesday captures",
               "window": seen, "import": imported, "counts": counts, "admitted": admitted,
               "failed": failed[:20], "failedCount": len(failed),
               "routes": dict(routes), "bands": dict(bands), "classes": dict(classes),
               "queueState": queue_state, "tier2Cases": total_cases,
               "seconds": round(time.time() - t0, 1)}
    (OUT / "lane_suricata_full.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("counts", "admitted", "failedCount", "routes", "classes",
                                              "bands", "tier2Cases", "seconds")}, indent=1), flush=True)


if __name__ == "__main__":
    main()
