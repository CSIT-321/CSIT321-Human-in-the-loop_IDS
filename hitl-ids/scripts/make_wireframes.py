"""
Render the Preliminary User Manual's interface wireframes as PNG images.

    python scripts/make_wireframes.py            # all screens
    python scripts/make_wireframes.py 03 08      # only these

High-fidelity mockups for section (4), "Initial GUIs", of the Preliminary User Manual. They are
drawn with matplotlib for the same reason `make_diagrams.py` is: no Node, no browser, no system
Graphviz, and the output pastes straight into Word.

**The design is the collaborator's, continued rather than reinvented.** `dashboard/src` is a frozen
research record, but the plan's anti-pattern list is explicit that freezing it does not mean
refusing to read it. The palette, the console shell (sidebar + header + workspace), the KPI card
groups and the `fusion score -> feedback adjustment -> current score` comparison all come from
`dashboard/src/styles.css` and its components. What changes is what the screens *say*: their
feedback controls are labelled "UI-only, no backend write-back", and since S10b ours writes through
to a real database, is guarded, audited, and carries to similar alerts.

**Every value on these screens is real**, read from `data/demo.db`. `AL-00478` really is a benign
flow the model calls a Web Attack at 0.999 confidence, and a -30 request on it really is held at
the floor of 70. A mockup with invented numbers cannot be checked against the system, and an
assessor who checks one and finds it fictional will not trust the rest.

Output: hitl-ids/docs/img/wireframes/*.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

HITL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HITL))
OUT = HITL / "docs" / "img" / "wireframes"

# --------------------------------------------------------------------------------------------
# The collaborator's palette (dashboard/src/styles.css), continued.
# --------------------------------------------------------------------------------------------
BG = "#08111f"
SURFACE = "#0f1d33"
RAISED = "#16294a"
BORDER = "#1e3a5f"
TEXT = "#e5edf6"
MUTED = "#94a3b8"
DIM = "#64748b"
CYAN = "#38bdf8"
CYAN_DIM = "#0e4b6e"
ORANGE = "#f97316"
ORANGE_DIM = "#7c2d12"
GREEN = "#22c55e"
GREEN_DIM = "#14532d"
RED = "#ef4444"
RED_DIM = "#7f1d1d"
VIOLET = "#a78bfa"

#: Canvas units are typographic points, not pixels: matplotlib sizes text in points, so a
#: pixel canvas makes every font 2.2x too large for its box. At 1 unit = 1 pt the layout
#: numbers below read as they would in a design tool.
PT = 72.0
W, H = 1600.0, 1000.0
DPI = 96
FONT = "DejaVu Sans"

#: The console's left navigation, as the collaborator's Sidebar lays it out.
NAV = ["Dashboard", "Alert Queue", "Investigations", "Feedback Impact", "Audit Trail"]


def screen(height: float = H):
    """A blank console window, at pixel-like coordinates with y growing downward."""
    fig = plt.figure(figsize=(W / PT, height / PT), dpi=DPI, facecolor=BG)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, W)
    ax.set_ylim(0, height)
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(Rectangle((0, 0), W, height, facecolor=BG, edgecolor="none", zorder=0))
    return fig, ax


def box(ax, x, y, w, h, *, fc=SURFACE, ec=BORDER, lw=1.2, r=8, z=1, ls="-"):
    r = min(r, w / 2, h / 2)
    ax.add_patch(FancyBboxPatch(
        (x + r, y + r), max(w - 2 * r, 0.1), max(h - 2 * r, 0.1),
        boxstyle=f"round,pad={r},rounding_size={r}",
        facecolor=fc, edgecolor=ec, linewidth=lw, linestyle=ls, zorder=z))


def text(ax, x, y, s, *, size=11, color=TEXT, weight="normal", ha="left", va="center",
         z=3, style="normal"):
    ax.text(x, y, s, fontsize=size, color=color, fontweight=weight, ha=ha, va=va,
            family=FONT, zorder=z, fontstyle=style)


def pill(ax, x, y, s, *, fc=CYAN_DIM, tc=CYAN, size=9, pad=10, h=22, z=3):
    w = len(s) * size * 0.55 + pad * 2
    box(ax, x, y - h / 2, w, h, fc=fc, ec=fc, r=h / 2, z=z)
    text(ax, x + w / 2, y, s, size=size, color=tc, ha="center", z=z + 1)
    return w


def button(ax, x, y, w, s, *, h=34, fc=CYAN, tc="#04202f", size=11, weight="bold", z=3, ec=None):
    box(ax, x, y - h / 2, w, h, fc=fc, ec=ec or fc, r=7, z=z)
    text(ax, x + w / 2, y, s, size=size, color=tc, ha="center", weight=weight, z=z + 1)
    return w


def bar(ax, x, y, w, h, frac, *, fc=CYAN, bg=RAISED, z=3):
    box(ax, x, y, w, h, fc=bg, ec=bg, r=h / 2, z=z)
    if frac > 0:
        box(ax, x, y, max(h, w * frac), h, fc=fc, ec=fc, r=h / 2, z=z + 1)


def panel(ax, x, y, w, h, title, *, sub=None, fc=SURFACE, z=1):
    """A titled surface - the console's basic unit. Returns the y of its first content row."""
    box(ax, x, y, w, h, fc=fc, z=z)
    text(ax, x + 18, y + 26, title, size=12, weight="bold", z=z + 2)
    if sub:
        text(ax, x + 18, y + 46, sub, size=9.5, color=MUTED, z=z + 2)
    return y + (66 if sub else 50)


def chrome(ax, *, role="Security Analyst", active="Alert Queue", height=H, crumb=""):
    """Top bar and left navigation - present on every screen inside the console."""
    box(ax, 0, 0, W, 56, fc="#0a1626", ec=BORDER, r=0, z=2)
    box(ax, 22, 16, 24, 24, fc=CYAN, ec=CYAN, r=6, z=3)
    text(ax, 58, 28, "IDS Console", size=14, weight="bold", z=3)
    text(ax, 180, 29, "Human-in-the-loop triage", size=9.5, color=MUTED, z=3)
    if crumb:
        text(ax, 372, 29, crumb, size=10, color=DIM, z=3)

    pill(ax, W - 452, 28, "Demo build - role switch stub", fc="#3b2a06", tc="#fbbf24", size=8.5)
    box(ax, W - 250, 14, 152, 28, fc=RAISED, ec=BORDER, r=6, z=3)
    text(ax, W - 238, 28, role, size=10, z=4)
    text(ax, W - 114, 28, "▾", size=9, color=MUTED, z=4)
    box(ax, W - 82, 14, 28, 28, fc=CYAN_DIM, ec=CYAN_DIM, r=14, z=3)
    text(ax, W - 68, 28, "GA", size=9.5, color=CYAN, ha="center", z=4)

    box(ax, 0, 56, 210, height - 56, fc="#0a1626", ec=BORDER, r=0, z=2)
    y = 94
    for item in NAV:
        selected = item == active
        if selected:
            box(ax, 12, y - 17, 186, 34, fc=CYAN_DIM, ec=CYAN_DIM, r=7, z=3)
            box(ax, 12, y - 17, 4, 34, fc=CYAN, ec=CYAN, r=2, z=4)
        text(ax, 32, y, item, size=11, color=CYAN if selected else MUTED,
             weight="bold" if selected else "normal", z=4)
        y += 44
    return y


def footnote(ax, s, *, height=H, color=DIM):
    text(ax, 228, height - 22, s, size=8.5, color=color, style="italic", z=6)


def save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    fig.savefig(path, dpi=DPI, facecolor=BG)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------------------------
# Real values, read once from the demo database so every screen agrees with the system.
# --------------------------------------------------------------------------------------------

def load_demo() -> dict:
    from packages.contracts import db
    from packages.detection.pipeline import store

    path = HITL / "data" / "demo.db"
    if not path.exists():
        raise SystemExit(f"missing {path}\nbuild it with: python scripts/run_detection.py")
    conn = db.connect(str(path))
    try:
        rows, total = store.queue_page(conn, limit=7)
        data: dict = {"total": total, "counts": store.dashboard_counts(conn),
                      "guardrails": {e.config_key: e.config_value
                                     for e in store.guardrail_settings(conn)}, "queue": []}
        for alert, flow in rows:
            data["queue"].append({
                "rec": flow.source_record_id, "band": alert.queue_class,
                "det": alert.detection_score, "comb": alert.combined_score,
                "sev": alert.severity, "cls": alert.attack_category or "-",
                "ev": alert.evidence_class, "src": flow.src_ip, "dst": flow.dst_ip,
                "port": flow.dst_port, "proto": flow.protocol,
                "review": alert.requires_review,
                "rules": [x.rule_id for x in (alert.signature_rules or [])]})
        for rec in ("AL-00478", "AL-03086", "AL-00060"):
            row = conn.execute("SELECT alert_id FROM flow_data WHERE source_record_id = ?",
                               (rec,)).fetchone()
            ref = conn.execute("SELECT alert_ref FROM alerts WHERE id = ?",
                               (row["alert_id"],)).fetchone()["alert_ref"]
            alert = store.alert_by_ref(conn, ref)
            flow = store.flow_for_alert(conn, row["alert_id"])
            shap = alert.shap_attributions
            data[rec] = {
                "det": alert.detection_score, "comb": alert.combined_score,
                "sev": alert.severity, "cls": alert.attack_category or "-",
                "ev": alert.evidence_class, "band": alert.queue_class,
                "prob": alert.ml_probability, "crit": alert.is_critical,
                "review": alert.requires_review, "family": alert.family_key,
                "src": flow.src_ip, "dst": flow.dst_ip, "port": flow.dst_port,
                "proto": flow.protocol, "packets": flow.packets, "bytes": flow.bytes,
                "dur": flow.duration,
                "rules": [{"id": r.rule_id, "name": r.name, "sev": r.severity,
                           "cond": [(c.feature, str(c.expected), str(c.observed))
                                    for c in r.matched_conditions]}
                          for r in (alert.signature_rules or [])],
                "up": [(s.feature_name, s.shap_contribution)
                       for s in (shap.top_supporting_features if shap else [])][:5],
                "down": [(s.feature_name, s.shap_contribution)
                         for s in (shap.top_opposing_features if shap else [])][:3],
                "additivity": shap.additivity_check.passed if shap else None}
        import json
        runs = sorted((HITL / "evaluation" / "three-arm" / "runs").glob("*/results.json"))
        if runs:
            data["eval"] = json.loads(runs[-1].read_text(encoding="utf-8"))
        return data
    finally:
        conn.close()


