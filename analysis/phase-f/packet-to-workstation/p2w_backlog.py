"""Add a reviewable backlog of real informational Suricata alerts to the populated database.

They are staged only, never admitted: the queue keeps its 2,443 non-informational alerts, and the Incoming
Alerts screen gets real work to do (review, hold, admit).

Usage: python p2w_backlog.py [--limit 200]
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "hitl-ids"
DB = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review\review-suri-full.db"))
TMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
EVE = ROOT / "data/spike/Wednesday-14-02-2018/suricata-172.31.65.56/eve.json"
INFO_PREFIX = ("ET INFO", "GPL ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    window = TMP / "review-suri-backlog.jsonl"
    kept = 0
    with window.open("w", encoding="utf-8") as out, EVE.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"event_type":"alert"' not in line:
                continue
            e = json.loads(line)
            if e.get("event_type") != "alert" or not e["alert"]["signature"].startswith(INFO_PREFIX):
                continue
            out.write(json.dumps(e) + "\n")
            kept += 1
            if kept >= args.limit:
                break
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_suricata_eve.py"),
                          "--input", str(window), "--sensor-id", "capture-set",
                          "--capture-scope", "wed-14-02-2018", "--database", str(DB)],
                         capture_output=True, text=True, cwd=ROOT)
    print(run.stdout.strip() or run.stderr.strip())
    print(f"backlog window wrote {kept} informational alerts")


if __name__ == "__main__":
    main()
