"""Collect the 9 slice reports, check each worker stayed in scope, and verify every citation.

A citation `hitl-ids/x.py:12` (or `:12-20`, `:12,40`) must name a real file, and every cited line must
exist in that file. A worker can invent a plausible line number; this catches that mechanically.
"""
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

REPO = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS")
WT = Path(r"C:\Users\Glenn Ang\fyp-review-wt")
OUT = REPO / "analysis/codebase-review"
CITE = re.compile(r"(hitl-ids/[\w./\-\[\]]+\.(?:py|sql|ts|tsx|json|md|ps1|txt)):(\d+(?:[-–,]\d+)*)")
ROW = re.compile(r"^\| (S\d+-\d+) \| (CRITICAL|HIGH|MEDIUM|LOW) \| ([A-Z\-]+) \| (.*?) \|", re.M)

total_rows, bad = 0, []
sev, cat = Counter(), Counter()
for n in range(1, 10):
    src = WT / f"slice-{n}/analysis/codebase-review/slice-{n}.md"
    dst = OUT / f"slice-{n}.md"
    shutil.copy(src, dst)
    text = dst.read_text(encoding="utf-8")
    stray = subprocess.run(["git", "-C", str(WT / f"slice-{n}"), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.splitlines()
    stray = [s for s in stray if "analysis/codebase-review" not in s]
    rows = ROW.findall(text)
    total_rows += len(rows)
    sev.update(r[1] for r in rows)
    cat.update(r[2] for r in rows)
    cites = CITE.findall(text)
    misses = []
    for path, spec in cites:
        file = REPO / path
        if not file.is_file():
            misses.append(f"{path} (no such file)")
            continue
        length = sum(1 for _ in file.open(encoding="utf-8", errors="replace"))
        for number in re.findall(r"\d+", spec):
            if int(number) > length:
                misses.append(f"{path}:{number} (file has {length} lines)")
    bad += [(n, m) for m in misses]
    header = text.splitlines()[1] if len(text.splitlines()) > 1 else ""
    print(f"slice {n}: {header[:60]:<60} rows={len(rows):>2} cites={len(cites):>3} "
          f"bad={len(misses)} stray_edits={len(stray)}")
print(f"\nTOTAL findings {total_rows} | severity {dict(sev)} | category {dict(cat)}")
print(f"citations that do not resolve: {len(bad)}")
for n, m in bad:
    print(f"  slice {n}: {m}")