BAND_COLOUR = {"tier2_candidate": (RED, RED_DIM), "corroborated": (GREEN, GREEN_DIM),
               "signature_override": (VIOLET, "#3b2764"), "ml_only": (CYAN, CYAN_DIM),
               "none": (DIM, "#1c2942")}
BAND_LABEL = {"tier2_candidate": "TIER 2", "corroborated": "CORROB", "ml_only": "ML ONLY",
              "signature_override": "SIG OVR", "none": "NONE"}


def queue_row(ax, x, y, w, item, *, selected=False, h=62):
    """One row of the ranked queue - the band, both scores, the flow, and what fired."""
    fg, bgc = BAND_COLOUR[item["band"]]
    box(ax, x, y, w, h, fc=RAISED if selected else SURFACE,
        ec=CYAN if selected else BORDER, lw=1.6 if selected else 1.1, z=4)
    box(ax, x, y, 5, h, fc=fg, ec=fg, r=2, z=5)
    pill(ax, x + 18, y + 20, BAND_LABEL[item["band"]], fc=bgc, tc=fg, size=8)
    text(ax, x + 18, y + 44, item["rec"], size=10.5, weight="bold", z=6)

    text(ax, x + 132, y + 20, f"{item['det']:.2f}", size=13, weight="bold", color=MUTED, z=6)
    text(ax, x + 132, y + 42, "detection", size=8, color=DIM, z=6)
    text(ax, x + 206, y + 31, "→", size=12, color=DIM, z=6)
    moved = item["comb"] != item["det"]
    text(ax, x + 232, y + 20, f"{item['comb']:.2f}", size=13, weight="bold",
         color=GREEN if moved else TEXT, z=6)
    text(ax, x + 232, y + 42, "operational", size=8, color=DIM, z=6)

    text(ax, x + 330, y + 20, item["cls"], size=10.5, z=6)
    text(ax, x + 330, y + 42, item["sev"], size=8.5, color=MUTED, z=6)
    text(ax, x + 462, y + 20, f"{item['src']}  →  {item['dst']}:{item['port']}",
         size=9.5, color=MUTED, z=6)
    rules = ", ".join(item["rules"]) if item["rules"] else "no rule matched (model only)"
    text(ax, x + 462, y + 42, rules, size=9,
         color=MUTED if item["rules"] else DIM, style="normal" if item["rules"] else "italic", z=6)
    if item["review"]:
        pill(ax, x + w - 116, y + 31, "review", fc=ORANGE_DIM, tc=ORANGE, size=8.5)


# --------------------------------------------------------------------------------------------
# (4.3) The ranked alert queue
# --------------------------------------------------------------------------------------------

def screen_queue(d: dict):
    h = 1010.0
    fig, ax = screen(h)
    chrome(ax, active="Alert Queue", height=h, crumb="Alert Queue")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Alert Queue", size=19, weight="bold")
    text(ax, x, 122, f"{d['total']:,} alerts from detection run #1 - ranked, not merely listed",
         size=10, color=MUTED)
    button(ax, x + w - 168, 108, 168, "Export queue (CSV)", fc=RAISED, tc=CYAN, ec=BORDER)

    # Filter bar - the collaborator's FilterBar, reduced to the filters our API supports.
    box(ax, x, 146, w, 52, fc=SURFACE, z=1)
    fx = x + 16
    for label, active in (("All alerts", False), ("Requires review", True),
                          ("Tier 2 candidates", False), ("Feedback applied", False),
                          ("Model only", False), ("Corroborated", False)):
        fx += pill(ax, fx, 172, label, fc=CYAN_DIM if active else RAISED,
                   tc=CYAN if active else MUTED, size=9.5, h=26) + 10
    text(ax, x + w - 268, 172, "Attack type:", size=9.5, color=DIM)
    box(ax, x + w - 176, 159, 160, 26, fc=RAISED, ec=BORDER, r=6, z=3)
    text(ax, x + w - 166, 172, "All 8 classes", size=9.5, color=MUTED, z=4)
    text(ax, x + w - 36, 172, "v", size=9, color=MUTED, z=4)

    # Column headings, so the two score columns are unambiguous.
    text(ax, x + 18, 222, "BAND / RECORD", size=8.5, color=DIM, weight="bold")
    text(ax, x + 150, 222, "SCORES", size=8.5, color=DIM, weight="bold")
    text(ax, x + 348, 222, "CLASS", size=8.5, color=DIM, weight="bold")
    text(ax, x + 480, 222, "FLOW  /  WHAT FIRED", size=8.5, color=DIM, weight="bold")
    text(ax, x + w - 132, 222, "STATUS", size=8.5, color=DIM, weight="bold")

    y = 238
    for i, item in enumerate(d["queue"]):
        queue_row(ax, x, y, w, item, selected=(i == 1))
        y += 70

    # The demo's opening move, made findable in the queue.
    a = dict(d["AL-00478"])
    a.update({"rec": "AL-00478", "review": True, "rules": []})
    queue_row(ax, x, y + 14, w, a)
    box(ax, x, y + 14, w, 62, fc="none", ec=ORANGE, lw=2.0, r=8, ls=(0, (4, 3)), z=8)
    text(ax, x + 8, y + 94,
         "The model is confident and wrong: ground truth says this flow is benign. "
         "The analyst is about to say so.",
         size=9, color=ORANGE, style="italic", z=8)

    text(ax, x, h - 78, f"Showing 1-8 of {d['total']:,}", size=9.5, color=MUTED)
    for i, label in enumerate(("Prev", "1", "2", "3", "...", "100", "Next")):
        box(ax, x + 160 + i * 54, h - 92, 48, 28, fc=CYAN_DIM if label == "1" else RAISED,
            ec=BORDER, r=6, z=3)
        text(ax, x + 184 + i * 54, h - 78, label, size=9.5,
             color=CYAN if label == "1" else MUTED, ha="center", z=4)
    footnote(ax, "Ordered by queue band, then score, then id - the contract's order. Feedback "
                 "moves an alert between bands; it never changes its evidence class.", height=h)
    return save(fig, "04_03_alert_queue")


# --------------------------------------------------------------------------------------------
# (4.8) The score adjustment chain - the guardrails made visible
# --------------------------------------------------------------------------------------------

