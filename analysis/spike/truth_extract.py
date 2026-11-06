"""Extract the labelled rows of the 3 spike hosts from the corrected release's day CSV (streamed, never unzipped).

Output: hitl-ids/data/spike/<day>/truth-<day>.csv - only rows where Src IP or Dst IP is a spike host.
    python truth_extract.py Wednesday-14-02-2018 172.31.69.25 172.31.64.80 172.31.65.56
"""
import csv
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
day, hosts = sys.argv[1], set(sys.argv[2:])
out = HITL / "data" / "spike" / day / f"truth-{day}.csv"
z = zipfile.ZipFile(HITL / "data/raw/CSECICIDS2018_improved.zip")
labels, kept, seen = Counter(), 0, 0
with z.open(f"{day}.csv") as raw, out.open("w", newline="", encoding="utf-8") as dst:
    reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline=""))
    header = next(reader)
    writer = csv.writer(dst)
    writer.writerow(header)
    si, di, li = header.index("Src IP"), header.index("Dst IP"), header.index("Label")
    for row in reader:
        seen += 1
        if row[si] in hosts or row[di] in hosts:
            writer.writerow(row)
            kept += 1
            labels[row[li]] += 1
print(f"{day}: {seen:,} rows read, {kept:,} kept for {sorted(hosts)}")
print("header tail:", header[-4:])
for k, v in labels.most_common():
    print(f"  {v:>9,}  {k}")
