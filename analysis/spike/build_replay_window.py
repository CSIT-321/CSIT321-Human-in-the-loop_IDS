"""Build the short live-demo replay window from spike B (decision D7, 2026-11-06).

The window is three slices of real capture day 2018-02-14, kept in their original order and time:
  S1 false-positive slice  12:34:00-12:47:00  host 172.31.64.80's flagged-benign flows (AL-00478 = 12:40:02)
  S2 FTP onset             14:33:00-14:36:00  start of the FTP brute force from 18.221.219.4
  S3 SSH onset             18:01:00-18:13:00  start of the SSH brute force from 13.58.98.64, including the first
                                              Suricata 'ET SCAN Potential SSH Scan' alerts (E1-suricata)
Each slice keeps every flow of the 3 hosts in that time (benign background included). Times are CICFlowMeter's
(UTC); Suricata's +0800 timestamps are converted.

Outputs (gitignored), hitl-ids/data/spike/<day>/replay-window/:
  flows.csv     CICFlowMeter rows with alert_id `PK-<host>-<n>` - the input `run_detection` reads
  eve.jsonl     the Suricata alerts that link to those flows (link.py rule)
  truth.json    the release's labels for those flows, keyed by alert_id (evaluation only, never the product)
Prints the measured content of each slice.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from link import key  # noqa: E402

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
DAY = "Wednesday-14-02-2018"
BASE = HITL / "data" / "spike" / DAY
OUT = BASE / "replay-window"
HOSTS = ("172.31.69.25", "172.31.64.80", "172.31.65.56")
SLICES = (("S1 false positive", "12:34:00", "12:47:00"),
          ("S2 FTP onset", "14:33:00", "14:36:00"),
          ("S3 SSH onset", "18:01:00", "18:13:00"))
GROUP_GAP = timedelta(minutes=30)
ATTACKERS = {"18.221.219.4", "13.58.98.64"}


def slice_of(ts: str) -> str | None:
    hms = ts[11:19]
    return next((name for name, a, b in SLICES if a <= hms < b), None)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    truth = {}
    with (BASE / f"truth-{DAY}.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            truth[(r["Protocol"], r["Src IP"], r["Src Port"], r["Dst IP"], r["Dst Port"], r["Timestamp"])] = r["Label"]

    # 1. flows in the window, with the engine's own verdict from spike.db (for measurement only)
    db = sqlite3.connect(f"file:{BASE / 'spike.db'}?mode=ro", uri=True)
    scored = {ref: (ev, score) for ref, ev, score in db.execute(
        "SELECT f.source_record_id, a.evidence_class, a.combined_score FROM alerts a JOIN flow_data f ON f.alert_id = a.id")}
    rows, header = [], None
    for host in HOSTS:
        with (BASE / "flows" / f"{host}.pcap_Flow.csv").open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            h = next(reader)
            header = header or h
            for i, r in enumerate(reader):
                s = slice_of(r[h.index("Timestamp")])
                if s:
                    rows.append((r[h.index("Timestamp")], f"PK-{host}-{i}", s, r))
    rows.sort()
    ti = {n: header.index(n) for n in ("Protocol", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp")}
    labels = {}
    with (OUT / "flows.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["alert_id"] + header)
        for ts, ref, s, r in rows:
            w.writerow([ref] + r)
            labels[ref] = truth.get(tuple(r[ti[n]] for n in ("Protocol", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp")))
    (OUT / "truth.json").write_text(json.dumps(labels), encoding="utf-8")

    # 2. Suricata alerts that link to a window flow
    by_key = {}
    for ts, ref, s, r in rows:
        start = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f" if "." in ts else "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        end = start + float(r[header.index("Flow Duration")]) / 1e6
        k = key(int(r[ti["Protocol"]]), r[ti["Src IP"]], int(r[ti["Src Port"]]), r[ti["Dst IP"]], int(r[ti["Dst Port"]]))
        by_key.setdefault(k, []).append((start, end, ref))
    eve_n, sur_flows = 0, Counter()
    with (OUT / "eve.jsonl").open("w", encoding="utf-8") as out:
        for host in HOSTS:
            with (BASE / f"suricata-{host}" / "eve.json").open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"event_type":"alert"' not in line:
                        continue
                    e = json.loads(line)
                    t = datetime.strptime(e["timestamp"], "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
                    k = key({"TCP": 6, "UDP": 17}.get(e["proto"], -1), e["src_ip"], int(e.get("src_port", 0)),
                            e["dest_ip"], int(e.get("dest_port", 0)))
                    hit = next((ref for a, b, ref in by_key.get(k, ()) if a - 1 <= t <= b + 1), None)
                    if hit:
                        e["linked_alert_id"] = hit
                        out.write(json.dumps(e) + "\n")
                        eve_n += 1
                        sur_flows[(hit, e["alert"]["severity"])] += 1

    # 3. measure each slice
    sur_sev = {}
    for (ref, sev), _ in sur_flows.items():
        sur_sev[ref] = min(sev, sur_sev.get(ref, 9))
    print(f"window: {len(rows):,} flows, {eve_n:,} linked Suricata alerts -> {OUT}")
    for name, a, b in SLICES:
        sel = [(ts, ref, r) for ts, ref, s, r in rows if s == name]
        c = Counter()
        last, groups = {}, 0
        for ts, ref, r in sel:
            ev, score = scored.get(ref, ("?", 0))
            e1 = ev == "corroborated" and score >= 80
            lab = labels.get(ref) or "unlabelled"
            src = r[ti["Src IP"]]
            c["flows"] += 1
            c["flagged"] += ev not in ("none", "?")
            c["E1-flow-rule"] += e1
            c["E1-suricata"] += ref in sur_sev and sur_sev[ref] <= 2 and score >= 80 and ev != "none"
            c["suricata-linked flows"] += ref in sur_sev
            c["false positives (flagged, labelled benign)"] += ev not in ("none", "?") and lab == "BENIGN"
            c["attack flows"] += lab not in ("BENIGN", "unlabelled")
            when = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
            if ev not in ("none", "?"):
                if src not in last or when - last[src] > GROUP_GAP:
                    groups += 1
                last[src] = when
        print(f"\n{name} ({a}-{b}):")
        for k, v in c.items():
            print(f"   {k:<44} {v:>6,}")
        print(f"   {'flagged groups (source IP, 30 min)':<44} {groups:>6,}")
    ap = [ref for ts, ref, s, r in rows if ref == "PK-172.31.64.80-15737"]
    print(f"\nAL-00478 counterpart PK-172.31.64.80-15737 in window: {bool(ap)}; engine says {scored.get('PK-172.31.64.80-15737')}")


if __name__ == "__main__":
    main()