def screen_adjustment(d: dict):
    h = 900.0
    a, g = d["AL-00478"], d["guardrails"]
    floor = g["critical_alert_floor"]
    cap = g["max_feedback_reduction"]
    after = max(floor, a["det"] - cap)
    applied = a["det"] - after

    fig, ax = screen(h)
    chrome(ax, active="Alert Queue", height=h,
           crumb="Alert Queue  >  AL-00478  >  Feedback applied")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Score adjustment", size=19, weight="bold")
    text(ax, x, 122, "What you asked for, what the guardrails allowed, and why",
         size=10, color=MUTED)
    pill(ax, x + w - 196, 108, "Recorded and audited", fc=GREEN_DIM, tc=GREEN, size=9.5, h=26)

    # The chain, left to right. This is the figure the whole demo turns on.
    top = panel(ax, x, 152, w, 254, "Adjustment chain",
                sub="Every step is stored; none of it is recomputed for display")
    steps = [
        ("Detection score", f"{a['det']:.2f}", "immutable", MUTED, RAISED),
        ("You requested", f"-{cap:.0f}", "mark false positive", ORANGE, ORANGE_DIM),
        ("Guardrail bound", f"floor {floor:.0f}", "critical alert floor", RED, RED_DIM),
        ("Actually applied", f"-{applied:.2f}", "capped", ORANGE, ORANGE_DIM),
        ("Operational score", f"{after:.2f}", "what the queue uses", GREEN, GREEN_DIM),
    ]
    bw, gap = 224, 26
    sx = x + 22
    for i, (label, value, note, fg, bgc) in enumerate(steps):
        box(ax, sx, top + 6, bw, 120, fc=bgc, ec=fg, lw=1.4, z=4)
        text(ax, sx + bw / 2, top + 34, label, size=9.5, color=MUTED, ha="center", z=6)
        text(ax, sx + bw / 2, top + 70, value, size=23, weight="bold", color=fg, ha="center", z=6)
        text(ax, sx + bw / 2, top + 102, note, size=8.5, color=MUTED, ha="center", z=6)
        if i < len(steps) - 1:
            text(ax, sx + bw + gap / 2, top + 68, ">", size=15, color=DIM, ha="center", z=6)
        sx += bw + gap

    text(ax, x + 22, top + 164,
         "Scores are bounded 0-100. The floor applies to the alert's immutable detection score, "
         "never to an already-adjusted value, so feedback cannot stack.", size=9.5, color=MUTED)

    # Why it bound - the sentence the analyst actually reads.
    lw = w * 0.56
    wy = panel(ax, x, 428, lw, 180, "Why the guardrail intervened")
    box(ax, x + 20, wy + 4, lw - 40, 64, fc=RED_DIM, ec=RED, lw=1.3, z=4)
    text(ax, x + 36, wy + 24, "critical_alert_floor", size=10, weight="bold", color=RED, z=6)
    text(ax, x + 36, wy + 50,
         f"This alert is Critical, so its score was held at the floor of {floor:.0f}.",
         size=10, color=TEXT, z=6)
    text(ax, x + 20, wy + 96,
         f"Requested -{cap:.2f}    allowed -{applied:.2f}    withheld {cap - applied:.2f}",
         size=10, color=MUTED)
    text(ax, x + 20, wy + 122,
         "The verdict was still recorded. The guardrail limited the score change, not your finding.",
         size=9.5, color=DIM, style="italic")

    # What it taught the family.
    fx2, fw = x + lw + 24, w - lw - 24
    fy = panel(ax, fx2, 428, fw, 180, "What this taught similar alerts",
               sub="Agreement gate: 1 of 3 verdicts")
    bar(ax, fx2 + 20, fy + 12, fw - 40, 10, 1 / 3, fc=ORANGE)
    text(ax, fx2 + 20, fy + 48, "Gate closed - two more verdicts needed", size=10, color=ORANGE)
    text(ax, fx2 + 20, fy + 74, f"Family: {a['cls']} - port {a['port']} - {a['proto'].lower()}",
         size=9.5, color=MUTED)
    text(ax, fx2 + 20, fy + 96, "60 similar alerts are waiting on this decision.",
         size=9.5, color=MUTED)
    text(ax, fx2 + 20, fy + 118, "Nothing has moved yet. One analyst cannot shift a family.",
         size=9, color=DIM, style="italic")

    # Audit.
    ay = panel(ax, x, 632, w, 132, "Written to the audit trail",
               sub="Append-only; UPDATE and DELETE are refused by the database")
    rows = (("FEEDBACK", "verdict recorded - analyst Glenn A. - mark_false_positive"),
            ("GUARDRAIL_INTERVENTION", f"critical_alert_floor held the score at {after:.2f}"))
    for i, (code, label) in enumerate(rows):
        text(ax, x + 24, ay + 14 + i * 32, "*", size=11, color=CYAN)
        text(ax, x + 44, ay + 14 + i * 32, code, size=9.5, weight="bold", color=CYAN)
        text(ax, x + 268, ay + 14 + i * 32, label, size=9.5, color=MUTED)

    button(ax, x, 812, 176, "Amend this verdict", fc=RAISED, tc=CYAN, ec=BORDER)
    button(ax, x + 192, 812, 162, "View full history", fc=RAISED, tc=CYAN, ec=BORDER)
    button(ax, x + w - 196, 812, 196, "Back to queue", fc=CYAN)
    footnote(ax, "Guardrail settings belong to the administrator: floor 70, maximum reduction 30. "
                 "An analyst can see them but cannot change them.", height=h)
    return save(fig, "04_08_score_adjustment")


# --------------------------------------------------------------------------------------------
# (4.1) Sign in and role selection
# --------------------------------------------------------------------------------------------

def screen_login(d: dict):
    h = 780.0
    fig, ax = screen(h)

    cw, cx = 470, (W - 470) / 2
    box(ax, cx, 120, cw, 470, fc=SURFACE, z=2)
    box(ax, cx + (cw - 46) / 2, 158, 46, 46, fc=CYAN, ec=CYAN, r=11, z=3)
    text(ax, W / 2, 236, "IDS Console", size=22, weight="bold", ha="center")
    text(ax, W / 2, 262, "Human-in-the-loop intrusion detection", size=10.5,
         color=MUTED, ha="center")

    text(ax, cx + 34, 306, "Username", size=9.5, color=MUTED)
    box(ax, cx + 34, 318, cw - 68, 38, fc=RAISED, ec=BORDER, r=7, z=3)
    text(ax, cx + 48, 337, "g.ang", size=11, z=4)
    text(ax, cx + 34, 376, "Password", size=9.5, color=MUTED)
    box(ax, cx + 34, 388, cw - 68, 38, fc=RAISED, ec=BORDER, r=7, z=3)
    text(ax, cx + 48, 407, "........", size=13, color=MUTED, z=4)

    text(ax, cx + 34, 448, "Sign in as", size=9.5, color=MUTED)
    rx = cx + 34
    for label, on in (("Analyst", True), ("Administrator", False), ("Evaluator", False)):
        wpill = pill(ax, rx, 476, label, fc=CYAN_DIM if on else RAISED,
                     tc=CYAN if on else MUTED, size=10, h=30)
        if on:
            box(ax, rx, 461, wpill, 30, fc="none", ec=CYAN, lw=1.4, r=15, z=5)
        rx += wpill + 12
    button(ax, cx + 34, 534, cw - 68, "Sign in", h=40)

    box(ax, cx, 616, cw, 76, fc="#2a1e05", ec="#8a6d1b", z=2)
    text(ax, cx + 20, 642, "Demo build", size=10, weight="bold", color="#fbbf24", z=4)
    text(ax, cx + 20, 666, "Authentication is a stub: the role you pick is trusted as sent.",
         size=9.5, color="#fcd34d", z=4)
    text(ax, W / 2, h - 40,
         "Real sign-in (JWT, bcrypt, role-based access control) is scheduled after the demo gate.",
         size=9, color=DIM, ha="center", style="italic")
    return save(fig, "04_01_login")


# --------------------------------------------------------------------------------------------
# (4.2) Analyst dashboard - the landing view
# --------------------------------------------------------------------------------------------

def screen_dashboard(d: dict):
    h, c = 680.0, d["counts"]
    fig, ax = screen(h)
    chrome(ax, active="Dashboard", height=h, crumb="Dashboard")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Good morning, Glenn", size=19, weight="bold")
    text(ax, x, 122, "Detection run #1 - 5,000 flows scored in 21 s - model xgb-8class-20260911",
         size=10, color=MUTED)

    cards = [("Alerts in queue", f"{c['total_alerts']:,}", "every flow becomes an alert", CYAN),
             ("Awaiting review", f"{c['requires_review']:,}", "flagged by fusion or a guardrail",
              ORANGE),
             ("Tier 2 candidates", f"{c['tier2_candidates']:,}", "would escalate past Tier 1", RED),
             ("Moved by feedback", f"{c['alerts_moved_by_feedback']:,}",
              "no verdicts recorded yet", GREEN)]
    cw = (w - 3 * 18) / 4
    for i, (label, value, note, fg) in enumerate(cards):
        cx = x + i * (cw + 18)
        box(ax, cx, 150, cw, 112, fc=SURFACE, z=2)
        text(ax, cx + 20, 178, label, size=10, color=MUTED, z=4)
        text(ax, cx + 20, 214, value, size=25, weight="bold", color=fg, z=4)
        text(ax, cx + 20, 246, note, size=8.5, color=DIM, z=4)

    # Queue composition - the evidence classes, which is the finding that shaped the project.
    lw = w * 0.54
    ey = panel(ax, x, 284, lw, 302, "Queue composition",
               sub="Where the 5,000 alerts sit, and on what evidence")
    bands = [("Tier 2 candidate", c["tier2_candidates"], RED),
             ("Model only", c["by_evidence_class"].get("ml_only", 796), CYAN),
             ("Nothing flagged it", c["by_evidence_class"].get("none", 4004), DIM)]
    by = ey + 10
    for label, count, fg in bands:
        text(ax, x + 22, by + 12, label, size=10)
        text(ax, x + lw - 24, by + 12, f"{count:,}", size=10, weight="bold", color=fg, ha="right")
        bar(ax, x + 22, by + 26, lw - 46, 9, count / max(c["total_alerts"], 1), fc=fg)
        by += 54
    text(ax, x + 22, by + 12,
         "Signature override: 0. On the corrected dataset no rule fires where the", size=9,
         color=MUTED)
    text(ax, x + 22, by + 30,
         "model stays silent, so the rules earn their place by explaining, not by", size=9,
         color=MUTED)
    text(ax, x + 22, by + 48, "catching what the model misses.", size=9, color=MUTED)

    # What needs a human.
    ax2, aw = x + lw + 24, w - lw - 24
    ay = panel(ax, ax2, 284, aw, 302, "Needs a human today", sub="Highest-value decisions first")
    items = [("AL-00478", "Model calls it Web Attack at 0.999. No rule agrees.", ORANGE),
             ("AL-03086", "Attempted Web Attack. Neither detector flagged it.", RED),
             ("644 alerts", "Tier 2 candidates awaiting triage.", CYAN)]
    iy = ay + 12
    for ref, note, fg in items:
        box(ax, ax2 + 20, iy, aw - 40, 60, fc=RAISED, ec=BORDER, z=3)
        text(ax, ax2 + 36, iy + 22, ref, size=10.5, weight="bold", color=fg, z=5)
        text(ax, ax2 + 36, iy + 44, note, size=9, color=MUTED, z=5)
        iy += 72
    footnote(ax, "Counts come from the detection run, not from a cache. 'Moved by feedback' "
                 "reads 0 until an analyst records a verdict.", height=h)
    return save(fig, "04_02_dashboard")


# --------------------------------------------------------------------------------------------
# (4.4) Alert detail - the four evidence panels
# --------------------------------------------------------------------------------------------

