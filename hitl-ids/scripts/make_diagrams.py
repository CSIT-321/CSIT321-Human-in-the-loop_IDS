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
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Polygon

HERE = Path(__file__).resolve().parent
IMG = HERE.parent / "docs" / "img"
PROC = HERE.parent / "data" / "processed"

GREEN, ORANGE, RED, BLUE, GREY = "#d5e8d4", "#ffe6cc", "#f8cecc", "#dae8fc", "#e8e8e8"
EDGE = {"green": "#82b366", "orange": "#d79b00", "red": "#b85450",
        "blue": "#6c8ebf", "grey": "#999999"}
DPI = 160


def box(ax, x, y, w, h, text, fc=GREY, ec="#999999", fs=8.5, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.04",
                                facecolor=fc, edgecolor=ec, linewidth=1.3, linestyle=ls))
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
        ("PHASE 0\nFoundation\nS2 done, S1 partial", ORANGE, "orange", "PARTIAL"),
        ("PHASE 1\nData & model\nS3 - S4", GREEN, "green", "DONE"),
        ("PHASE 2\nDetection core\nS5 S4b S6 S8 done", ORANGE, "orange", "S7 NEXT"),
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
            "Phase 0: S2 contracts done, S1 scaffold partial.   Phase 2: S5, S4b, S6, S8 done - "
            "S7 next.   Phase 6 blocked until the S16 demo gate passes.",
            ha="center", fontsize=6.8, style="italic", color="#555555")
    save(fig, "06_roadmap.png")


# --------------------------------------------------------------------------------------------
# Iteration 2 - the detection core (S2, S5 + S4b, S6, S8). These figures read the tracked
# summaries data/processed/fusion_demo_summary.json and rule_set_validation.json.
# --------------------------------------------------------------------------------------------

EVIDENCE_COLOURS = {  # evidence class -> (edge, fill)
    "corroborated": ("#82b366", GREEN), "signature_override": ("#b85450", RED),
    "ml_only": ("#d79b00", ORANGE), "none": ("#999999", GREY),
}


def load(name):
    return json.load(open(PROC / name, encoding="utf-8"))


def diamond(ax, cx, cy, w, h, text, fs=7.6):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
                         closed=True, facecolor=BLUE, edgecolor=EDGE["blue"], linewidth=1.3))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, linespacing=1.25)


def tag(ax, x, y, text, color="#444444"):
    ax.text(x, y, text, ha="center", va="center", fontsize=7.5, weight="bold", color=color,
            bbox={"boxstyle": "round,pad=0.15", "facecolor": "white", "edgecolor": "none"})


