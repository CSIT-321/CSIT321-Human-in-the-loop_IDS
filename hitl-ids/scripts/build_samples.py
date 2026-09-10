"""
Build the training and demo samples from the corrected CSE-CIC-IDS2018 archive.

Decisions encoded here (see docs/plan-changelog.md v1.1):
  Q18  Attempted attacks are MALICIOUS, but carry an `is_attempted` flag so the sensitivity
       analysis can be run both ways. Excluding them would delete the entire FTP-BruteForce
       class, which is 100% attempted (298,874 of 298,874 flows).
  Q19  `Infiltration - NMAP Portscan` is split out as its own class `Port Scan`. Lumping a
       port scan in with infiltration is the mislabelling that made Infiltration unlearnable.
       True Infiltration is left with only 317 flows across 63M - reported, not hidden.
  Q20  Two disjoint datasets: a training sample with per-class caps, and a smaller demo sample
       at roughly 80/20 benign/attack so the dashboard queue looks alive.

Leakage prevention: each row is drawn once into a per-class reservoir, then partitioned into
demo OR train - never both. Verified by an id-intersection assertion before writing completes.

Reproducibility: fixed SEED; reservoir sampling is deterministic given the seed and the
archive's row order.

Outputs (hitl-ids/data/processed/):
    train_sample.csv      per-class capped, for model training
    demo_sample.csv       ~80/20, for the dashboard demo
    sample_manifest.json  provenance, class counts, decisions
"""
from __future__ import annotations

import csv
import io
import json
import random
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZIP = HERE.parent / "data" / "raw" / "CSECICIDS2018_improved.zip"
OUTDIR = HERE.parent / "data" / "processed"

SEED = 20260911

TRAIN_CAP = {"Benign": 100_000, "DoS": 30_000, "DDoS": 30_000, "Brute Force": 30_000,
             "Botnet": 30_000, "Port Scan": 30_000, "Web Attack": 400, "Infiltration": 300}
DEMO_CAP = {"Benign": 4_000, "DoS": 200, "DDoS": 200, "Brute Force": 200,
            "Botnet": 150, "Port Scan": 150, "Web Attack": 60, "Infiltration": 40}


def classify(label):
    """Map a corrected-release label to (attack_class, is_attempted)."""
    attempted = "attempted" in label.lower()
    l = label.lower()
    if l.startswith("benign"):
        return "Benign", False
    if l.startswith("infiltration"):
        # Q19: the portscan is a different attack and gets its own class
        return ("Port Scan" if "portscan" in l.replace(" ", "") else "Infiltration"), attempted
    if l.startswith("web attack"):
        return "Web Attack", attempted
    if l.startswith("botnet"):
        return "Botnet", attempted
    if l.startswith("ddos"):
        return "DDoS", attempted
    if l.startswith("dos"):
        return "DoS", attempted
    if "bruteforce" in l.replace("-", "").replace(" ", ""):
        return "Brute Force", attempted
    return "UNMAPPED:" + label, attempted


def main() -> int:
    if not ZIP.exists():
        print(f"archive not found: {ZIP}", file=sys.stderr)
        return 2
    OUTDIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    reservoirs = defaultdict(list)
    seen = Counter()
    header = None
    li = None
    unmapped = Counter()

    with zipfile.ZipFile(ZIP) as zf:
        members = sorted(i.filename for i in zf.infolist() if i.filename.endswith(".csv"))
        for idx, name in enumerate(members, 1):
            print(f"[{idx}/{len(members)}] {name}", flush=True)
            with zf.open(name) as fh:
                txt = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
                reader = csv.reader(txt)
                hdr = next(reader)
                if header is None:
                    header = hdr
                    li = hdr.index("Label")
                elif hdr != header:
                    print(f"  SCHEMA MISMATCH in {name}", file=sys.stderr)
                    return 3

                for row in reader:
                    if len(row) <= li:
                        continue
                    cls, att = classify(row[li])
                    if cls.startswith("UNMAPPED"):
                        unmapped[cls] += 1
                        continue
                    cap = TRAIN_CAP.get(cls, 0) + DEMO_CAP.get(cls, 0)
                    if cap == 0:
                        continue
                    seen[cls] += 1
                    res = reservoirs[cls]
                    if len(res) < cap:
                        res.append((row, cls, att))
                    else:
                        j = rng.randrange(seen[cls])
                        if j < cap:
                            res[j] = (row, cls, att)

    if unmapped:
        print("\nWARNING unmapped labels:", dict(unmapped), file=sys.stderr)

    out_header = ["alert_id", "attack_class", "is_attempted"] + header

    train_rows, demo_rows = [], []
    for cls, res in reservoirs.items():
        rng.shuffle(res)
        n_demo = DEMO_CAP.get(cls, 0)
        demo_rows += res[:n_demo]
        train_rows += res[n_demo:][: TRAIN_CAP.get(cls, 0)]

    rng.shuffle(demo_rows)
    rng.shuffle(train_rows)

    idx_id = header.index("id")
    idx_flow = header.index("Flow ID") if "Flow ID" in header else None

    def key(r):
        return (r[0][idx_id], r[0][idx_flow] if idx_flow is not None else "")

    overlap = {key(r) for r in demo_rows} & {key(r) for r in train_rows}
    print(f"\nleakage check: {len(overlap)} shared source rows between demo and train")
    if overlap:
        print("LEAKAGE DETECTED - refusing to write", file=sys.stderr)
        return 4

    def write(path, rows, prefix):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(out_header)
            for i, (row, cls, att) in enumerate(rows, 1):
                w.writerow([f"{prefix}-{i:05d}", cls, int(att)] + row)

    write(OUTDIR / "demo_sample.csv", demo_rows, "AL")
    write(OUTDIR / "train_sample.csv", train_rows, "TR")

    manifest = {
        "seed": SEED,
        "archive": ZIP.name,
        "source_rows_considered": sum(seen.values()),
        "decisions": {
            "Q18_attempted": "malicious, flagged via is_attempted",
            "Q19_portscan": "Infiltration - NMAP Portscan split out as class 'Port Scan'",
            "Q20_datasets": "disjoint train + demo samples",
        },
        "demo": {"rows": len(demo_rows),
                 "classes": dict(Counter(c for _, c, _ in demo_rows)),
                 "attempted": sum(1 for _, _, a in demo_rows if a)},
        "train": {"rows": len(train_rows),
                  "classes": dict(Counter(c for _, c, _ in train_rows)),
                  "attempted": sum(1 for _, _, a in train_rows if a)},
    }
    (OUTDIR / "sample_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\ndemo_sample.csv  {len(demo_rows):,} rows")
    for k, v in sorted(manifest["demo"]["classes"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:<14}{v:>8,}")
    print(f"\ntrain_sample.csv {len(train_rows):,} rows")
    for k, v in sorted(manifest["train"]["classes"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:<14}{v:>8,}")
    print(f"\nwrote manifest to {OUTDIR / 'sample_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
