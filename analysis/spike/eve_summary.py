"""Summarise a Suricata eve.json: alerts by signature, by severity, and the time span."""
import json
import sys
from collections import Counter

sig, sev, cats, first, last, n = Counter(), Counter(), Counter(), None, None, 0
with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
    for line in f:
        if '"event_type":"alert"' not in line:
            continue
        e = json.loads(line)
        n += 1
        a = e["alert"]
        sig[(a["signature_id"], a["signature"])] += 1
        sev[a["severity"]] += 1
        cats[a.get("category", "")] += 1
        ts = e["timestamp"]
        first = ts if first is None or ts < first else first
        last = ts if last is None or ts > last else last
print(f"alerts={n} span {first} .. {last}")
print("severity:", dict(sorted(sev.items())))
for (sid, name), c in sig.most_common(int(sys.argv[2]) if len(sys.argv) > 2 else 12):
    print(f"{c:>7}  {sid:<9} {name}")