def architecture():
    fig, ax = canvas(11, 5.5)
    H = 5.5 / 11 * 10
    ax.text(5, H - 0.28, "Detection core after Iteration 2 - what exists and what is next",
            ha="center", fontsize=10.5, weight="bold")
    ax.text(5, H - 0.58, "green = built and tested     orange = next (Claude only)     "
            "grey = planned", ha="center", fontsize=7.5, style="italic", color="#555555")
    # detection path
    box(ax, 0.2, 3.35, 2.3, 0.85, "signature/  (S5 + S4b)\nengine.py - delegated, golden-tested"
        "\nrule-set-s4b-1.json: 2 live rules", GREEN, EDGE["green"], fs=6.8)
    box(ax, 0.2, 2.25, 2.3, 0.85, "ml/inference.py  (Iteration 1)\n8-class XGBoost\n"
        "native TreeSHAP, additivity-checked", GREEN, EDGE["green"], fs=6.8)
    box(ax, 3.1, 2.8, 2.4, 0.85, "fusion/cef.py  (S6)\nevidence class - score - review\n"
        "explanation - queue order", GREEN, EDGE["green"], fs=6.8)
    box(ax, 6.1, 2.8, 1.8, 0.85, "S9  persistence\n+ batch runner", GREY, EDGE["grey"], fs=6.8)
    box(ax, 8.2, 2.8, 1.6, 0.85, "S10 - S14\nAPI + analyst UI", GREY, EDGE["grey"], fs=6.8)
    arrow(ax, 2.5, 3.775, 3.1, 3.4)
    arrow(ax, 2.5, 2.675, 3.1, 3.05)
    arrow(ax, 5.5, 3.225, 6.1, 3.225)
    arrow(ax, 7.9, 3.225, 8.2, 3.225)
    # human path
    box(ax, 0.2, 1.05, 2.3, 0.8, "analyst feedback\n(from the S11 - S12 UI)", GREY, EDGE["grey"],
        fs=6.8)
    box(ax, 3.1, 1.05, 2.4, 0.8, "S7  feedback + guardrails\nNEXT - the safety claim", ORANGE,
        EDGE["orange"], fs=6.8)
    box(ax, 6.1, 1.05, 3.7, 0.8, "audit/writer.py  (S8) - delegated\nappend-only trail - typed "
        "events - query - CSV export", GREEN, EDGE["green"], fs=6.8)
    arrow(ax, 2.5, 1.45, 3.1, 1.45)
    arrow(ax, 5.5, 1.45, 6.1, 1.45)
    arrow(ax, 4.3, 2.8, 4.3, 1.85)
    ax.text(4.42, 2.32, "fused scores", fontsize=6.5, style="italic", color="#555555")
    # foundation
    box(ax, 0.2, 0.12, 9.6, 0.62, "packages/contracts  (S2)   -   models.py   -   schema.sql: "
        "12 tables, append-only triggers   -   db.py codec   -   QUEUE_ORDER_BY",
        BLUE, EDGE["blue"], fs=7.2)
    save(fig, "07_architecture.png")


def fusion_decision():
    fig, ax = canvas(11, 6.3)
    H = 6.3 / 11 * 10
    ax.text(5, H - 0.3, "S6 - how one flow's evidence is combined  (Complementary Evidence "
            "Fusion, trust model)", ha="center", fontsize=10.5, weight="bold")
    box(ax, 0.3, 4.25, 4.3, 0.85, "Signature engine  (S5 - 2 live rules)\n"
        "sig = max severity score of the matching rules\n"
        "Low 0.40 - Medium 0.60 - High 0.80 - Critical 0.95", GREEN, EDGE["green"], fs=7.2)
    box(ax, 5.4, 4.25, 4.3, 0.85, "ML model  (8-class XGBoost + TreeSHAP)\n"
        "ml = 1 - P(Benign)      predicted class = argmax\n"
        "prediction unavailable -> review is forced", GREEN, EDGE["green"], fs=7.2)
    arrow(ax, 2.45, 4.25, 4.95, 3.88)
    arrow(ax, 7.55, 4.25, 5.05, 3.88)
    diamond(ax, 5.0, 3.45, 2.3, 0.8, "Did any\nrule match?")
    diamond(ax, 2.45, 2.35, 3.0, 0.9, "Does the model predict\na class a matching\nrule asserts?",
            fs=7.2)
    diamond(ax, 7.55, 2.35, 2.6, 0.85, "Does the model\npredict an attack?", fs=7.2)
    arrow(ax, 3.85, 3.45, 2.45, 2.80)
    tag(ax, 3.2, 3.25, "yes")
    arrow(ax, 6.15, 3.45, 7.55, 2.775)
    tag(ax, 6.8, 3.25, "no")
    leaves = [
        (0.1, "corroborated", "CORROBORATED  -  priority 0\nscore = min(100, max(sig, ml) x 100 + 5)"
                              "\nreview when score >= 80\nrule and model agree on the class"),
        (2.5, "signature_override", "SIGNATURE_OVERRIDE  -  priority 1\nscore = sig x 100\n"
                                    "review ALWAYS  (I2)\nthe model disputes the rule's class"),
        (5.2, "ml_only", "ML_ONLY  -  priority 2\nscore = ml x 100\nreview when score >= 80\n"
                         "no checkable reason"),
        (7.6, "none", "NONE  -  priority 3\nscore = ml x 100\nseverity Informational\n"
                      "no detector flagged the flow"),
    ]
    for x, evidence, text in leaves:
        edge, fill = EVIDENCE_COLOURS[evidence]
        box(ax, x, 0.45, 2.3, 1.15, text, fill, edge, fs=6.6)
    arrow(ax, 2.45, 1.9, 1.25, 1.6)
    tag(ax, 1.65, 1.82, "yes")
    arrow(ax, 2.45, 1.9, 3.65, 1.6)
    tag(ax, 3.25, 1.82, "no")
    arrow(ax, 7.55, 1.925, 6.35, 1.6)
    tag(ax, 6.75, 1.82, "yes")
    arrow(ax, 7.55, 1.925, 8.75, 1.6)
    tag(ax, 8.35, 1.82, "no")
    ax.text(5, 0.17, "Queue: ORDER BY evidence_priority, combined_score DESC (Q22).   One critical "
            "threshold - 80, the guardrails' critical_alert_threshold - sets severity Critical, "
            "is_critical and review together.", ha="center", fontsize=6.8, style="italic",
            color="#555555")
    save(fig, "08_fusion_decision.png")


