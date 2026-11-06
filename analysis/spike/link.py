"""Spike B criterion 2: what share of Suricata alerts link to a CICFlowMeter flow?

Link rule: same protocol, same two endpoints (either direction, IP and port), and the alert time falls inside
the flow's time span [start - 1 s, start + duration + 1 s]. Suricata writes local time with an offset; CICFlowMeter
writes UTC without one. Both are converted to UTC epoch seconds.

    python link.py <eve.json> <flows.csv> [<eve.json> <flows.csv> ...] [--write linked.jsonl]
"""
from __future__ import annotations

import bisect
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

PROTO = {"TCP": 6, "UDP": 17, "ICMP": 1, "IPV6-ICMP": 58}
SLACK = 1.0


def key(proto: int, a: str, ap: int, b: str, bp: int) -> tuple:
    return (proto,) + tuple(sorted([(a, ap), (b, bp)]))


def load_flows(path: str):
    index = defaultdict(list)  # key -> sorted list of (start, end, row)
    n = 0
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try:
                start = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                start = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
            end = start + float(row["Flow Duration"]) / 1e6
            k = key(int(row["Protocol"]), row["Src IP"], int(row["Src Port"]), row["Dst IP"], int(row["Dst Port"]))
            index[k].append((start, end, row))
            n += 1
    for v in index.values():
        v.sort(key=lambda t: t[0])
    return index, n


def link(eve_path: str, index, out=None) -> Counter:
    stats = Counter()
    with open(eve_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"event_type":"alert"' not in line:
                continue
            e = json.loads(line)
            stats["alerts"] += 1
            proto = PROTO.get(e.get("proto", ""), -1)
            ts = datetime.strptime(e["timestamp"], "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
            k = key(proto, e["src_ip"], int(e.get("src_port", 0)), e["dest_ip"], int(e.get("dest_port", 0)))
            spans = index.get(k)
            if not spans:
                stats["no_5tuple"] += 1
                stats[f"no_5tuple:{e.get('proto')}"] += 1
                continue
            i = bisect.bisect_right([s for s, _, _ in spans], ts + SLACK)
            hit = next((spans[j] for j in range(i - 1, -1, -1) if spans[j][0] - SLACK <= ts <= spans[j][1] + SLACK), None)
            if hit is None:
                stats["5tuple_but_outside_time"] += 1
                continue
            stats["linked"] += 1
            if out is not None:
                out.write(json.dumps({"alert": e, "flow_id": hit[2]["Flow ID"], "flow_start": hit[2]["Timestamp"]}) + "\n")
    return stats


def main() -> None:
    args = sys.argv[1:]
    write = None
    if "--write" in args:
        i = args.index("--write")
        write = open(args[i + 1], "w", encoding="utf-8")
        args = args[:i] + args[i + 2:]
    total = Counter()
    for eve, flows in zip(args[0::2], args[1::2]):
        index, n = load_flows(flows)
        s = link(eve, index, write)
        total.update(s)
        print(f"{eve.split('/')[-2]}: flows={n:,} alerts={s['alerts']:,} linked={s['linked']:,} "
              f"({s['linked'] / max(1, s['alerts']):.4f}) no_5tuple={s['no_5tuple']:,} outside_time={s['5tuple_but_outside_time']:,}")
        print("   unlinked by protocol:", {k: v for k, v in s.items() if k.startswith("no_5tuple:")})
    print(f"TOTAL alerts={total['alerts']:,} linked={total['linked']:,} share={total['linked'] / max(1, total['alerts']):.4f}")


if __name__ == "__main__":
    main()
