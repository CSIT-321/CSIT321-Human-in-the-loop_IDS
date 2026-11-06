"""Which per-host capture files hold the 2018-02-14 demo flows? Match demo_sample.csv IPs to member names."""
import csv
import os
import re
from collections import Counter
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
listing = (Path(os.environ["LOCALAPPDATA"]) / "Temp/hitl-review/members-0214.txt").read_text(encoding="utf-8")
members = {}
for size, _, name in re.findall(r"^\s*([\d,]+)\s+([\d,]+)\s+(\S+)$", listing, re.M):
    ip = re.search(r"(\d+\.\d+\.\d+\.\d+)$", name)
    if ip:
        members.setdefault(ip.group(1), []).append((int(size.replace(",", "")), name))
print(f"{sum(len(v) for v in members.values())} members with an IP, {len(members)} distinct IPs; "
      f"total {sum(s for v in members.values() for s, _ in v) / 2**30:.2f} GiB")

rows = []
with (HITL / "data/processed/demo_sample.csv").open(newline="", encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f) if r["Timestamp"].startswith("2018-02-14")]
need = Counter()
unmatched = 0
for r in rows:
    hosts = [ip for ip in (r["Src IP"], r["Dst IP"]) if ip in members]
    if not hosts:
        unmatched += 1
    for ip in hosts:
        need[(ip, r["attack_class"])] += 1
print(f"demo flows on 2018-02-14: {len(rows)}, with no host capture: {unmatched}")
by_ip = Counter()
for (ip, k), n in need.items():
    by_ip[ip] += n
for ip, n in by_ip.most_common(12):
    size = sum(s for s, _ in members[ip])
    classes = {k: v for (i, k), v in need.items() if i == ip}
    print(f"{ip:<16} flows={n:>4} size={size / 2**20:8.1f} MiB  {classes}  {[m for _, m in members[ip]][:2]}")
bf = [r for r in rows if r["attack_class"] == "Brute Force"]
print("brute force endpoints:", Counter((r["Src IP"], r["Dst IP"], r["Dst Port"]) for r in bf).most_common(5))
print("benign hosts covered by the top host set:")