def fusion_scoring():
    summary = load("fusion_demo_summary.json")
    live = summary["live_rules"]
    sig = max(rule["severity_score"] for rule in live)
    severities = sorted({rule["severity"] for rule in live})
    which = "as both live rules are" if len(severities) == 1 else "the most severe live rule"
    x = np.linspace(0, 1, 401)
    fig, ax = plt.subplots(figsize=(10, 5))
    for low, high, colour, name in [(0, 40, "#f2f2f2", "Low"), (40, 70, "#fff2cc", "Medium"),
                                    (70, 80, "#ffe6cc", "High"), (80, 100, "#f8cecc", "Critical")]:
        ax.axhspan(low, high, color=colour, alpha=0.7, zorder=0)
        ax.text(1.01, (low + high) / 2, name, transform=ax.get_yaxis_transform(), va="center",
                fontsize=8, color="#555555")
    ax.plot(x, np.minimum(100, np.maximum(sig * 100, 100 * x) + 5), color="#82b366", lw=2.6,
            label="corroborated = min(100, max(sig, ml) x 100 + 5)")
    ax.plot(x, np.full_like(x, sig * 100), color="#b85450", lw=2.2, ls="--",
            label=f"signature_override = sig x 100 = {sig * 100:g}  (the model's view is not used)")
    ax.plot(x, 100 * x, color="#d79b00", lw=2.2, label="ml_only and none = ml x 100")
    ax.axhline(80, color="#b85450", lw=1, ls=":")
    ax.text(0.01, 81.3, "critical threshold 80 - review, severity Critical and is_critical",
            fontsize=7.8, color="#b85450")
    ax.annotate(f"I1: a rule match never scores below\nsig x 100 = {sig * 100:g}",
                xy=(0.3, sig * 100), xytext=(0.04, 22), fontsize=8,
                arrowprops={"arrowstyle": "->", "color": "#555555"})
    offsets = {"corroborated": (-150, -22), "ml_only": (-150, -46), "none": (8, 8),
               "signature_override": (8, 8)}
    for evidence, ex in summary["examples"].items():
        if ex and ex["ml_probability"] is not None:
            edge, _ = EVIDENCE_COLOURS[evidence]
            point = (ex["ml_probability"], ex["combined_score"])
            ax.scatter(*point, s=60, color=edge, edgecolor="black", zorder=5)
            ax.annotate(f"{ex['alert_id']}  {evidence}  ({ex['combined_score']:g})", point,
                        xytext=offsets[evidence], textcoords="offset points", fontsize=7.5,
                        arrowprops={"arrowstyle": "-", "color": edge})
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 102)
    ax.set_xlabel("model's malicious probability   ml = 1 - P(Benign)", fontsize=9)
    ax.set_ylabel("combined score (0-100)", fontsize=9)
    ax.set_title(f"S6 - the calculation per evidence class, for a {'/'.join(severities)} rule "
                 f"(sig = {sig:.2f}, {which})", fontsize=10.5, weight="bold")
    ax.legend(loc="lower right", fontsize=7.8, framealpha=0.95)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    save(fig, "09_fusion_scoring.png")


