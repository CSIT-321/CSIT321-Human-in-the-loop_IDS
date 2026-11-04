"""Where do E1 (corroborated + detection score >= 80) alerts fall in arrival order?

A rolling-window circuit breaker on the automatic-escalation share only works if E1 alerts do not
arrive as one contiguous burst. Measure, for windows of the last N flagged alerts, the peak E1 share.
"""
import os
import sqlite3
from pathlib import Path

TMP = Path(os.environ["LOCALAPPDATA"]) / "Temp/hitl-review"
HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
for name, path in {"demo": TMP / "run-base/demo.db", "stress": HITL / "data/stress.db"}.items():
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    seq = [r[0] == "corroborated" and r[1] >= 80 for r in c.execute(
        "SELECT evidence_class, detection_score FROM alerts WHERE evidence_class != 'none' ORDER BY id")]
    total = sum(seq)
    print(f"{name}: {len(seq)} flagged, {total} E1 ({total / len(seq):.3f} overall)")
    for window in (25, 50, 100, 200):
        peak = max(sum(seq[i:i + window]) / window for i in range(0, len(seq) - window + 1))
        print(f"  window {window:>3}: peak E1 share {peak:.3f}")
    # Longest unbroken run of E1 in arrival order.
    run = best = 0
    for flag in seq:
        run = run + 1 if flag else 0
        best = max(best, run)
    print(f"  longest consecutive E1 run: {best}")