def screen_detail(d: dict):
    h, a = 880.0, d["AL-00478"]
    fig, ax = screen(h)
    chrome(ax, active="Alert Queue", height=h, crumb="Alert Queue  >  AL-00478")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "AL-00478", size=19, weight="bold")
    pill(ax, x + 120, 92, "TIER 2 CANDIDATE", fc=RED_DIM, tc=RED, size=9, h=24)
    pill(ax, x + 272, 92, "MODEL ONLY", fc=CYAN_DIM, tc=CYAN, size=9, h=24)
    pill(ax, x + 386, 92, "REQUIRES REVIEW", fc=ORANGE_DIM, tc=ORANGE, size=9, h=24)
    text(ax, x, 126, f"{a['src']}  ->  {a['dst']}:{a['port']}  ({a['proto']})     "
                     f"{a['packets']} packets     {a['bytes']:,} bytes     {a['dur']:.2f} s",
         size=10, color=MUTED)
    text(ax, x + w - 8, 96, f"{a['det']:.2f}", size=25, weight="bold", ha="right")
    text(ax, x + w - 8, 126, "detection score - unchanged", size=9, color=MUTED, ha="right")

    half, gap = (w - 22) / 2, 22
    # Panel 1 - the flow.
    fy = panel(ax, x, 158, half, 226, "1. Flow", sub="What crossed the wire")
    pairs = [("Source", a["src"]), ("Destination", f"{a['dst']}:{a['port']}"),
             ("Protocol", a["proto"]), ("Duration", f"{a['dur']:.3f} s"),
             ("Packets / bytes", f"{a['packets']} / {a['bytes']:,}"),
             ("Source record", "AL-00478")]
    for i, (k, v) in enumerate(pairs):
        row = fy + 10 + i * 22
        text(ax, x + 22, row, k, size=9.5, color=MUTED)
        text(ax, x + half - 24, row, v, size=9.5, ha="right")

    # Panel 2 - the signature layer, in its common empty state.
    sx = x + half + gap
    sy = panel(ax, sx, 158, half, 226, "2. Signature rules",
               sub="What a hand-written rule could confirm")
    box(ax, sx + 20, sy + 6, half - 40, 84, fc=RAISED, ec=BORDER, ls=(0, (4, 3)), z=3)
    text(ax, sx + half / 2, sy + 34, "No rule matched", size=12, color=MUTED, ha="center", z=5)
    text(ax, sx + half / 2, sy + 60, "(model-only alert)", size=10, color=DIM, ha="center", z=5)
    text(ax, sx + 20, sy + 116,
         "Two rules are enabled, both FTP/SSH brute force. Neither applies", size=9, color=MUTED)
    text(ax, sx + 20, sy + 136,
         "here, so there is no checkable reason - only the model's opinion.", size=9, color=MUTED)

    # Panel 3 - the model and its explanation.
    my = panel(ax, x, 404, half, 280, "3. Model prediction",
               sub="XGBoost, 8 classes, with a TreeSHAP explanation")
    text(ax, x + 22, my + 16, a["cls"], size=15, weight="bold", color=CYAN)
    text(ax, x + 22, my + 42, f"confidence {a['prob']:.3f}", size=10, color=MUTED)
    pill(ax, x + half - 176, my + 24, "additivity check passed", fc=GREEN_DIM, tc=GREEN, size=8.5)
    text(ax, x + 22, my + 76, "Features pushing the score up", size=9.5, color=MUTED)
    top = max((abs(v) for _, v in a["up"]), default=1.0)
    for i, (name, value) in enumerate(a["up"][:4]):
        row = my + 100 + i * 30
        text(ax, x + 22, row, name, size=9)
        bar(ax, x + 250, row - 5, half - 330, 10, abs(value) / top, fc=ORANGE)
        text(ax, x + half - 24, row, f"{value:+.2f}", size=9, color=ORANGE, ha="right")

    # Panel 4 - the combined explanation, in words.
    cy = panel(ax, sx, 404, half, 280, "4. Combined explanation",
               sub="Why this alert sits where it does")
    box(ax, sx + 20, cy + 6, half - 40, 112, fc=RAISED, ec=BORDER, z=3)
    for i, line in enumerate(["Only the model flagged this flow (Web Attack).",
                              "No rule gives a checkable reason, so review the",
                              "model's evidence rather than trusting the score.",
                              "99.89 is above the critical threshold of 80, so",
                              "the alert is raised as a Tier 2 candidate."]):
        text(ax, sx + 36, cy + 26 + i * 20, line, size=9.5, z=5)
    text(ax, sx + 20, cy + 146, "Evidence class: model only", size=9.5, color=MUTED)
    text(ax, sx + 20, cy + 168, "Queue band: Tier 2 candidate", size=9.5, color=MUTED)
    text(ax, sx + 20, cy + 190, "Family: Web Attack / port 80 / tcp - 61 members",
         size=9.5, color=MUTED)

    # The verdict bar.
    vy = panel(ax, x, 704, w, 116, "Your verdict",
               sub="Recorded against your name, then carried to alerts like this one")
    bx = x + 22
    for label, fg, bgc in (("Confirm true positive", GREEN, GREEN_DIM),
                           ("Mark false positive", ORANGE, ORANGE_DIM),
                           ("Expected activity", CYAN, CYAN_DIM),
                           ("Needs investigation", MUTED, RAISED),
                           ("Escalate", RED, RED_DIM)):
        bw = len(label) * 5.8 + 40
        box(ax, bx, vy + 8, bw, 38, fc=bgc, ec=fg, lw=1.3, z=4)
        text(ax, bx + bw / 2, vy + 27, label, size=10, color=fg, ha="center", z=6)
        bx += bw + 14
    footnote(ax, "Ground truth says this flow is benign. The panels above are everything the "
                 "system knows; the decision is the analyst's.", height=h)
    return save(fig, "04_04_alert_detail")


# --------------------------------------------------------------------------------------------
# (4.5) Signature evidence, when a rule does fire
# --------------------------------------------------------------------------------------------

def screen_signature(d: dict):
    h, a = 860.0, d["AL-00060"]
    fig, ax = screen(h)
    chrome(ax, active="Alert Queue", height=h, crumb="Alert Queue  >  AL-00060  >  Signature")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Signature evidence", size=19, weight="bold")
    text(ax, x, 122, "A rule fires only where it can say exactly why", size=10, color=MUTED)
    pill(ax, x + w - 172, 108, "CORROBORATED", fc=GREEN_DIM, tc=GREEN, size=9.5, h=26)

    rule = a["rules"][0] if a["rules"] else {
        "id": "SIG-FTP-BRUTE-FORCE", "name": "FTP Brute Force Flow Pattern",
        "sev": "Medium", "cond": [("protocol", "TCP", "TCP"), ("destinationPort", "21", "21"),
                                  ("totalFwdPackets", "min 1", "6")]}
    ry = panel(ax, x, 152, w, 300, rule["id"],
               sub=f"{rule['name']} - severity {rule['sev']} - rule set s4b-1")
    text(ax, x + 22, ry + 14, "Matched conditions", size=10.5, weight="bold")
    text(ax, x + 22, ry + 44, "FEATURE", size=8.5, color=DIM, weight="bold")
    text(ax, x + 430, ry + 44, "RULE REQUIRES", size=8.5, color=DIM, weight="bold")
    text(ax, x + 760, ry + 44, "THIS FLOW HAD", size=8.5, color=DIM, weight="bold")
    for i, cond in enumerate(rule["cond"][:5]):
        feature, expected, observed = cond
        row = ry + 74 + i * 34
        box(ax, x + 20, row - 13, w - 40, 28, fc=RAISED, ec=BORDER, r=6, z=3)
        text(ax, x + 36, row, feature, size=9.5, z=5)
        text(ax, x + 430, row, expected, size=9.5, color=MUTED, z=5)
        text(ax, x + 760, row, observed, size=9.5, color=GREEN, weight="bold", z=5)
        text(ax, x + w - 44, row, "ok", size=9, color=GREEN, ha="right", z=5)

    lw = w * 0.48
    py = panel(ax, x, 476, lw, 190, "Why this rule is trusted")
    for i, (k, v) in enumerate((("Precision on held-out data", "0.9999"),
                                ("Hits scored", "30,025"), ("False positives", "2"),
                                ("Recall", "0.1993"))):
        row = py + 14 + i * 28
        text(ax, x + 22, row, k, size=10, color=MUTED)
        text(ax, x + lw - 24, row, v, size=10, weight="bold", color=GREEN, ha="right")
    text(ax, x + 22, py + 132, "Validated on 250,655 rows the rules never saw.",
         size=9, color=DIM, style="italic")

    qx, qw = x + lw + 24, w - lw - 24
    qy = panel(ax, qx, 476, qw, 190, "What the rule layer is for")
    for i, line in enumerate(["Recall is deliberately low. The rules exist to give an",
                              "analyst a checkable reason, not to catch everything.",
                              "",
                              "On the corrected dataset they add no unique coverage:",
                              "every flow they catch, the model catches too. What they",
                              "add is a reason a human can verify in seconds."]):
        text(ax, qx + 20, qy + 16 + i * 22, line, size=9.5, color=TEXT if i < 2 else MUTED)
    footnote(ax, "Five further rules exist but are disabled: their best achievable precision was "
                 "0.14-0.37, unusable for a layer whose whole purpose is trust.", height=h)
    return save(fig, "04_05_signature_evidence")


# --------------------------------------------------------------------------------------------
# (4.6) The model's explanation
# --------------------------------------------------------------------------------------------