def queue_order():
    summary = load("fusion_demo_summary.json")
    fig, ax = plt.subplots(figsize=(11, 3.1))
    for band in summary["queue_bands"]:
        evidence, first, last = band["evidence_class"], band["first"], band["last"]
        count = last - first + 1
        review = summary["classes"][evidence]["requires_review"]
        edge, fill = EVIDENCE_COLOURS[evidence]
        ax.barh(0, count, left=first - 1, color=fill, edgecolor=edge, linewidth=1.3)
        if review:  # review-flagged alerts score highest, so they lead their band
            ax.barh(0, min(review, count), left=first - 1, color="none", edgecolor=edge,
                    hatch="////", linewidth=0)
        text = f"{evidence}\npositions {first:,} - {last:,}\n{count:,} alerts, {review:,} for review"
        if count >= 600:
            ax.text(first - 1 + count / 2, 0, text, ha="center", va="center", fontsize=8)
        else:
            ax.annotate(text, (first - 1 + count / 2, 0.4),
                        xytext=(first - 1 + count / 2 + 250, 0.8), fontsize=8,
                        arrowprops={"arrowstyle": "-", "color": edge})
    ax.set_xlim(0, summary["rows"])
    ax.set_ylim(-0.6, 1.5)
    ax.set_yticks([])
    ax.set_xlabel("queue position   (1 = the first alert the analyst sees)", fontsize=9)
    ax.set_title("The analyst's queue - all 5,000 demo flows, evidence class first, score second "
                 "(Q22)", fontsize=10.5, weight="bold")
    ax.legend(handles=[Patch(facecolor="white", edgecolor="#555555", hatch="////",
                             label="requires_review")], loc="lower right", fontsize=8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    plt.tight_layout()
    save(fig, "10_queue_order.png")


def demo_fusion():
    summary = load("fusion_demo_summary.json")
    names = list(summary["classes"])
    stats = [summary["classes"][name] for name in names]
    position, width = np.arange(len(names)), 0.38
    fig, ax = plt.subplots(figsize=(10, 3.9))
    malicious = ax.bar(position - width / 2, [s["truly_malicious"] for s in stats], width,
                       color="#f4b183", edgecolor="#c55a11", label="truly malicious")
    benign = ax.bar(position + width / 2, [s["truly_benign"] for s in stats], width,
                    color="#cfe2f3", edgecolor="#6c8ebf", label="truly benign")
    for bars in (malicious, benign):
        ax.bar_label(bars, labels=[f"{int(bar.get_height()):,}" for bar in bars], padding=2,
                     fontsize=8.5, weight="bold")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_ylim(0, max(max(s["truly_malicious"], s["truly_benign"]) for s in stats) * 5)
    ax.set_xticks(position, [f"{name}\n{s['alerts']:,} alerts - {s['requires_review']:,} for review"
                             for name, s in zip(names, stats)], fontsize=8.3)
    ax.set_ylabel("flows (symlog scale)", fontsize=9)
    ax.set_title("End to end on the demo sample - what each evidence class holds "
                 "(ground truth joined after fusion)", fontsize=10.5, weight="bold")
    ax.legend(fontsize=8.5, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    save(fig, "11_demo_fusion.png")


def held_out():
    held = load("rule_set_validation.json")["held_out"]
    wrong = held["misattributed"]
    labels = ["class-correct\nhits"] + [f"{row['rule_id'].removeprefix('SIG-')} rule on\n"
                                         f"{row['true_class']} flows" for row in wrong]
    values = [held["class_correct"]] + [row["flows"] for row in wrong]
    colours = ["#82b366"] + ["#b85450" if row["true_class"] == "Benign" else "#d79b00"
                             for row in wrong]
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 3.6),
                                      gridspec_kw={"width_ratios": [1.6, 1]})
    bars = left.barh(labels, values, color=colours, edgecolor="white", linewidth=1.3)
    left.bar_label(bars, labels=[f"{value:,}" for value in values], padding=3, fontsize=9,
                   weight="bold")
    left.set_xscale("log")
    left.invert_yaxis()
    left.set_xlim(1, held["hits"] * 6)
    left.set_title(f"{held['hits']:,} rule hits on {held['rows']:,} held-out flows", fontsize=10,
                   weight="bold")
    left.tick_params(labelsize=8.5)
    left.spines[["top", "right"]].set_visible(False)
    right.axis("off")
    table = right.table(
        cellText=[["any attack\n(first reported)", f"{held['precision_malicious']:.4f}",
                   f"{held['recall_malicious']:.4f}"],
                  ["class-correct\n(rule's own class)", f"{held['precision_class']:.4f}",
                   f"{held['recall_class']:.4f}"]],
        colLabels=["scoring", "precision", "recall"], colWidths=[0.5, 0.25, 0.25],
        loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2.6)
    right.set_title("the same hits, scored two ways", fontsize=10, weight="bold")
    plt.suptitle("S4b held-out validation - the production engine on flows the rules never saw",
                 fontsize=11, weight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "12_held_out_scoring.png")


