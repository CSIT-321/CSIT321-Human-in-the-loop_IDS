"""Join spike B flows to the release's labels; measure E1 on the full day; size candidate replay windows.

Join: protocol + 5-tuple + start timestamp string (both come from CICFlowMeter-family tools).
Groups: same source IP within 30 minutes (decision D3b, extended to flow alerts).
    python window_measure.py Wednesday-14-02-2018
"""
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
day = sys.argv[1]
base = HITL / "data" / "spike" / day
GROUP_GAP = timedelta(minutes=30)

truth = {}
with (base / f"truth-{day}.csv").open(newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        truth[(r["Protocol"], r["Src IP"], r["Src Port"], r["Dst IP"], r["Dst Port"], r["Timestamp"])] = r["Label"]

c = sqlite3.connect(f"file:{base / 'spike.db'}?mode=ro", uri=True)
rows = []
for ref, ev, score, feats in c.execute("""SELECT f.source_record_id, a.evidence_class, a.combined_score, f.flow_features
                                          FROM alerts a JOIN flow_data f ON f.alert_id = a.id"""):
    x = json.loads(feats)
    k = (str(x["Protocol"]), x["Src IP"], str(x["Src Port"]), x["Dst IP"], str(x["Dst Port"]), x["Timestamp"])
    label = truth.get(k)
    when = datetime.strptime(x["Timestamp"][:19], "%Y-%m-%d %H:%M:%S")
    rows.append((when, ref, x["Src IP"], ev == "corroborated" and score >= 80, ev != "none", label))
rows.sort()
print(f"flows {len(rows):,}; matched to a label {sum(r[5] is not None for r in rows):,}")

attack = lambda lab: lab is not None and lab != "BENIGN"
tab = Counter((("E1" if r[3] else "-"), ("attack" if attack(r[5]) else "benign" if r[5] else "unlabelled")) for r in rows)
print("full day, E1 vs label:", dict(sorted(tab.items())))
tp, fp = tab[("E1", "attack")], tab[("E1", "benign")]
fn = tab[("-", "attack")]
print(f"E1 precision {tp / max(1, tp + fp):.5f} ({fp} benign escalated); recall {tp / max(1, tp + fn):.5f} ({fn} attacks missed)")


def groups_and_rate(sel):
    """New E1 groups (source IP, 30-min gap) and the busiest minute of new groups."""
    last, new_per_min, groups = {}, Counter(), 0
    for when, _, src, e1, *_ in sel:
        if not e1:
            continue
        if src not in last or when - last[src] > GROUP_GAP:
            groups += 1
            new_per_min[when.replace(second=0)] += 1
        last[src] = when
    return groups, max(new_per_min.values(), default=0)


def window(label, start, end):
    sel = [r for r in rows if start <= r[0] < end]
    e1 = sum(r[3] for r in sel)
    flagged = sum(r[4] for r in sel)
    labels = Counter(r[5] or "unlabelled" for r in sel)
    g, peak = groups_and_rate(sel)
    print(f"{label:<34} flows={len(sel):>7,} flagged={flagged:>7,} E1={e1:>7,} E1-groups={g} "
          f"peak-new-groups/min={peak}  {dict(labels)}")
    return sel


day0 = rows[0][0].replace(hour=0, minute=0, second=0, microsecond=0)
t = lambda hh, mm: day0 + timedelta(hours=hh, minutes=mm)
print()
window("full day", day0, day0 + timedelta(days=1))
for half in (2, 5, 10):
    window(f"FP slice 12:40 +-{half} min", t(12, 40) - timedelta(minutes=half), t(12, 40) + timedelta(minutes=half))
for half in (2, 5, 10):
    window(f"attack slice 18:01 +-{half} min", t(18, 1) - timedelta(minutes=half), t(18, 1) + timedelta(minutes=half))
fp = [r for r in rows if r[1] and r[5] == "BENIGN" and r[4]]
print(f"\nflagged benign flows (false positives) on the day: {len(fp)}")
for r in fp[:12]:
    print(f"   {r[0]}  {r[1]}  src={r[2]}  E1={r[3]}")
