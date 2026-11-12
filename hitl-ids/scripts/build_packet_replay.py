"""Build the packet replay base for the Admin-controlled dual-chain replay (Operational Workspace page).

Both chains start from the same packets of capture day 2018-02-14 (see data/raw/PCAP-DOWNLOAD.md):
  flow chain      CICFlowMeter flows  -> the unchanged detection engine (rules + XGBoost + fusion)
  Suricata chain  eve.json alerts     -> staged and admitted at replay time, not here

Input   data/spike/Wednesday-14-02-2018/replay-window/{flows.csv,eve.jsonl}  (analysis/spike/build_replay_window.py)
Output  data/packet-replay/
          base.db     every window flow scored; no queue rows yet (the replay projects them step by step)
          steps.json  160 arrival steps: the last alert id and the capture time of each step
          eve.jsonl   the linked, non-informational Suricata alerts, each with the step in which it arrives

A step is an equal share of capture time. Idle time between the window's slices (a gap over 60 s) is skipped.
Staging seals a Suricata flow bundle, so every alert of one Suricata flow_id arrives in the step of its last alert.
Informational signatures (ET INFO, GPL) are left out, the same rule as the earlier Suricata population.
Known gap (docs/deviations.md): the CICFlowMeter fork writes no `Total TCP Flow Time`; it is set to 0.

    python scripts/build_packet_replay.py [--reuse-base]
"""
from __future__ import annotations

import bisect
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

WINDOW = HITL / "data" / "spike" / "Wednesday-14-02-2018" / "replay-window"
OUT = HITL / "data" / "packet-replay"
STEPS = 160
IDLE_SECONDS = 60
MISSING_FEATURE = "Total TCP Flow Time"
INFORMATIONAL = ("ET INFO", "GPL ")


def _epoch(text: str) -> float:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def detect() -> None:
    import pandas as pd

    from packages.contracts import models as m
    from packages.detection.pipeline import store
    from packages.detection.pipeline.predictor import MODEL_FILE, MODEL_VERSION, XgboostPredictor
    from packages.detection.pipeline.runner import open_database, run_detection
    from packages.detection.pipeline.source import CsvReplaySource

    for name in ("base.db", "base.db-wal", "base.db-shm"):
        (OUT / name).unlink(missing_ok=True)
    frame = pd.read_csv(WINDOW / "flows.csv", low_memory=False)
    if MISSING_FEATURE not in frame.columns:
        frame[MISSING_FEATURE] = 0
    flows_csv = OUT / "flows.csv"
    frame.to_csv(flows_csv, index=False)
    conn = open_database(str(OUT / "base.db"))
    now = m.utc_now()
    store.register_model(conn, version=MODEL_VERSION, model_file=MODEL_FILE, metrics={}, now=now)
    dataset = store.register_dataset(
        conn, name="CSE-CIC-IDS2018 packets 2018-02-14 via CICFlowMeter fork - replay window",
        version="packet-replay-1", source_file="data/packet-replay/flows.csv", total_records=len(frame),
        class_distribution={}, preparation_meta={"window": "analysis/spike/REPLAY-WINDOW.md"}, now=now)
    conn.commit()
    summary = run_detection(conn, CsvReplaySource(flows_csv), XgboostPredictor(), dataset_id=dataset, now=now)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    print(f"detection: flows={summary.flows:,} by_evidence={summary.by_evidence}", flush=True)


def main() -> int:
    if not (WINDOW / "flows.csv").exists():
        print(f"missing {WINDOW / 'flows.csv'} - run analysis/spike/build_replay_window.py", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    if "--reuse-base" not in sys.argv[1:] or not (OUT / "base.db").exists():
        detect()

    conn = sqlite3.connect(f"file:{(OUT / 'base.db').as_posix()}?mode=ro", uri=True)
    rows = conn.execute("SELECT a.id, f.source_record_id, json_extract(f.flow_features, '$.Timestamp') "
                        "FROM alerts a JOIN flow_data f ON f.alert_id = a.id ORDER BY a.id").fetchall()
    conn.close()
    times = [_epoch(row[2]) for row in rows]
    if times != sorted(times):
        raise SystemExit("alert ids are not in capture-time order; the step cutoffs would be wrong")
    # Active time: capture time with every idle gap removed.
    active, total = [], 0.0
    for index, when in enumerate(times):
        gap = when - times[index - 1] if index else 0.0
        total += 0.0 if gap > IDLE_SECONDS else gap
        active.append(total)
    step_of = [min(STEPS - 1, int(value / total * STEPS)) for value in active]
    steps, last = [], 0
    for step in range(STEPS):
        position = bisect.bisect_right(step_of, step)          # flows 0..position-1 belong to steps <= step
        last = rows[position - 1][0] if position else last
        steps.append({"throughAlertId": last, "captureTime": rows[position - 1][2] if position else None})
    (OUT / "steps.json").write_text(json.dumps(steps), encoding="utf-8")

    step_by_record = {row[1]: step_of[index] for index, row in enumerate(rows)}
    events, bundle_step, informational = [], {}, 0
    with (WINDOW / "eve.jsonl").open(encoding="utf-8") as source:
        for line in source:
            event = json.loads(line)
            linked = event.pop("linked_alert_id")
            if event["alert"]["signature"].startswith(INFORMATIONAL):
                informational += 1
                continue
            when = datetime.strptime(event["timestamp"], "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
            step = max(step_of[max(0, bisect.bisect_right(times, when) - 1)], step_by_record[linked])
            bundle = event.get("flow_id", len(events))
            bundle_step[bundle] = max(step, bundle_step.get(bundle, 0))
            events.append((bundle, linked, event))
    with (OUT / "eve.jsonl").open("w", encoding="utf-8", newline="\n") as out:
        for bundle, linked, event in sorted(events, key=lambda item: bundle_step[item[0]]):
            out.write(json.dumps({"step": bundle_step[bundle], "linkedRecord": linked, "event": event}) + "\n")
    print(f"steps: {STEPS} over {total:,.0f} s of capture; flows: {len(rows):,}; suricata alerts kept: "
          f"{len(events):,} in {len(bundle_step):,} bundles; informational left out: {informational:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