# --------------------------------------------------------------------------------------------
# The full workflow (docs/system-workflow.md)
# --------------------------------------------------------------------------------------------

STATUS_FILL = {"green": GREEN, "orange": ORANGE, "grey": GREY}


def end_to_end():
    fig, ax = canvas(12, 7.4)
    H = 7.4 / 12 * 10
    ax.text(5, H - 0.22, "The full workflow - network traffic to the analyst's dashboard, and back",
            ha="center", fontsize=11, weight="bold")
    ax.text(5, H - 0.48, "green = built and tested     orange = next or missing     grey = planned"
            "     dashed = post-demo", ha="center", fontsize=7.5, style="italic", color="#555555")
    xs, w, h = [1.3, 3.45, 5.6, 7.75], 1.95, 0.9
    for y, name in [(4.35, "1  REAL WORLD\npost-demo (S17)"), (3.0, "2  LOCAL TODAY\ndemo data"),
                    (1.65, "3  DETECTION\nCORE"), (0.3, "4  STORE, SHOW,\nFEEDBACK")]:
        ax.add_patch(FancyBboxPatch((0.05, y - 0.08), 9.9, 1.06,
                                    boxstyle="round,pad=0.01,rounding_size=0.03",
                                    facecolor="#fafafa", edgecolor="#dddddd", linewidth=1))
        ax.text(0.62, y + 0.45, name, ha="center", va="center", fontsize=6.8, weight="bold",
                color="#555555")

    def lane(y, boxes, rightward=True):
        for i, (text, status, dashed) in enumerate(boxes):
            box(ax, xs[i], y, w, h, text, STATUS_FILL[status], EDGE[status], fs=6.3,
                ls="--" if dashed else "-")
        for i in range(3):
            if rightward:
                arrow(ax, xs[i] + w, y + h / 2, xs[i + 1], y + h / 2)
            else:
                arrow(ax, xs[i + 1], y + h / 2, xs[i] + w, y + h / 2)

    lane(4.35, [("Network traffic\nhosts, servers, users", "grey", True),
                ("Packet capture\nSPAN / TAP port, or PCAP", "grey", True),
                ("Flow exporter\nCICFlowMeter fork (Engelen)\nthe tool that made the dataset", "grey", True),
                ("ExporterSource\na second FlowSource\n(D7)", "grey", True)])
    lane(3.0, [("Corrected CSE-CIC-IDS2018\n10.4 GB zip, authors' server\n63.2M labelled flows", "green", False),
               ("scan + sample\nstreamed, seed 20260911\n5,000 demo / 250,655 train", "green", False),
               ("FlowSource: CsvReplaySource\nreplays rows in time order\nS3 seam - NOT BUILT", "orange", False),
               ("Flow records\none row per flow, CIC features\nlabels set aside", "green", False)])
    lane(1.65, [("Alert\ndetection_score  (fixed)\ncombined_score  (moves)", "green", False),
                ("Fusion  (S6)\nevidence class + score\n+ review flag + explanation", "green", False),
                ("Signature engine (2 rules)\n+ ML model (8 classes, SHAP)\nrun side by side", "green", False),
                ("Two views of each flow\n16 fields for the rules\n82 features for the model", "green", False)],
         rightward=False)
    lane(0.3, [("SQLite + batch runner (S9)\nalerts, flow_data,\ndetection_runs, audit_log", "grey", False),
               ("API (S10) + dashboard\n(S11 - S14): queue by class,\nthen by combined_score", "grey", False),
               ("Analyst decision\none of 5 feedback\ncategories", "grey", False),
               ("Guardrails (S7) - NEXT\ncap, floors, I3\naudit trail (S8) built", "orange", False)])
    arrow(ax, xs[3] + w / 2, 4.35, xs[3] + w / 2, 3.9)
    ax.text(xs[3] + w / 2 + 0.06, 4.12, "plugs in later", fontsize=6, style="italic", color="#555555")
    arrow(ax, xs[3] + w / 2, 3.0, xs[3] + w / 2, 2.55)
    arrow(ax, xs[0] + w / 2, 1.65, xs[0] + w / 2, 1.2)
    ax.plot([xs[3] + w / 2, xs[3] + w / 2, xs[0] + w / 2], [0.3, 0.1, 0.1], color="#b85450",
            linewidth=1.4)
    arrow(ax, xs[0] + w / 2, 0.1, xs[0] + w / 2, 0.3, color="#b85450")
    ax.text(5.0, 0.1, "new combined_score written back  -  detection_score never changes",
            ha="center", va="center", fontsize=6.6, style="italic", color="#b85450",
            bbox={"boxstyle": "round,pad=0.15", "facecolor": "white", "edgecolor": "none"})
    save(fig, "13_workflow_end_to_end.png")


