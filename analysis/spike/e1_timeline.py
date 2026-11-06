"""Per-minute E1 by attacker near the FTP/SSH boundary, and what the 40 benign E1 flows are."""
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

base = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids\data\spike\Wednesday-14-02-2018")
truth = {}
with (base / "truth-Wednesday-14-02-2018.csv").open(newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        truth[(r["Protocol"], r["Src IP"], r["Src Port"], r["Dst IP"], r["Dst Port"], r["Timestamp"])] = r["Label"]
c = sqlite3.connect(f"file:{base / 'spike.db'}?mode=ro", uri=True)
per_min = Counter()
benign_e1 = Counter()
for ev, score, feats in c.execute("SELECT a.evidence_class, a.combined_score, f.flow_features FROM alerts a JOIN flow_data f ON f.alert_id = a.id"):
    if not (ev == "corroborated" and score >= 80):
        continue
    x = json.loads(feats)
    hhmm = x["Timestamp"][11:16]
    per_min[(hhmm[:4] + "x", x["Src IP"])] += 1  # 10-minute buckets
    k = (str(x["Protocol"]), x["Src IP"], str(x["Src Port"]), x["Dst IP"], str(x["Dst Port"]), x["Timestamp"])
    if truth.get(k) == "BENIGN":
        benign_e1[(x["Src IP"], x["Dst IP"], x["Dst Port"], int(x["Total Fwd Packet"]) + int(x["Total Bwd packets"]))] += 1
print("E1 flows per 10-minute bucket and source:")
for (b, src), n in sorted(per_min.items()):
    print(f"  {b}  {src:<15} {n:>6,}")
print("benign-labelled E1 flows (src, dst, dport, packets):")
for k, n in benign_e1.most_common(10):
    print(f"  {n:>3}  {k}")
