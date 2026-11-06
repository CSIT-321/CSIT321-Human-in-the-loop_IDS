"""Check the spike's E1 count against the known attackers, and replay the 90%/500 share limit on it.

Known attack endpoints on 2018-02-14 (from the demo sample's labelled brute-force rows, `pick_hosts.py`):
  18.221.219.4 -> 172.31.69.25:21 (FTP), 13.58.98.64 -> 172.31.69.25:22 (SSH).
A flow is counted as "attacker" when either endpoint is one of the two attacker IPs. This is an inference
from the labelled sample, not the full day's ground-truth file.
Reads spike.db read-only.
"""
import sqlite3
import sys
from collections import Counter, deque
from pathlib import Path

DB = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids\data\spike") / sys.argv[1] / "spike.db"
ATTACKERS = {"18.221.219.4", "13.58.98.64"}
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = c.execute("""SELECT a.evidence_class, a.combined_score, a.ml_predicted_class, f.src_ip, f.dst_ip, f.dst_port
                    FROM alerts a JOIN flow_data f ON f.alert_id = a.id ORDER BY a.id""").fetchall()
tab = Counter()
for ev, score, ml, s, d, dp in rows:
    e1 = ev == "corroborated" and score >= 80
    who = "attacker" if s in ATTACKERS or d in ATTACKERS else "other"
    tab[(who, "E1" if e1 else "-")] += 1
print("flows:", len(rows))
for k in sorted(tab):
    print(f"  {k[0]:<9} {k[1]:<3} {tab[k]:>8,}")
other_e1 = Counter((ml, s, d, dp) for ev, score, ml, s, d, dp in rows
                   if ev == "corroborated" and score >= 80 and s not in ATTACKERS and d not in ATTACKERS)
print("E1 flows NOT involving a known attacker (top 8):")
for k, n in other_e1.most_common(8):
    print(f"  {n:>6}  ml={k[0]} {k[1]} -> {k[2]}:{k[3]}")

w, hits, blocked, peak = deque(maxlen=500), 0, 0, 0.0
for ev, score, *_ in rows:
    e1 = ev == "corroborated" and score >= 80
    if len(w) == 500 and w[0]:
        hits -= 1
    w.append(e1)
    hits += e1
    if len(w) == 500:
        peak = max(peak, hits / 500)
        if e1 and hits / 500 >= 0.90:
            blocked += 1
e1_total = sum(1 for ev, score, *_ in rows if ev == "corroborated" and score >= 80)
print(f"share limit 90%/500: peak share {peak:.3f}; E1 blocked {blocked:,} of {e1_total:,}")