def feedback_loop():
    fig, ax = canvas(11, 6.0)
    H = 6.0 / 11 * 10
    ax.text(5, H - 0.22, "S7 (next) - how analyst feedback becomes a new score, inside the "
            "guardrails", ha="center", fontsize=10.5, weight="bold")
    box(ax, 0.2, 3.7, 3.0, 1.3, "Analyst feedback on one alert  ->  requested change\n"
        "confirm_true_positive   +10   (forces review)\nmark_false_positive   -30\n"
        "mark_expected_activity   -15\nneeds_investigation   0   (forces review)\n"
        "escalate   +15   (forces review)", ORANGE, EDGE["orange"], fs=6.7)
    box(ax, 3.5, 3.9, 2.3, 0.9, "duplicate is a queue action,\nnot a score change:\n"
        "alerts.is_duplicate_of", GREY, EDGE["grey"], fs=6.6)
    box(ax, 6.1, 3.7, 3.7, 1.3, "Later - similar-alert learning (adaptation-config)\n"
        ">= 3 similar events with >= 67% agreement\nfalse positive -10 / -25     true positive +8 / +15"
        "\nexpected activity -15 (strong agreement only)\nthe same guardrails apply",
        GREY, EDGE["grey"], fs=6.6, ls="--")
    chain = [(0.2, "1  Evidence check\nsignature_override: score frozen,\nrouted to the administrator (I3)"),
             (2.65, "2  Cap the change\nat most -30 or +20\nper feedback event"),
             (5.1, "3  Floors\nCritical alert held at >= 70\nInfiltration held at >= 75"),
             (7.55, "4  Outcome\napplied / capped / rejected\n+ reason + review flag")]
    for x, text in chain:
        box(ax, x, 2.1, 2.25, 1.0, text, ORANGE, EDGE["orange"], fs=6.8)
    arrow(ax, 1.7, 3.7, 1.32, 3.1)
    for (x, _), (next_x, _) in zip(chain, chain[1:]):
        arrow(ax, x + 2.25, 2.6, next_x, 2.6)
    for x, text, status in [
            (0.2, "feedback_events  (S2)\nappend-only row: original,\nrequested and actual change", "green"),
            (2.65, "alerts.combined_score  (S2)\n= the score after the guardrails\ndetection_score never changes", "green"),
            (5.1, "audit_log  (S8)\nFEEDBACK + GUARDRAIL_* entries\nactor, time, rationale", "green"),
            (7.55, "dashboard  (S10 - S12)\ndetection vs current score,\nguardrail badge, queue re-sorted", "grey")]:
        box(ax, x, 0.45, 2.25, 1.0, text, STATUS_FILL[status], EDGE[status], fs=6.6)
        arrow(ax, 8.675, 2.1, x + 1.125, 1.45)
    ax.text(5, 0.15, "green = the tables and the writer already exist (S2, S8)     orange = S7 builds "
            "the logic     grey = planned", ha="center", fontsize=7, style="italic", color="#555555")
    save(fig, "14_feedback_loop.png")