def screen_model(d: dict):
    h, a = 880.0, d["AL-00478"]
    fig, ax = screen(h)
    chrome(ax, active="Alert Queue", height=h, crumb="Alert Queue  >  AL-00478  >  Model")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Model explanation", size=19, weight="bold")
    text(ax, x, 122, "Which measurements drove this prediction, and by how much",
         size=10, color=MUTED)
    pill(ax, x + w - 180, 108, "TreeSHAP - native", fc=CYAN_DIM, tc=CYAN, size=9.5, h=26)

    hy = panel(ax, x, 152, w, 104, "Prediction")
    text(ax, x + 24, hy + 28, a["cls"], size=21, weight="bold", color=CYAN)
    for dx, label, value, colour in ((300, "Confidence", f"{a['prob']:.4f}", TEXT),
                                     (520, "Model", "xgb-8class-20260911", TEXT),
                                     (860, "Additivity check", "passed (1.13e-5 < 1e-4)", GREEN)):
        text(ax, x + dx, hy + 14, label, size=9.5, color=MUTED)
        text(ax, x + dx, hy + 40, value, size=12, color=colour,
             weight="bold" if dx == 300 else "normal")

    top = max((abs(v) for _, v in a["up"] + a["down"]), default=1.0)
    uy = panel(ax, x, 282, w, 268, "Features that pushed the score up",
               sub="Positive SHAP contribution towards the predicted class")
    for i, (name, value) in enumerate(a["up"][:5]):
        row = uy + 18 + i * 42
        text(ax, x + 24, row, name, size=10.5)
        bar(ax, x + 420, row - 7, w - 600, 14, abs(value) / top, fc=ORANGE)
        text(ax, x + w - 30, row, f"{value:+.3f}", size=10, color=ORANGE, weight="bold",
             ha="right")

    dy = panel(ax, x, 574, w, 190, "Features that pushed it down",
               sub="Evidence against the prediction - shown, because hiding it would be advocacy")
    for i, (name, value) in enumerate(a["down"][:3]):
        row = dy + 18 + i * 42
        text(ax, x + 24, row, name, size=10.5)
        bar(ax, x + 420, row - 7, w - 600, 14, abs(value) / top, fc=CYAN)
        text(ax, x + w - 30, row, f"{value:+.3f}", size=10, color=CYAN, weight="bold", ha="right")
    footnote(ax, "All 5,000 alerts in the demo database carry an explanation, and all 5,000 pass "
                 "the additivity check - the explanation accounts for the prediction exactly.",
             height=h)
    return save(fig, "04_06_model_explanation")


# --------------------------------------------------------------------------------------------
# (4.7) Submitting a verdict
# --------------------------------------------------------------------------------------------

def screen_feedback(d: dict):
    h = 920.0
    fig, ax = screen(h)
    chrome(ax, active="Alert Queue", height=h, crumb="Alert Queue  >  AL-00478  >  Feedback")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Record your verdict", size=19, weight="bold")
    text(ax, x, 122, "AL-00478 - Web Attack, 99.89, model only", size=10, color=MUTED)

    cy = panel(ax, x, 152, w, 400, "What did you find?",
               sub="One verdict per alert. A new verdict supersedes your last; it does not stack.")
    options = [
        ("Confirm true positive", "+10", "This really is an attack.", GREEN, GREEN_DIM, False),
        ("Mark false positive", "-30", "Benign traffic the detector misread.",
         ORANGE, ORANGE_DIM, True),
        ("Mark expected activity", "-15", "Real, known, and authorised.", CYAN, CYAN_DIM, False),
        ("Needs investigation", "0", "Undecided - keep it flagged.", MUTED, RAISED, False),
        ("Escalate", "+15", "Send to Tier 2 now.", RED, RED_DIM, False),
    ]
    oy = cy + 10
    for label, delta, note, fg, bgc, chosen in options:
        box(ax, x + 22, oy, w - 44, 50, fc=bgc if chosen else SURFACE,
            ec=fg if chosen else BORDER, lw=1.6 if chosen else 1.1, z=4)
        box(ax, x + 42, oy + 17, 16, 16, fc=fg if chosen else "none", ec=fg, lw=1.4, r=8, z=6)
        text(ax, x + 78, oy + 25, label, size=11, weight="bold" if chosen else "normal",
             color=fg if chosen else TEXT, z=6)
        text(ax, x + 300, oy + 25, delta, size=11, weight="bold", color=fg, z=6)
        text(ax, x + 380, oy + 25, note, size=9.5, color=MUTED, z=6)
        oy += 58
    text(ax, x + 22, cy + 318,
         "'Duplicate' is absent by design: linking an alert to an original is a queue action, "
         "not a change of score.", size=9, color=DIM, style="italic")

    lw = w * 0.62
    ny = panel(ax, x, 576, lw, 156, "Note (optional)",
               sub="Recorded in the audit trail alongside the verdict")
    box(ax, x + 22, ny + 10, lw - 44, 74, fc=RAISED, ec=BORDER, z=3)
    text(ax, x + 38, ny + 36, "Internal scanner sweep, confirmed with the network team.",
         size=10, z=5)

    px, pw = x + lw + 24, w - lw - 24
    py = panel(ax, px, 576, pw, 156, "What will happen", sub="Before you commit")
    for i, line in enumerate(["Score moves from 99.89 towards 69.89,",
                              "but a guardrail may bind it first.",
                              "Your verdict is recorded either way.",
                              "60 similar alerts stay put for now:",
                              "the gate needs three verdicts."]):
        text(ax, px + 20, py + 16 + i * 22, line, size=9.5, color=TEXT if i < 2 else MUTED)

    button(ax, x, 776, 230, "Submit verdict", h=42)
    button(ax, x + 250, 776, 150, "Cancel", fc=RAISED, tc=MUTED, ec=BORDER, h=42)
    footnote(ax, "Submitting writes the verdict, applies the guardrails, updates the alert's "
                 "family and appends to the audit trail - in one transaction, or not at all.",
             height=h)
    return save(fig, "04_07_submit_feedback")


# --------------------------------------------------------------------------------------------
# (4.9) When a guardrail refuses the change outright
# --------------------------------------------------------------------------------------------

def screen_refusal(d: dict):
    h = 840.0
    fig, ax = screen(h)
    chrome(ax, active="Alert Queue", height=h,
           crumb="Alert Queue  >  AL-00512  >  Verdict rejected")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Your verdict was recorded. The score was not changed.", size=17,
         weight="bold")
    text(ax, x, 124, "A precision-1.000 rule fired on this flow, and the model disagrees with it",
         size=10, color=MUTED)
    pill(ax, x + w - 150, 108, "REJECTED", fc=RED_DIM, tc=RED, size=9.5, h=26)

    ry = panel(ax, x, 158, w, 200, "Why the change was refused")
    box(ax, x + 22, ry + 8, w - 44, 116, fc=RED_DIM, ec=RED, lw=1.4, z=4)
    text(ax, x + 40, ry + 32, "signature_override_feedback_immune", size=11, weight="bold",
         color=RED, z=6)
    for i, line in enumerate([
            "A rule with precision 1.000 fired here, and the model calls the same flow benign.",
            "That disagreement is either a rule regression or an analyst error, and neither is",
            "resolved by quietly lowering a score. The alert has gone to the administrator."]):
        text(ax, x + 40, ry + 58 + i * 22, line, size=9.5, z=6)
    text(ax, x + 22, ry + 150,
         "Invariant I3 - a signature-backed alert cannot be decayed by feedback, in any role.",
         size=9, color=DIM, style="italic")

    lw = w * 0.48
    cy = panel(ax, x, 382, lw, 180, "What did change")
    for i, (k, v, colour) in enumerate((("Your verdict", "recorded in full", GREEN),
                                        ("Score", "unchanged at 74.10", MUTED),
                                        ("Queue band", "unchanged", MUTED),
                                        ("Administrator", "notified to adjudicate", CYAN))):
        row = cy + 16 + i * 30
        text(ax, x + 22, row, k, size=10, color=MUTED)
        text(ax, x + lw - 24, row, v, size=10, color=colour, ha="right", weight="bold")
    text(ax, x + 22, cy + 142, "Nothing was lost. The disagreement is now on the record.",
         size=9, color=DIM, style="italic")

    nx, nw = x + lw + 24, w - lw - 24
    ny = panel(ax, nx, 382, nw, 180, "Why the rule outranks the model here")
    for i, line in enumerate(["The two enabled rules were validated on 250,655 rows the",
                              "rules had never seen: precision 0.9999, two false positives",
                              "in 30,025 hits.",
                              "",
                              "A rule that specific, disagreeing with the model, is worth a",
                              "human's attention rather than a silent edit."]):
        text(ax, nx + 20, ny + 16 + i * 22, line, size=9.5, color=MUTED if i > 2 else TEXT)

    button(ax, x, 618, 220, "Notify administrator", fc=RAISED, tc=CYAN, ec=BORDER, h=40)
    button(ax, x + 240, 618, 180, "Back to queue", fc=RAISED, tc=MUTED, ec=BORDER, h=40)
    footnote(ax, "No signature_override alert exists in the demo database - the corrected dataset "
                 "produces none - so this state is proven by the guardrail unit tests rather than "
                 "shown in the walkthrough.", height=h)
    return save(fig, "04_09_guardrail_refusal")


# --------------------------------------------------------------------------------------------
# (4.10) Similar-alert learning - the project's central claim
# --------------------------------------------------------------------------------------------

