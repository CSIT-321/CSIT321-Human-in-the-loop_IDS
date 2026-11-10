"""What real Suricata alerts are available for a Suricata-only population? Read-only.

Prints, per capture: total alerts, how many are informational (ET INFO / GPL) versus actionable,
and the distinct signatures of the actionable set.
"""
import collections
import json
import os

BASE = r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids\data\spike\Wednesday-14-02-2018"
CAPTURES = ("suricata-172.31.69.25", "suricata-172.31.65.56", "suricata-172.31.64.80")
INFO_PREFIX = ("ET INFO", "GPL ")

for cap in CAPTURES:
    path = os.path.join(BASE, cap, "eve.json")
    total = 0
    info = 0
    sigs = collections.Counter()
    sev = collections.Counter()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"event_type":"alert"' not in line:
                continue
            e = json.loads(line)
            if e.get("event_type") != "alert":
                continue
            total += 1
            s = e["alert"]["signature"]
            if s.startswith(INFO_PREFIX):
                info += 1
                continue
            sigs[s] += 1
            sev[e["alert"]["severity"]] += 1
    print(f"== {cap}: {total} alerts, {info} informational, {total - info} actionable")
    print(f"   severity of actionable: {dict(sorted(sev.items()))}")
    for s, n in sigs.most_common(6):
        print(f"   {n:6} {s}")