def dashboard_columns():
    # Real demo scores and queue positions. The feedback is ILLUSTRATIVE - S7 is not built yet -
    # and follows the adopted constants: change capped to -30..+20, Critical alerts held at 70.
    rows = [
        ["3", "AL-00060", "corroborated", "100.00", "100.00", "", "", "yes", ""],
        ["201", "AL-00004", "ml_only", "100.00", "100.00", "", "", "yes", ""],
        ["989 -> 995", "AL-00478", "ml_only", "99.89", "70.00", "-29.89",
         "critical floor (asked -30)", "yes", "false positive"],
        ["995 -> 996", "AL-02717", "ml_only", "88.48", "70.00", "-18.48",
         "critical floor (asked -30)", "yes", "false positive"],
        ["998 -> 997", "AL-03086", "none", "36.94", "46.94", "+10.00", "applied in full", "yes",
         "confirmed attack"],
        ["997 -> 998", "AL-00900", "none", "42.77", "42.77", "", "", "no", ""],
    ]
    columns = ["queue #", "alert", "evidence class", "detection score\n(fixed)",
               "current score\n(after feedback)", "change", "guardrail", "review", "last feedback"]
    fig, ax = plt.subplots(figsize=(12, 3.5))
    ax.axis("off")
    table = ax.table(cellText=rows, colLabels=columns, loc="center", cellLoc="center",
                     colWidths=[0.09, 0.08, 0.11, 0.12, 0.13, 0.07, 0.155, 0.06, 0.115])
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.9)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#bbbbbb")
        if row == 0:
            cell.set_facecolor("#dae8fc")
            cell.set_text_props(weight="bold")
        elif col == 4:
            cell.set_facecolor("#d5e8d4")
        elif rows[row - 1][5] and col in (5, 6, 8):
            cell.set_facecolor("#ffe6cc")
    ax.set_title("The dashboard after feedback - two score columns (illustrative feedback on real "
                 "demo alerts)", fontsize=10.5, weight="bold")
    fig.text(0.5, 0.04, "Scores and queue positions are real. The three feedback events are "
             "hypothetical and follow the adopted guardrail constants; S7 builds the real service.",
             ha="center", fontsize=7.8, style="italic", color="#555555")
    save(fig, "15_dashboard_columns.png")


if __name__ == "__main__":
    # Iteration 1
    pipeline(); classes(); versions(); reversal(); triage(); roadmap()
    # Iteration 2 - needs data/processed/fusion_demo_summary.json (scripts/fusion_demo_summary.py)
    architecture(); fusion_decision(); fusion_scoring(); queue_order(); demo_fusion(); held_out()
    # the full workflow (docs/system-workflow.md)
    end_to_end(); feedback_loop(); dashboard_columns()
    print("\nall diagrams written to", IMG)