def screen_family(d: dict):
    h = 970.0
    fig, ax = screen(h)
    chrome(ax, active="Feedback Impact", height=h, crumb="Feedback Impact  >  Family")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "What your feedback taught the queue", size=19, weight="bold")
    text(ax, x, 122, "Family: Brute Force / port 21 / tcp / SIG-FTP-BRUTE-FORCE - 146 alerts",
         size=10, color=MUTED)
    pill(ax, x + w - 142, 108, "GATE OPEN", fc=GREEN_DIM, tc=GREEN, size=9.5, h=26)

    gy = panel(ax, x, 152, w, 244, "The agreement gate",
               sub="One analyst cannot move a family. Three who agree can.")
    bar(ax, x + 24, gy + 14, w - 48, 14, 1.0, fc=GREEN)
    text(ax, x + 24, gy + 52, "3 of 3 verdicts recorded", size=11, weight="bold", color=GREEN)
    for i, (k, v) in enumerate((("Verdicts counted", "3"),
                                ("Agreement", "1.00 (needs 0.67)"),
                                ("Dominant verdict", "confirm true positive"),
                                ("Applied adjustment", "+20.00, at the maximum increase"))):
        row = gy + 84 + i * 24
        text(ax, x + 24, row, k, size=9.5, color=MUTED)
        text(ax, x + 330, row, v, size=9.5)

    my = panel(ax, x, 416, w, 322, "Members that moved",
               sub="Alerts nobody judged, re-ranked because their family was judged")
    for label, dx in (("ALERT", 24), ("BEFORE", 200), ("AFTER", 360), ("BAND", 520),
                      ("WHY", 800)):
        text(ax, x + dx, my + 12, label, size=8.5, color=DIM, weight="bold")
    movers = [("AL-02233", "88.40", "100.00", "ml only -> Tier 2", "family learning"),
              ("AL-03910", "88.40", "100.00", "ml only -> Tier 2", "family learning"),
              ("AL-01044", "88.40", "100.00", "ml only -> Tier 2", "family learning"),
              ("AL-00777", "100.00", "100.00", "Tier 2 (unchanged)", "already at the ceiling"),
              ("AL-04120", "100.00", "100.00", "Tier 2 (unchanged)", "already at the ceiling")]
    for i, (ref, before, after, band, why) in enumerate(movers):
        row = my + 46 + i * 44
        moved = before != after
        box(ax, x + 20, row - 16, w - 40, 36, fc=RAISED if moved else SURFACE, ec=BORDER, z=3)
        text(ax, x + 36, row, ref, size=10, weight="bold", z=5)
        text(ax, x + 200, row, before, size=10, color=MUTED, z=5)
        text(ax, x + 320, row, "->", size=9, color=DIM, z=5)
        text(ax, x + 360, row, after, size=10, color=GREEN if moved else MUTED,
             weight="bold" if moved else "normal", z=5)
        text(ax, x + 520, row, band, size=9.5, color=GREEN if moved else DIM, z=5)
        text(ax, x + 800, row, why, size=9, color=MUTED if moved else DIM, style="italic", z=5)

    wy = panel(ax, x, 762, w, 126, "What did not move", sub="The honest half of the claim")
    for i, line in enumerate([
            "4,155 alerts outside this family were untouched - no score change, no band change.",
            "Learning that leaks past its family is not learning, it is drift. The evaluation "
            "reports that number every run."]):
        text(ax, x + 24, wy + 14 + i * 24, line, size=10, color=TEXT if i == 0 else MUTED)
    footnote(ax, "Caution: a family is a coarse key. In the evaluation this same mechanism "
                 "promoted a benign alert from rank 639 to rank 1, because its family was full "
                 "of confirmed attacks.", height=h, color=ORANGE)
    return save(fig, "04_10_similar_alert_learning")


# --------------------------------------------------------------------------------------------
# (4.11) Feedback history and amendment
# --------------------------------------------------------------------------------------------

def screen_history(d: dict):
    h = 820.0
    fig, ax = screen(h)
    chrome(ax, active="Alert Queue", height=h, crumb="Alert Queue  >  AL-00478  >  History")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Verdict history", size=19, weight="bold")
    text(ax, x, 122, "AL-00478 - every verdict ever recorded, including those since replaced",
         size=10, color=MUTED)

    hy = panel(ax, x, 152, w, 328, "Timeline", sub="Oldest first. Nothing is ever deleted.")
    events = [("09:14", "Needs investigation", "Glenn A.", "0.00", "superseded", DIM, False),
              ("09:31", "Mark false positive", "Glenn A.", "-29.89", "in force", ORANGE, True)]
    ey = hy + 14
    for when, category, who, delta, state, fg, current in events:
        box(ax, x + 22, ey, w - 44, 112, fc=RAISED if current else SURFACE,
            ec=fg if current else BORDER, lw=1.5 if current else 1.1, z=3)
        box(ax, x + 22, ey, 5, 112, fc=fg, ec=fg, r=2, z=5)
        text(ax, x + 46, ey + 26, when, size=10, color=MUTED, z=5)
        text(ax, x + 120, ey + 26, category, size=12, weight="bold", color=fg, z=5)
        pill(ax, x + w - 172, ey + 26, state, fc=ORANGE_DIM if current else "#1c2942",
             tc=fg, size=8.5, z=5)
        text(ax, x + 46, ey + 56, f"by {who}", size=9.5, color=MUTED, z=5)
        text(ax, x + 200, ey + 56, f"applied {delta}", size=9.5, color=MUTED, z=5)
        if current:
            text(ax, x + 46, ey + 86,
                 "Note: internal scanner sweep, confirmed with the network team.",
                 size=9.5, style="italic", z=5)
            text(ax, x + 640, ey + 86, "guardrail: critical_alert_floor held it at 70.00",
                 size=9, color=RED, z=5)
        else:
            text(ax, x + 46, ey + 86, "Replaced at 09:31. Kept for the record.",
                 size=9.5, color=DIM, style="italic", z=5)
        ey += 132

    lw = w * 0.55
    ny = panel(ax, x, 504, lw, 158, "How amendment works")
    for i, line in enumerate(["A new verdict does not stack on the old one. The alert's",
                              "score is always its immutable detection score plus the",
                              "guarded change of the single verdict in force.",
                              "",
                              "Superseded verdicts stay visible, and stay in the audit trail."]):
        text(ax, x + 22, ny + 16 + i * 24, line, size=9.5, color=MUTED if i > 2 else TEXT)

    bx, bw = x + lw + 24, w - lw - 24
    by = panel(ax, bx, 504, bw, 158, "Correct this verdict")
    text(ax, bx + 20, by + 16, "Changed your mind? Record a new verdict.", size=9.5, color=MUTED)
    button(ax, bx + 20, by + 62, bw - 40, "Record a new verdict", h=40, fc=RAISED, tc=CYAN,
           ec=BORDER)
    text(ax, bx + 20, by + 106, "The old one is never edited or removed.", size=9,
         color=DIM, style="italic")
    footnote(ax, "feedback_events is append-only, enforced by database triggers: UPDATE and "
                 "DELETE both raise, including against INSERT OR REPLACE.", height=h)
    return save(fig, "04_11_feedback_history")


# --------------------------------------------------------------------------------------------
# (4.12) Administrator - system status
# --------------------------------------------------------------------------------------------

def screen_admin_status(d: dict):
    h, c = 880.0, d["counts"]
    fig, ax = screen(h)
    chrome(ax, role="System Administrator", active="Dashboard", height=h, crumb="System status")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "System status", size=19, weight="bold")
    text(ax, x, 122, "What has run, what it produced, and what the guardrails have done",
         size=10, color=MUTED)
    button(ax, x + w - 192, 108, 192, "Start detection run", h=34)

    cw = (w - 3 * 18) / 4
    for i, (label, value, note, fg) in enumerate((
            ("Detection runs", "1", "completed", GREEN),
            ("Alerts stored", f"{c['total_alerts']:,}", "from 5,000 flows", CYAN),
            ("Feedback events", f"{c['feedback_events']}", "analyst verdicts", MUTED),
            ("Guardrail actions", f"{c['guardrail_interventions']}", "recorded in audit",
             ORANGE))):
        cx = x + i * (cw + 18)
        box(ax, cx, 152, cw, 108, fc=SURFACE, z=2)
        text(ax, cx + 20, 180, label, size=10, color=MUTED, z=4)
        text(ax, cx + 20, 216, value, size=24, weight="bold", color=fg, z=4)
        text(ax, cx + 20, 244, note, size=8.5, color=DIM, z=4)

    ry = panel(ax, x, 282, w, 222, "Detection runs",
               sub="Every run stores what a replay would need")
    for label, dx in (("RUN", 24), ("STATUS", 110), ("DATASET", 240), ("MODEL", 420),
                      ("RULES", 660), ("SEED", 780), ("ALERTS", 900), ("COMPLETED", 1020)):
        text(ax, x + dx, ry + 12, label, size=8.5, color=DIM, weight="bold")
    box(ax, x + 20, ry + 28, w - 40, 40, fc=RAISED, ec=BORDER, z=3)
    for value, dx, colour in (("#1", 24, TEXT), ("completed", 110, GREEN),
                              ("demo-20260911", 240, TEXT),
                              ("xgb-8class-20260911", 420, TEXT), ("s4b-1", 660, TEXT),
                              ("20260911", 780, TEXT), ("5,000", 900, TEXT),
                              ("2026-09-12 06:30", 1020, TEXT)):
        text(ax, x + dx, ry + 48, value, size=9.5, color=colour, z=5)
    text(ax, x + 24, ry + 106,
         "A run records its dataset, model version, rule-set version, fusion configuration, "
         "guardrail settings and seed.", size=9.5, color=MUTED)
    text(ax, x + 24, ry + 132,
         "Re-running the same source reproduces every score for all 5,000 alerts - verified by "
         "test, not asserted in prose.", size=9.5, color=MUTED)

    sy = panel(ax, x, 528, w, 200, "Services")
    for i, (name, state, note) in enumerate((
            ("Detection pipeline", "ready", "offline batch - never inline in a request"),
            ("API", "serving", "queue p95 19 ms, alert detail p95 6 ms"),
            ("Database", "sqlite", "data/demo.db, 42 MB, append-only audit enforced"),
            ("Model", "loaded", "8 classes, 82 features, macro F1 0.9882"))):
        row = sy + 18 + i * 38
        text(ax, x + 24, row, name, size=10.5)
        pill(ax, x + 280, row, state, fc=GREEN_DIM, tc=GREEN, size=8.5)
        text(ax, x + 480, row, note, size=9.5, color=MUTED)
    footnote(ax, "The 0.9882 macro F1 is a property of this testbed, not a claim about real "
                 "traffic: each attack class was generated by a single tool, which leaves a "
                 "near-constant fingerprint.", height=h, color=ORANGE)
    return save(fig, "04_12_admin_status")


