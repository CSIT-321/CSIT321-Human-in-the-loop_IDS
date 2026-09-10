"""
Scan the corrected CSE-CIC-IDS2018 archive and report the label distribution per capture day.

Reads only the `Label` and `Attempted Category` columns, streaming each CSV directly out of the
zip so the 36 GB of uncompressed data is never written to disk.

Output: hitl-ids/data/processed/label_scan.json
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZIP = HERE.parent / "data" / "raw" / "CSECICIDS2018_improved.zip"
OUT = HERE.parent / "data" / "processed" / "label_scan.json"


def scan_member(zf: zipfile.ZipFile, name: str) -> dict:
    """Count Label x Attempted Category for one CSV member."""
    counts: Counter = Counter()
    rows = 0
    with zf.open(name) as fh:
        txt = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
        reader = csv.reader(txt)
        header = next(reader)
        if "Label" not in header:
            return {"error": "no Label column", "columns": len(header)}
        li = header.index("Label")
        ai = header.index("Attempted Category") if "Attempted Category" in header else None

        for row in reader:
            rows += 1
            if len(row) <= li:
                continue
            att = row[ai] if ai is not None and len(row) > ai else ""
            counts[(row[li], att)] += 1

    return {
        "rows": rows,
        "columns": len(header),
        "counts": [{"label": k[0], "attempted": k[1], "n": v}
                   for k, v in sorted(counts.items(), key=lambda kv: -kv[1])],
    }


def main() -> int:
    if not ZIP.exists():
        print(f"archive not found: {ZIP}", file=sys.stderr)
        return 2

    OUT.parent.mkdir(parents=True, exist_ok=True)
    result: dict = {"archive": ZIP.name, "days": {}}

    with zipfile.ZipFile(ZIP) as zf:
        members = sorted(i.filename for i in zf.infolist() if i.filename.endswith(".csv"))
        for idx, name in enumerate(members, 1):
            t0 = time.time()
            print(f"[{idx}/{len(members)}] {name} ...", flush=True)
            info = scan_member(zf, name)
            info["seconds"] = round(time.time() - t0, 1)
            result["days"][name] = info
            print(f"    rows={info.get('rows', 0):,} in {info['seconds']}s", flush=True)

    total: Counter = Counter()
    for day in result["days"].values():
        for c in day.get("counts", []):
            total[(c["label"], c["attempted"])] += c["n"]
    result["total"] = [{"label": k[0], "attempted": k[1], "n": v}
                       for k, v in sorted(total.items(), key=lambda kv: -kv[1])]
    result["total_rows"] = sum(d.get("rows", 0) for d in result["days"].values())

    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}  ({result['total_rows']:,} rows scanned)")
    print("\nAggregate label distribution:")
    for c in result["total"]:
        att = f"  [attempted={c['attempted']}]" if c["attempted"] not in ("", "-1") else ""
        print(f"   {c['label']:<28} {c['n']:>12,}{att}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
