"""
Render the iteration-report diagrams as PNG images.

Mermaid fences do not display in plain Markdown viewers (Word, most editors, PDF export), so the
report embeds real images instead and keeps the Mermaid source in a collapsed block for viewers
that do support it.

Uses matplotlib only - no Node, no puppeteer, no system Graphviz.

Output: hitl-ids/docs/img/*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = Path(__file__).resolve().parent
IMG = HERE.parent / "docs" / "img"
PROC = HERE.parent / "data" / "processed"

GREEN, ORANGE, RED, BLUE, GREY = "#d5e8d4", "#ffe6cc", "#f8cecc", "#dae8fc", "#e8e8e8"
EDGE = {"green": "#82b366", "orange": "#d79b00", "red": "#b85450",
        "blue": "#6c8ebf", "grey": "#999999"}
DPI = 160


def box(ax, x, y, w, h, text, fc=GREY, ec="#999999", fs=8.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.04",
                                facecolor=fc, edgecolor=ec, linewidth=1.3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, color="#666666"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=13, color=color, linewidth=1.3,
                                 shrinkA=2, shrinkB=2))


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 10); ax.set_ylim(0, h / w * 10)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    IMG.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG / name, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", IMG / name)


def pipeline():
    fig, ax = canvas(11, 4.2)
    H = 4.2 / 11 * 10
    y = H / 2 - 0.45
    nodes = [
        (0.05, "CSECICIDS2018\n_improved.zip\n10.43 GB - 10 days", GREY, "grey"),
        (2.05, "scan_labels.py\n63,195,145 flows", GREY, "grey"),
        (4.05, "build_samples.py\nseed 20260911\nleakage-checked", GREEN, "green"),
        (6.05, "train_model.py\n8-class XGBoost\nmacro F1 0.988", GREEN, "green"),
        (8.05, "Notebooks 01-04\nevidence +\ndecision record", ORANGE, "orange"),
    ]
    for x, t, fc, ec in nodes:
        box(ax, x, y, 1.8, 0.95, t, fc, EDGE[ec], fs=7.6)
    for i in range(len(nodes) - 1):
        arrow(ax, nodes[i][0] + 1.8, y + 0.475, nodes[i + 1][0], y + 0.475)
    ax.text(5, H - 0.35, "Build pipeline - 36 GB streamed from the zip, never extracted",
            ha="center", fontsize=10.5, weight="bold")
    ax.text(5, y - 0.42, "train_sample.csv 250,655 rows        demo_sample.csv 5,000 rows",
            ha="center", fontsize=8, style="italic", color="#555555")
    save(fig, "01_pipeline.png")


def classes():
    scan = json.load(open(PROC / "label_scan.json", encoding="utf-8"))
    agg = {}
    for c in scan["total"]:
        l = c["label"].lower()
        if l.startswith("benign"): k = "Benign"
        elif l.startswith("infiltration"):
            k = "Port Scan" if "portscan" in l.replace(" ", "") else "Infiltration"
        elif l.startswith("web attack"): k = "Web Attack"
        elif l.startswith("botnet"): k = "Botnet"
        elif l.startswith("ddos"): k = "DDoS"
        elif l.startswith("dos"): k = "DoS"
        else: k = "Brute Force"
        agg[k] = agg.get(k, 0) + c["n"]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
    ben = agg.pop("Benign")
    a1.pie([ben, sum(agg.values())], labels=["Benign\n93.92%", "Attack\n6.08%"],
           colors=["#cfe2f3", "#f4b183"], startangle=90,
           wedgeprops={"edgecolor": "white", "linewidth": 2})
    a1.set_title(f"{scan['total_rows']:,} flows", fontsize=10.5, weight="bold")

    ks = sorted(agg, key=agg.get, reverse=True)
    bars = a2.barh(ks, [agg[k] for k in ks], color="#f4b183", edgecolor="#c55a11")
    a2.set_xscale("log"); a2.invert_yaxis()
    a2.set_xlabel("flows (log scale)", fontsize=9)
    a2.set_title("Attack classes - note the 4-order spread", fontsize=10.5, weight="bold")
    for b, k in zip(bars, ks):
        a2.text(b.get_width() * 1.25, b.get_y() + b.get_height() / 2,
                f"{agg[k]:,}", va="center", fontsize=8)
    a2.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    save(fig, "02_class_distribution.png")


def versions():
    fig, ax = canvas(11, 4.8)
    H = 4.8 / 11 * 10
    items = [
        ('v0.1  Inherited\nCICIDS2017 - weighted fusion\n"agreement = strongest"', GREY, "grey"),
        ("v0.2  Post-grilling\ncorrected 2018 - demo-first\n10 decisions locked", GREEN, "green"),
        ("v0.3  Adversarial review\n28 findings - 5 critical\ngolden test impossible", ORANGE, "orange"),
        ("v1.0  Evidence\nco-occurrence = 0\nCEF designed", RED, "red"),
        ("v1.1  Corrected data\nPort Scan split out\n8 classes", GREEN, "green"),
        ("v1.2  REVERSAL\nco-occurrence = 200\nsignature_only = 0", RED, "red"),
        ("v1.3  Repositioned\nsignature = trust,\nnot coverage", GREEN, "green"),
    ]
    y0 = H - 1.80          # leaves clear air under the title
    ROW = 1.95
    for i, (t, fc, ec) in enumerate(items):
        col, row = i % 4, i // 4
        x = 0.15 + col * 2.5
        y = y0 - row * ROW
        box(ax, x, y, 2.15, 1.15, t, fc, EDGE[ec], fs=7.2)
        if i < len(items) - 1:
            if col < 3:
                arrow(ax, x + 2.15, y + 0.575, x + 2.5, y + 0.575)
            else:
                # wrap to the next row: down the right edge, back along, then up
                ymid = y - (ROW - 1.15) / 2
                ax.plot([x + 1.07, x + 1.07, 0.15 + 1.07],
                        [y, ymid, ymid], color="#666666", linewidth=1.3, zorder=0)
                arrow(ax, 0.15 + 1.07, ymid, 0.15 + 1.07, y - ROW + 1.15)
    ax.text(5, H - 0.30, "Direction history - red nodes were later overturned by evidence",
            ha="center", fontsize=10.5, weight="bold")
    ax.text(5, y0 - ROW - 0.45,
            "Superseded conclusions are kept, not deleted - notebooks 01-03 carry banners",
            ha="center", fontsize=8, style="italic", color="#555555")
    save(fig, "03_version_history.png")


def reversal():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    cats = ["ML only", "signature\nonly", "both", "missed\nby both"]
    for ax, vals, title, note in [
        (a1, [403, 8, 0, 89], "Old sample (uncorrected)",
         "complementary: signature caught 8 the model missed"),
        (a2, [794, 0, 200, 6], "Corrected sample",
         "subsumed: signature catches nothing unique"),
    ]:
        cols = ["#6c8ebf", "#82b366" if vals[1] else "#b85450", "#d79b00", "#999999"]
        b = ax.bar(cats, vals, color=cols, edgecolor="white", linewidth=1.4)
        ax.bar_label(b, padding=2, fontsize=9, weight="bold")
        ax.set_title(title, fontsize=10.5, weight="bold")
        ax.text(0.5, -0.30, note, transform=ax.transAxes, ha="center",
                fontsize=8.5, style="italic", color="#555555")
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8.5)
    a1.set_ylabel("malicious flows", fontsize=9)
    plt.suptitle("The reversal - 1,000 malicious flows, before and after correction",
                 fontsize=11, weight="bold")
    plt.tight_layout(rect=[0, 0.05, 1, 0.97])
    save(fig, "04_reversal.png")


def triage():
    fig, ax = plt.subplots(figsize=(10, 3.4))
    labels = ["corroborated\nrule + model agree", "ml_only\nmodel alone", "missed by both"]
    vals = [200, 794, 6]
    b = ax.barh(labels, vals, color=["#82b366", "#d79b00", "#b85450"],
                edgecolor="white", linewidth=1.4)
    ax.bar_label(b, padding=4, fontsize=10, weight="bold")
    ax.invert_yaxis()
    ax.set_xlabel("malicious flows (of 1,000)", fontsize=9)
    ax.set_xlim(0, 1150)
    ax.set_title("Triage effort allocation - the hybrid's actual contribution",
                 fontsize=11, weight="bold")
    for i, n in enumerate(["fast-track - lowest analyst effort",
                           "HIGHEST human value - no checkable reason",
                           "residual blind spot -> rule development"]):
        ax.text(vals[i] + 60, i, n, va="center", fontsize=8.5,
                style="italic", color="#555555")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    save(fig, "05_triage.png")


def roadmap():
    fig, ax = canvas(12, 2.9)
    H = 2.9 / 12 * 10
    # Phase numbering is CANONICAL and matches plans/hitl-ids-demo-build.md exactly.
    # Do not renumber here without renumbering the plan.
    phases = [
        ("PHASE 0\nFoundation\nS1 - S2", ORANGE, "orange", "PARTIAL"),
        ("PHASE 1\nData & model\nS3 - S4", GREEN, "green", "DONE"),
        ("PHASE 2\nDetection core\nS5 S4b S6 S7 S8", ORANGE, "orange", "NEXT"),
        ("PHASE 3\nPersistence\n+ API - S9 S10", GREY, "grey", ""),
        ("PHASE 4\nInterface\nS11 - S14", GREY, "grey", ""),
        ("PHASE 5\nEvaluation\n+ demo - S15 S16", BLUE, "blue", "GATE"),
        ("PHASE 6\nPost-demo\nS17 - S18", GREY, "grey", "BLOCKED"),
    ]
    y = 0.45
    for i, (t, fc, ec, tag) in enumerate(phases):
        x = 0.06 + i * 1.42
        box(ax, x, y, 1.28, 1.05, t, fc, EDGE[ec], fs=6.5)
        if tag:
            ax.text(x + 0.64, y + 1.16, tag, ha="center", fontsize=7,
                    weight="bold", color=EDGE[ec])
        if i < len(phases) - 1:
            arrow(ax, x + 1.28, y + 0.525, x + 1.42, y + 0.525)
    ax.text(5, H - 0.12, "Roadmap - phase numbers match plans/hitl-ids-demo-build.md",
            ha="center", fontsize=10, weight="bold")
    ax.text(5, 0.10,
            "Phase 0 partial: S1 scaffold incomplete, S2 not started.   "
            "Phase 2 partial: only S4b done.   Phase 6 blocked until the S16 demo gate passes.",
            ha="center", fontsize=6.8, style="italic", color="#555555")
    save(fig, "06_roadmap.png")


if __name__ == "__main__":
    pipeline(); classes(); versions(); reversal(); triage(); roadmap()
    print("\nall diagrams written to", IMG)