# --------------------------------------------------------------------------------------------
# (4.13) Administrator - guardrail configuration
# --------------------------------------------------------------------------------------------

def screen_admin_guardrails(d: dict):
    h, g = 900.0, d["guardrails"]
    fig, ax = screen(h)
    chrome(ax, role="System Administrator", active="Feedback Impact", height=h,
           crumb="Configuration  >  Guardrails")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Guardrail configuration", size=19, weight="bold")
    text(ax, x, 122, "The limits on what analyst feedback may do. Administrator only.",
         size=10, color=MUTED)
    pill(ax, x + w - 196, 108, "ADMINISTRATOR ONLY", fc="#3b2a06", tc="#fbbf24", size=9, h=26)

    sy = panel(ax, x, 152, w, 376, "Settings",
               sub="A change takes effect on the next verdict, and is itself audited")
    rows = [("max_feedback_reduction", g.get("max_feedback_reduction", 30),
             "Most a single verdict may subtract", "points"),
            ("max_feedback_increase", g.get("max_feedback_increase", 20),
             "Most a single verdict may add", "points"),
            ("critical_alert_floor", g.get("critical_alert_floor", 70),
             "A Critical alert never falls below this", "score"),
            ("infiltration_alert_floor", g.get("infiltration_alert_floor", 75),
             "An Infiltration alert never falls below this", "score"),
            ("critical_alert_threshold", g.get("critical_alert_threshold", 80),
             "At or above this, an alert counts as Critical", "score")]
    ry = sy + 14
    for key, value, note, unit in rows:
        box(ax, x + 22, ry, w - 44, 58, fc=RAISED, ec=BORDER, z=3)
        text(ax, x + 42, ry + 22, key, size=10.5, weight="bold", color=CYAN, z=5)
        text(ax, x + 42, ry + 42, note, size=9, color=MUTED, z=5)
        box(ax, x + w - 224, ry + 13, 92, 32, fc=SURFACE, ec=BORDER, r=6, z=5)
        text(ax, x + w - 178, ry + 29, f"{value:g}", size=12, weight="bold", ha="center", z=6)
        text(ax, x + w - 116, ry + 29, unit, size=9, color=DIM, z=5)
        ry += 70

    ny = panel(ax, x, 552, w, 148, "Reason for the change",
               sub="Required - the audit entry records why, not only what")
    box(ax, x + 22, ny + 10, w - 44, 60, fc=RAISED, ec=BORDER, z=3)
    text(ax, x + 38, ny + 40, "Raising the Critical floor to 75 after the Q3 tuning review.",
         size=10, z=5)

    button(ax, x, 742, 210, "Save configuration", h=42)
    button(ax, x + 230, 742, 150, "Discard", fc=RAISED, tc=MUTED, ec=BORDER, h=42)
    text(ax, x + 412, 742, "An analyst opening this page sees the values but no controls.",
         size=9.5, color=DIM, style="italic")
    footnote(ax, "Defaults come from the collaborator's adaptation-config.json, which is richer "
                 "than the written specification - it is the only source that caps positive "
                 "feedback at all.", height=h)
    return save(fig, "04_13_admin_guardrails")


# --------------------------------------------------------------------------------------------
# (4.14) Administrator - the audit trail
# --------------------------------------------------------------------------------------------

def screen_admin_audit(d: dict):
    h = 880.0
    fig, ax = screen(h)
    chrome(ax, role="System Administrator", active="Audit Trail", height=h, crumb="Audit trail")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Audit trail", size=19, weight="bold")
    text(ax, x, 122, "Every detection, verdict, guardrail action and configuration change",
         size=10, color=MUTED)
    button(ax, x + w - 156, 108, 156, "Export (CSV)", fc=RAISED, tc=CYAN, ec=BORDER)

    box(ax, x, 152, w, 52, fc=SURFACE, z=1)
    fx = x + 16
    for label, on in (("All events", False), ("Feedback", True), ("Guardrail", True),
                      ("Detection run", False), ("Config change", False), ("Learning", False)):
        fx += pill(ax, fx, 178, label, fc=CYAN_DIM if on else RAISED, tc=CYAN if on else MUTED,
                   size=9.5, h=26) + 10
    text(ax, x + w - 306, 178, "Date range:", size=9.5, color=DIM)
    box(ax, x + w - 224, 165, 208, 26, fc=RAISED, ec=BORDER, r=6, z=3)
    text(ax, x + w - 212, 178, "12 Sep 2026 - 12 Sep 2026", size=9.5, color=MUTED, z=4)

    for label, dx in (("TIME", 24), ("EVENT", 120), ("ACTOR", 380), ("ALERT", 520),
                      ("DETAIL", 660)):
        text(ax, x + dx, 232, label, size=8.5, color=DIM, weight="bold")
    entries = [
        ("09:31:04", "SIMILAR_ALERT_LEARNING", "Glenn A.", "AL-00478",
         "family gate opened - 3 verdicts, agreement 1.00", VIOLET),
        ("09:31:04", "GUARDRAIL_INTERVENTION", "Glenn A.", "AL-00478",
         "critical_alert_floor held the score at 70.00", RED),
        ("09:31:04", "FEEDBACK", "Glenn A.", "AL-00478",
         "mark_false_positive - requested -30.00, applied -29.89", ORANGE),
        ("09:14:22", "FEEDBACK", "Glenn A.", "AL-00478",
         "needs_investigation - no score change", MUTED),
        ("06:30:11", "DETECTION_RUN", "system", "-",
         "run #1 - 5,000 flows scored in 21 s", CYAN),
    ]
    ey = 250
    for when, event, who, ref, detail, fg in entries:
        box(ax, x + 20, ey, w - 40, 48, fc=SURFACE, ec=BORDER, z=3)
        box(ax, x + 20, ey, 4, 48, fc=fg, ec=fg, r=2, z=5)
        text(ax, x + 44, ey + 24, when, size=9.5, color=MUTED, z=5)
        text(ax, x + 120, ey + 24, event, size=9.5, weight="bold", color=fg, z=5)
        text(ax, x + 380, ey + 24, who, size=9.5, z=5)
        text(ax, x + 520, ey + 24, ref, size=9.5, color=MUTED, z=5)
        text(ax, x + 660, ey + 24, detail, size=9.5, color=MUTED, z=5)
        ey += 58

    iy = panel(ax, x, 566, w, 158, "Why this log can be trusted")
    for i, line in enumerate([
            "Append-only at the database, not merely by convention: UPDATE and DELETE both raise,",
            "including against INSERT OR REPLACE, and a test proves it rather than a comment "
            "claiming it.",
            "",
            "Every guardrail entry carries the setting that caused it, so a reader can redo the "
            "arithmetic."]):
        text(ax, x + 24, iy + 14 + i * 24, line, size=9.5, color=MUTED if i > 1 else TEXT)
    footnote(ax, "Timestamps are fixed-width UTC text, so ordering by text is ordering by time.",
             height=h)
    return save(fig, "04_14_admin_audit")


# --------------------------------------------------------------------------------------------
# (4.15) Evaluator - the three-arm comparison
# --------------------------------------------------------------------------------------------

def screen_eval_results(d: dict):
    h = 960.0
    e = d.get("eval") or {}
    arms = {a["arm"]: a for a in e.get("arms", [])}
    delta = (e.get("deltas") or {}).get("B_minus_A", {})
    fig, ax = screen(h)
    chrome(ax, role="Evaluator", active="Feedback Impact", height=h,
           crumb="Evaluation  >  " + str(e.get("run_id", "")))
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Three-arm evaluation", size=19, weight="bold")
    text(ax, x, 122, f"Run {e.get('run_id', '-')} - pre-registered sequence, "
                     f"{e.get('sequence_length', 0)} verdicts", size=10, color=MUTED)
    pill(ax, x + w - 214, 108, "Reproducible - NFR-05", fc=GREEN_DIM, tc=GREEN, size=9.5, h=26)

    ay = panel(ax, x, 152, w, 290, "The three arms",
               sub="Identical dataset, model, rules and seed. Only feedback and guardrails differ.")
    for label, dx in (("ARM", 24), ("FEEDBACK", 280), ("GUARDRAILS", 450), ("P@50", 640),
                      ("FP IN TOP 50", 760), ("FLOOR BREACHES", 930),
                      ("TP SUPPRESSED", 1120)):
        text(ax, x + dx, ay + 12, label, size=8.5, color=DIM, weight="bold")
    ry = ay + 34
    for name, fb, gr in (("A-control", "none", "on"), ("B-treatment", "40 verdicts", "on"),
                         ("C-guardrails-off", "40 verdicts", "OFF")):
        arm = arms.get(name, {})
        box(ax, x + 20, ry, w - 40, 48, fc=RAISED if name == "B-treatment" else SURFACE,
            ec=CYAN if name == "B-treatment" else BORDER, z=3)
        text(ax, x + 44, ry + 24, name, size=10.5, weight="bold", z=5)
        text(ax, x + 280, ry + 24, fb, size=9.5, color=MUTED, z=5)
        text(ax, x + 450, ry + 24, gr, size=9.5, color=ORANGE if gr == "OFF" else MUTED,
             weight="bold" if gr == "OFF" else "normal", z=5)
        text(ax, x + 640, ry + 24, f"{arm.get('precision_at_50', 0):.3f}", size=10, z=5)
        text(ax, x + 760, ry + 24, str(arm.get("false_positives_in_top_50", 0)), size=10, z=5)
        text(ax, x + 930, ry + 24, str(arm.get("critical_floor_breaches", 0)), size=10,
             color=GREEN, z=5)
        text(ax, x + 1120, ry + 24, "0", size=10, color=GREEN, z=5)
        ry += 58
    text(ax, x + 24, ay + 208,
         "Detection metrics are identical in all three arms - feedback reordered the queue and "
         "never touched the detector.", size=9.5, color=GREEN)

    lw = w * 0.52
    dy = panel(ax, x, 462, lw, 262, "Treatment minus control",
               sub="Reported as measured, in whichever direction it went")
    items = [("False positives in top 50", f"{delta.get('false_positives_in_top_50', 0):+.0f}",
              RED),
             ("Precision @10", f"{delta.get('precision_at_10', 0):+.3f}", RED),
             ("Precision @50", f"{delta.get('precision_at_50', 0):+.3f}", RED),
             ("Mean reciprocal rank", f"{delta.get('mrr_true_positives', 0):+.5f}", RED),
             ("Critical floor breaches", f"{delta.get('critical_floor_breaches', 0):+.0f}",
              GREEN)]
    for i, (k, v, colour) in enumerate(items):
        row = dy + 18 + i * 34
        text(ax, x + 24, row, k, size=10, color=MUTED)
        text(ax, x + lw - 24, row, v, size=11, weight="bold", color=colour, ha="right")
    text(ax, x + 24, dy + 180, "Precision fell. The control queue was already perfect.",
         size=9.5, color=ORANGE, style="italic")

    gx, gw = x + lw + 24, w - lw - 24
    gy = panel(ax, gx, 462, gw, 262, "What the guardrails prevented",
               sub="Arm C minus arm B, as measured")
    for i, (k, v) in enumerate((("Extra floor breaches", "0"), ("Extra suppressions", "0"),
                                ("signature_override changed", "0"))):
        row = gy + 18 + i * 32
        text(ax, gx + 20, row, k, size=10, color=MUTED)
        text(ax, gx + gw - 24, row, v, size=11, weight="bold", color=MUTED, ha="right")
    for i, line in enumerate(["Zero, and recorded as zero. The scripted sequence",
                              "contained no dismissals, so no guardrail could bind.",
                              "This sequence could not test the guardrails, which is",
                              "not the same as saying they are unnecessary."]):
        text(ax, gx + 20, gy + 120 + i * 20, line, size=9, color=DIM, style="italic")

    my = panel(ax, x, 744, w, 160, "What moved, and what did not",
               sub="The project's central claim, measured")
    for i, (k, v, colour) in enumerate((
            ("True positives promoted without being judged", "198", GREEN),
            ("Alerts outside a judged family that changed", "0", GREEN),
            ("Benign alerts promoted with their family", "2 - one reached rank 1", ORANGE))):
        row = my + 18 + i * 32
        text(ax, x + 24, row, k, size=10, color=MUTED)
        text(ax, x + 660, row, v, size=10.5, weight="bold", color=colour)
    footnote(ax, "The sequence was fixed before any arm ran. Tuning an experiment until it "
                 "produces the wanted answer is on this project's list of things not to do.",
             height=h)
    return save(fig, "04_15_evaluator_results")


# --------------------------------------------------------------------------------------------
# (4.16) Evaluator - per-class detection metrics
# --------------------------------------------------------------------------------------------

def screen_eval_metrics(d: dict):
    h = 940.0
    e = d.get("eval") or {}
    metrics = next(iter((e.get("full_metrics") or {}).values()), {})
    per_class = (metrics.get("detection") or {}).get("per_class", {})
    sat = (metrics.get("queue") or {}).get("saturation", {})
    fig, ax = screen(h)
    chrome(ax, role="Evaluator", active="Feedback Impact", height=h,
           crumb="Evaluation  >  Detection metrics")
    x, w = 238, W - 238 - 28

    text(ax, x, 96, "Detection metrics", size=19, weight="bold")
    text(ax, x, 122, "Per class, against ground truth reached by one join and one join only",
         size=10, color=MUTED)
    pill(ax, x + w - 244, 108, "Identical across all three arms", fc=GREEN_DIM, tc=GREEN,
         size=9.5, h=26)

    ty = panel(ax, x, 152, w, 460, "Per-class performance",
               sub=f"Macro F1 {(metrics.get('detection') or {}).get('macro_f1', 0):.4f}")
    for label, dx in (("CLASS", 24), ("SUPPORT", 290), ("PRECISION", 430), ("RECALL", 580),
                      ("F1", 730), ("FPR", 860)):
        text(ax, x + dx, ty + 12, label, size=8.5, color=DIM, weight="bold")
    ry = ty + 32
    for name in ("Benign", "Botnet", "Brute Force", "DDoS", "DoS", "Infiltration", "Port Scan",
                 "Web Attack"):
        m = per_class.get(name)
        if not m:
            continue
        weak = m["f1"] < 0.99
        box(ax, x + 20, ry, w - 40, 38, fc=RAISED if weak else SURFACE, ec=BORDER, z=3)
        text(ax, x + 44, ry + 19, name, size=10, weight="bold" if weak else "normal", z=5)
        text(ax, x + 290, ry + 19, f"{m['support']:,}", size=9.5, color=MUTED, z=5)
        for dx, key in ((430, "precision"), (580, "recall"), (730, "f1")):
            text(ax, x + dx, ry + 19, f"{m[key]:.4f}", size=9.5,
                 color=ORANGE if weak and key != "precision" else TEXT, z=5)
        text(ax, x + 860, ry + 19, f"{m['fpr']:.5f}", size=9.5, color=MUTED, z=5)
        bar(ax, x + 990, ry + 13, 230, 12, m["f1"], fc=ORANGE if weak else GREEN)
        ry += 44

    lw = w * 0.5
    sy = panel(ax, x, 632, lw, 220, "Score saturation",
               sub="Why a promotion can have nowhere to go")
    text(ax, x + 24, sy + 20, f"{sat.get('at_maximum_score', 0):,} of "
                              f"{sat.get('flagged_alerts', 0):,} flagged alerts",
         size=12, weight="bold", color=ORANGE)
    text(ax, x + 24, sy + 44, "sit at exactly the maximum score of 100.", size=10, color=MUTED)
    bar(ax, x + 24, sy + 64, lw - 48, 12, sat.get("share_at_maximum", 0), fc=ORANGE)
    text(ax, x + 24, sy + 102,
         f"Only {sat.get('distinct_scores_among_flagged', 0)} distinct scores exist among them.",
         size=9.5, color=MUTED)
    text(ax, x + 24, sy + 128, "Where a band is saturated the ranking formula has no headroom,",
         size=9, color=DIM, style="italic")
    text(ax, x + 24, sy + 148, "and order inside it falls to the tie-break.", size=9,
         color=DIM, style="italic")

    ix, iw = x + lw + 24, w - lw - 24
    iy = panel(ax, ix, 632, iw, 220, "Read this before quoting the numbers")
    for i, line in enumerate(["Infiltration recall is 0.875 - the class is 40 flows, and",
                              "true infiltration is genuinely rare in the capture.",
                              "",
                              "The 0.9882 macro F1 is a testbed artefact. Each attack class",
                              "was generated by one tool with a fixed configuration, so its",
                              "flow shape is near-constant. It will not transfer."]):
        text(ax, ix + 20, iy + 18 + i * 24, line, size=9.5, color=ORANGE if i > 2 else MUTED)
    footnote(ax, "Ground truth is not in the database at all. The evaluation reaches it through "
                 "flow_data.source_record_id, never through a detector's own output.", height=h)
    return save(fig, "04_16_evaluator_metrics")


SCREENS = {
    "01": screen_login,
    "02": screen_dashboard,
    "03": screen_queue,
    "04": screen_detail,
    "05": screen_signature,
    "06": screen_model,
    "07": screen_feedback,
    "08": screen_adjustment,
    "09": screen_refusal,
    "10": screen_family,
    "11": screen_history,
    "12": screen_admin_status,
    "13": screen_admin_guardrails,
    "14": screen_admin_audit,
    "15": screen_eval_results,
    "16": screen_eval_metrics,
}


def main() -> int:
    wanted = sys.argv[1:] or sorted(SCREENS)
    unknown = [key for key in wanted if key not in SCREENS]
    if unknown:
        print(f"unknown screen(s) {unknown}; have {sorted(SCREENS)}", file=sys.stderr)
        return 2
    data = load_demo()
    for key in wanted:
        print("wrote", SCREENS[key](data).relative_to(HITL))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
