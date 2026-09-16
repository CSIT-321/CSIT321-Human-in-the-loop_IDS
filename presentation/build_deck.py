#!/usr/bin/env python3
"""Build the FYP-26-S3-13 presentation deck (light academic theme).

Every figure in this deck is taken from the repository's own documents:
docs/HANDOVER.md, docs/plan-changelog.md, docs/deviations.md,
docs/system-workflow.md, docs/ranking-and-escalation-design.md,
docs/evaluation-report.md, docs/research/soc-console-research.md,
docs/iteration-report.md, docs/iteration-2-report.md,
notebooks/04_corrected_findings.ipynb, notebooks/07_model_bakeoff.ipynb,
models/training-metrics.json, models/preprocessing-config.json,
data/processed/sample_manifest.json, requirements.txt, apps/web/package.json.

Run:  <python312> build_deck.py
"""
from __future__ import annotations

import os
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

# ---------------------------------------------------------------- palette ---
INK = "0F2A47"        # headings
BODY = "2A3441"       # body text
MUTED = "6B7684"      # secondary text
FAINT = "9AA4B0"      # footer
ACCENT = "1F6FEB"     # primary blue
ACCENT_BG = "E8F0FE"
CARD = "F4F7FB"
CARD2 = "EAEFF6"
BORDER = "D6DEE8"
WHITE = "FFFFFF"
NAVY = "0F2A47"
GOOD = "1E7A45"
BAD = "C0392B"
WARN = "B06A00"
CRIT = "C0392B"
HIGH = "E07B18"
MED = "B08900"
LOW = "2E7D32"

HEAD_FONT = "Segoe UI"
BODY_FONT = "Segoe UI"
MONO_FONT = "Consolas"

SW, SH = 13.333, 7.5
M = 0.62                      # side margin
CW = SW - 2 * M               # content width

FOOTER_L = "FYP-26-S3-13  ·  Human-in-the-Loop Intrusion Detection Dashboard"


# ---------------------------------------------------------------- helpers ---
def rgb(hexstr: str) -> RGBColor:
    return RGBColor.from_string(hexstr)


def rect(slide, x, y, w, h, fill=None, line=None, shape=MSO_SHAPE.RECTANGLE,
         line_w=0.75, shadow=False):
    shp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
    else:
        shp.fill.background()
    if line:
        shp.line.color.rgb = rgb(line)
        shp.line.width = Pt(line_w)
    else:
        shp.line.fill.background()
    if not shadow:
        # kill the default preset shadow
        sp = shp._element.spPr
        for tag in ("a:effectLst", "a:effectDag"):
            for el in sp.findall(qn(tag)):
                sp.remove(el)
        sp.append(sp.makeelement(qn("a:effectLst"), {}))
    shp.text_frame.text = ""
    return shp


def tb(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    return tf


def para(tf, text, size=12.5, color=BODY, bold=False, italic=False,
         font=BODY_FONT, align=PP_ALIGN.LEFT, before=0, after=4,
         first=False, line=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(before)
    p.space_after = Pt(after)
    if line:
        p.line_spacing = line
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.name = font
    r.font.color.rgb = rgb(color)
    return p


def rt(tf, parts, size=12.5, color=BODY, align=PP_ALIGN.LEFT, before=0,
       after=4, first=False, line=None):
    """Paragraph built from (text, bold, color, mono) tuples."""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(before)
    p.space_after = Pt(after)
    if line:
        p.line_spacing = line
    for part in parts:
        text, bold, pcolor, mono = (list(part) + [None, None, None])[:4]
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.bold = bool(bold)
        r.font.name = MONO_FONT if mono else BODY_FONT
        r.font.color.rgb = rgb(pcolor or color)
    return p


def bullets(slide, items, x, y, w, h, size=12.5, gap=5):
    """items: list of dicts {t, lvl, b, c, s}."""
    tf = tb(slide, x, y, w, h)
    for i, it in enumerate(items):
        lvl = it.get("lvl", 0)
        marker = "—" if lvl == 0 else "·"
        text = f"{marker}  {it['t']}" if it.get("mark", True) else it["t"]
        p = para(tf, text, size=it.get("s", size - (1 if lvl else 0)),
                 color=it.get("c", BODY), bold=it.get("b", False),
                 first=(i == 0), after=it.get("after", gap),
                 line=1.12 if lvl else 1.18)
        if lvl:
            p.space_before = Pt(1)
    return tf


# ------------------------------------------------------------- chrome ------
def header(slide, kicker, title, title_size=25):
    if kicker:
        tf = tb(slide, M, 0.40, CW, 0.26)
        para(tf, kicker.upper(), size=10.5, color=ACCENT, bold=True,
             first=True, after=0)
    tf = tb(slide, M, 0.63, CW, 0.62)
    para(tf, title, size=title_size, color=INK, bold=True, first=True, after=0,
         line=1.0)
    # accent tick + hairline
    rect(slide, M, 1.30, 0.62, 0.045, fill=ACCENT)
    rect(slide, M + 0.62, 1.3155, CW - 0.62, 0.011, fill=BORDER)


def footer(slide, n):
    tf = tb(slide, M, SH - 0.44, CW * 0.72, 0.24)
    para(tf, FOOTER_L, size=8.5, color=FAINT, first=True, after=0)
    tf = tb(slide, SW - M - 1.0, SH - 0.44, 1.0, 0.24)
    para(tf, str(n), size=8.5, color=FAINT, align=PP_ALIGN.RIGHT, first=True,
         after=0)


# ------------------------------------------------------------- slides ------
def content_slide(prs, n, kicker, title, subtitle=None, title_size=25):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    header(s, kicker, title, title_size=title_size)
    if subtitle:
        tf = tb(s, M, 1.44, CW, 0.44)
        para(tf, subtitle, size=11.5, color=MUTED, italic=True, first=True,
             after=0, line=1.15)
    footer(s, n)
    return s


def divider(prs, n, num, kicker, title, blurb):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, SW, SH, fill=NAVY)
    rect(s, 0, 0, 0.10, SH, fill=ACCENT)
    tf = tb(s, M + 0.35, 2.42, CW - 0.7, 0.4)
    para(tf, kicker.upper(), size=11.5, color="7FB0F5", bold=True, first=True,
         after=0)
    tf = tb(s, M + 0.35, 2.84, CW - 1.2, 1.0)
    para(tf, title, size=34, color=WHITE, bold=True, first=True, after=0,
         line=1.0)
    tf = tb(s, M + 0.35, 3.98, CW - 2.6, 0.9)
    para(tf, blurb, size=12.5, color="C3CEDA", first=True, after=0, line=1.25)
    # big section number
    tf = tb(s, SW - M - 2.2, 1.95, 2.2, 1.6)
    para(tf, num, size=76, color="1E3E63", bold=True, align=PP_ALIGN.RIGHT,
         first=True, after=0, line=1.0)
    footer(s, n)
    return s


def cards(slide, items, y, cols=2, height=1.28, gapx=0.24, gapy=0.2,
          title_size=12.5, body_size=10.5, left=M, width=CW, fill=CARD,
          accent_bar=None):
    """items: list of (title, body) or (title, body, accent_colour)."""
    cw = (width - gapx * (cols - 1)) / cols
    for i, it in enumerate(items):
        title, body = it[0], it[1]
        accent = it[2] if len(it) > 2 else None
        r, c = divmod(i, cols)
        x = left + c * (cw + gapx)
        yy = y + r * (height + gapy)
        rect(slide, x, yy, cw, height, fill=fill, line=BORDER)
        if accent:
            rect(slide, x, yy, 0.055, height, fill=accent)
        pad = 0.20 if accent else 0.16
        tf = tb(slide, x + pad, yy + 0.12, cw - pad - 0.14, height - 0.22)
        para(tf, title, size=title_size, color=INK, bold=True, first=True,
             after=2, line=1.05)
        para(tf, body, size=body_size, color=BODY, after=0, line=1.2)


def kpis(slide, items, y, height=1.16, gapx=0.22, left=M, width=CW,
         value_size=25, label_size=9.5):
    """items: list of (big_value, label, colour)."""
    n = len(items)
    cw = (width - gapx * (n - 1)) / n
    for i, (val, label, colour) in enumerate(items):
        x = left + i * (cw + gapx)
        rect(slide, x, y, cw, height, fill=CARD, line=BORDER)
        rect(slide, x, y, cw, 0.05, fill=colour)
        tf = tb(slide, x + 0.14, y + 0.16, cw - 0.28, height - 0.26)
        para(tf, val, size=value_size, color=colour, bold=True, first=True,
             after=1, align=PP_ALIGN.CENTER, line=1.0)
        para(tf, label, size=label_size, color=MUTED, after=0,
             align=PP_ALIGN.CENTER, line=1.12)


def table(slide, headers, rows, x, y, w, col_w=None, row_h=0.30,
          head_h=0.34, size=10, head_size=9.5, mono_cols=(), align_right=(),
          zebra=True, head_fill=NAVY, cell_colors=None):
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(x),
                                   Inches(y), Inches(w),
                                   Inches(head_h + row_h * len(rows)))
    tbl = shape.table
    tblPr = tbl._tbl.tblPr
    tblPr.set("firstRow", "0")
    tblPr.set("bandRow", "0")
    for el in tblPr.findall(qn("a:tableStyleId")):
        tblPr.remove(el)

    if col_w:
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = Inches(cw)
    tbl.rows[0].height = Inches(head_h)
    for r in range(1, len(rows) + 1):
        tbl.rows[r].height = Inches(row_h)

    def put(cell, text, bold, color, fill, right=False, mono=False, sz=size):
        cell.margin_left = Inches(0.09)
        cell.margin_right = Inches(0.09)
        cell.margin_top = Inches(0.015)
        cell.margin_bottom = Inches(0.015)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(fill)
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT if right else PP_ALIGN.LEFT
        r = p.add_run()
        r.text = str(text)
        r.font.size = Pt(sz)
        r.font.bold = bold
        r.font.name = MONO_FONT if mono else BODY_FONT
        r.font.color.rgb = rgb(color)

    for c, h in enumerate(headers):
        put(tbl.cell(0, c), h, True, WHITE, head_fill,
            right=(c in align_right), sz=head_size)
    for r, row in enumerate(rows, start=1):
        fill = WHITE if (r % 2 == 1 or not zebra) else CARD
        custom = None
        if cell_colors:
            custom = cell_colors.get(r - 1)
        for c, val in enumerate(row):
            col = BODY
            bd = False
            if custom and c in custom:
                col, bd = custom[c]
            put(tbl.cell(r, c), val, bd, col, fill,
                right=(c in align_right), mono=(c in mono_cols))
    return tbl


# ================================================================ build =====
def build(out_path: str) -> int:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(SW), Inches(SH)
    n = 0

    def nxt():
        nonlocal n
        n += 1
        return n

    # ---------------------------------------------------------- 1 TITLE ----
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, SW, 0.14, fill=ACCENT)
    rect(s, 0, SH - 0.14, SW, 0.14, fill=NAVY)
    tf = tb(s, M + 0.3, 1.28, CW - 0.6, 0.3)
    para(tf, "CSIT321  ·  FINAL YEAR PROJECT  ·  FYP-26-S3-13", size=12,
         color=ACCENT, bold=True, first=True, after=0)
    tf = tb(s, M + 0.3, 1.78, CW - 1.0, 1.5)
    para(tf, "Human-in-the-Loop", size=44, color=INK, bold=True, first=True,
         after=0, line=1.0)
    para(tf, "Intrusion Detection Dashboard", size=44, color=INK, bold=True,
         after=0, line=1.0)
    rect(s, M + 0.3, 3.34, 1.5, 0.05, fill=ACCENT)
    tf = tb(s, M + 0.3, 3.56, CW - 1.6, 0.5)
    para(tf, "Fusing signature and machine-learning detection with analyst "
             "feedback, bounded by safety guardrails.", size=13.5,
         color=MUTED, first=True, after=0, line=1.2)
    rect(s, M + 0.3, 4.30, CW - 0.6, 0.011, fill=BORDER)
    tf = tb(s, M + 0.3, 4.46, 6.4, 1.5)
    para(tf, "PROJECT TEAM", size=9.5, color=ACCENT, bold=True, first=True,
         after=4)
    for name in ("Tan Jing Kai", "Zay Yar Naing", "Glenn Ang Zhen Xiang",
                 "Isaac Koh Zhi Xian", "Thian Wen Jun Gene", "Liow Chee Kuang"):
        para(tf, name, size=11, color=BODY, after=1.5, line=1.05)
    tf = tb(s, 7.6, 4.46, CW - 7.0, 1.2)
    para(tf, "SUPERVISOR", size=9.5, color=ACCENT, bold=True, first=True,
         after=4)
    para(tf, "Mr Lim Min Han", size=11, color=BODY, after=8, line=1.05)
    para(tf, "REPOSITORY", size=9.5, color=ACCENT, bold=True, after=4)
    para(tf, "github.com/CSIT-321/CSIT321-Human-in-the-loop_IDS", size=9.5,
         color=MUTED, after=0, font=MONO_FONT, line=1.15)
    tf = tb(s, M + 0.3, 6.62, CW, 0.3)
    para(tf, "Presented by the project team  ·  Demo build, September 2026",
         size=9.5, color=FAINT, first=True, after=0)
    n = nxt()

    # --------------------------------------------------------- 2 AGENDA ----
    s = content_slide(prs, nxt(), "Contents",
                      "What this presentation covers")
    left = [
        {"t": "The problem: analyst alert fatigue, and what the research shows", "b": True},
        {"t": "Our solution, and why we built it this specific way", "b": True},
        {"t": "How it works: the implemented workflow, end to end", "b": True},
        {"t": "Where we fit: existing IDS tools, and the gap we close", "b": True},
        {"t": "The live demo — the console, end to end", "b": True},
    ]
    right = [
        {"t": "The team, and what comes next", "b": True},
        {"t": "Technical FAQ — held back in case it is asked for: "
              "architecture, the dataset and its audit, notebooks 04 to 07, "
              "the fusion and ranking mathematics, and the three-arm "
              "evaluation", "b": False},
    ]
    bullets(s, left, M, 1.72, CW / 2 - 0.22, 4.6, size=12.5, gap=11)
    bullets(s, right, M + CW / 2 + 0.22, 1.72, CW / 2 - 0.22, 4.6, size=12.5,
            gap=11)

    # ------------------------------------------------------ 3 DIVIDER ------
    divider(prs, nxt(), "01", "Speaker 1 · Part one", "The problem",
            "Networks generate more security events than analysts can read. "
            "The evidence says the bottleneck is no longer detection — it is "
            "deciding what deserves attention.")

    # --------------------------------------------------- 4 ALERT FATIGUE ---
    s = content_slide(prs, nxt(), "The problem",
                      "Analysts are drowning in alerts",
                      "Volume is not the only problem — context is the missing "
                      "half.")
    kpis(s, [("Huge", "security events generated by modern networks", ACCENT),
             ("Repetitive", "low-value alerts that pile up unattended", HIGH),
             ("Falling", "investigation efficiency as the backlog grows", MED),
             ("Fatigue", "the human result of triaging without context", CRIT)],
         y=1.86, height=1.06)
    bullets(s, [
        {"t": "Modern networks generate enormous volumes of security activity, so analysts cannot tell quickly what needs attention first.", "mark": False},
        {"t": "Signature and machine-learning detectors each catch different patterns, but neither understands operational context.", "mark": False},
        {"t": "An event flagged as malicious may be authorised, expected, or a scheduled scan inside a given environment.", "mark": False},
        {"t": "The result is the same in every report: repetitive low-value alerts accumulate, investigation efficiency drops, and alert fatigue sets in.", "mark": False},
    ], M, 3.24, CW, 2.6, size=12.5, gap=9)
    rect(s, M, 5.62, CW, 0.86, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 5.76, CW - 0.44, 0.62)
    para(tf, "The bottleneck has moved. Detection is no longer the hard part — "
             "deciding what deserves a human's attention is.",
         size=12.5, color=INK, bold=True, first=True, after=3, line=1.15)
    para(tf, "That is the problem this project takes as its starting point.",
         size=10.5, color=MUTED, after=0)

    # --------------------------------------------------- 5 RESEARCH --------
    s = content_slide(prs, nxt(), "The problem",
                      "What the research says",
                      "Sources below were fetched and read; two further papers "
                      "are cited from metadata only, and are marked as such.")
    table(s, ["Source", "What it found", "Why it shapes our design"],
          [["Too Much to Trust?\n(CCS 2025)",
            "Survey N = 248, interviews N = 24. Analysts accepted explainable "
            "output when explanations were relevant and evidence-backed.",
            "Pair every model verdict with raw evidence, not model internals."],
           ["ContextBuddy\n(2025)",
            "Recommending relevant context cues raised classification accuracy "
            "21.1% and cut alert-validation time 24%.",
            "Show a short, curated key-evidence panel instead of every field."],
           ["Decision-Aware Trust\nSignal Alignment",
            "Uncalibrated confidence displays are hard to read under pressure "
            "and amplify false negatives.",
            "Show confidence as a band, and keep guardrail floors separate "
            "from model confidence."],
           ["LLMs in the SOC\n(2025)",
            "3,090 queries from 45 analysts over 10 months. Analysts retained "
            "decision authority and used AI as a sensemaking aid.",
            "The model advises; the verdict is always the analyst's."],
           ["Vendor console docs\n(Sentinel, Elastic, Splunk)",
            "Every console requires a closing classification, and all expose "
            "owner, status and severity as triage controls.",
            "One verdict per alert, with industry-standard labels."]],
          M, 1.94, CW, col_w=[2.05, 5.05, 5.03], row_h=0.79, head_h=0.32,
          size=9.3, head_size=9)
    tf = tb(s, M, 6.66, CW, 0.4)
    para(tf, "Cited from metadata only, not yet re-fetched: Alahmadi et al., "
             "\u201c99% False Positives\u201d (USENIX Security 2022) and Tariq "
             "et al., \u201cAlert Fatigue in SOCs\u201d (ACM CSUR 2025).",
         size=9, color=MUTED, italic=True, first=True, after=0, line=1.15)

    # ------------------------------------------- 6 AUTOMATION SHORT -------
    s = content_slide(prs, nxt(), "The problem",
                      "Why automation alone falls short")
    cards(s, [
        ("Signature-based detection",
         "Matches known attack patterns against packet and flow fields. "
         "Precise and human-checkable — but blind to anything new, and it "
         "offers no way to say which of its matches matter most.", ACCENT),
        ("Machine-learning detection",
         "Finds complex patterns that rules cannot express. Powerful on "
         "volume — but an opaque decision, and its confidence is only useful "
         "where it is calibrated.", ACCENT),
        ("Operational context",
         "Neither approach can know whether a flagged event is authorised or "
         "expected in this environment. That judgement is organisational "
         "knowledge, and it lives with the analyst.", HIGH),
        ("The triage burden",
         "Existing products still produce high alert volumes, need complex "
         "configuration, and give limited transparency into how analyst "
         "feedback is supposed to change prioritisation.", HIGH),
    ], y=1.66, cols=2, height=1.66, title_size=13, body_size=10.7)
    rect(s, M, 5.30, CW, 1.18, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.24, 5.42, CW - 0.48, 0.96)
    para(tf, "→  We need automation and human judgement, working together — "
             "and we need the machine to tell the analyst where its own "
             "evidence is weak.",
         size=13, color=INK, bold=True, first=True, after=4, line=1.15)
    para(tf, "That is the design premise of a human-in-the-loop system: the "
             "machine narrows the field, the human supplies context, and the "
             "system learns from the human's decision.",
         size=10.5, color=MUTED, after=0, line=1.2)

    # ------------------------------------------------------ 7 DIVIDER ------
    divider(prs, nxt(), "02", "Speaker 2 · Part two", "Our solution",
            "A hybrid detector that ranks its own evidence, and an analyst "
            "verdict that re-ranks future alerts — inside guardrails that "
            "explain themselves.")

    # ------------------------------------------------- 8 SOLUTION ---------
    s = content_slide(prs, nxt(), "Our solution",
                      "What we built, and the claim we can defend")
    rect(s, M, 1.62, CW, 0.94, fill=NAVY)
    tf = tb(s, M + 0.24, 1.76, CW - 0.48, 0.68)
    para(tf, "The model is confidently wrong. A human overrules it inside "
             "guardrails that explain themselves, and the correction spreads — "
             "measurably, and within limits — to the alerts like it.",
         size=13.5, color=WHITE, bold=True, first=True, after=0, line=1.2)
    cards(s, [
        ("1 · Fuse two detectors into one ranked alert",
         "A signature engine and an 8-class XGBoost model score every flow. "
         "Fusion assigns one evidence class, one score, one review flag and "
         "one explanation.", ACCENT),
        ("2 · Show the analyst why",
         "Every alert carries the rule's checkable clauses, the model's "
         "prediction, and a native TreeSHAP attribution of the features that "
         "pushed towards and away.", ACCENT),
        ("3 · Take the analyst's verdict",
         "One of five verdicts per alert. The verdict moves the alert's "
         "operational score through the guardrails, and the adjustment chain "
         "states exactly how far it moved and why.", GOOD),
        ("4 · Spread it to similar alerts",
         "A verdict teaches its family of similar alerts — but only after at "
         "least three agree. Unjudged alerts in that family then move too.",
         GOOD),
    ], y=2.72, cols=2, height=1.62, title_size=12.3, body_size=10.5)
    rect(s, M, 6.06, CW, 0.72, fill=CARD2, line=BORDER)
    tf = tb(s, M + 0.22, 6.18, CW - 0.44, 0.5)
    para(tf, "The claim we can defend:  the hybrid does not detect more — it "
             "tells the analyst where their attention is worth spending.",
         size=12, color=INK, bold=True, first=True, after=2, line=1.15)
    para(tf, "We deliberately do not claim a detection-coverage gain. "
             "Notebook 04 shows there is none on this data.",
         size=9.8, color=MUTED, after=0)

    # --------------------------------------------- 9 WHY THIS WAY ---------
    s = content_slide(prs, nxt(), "Our solution",
                      "Why we built it this specific way",
                      "Each choice below was forced by a measurement, not by "
                      "preference.")
    table(s, ["Design decision", "Why — the evidence that forced it"],
          [["Complementary Evidence Fusion, not a weighted sum",
            "The two detectors produce scores from different evidence classes, "
            "which are not commensurable. A weight sweep rescaled two disjoint "
            "populations: rank correlation stayed \u03c1 = 1.0000 at every "
            "setting. All averaging could do was hide the real problem."],
           ["Evidence classes instead of one blended number",
            "Classes preserve what averaging destroys: whether an alert is "
            "fast-track, needs review, or is a rule the model disputes. They "
            "also let the queue order carry a triage meaning."],
           ["The signature layer repositioned as trust, not coverage",
            "Retuning the rules reached precision 1.000 and recall 20%, yet "
            "unique signature coverage stayed at exactly zero. Coverage could "
            "not be the justification, so trust and explainability became it."],
           ["Ranking parameters chosen by experiment",
            "The project lead's decision: test candidate systems and pick one, "
            "rather than argue for one. Four formulas and two movement rules "
            "were pre-registered and run."],
           ["Guardrail values taken from the collaborator's engine",
            "Their feedback engine states the caps, floors and thresholds in "
            "code, and is richer than the written documents — the documents "
            "omit a positive cap entirely, without which confirmations inflate "
            "without bound."],
           ["TreeSHAP computed inside the detection run",
            "Explainability is a hard requirement, but computing it on demand "
            "would break the 2-second response budget. Inside the batch run it "
            "is free at request time."]],
          M, 1.96, CW, col_w=[3.95, 8.14], row_h=0.72, head_h=0.32,
          size=9.4, head_size=9)

    # ----------------------------------------------------- 10 DIVIDER ------
    divider(prs, nxt(), "03", "Speaker 3 · Part three",
            "The workflow, and what we built",
            "From a recorded flow to a re-ranked queue — and the eight stages "
            "that sit between them.")

    # ------------------------------------------- 11 WORKFLOW --------------
    s = content_slide(prs, nxt(), "Workflow", "End to end, in eight stages")
    stages = ["Recorded\nflow", "Signature\n+ ML", "Detection\nscore",
              "Analyst\nreview", "Human\nfeedback", "Guard-\nrails",
              "Operational\npriority", "Re-ranked\nqueue"]
    cw = (CW - 0.06 * 7) / 8
    for i, st in enumerate(stages):
        x = M + i * (cw + 0.06)
        fill = NAVY if i in (0, 2, 6, 7) else ACCENT
        rect(s, x, 1.62, cw, 0.78, fill=fill, shape=MSO_SHAPE.CHEVRON)
        tf = tb(s, x + 0.08, 1.74, cw - 0.16, 0.56,
                anchor=MSO_ANCHOR.MIDDLE)
        para(tf, st.replace("\n", " "), size=8.6, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER, first=True, after=0, line=1.0)
    cards(s, [
        ("The four lanes of the system",
         "1 · Real world (post-demo, S17): traffic → flow exporter → "
         "ExporterSource.   2 · Local today: dataset → sample → "
         "CsvReplaySource.   3 · Detection core (built): two views → two "
         "detectors → fusion → alert.   4 · Store, show, feedback: SQLite → "
         "API → analyst → guardrails → new score.", ACCENT),
        ("Two score fields on every alert",
         "detection_score is what the detectors concluded, set once and never "
         "changed. combined_score is the operational score that feedback "
         "moves. Keeping both is deliberate: their difference is the "
         "measurable effect of human feedback.", GOOD),
    ], y=2.62, cols=2, height=1.42, title_size=12.2, body_size=10.2)
    bullets(s, [
        {"t": "Detection is an offline batch run: python scripts/run_detection.py turns 5,000 flows into 5,000 alerts in about 21 seconds.", "mark": False},
        {"t": "Every flow becomes an alert — including the 4,004 no detector flagged. They are the queue's bottom band and the evaluation's denominator.", "mark": False},
        {"t": "The system is deterministic: a second run over the same sample differs in no scored field, for any of the 5,000 alerts (NFR-05).", "mark": False},
    ], M, 4.26, CW, 1.5, size=11.5, gap=8)
    rect(s, M, 5.86, CW, 0.92, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 5.98, CW - 0.44, 0.7)
    para(tf, "Shipped and reachable:  python -m uvicorn apps.api.main:app "
             "serves the API on port 8000; cd apps/web && npm run dev serves "
             "the console on port 5173.",
         size=11, color=INK, bold=True, first=True, after=2, line=1.15)
    para(tf, "The console's three views are three real accounts, each signing "
             "in to its own role — not one user switching a dropdown.",
         size=9.8, color=MUTED, after=0)

    # ----------------------------------------------------- 35 DIVIDER -----
    divider(prs, nxt(), "04", "Speaker 4 · Part four",
            "Commercial tools, and where we fit",
            "The commercial landscape, what the research says consoles must "
            "do, and where this project sits inside a real SOC workflow.")

    # ----------------------------------------- 36 COMMERCIAL TOOLS ------
    s = content_slide(prs, nxt(), "Commercial landscape",
                      "Existing IDS tools, and the gap they leave")
    table(s, ["Product", "Approach", "What it does well",
              "The gap this project targets"],
          [["Snort", "Signature-based IDS",
            "Mature rule ecosystem; matches are explainable",
            "No feedback-driven prioritisation — every rule hit arrives with "
            "the same standing"],
           ["Suricata", "Signature and protocol analysis",
            "High throughput; detailed, well-structured logs",
            "The same triage burden is passed downstream to the analyst"],
           ["Darktrace", "Behavioural machine learning",
            "Self-learning; offers autonomous response",
            "Limited transparency into how decisions are reached"],
           ["Vectra AI", "AI behavioural detection (NDR)",
            "Correlates and scores attacker behaviour across the estate",
            "Enterprise-priced, and opaque as a decision surface"],
           ["SIEM consoles\n(Sentinel, Elastic, Splunk)",
            "Aggregation and triage on top of detection",
            "Genuinely good triage workflow — queue, owner, status, "
            "classification, notes",
            "They inherit the alert volume, and still leave the analyst to "
            "decide what matters"]],
          M, 1.72, CW, col_w=[1.85, 2.35, 4.05, 3.84], row_h=0.78, head_h=0.34,
          size=9.2, head_size=9)
    rect(s, M, 6.06, CW, 0.72, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 6.18, CW - 0.44, 0.5)
    para(tf, "The gap: existing products still generate large alert volumes, "
             "need complex configuration, and give limited transparency into "
             "how analyst feedback should shape prioritisation.",
         size=11, color=INK, bold=True, first=True, after=2, line=1.15)
    para(tf, "This project fuses two detectors into one explainable alert and "
             "closes the loop with guardrailed, structured feedback.",
         size=9.6, color=MUTED, after=0)

    # ------------------------------------------- 37 SOC FIT --------------
    s = content_slide(prs, nxt(), "Commercial landscape",
                      "How our product fits the workflow commercial settings "
                      "already use")
    table(s, ["SOC tier", "What they do", "Where our system sits"],
          [["Tier 1 — triage",
            "Monitors the queue, decides real or false positive, enriches, "
            "escalates",
            "This is Tier 1's tool. The analyst queue is Tier 1's queue and "
            "every verdict is a Tier 1 decision."],
           ["Tier 2 — incident response",
            "Takes escalated incidents; deep investigation, containment, "
            "remediation",
            "Alerts meeting escalation criteria carry a \u2192 Tier 2 marker. "
            "In the demo this is a recommendation; automatic routing is "
            "post-demo."],
           ["Tier 3 — detection engineering",
            "Hunts advanced threats; builds and fixes detections",
            "A verdict that disputes a precision-1.000 rule is routed to the "
            "administrator, as are the attacks both detectors missed."]],
          M, 1.72, CW, col_w=[2.40, 4.35, 5.34], row_h=0.86, head_h=0.34,
          size=9.4, head_size=9)
    cards(s, [
        ("Our verdicts use the industry's own vocabulary",
         "True Positive · Benign Positive · False Positive · Needs "
         "investigation · Escalate to Tier 2. These map one-to-one onto the "
         "closing classifications that Sentinel, Elastic and Splunk already "
         "require.", ACCENT),
        ("Console patterns we adopted from verified product documentation",
         "A queue beside a details pane, not a page per alert. Explanation "
         "first. Four triage controls. Related context as a first-class "
         "section — our family is Sentinel's \u201csimilar incidents\u201d. "
         "Guardrail floors kept visually separate from model confidence.", GOOD),
        ("Where we deliberately stop",
         "No live capture, no automated response, no host-based agents, and no "
         "online retraining. Nothing invented for the demo: no geolocation, no "
         "threat-intel feeds, no asset names. The console says "
         "\u201cRecorded flows\u201d, not \u201cLive\u201d.", WARN),
    ], y=4.54, cols=3, height=2.02, title_size=10.6, body_size=9.2)

    # ----------------------------------------------------- 38 DIVIDER -----
    divider(prs, nxt(), "05", "Speaker 5 · Part five", "The demo",
            "What is implemented and running, what remains planned, and the "
            "narrative the demo performs.")

    # ---------------------------------------- 39 DEMO IMPLEMENTED -------
    s = content_slide(prs, nxt(), "The demo",
                      "What the demo covers — implemented and running")
    kpis(s, [("5,000", "flows → 5,000 alerts", ACCENT),
             ("445", "Python tests, 0 skipped", GOOD),
             ("132", "web tests", GOOD),
             ("41/41", "rehearsal checks", GOOD),
             ("3", "real signed-in accounts", ACCENT)],
         y=1.62, height=1.10)
    cards(s, [
        ("Analyst — the workstation",
         "Ranked queue with filters, sort and paging; alert detail with the "
         "four evidence panels, the family panel and the flow record; the "
         "verdict form with the score-adjustment chain and its guardrail "
         "sentences; Investigations and Feedback Impact; journey keys j and k.",
         ACCENT),
        ("Analyst — Overview and Entity",
         "Overview: flow volume by capture hour, top source and destination "
         "addresses and ports, alerts by predicted class, verdict and status "
         "mix, guardrail interventions. Entity: a per-address page with its "
         "peers, each linking onward.", ACCENT),
        ("Administrator",
         "The platform owner, not a triage role: they own the guardrail policy "
         "— how far feedback may move a score, which floors protect critical "
         "findings — plus service health, the guardrail log and the audit "
         "trail with CSV export.", GOOD),
        ("Evaluator",
         "The detection engineer who answers \"is this getting better?\": the "
         "three-arm comparison with every delta as measured, per-class metrics, "
         "and each run's pre-registration — accountability rather than a black "
         "box.", GOOD),
    ], y=2.88, cols=2, height=1.62, title_size=11.3, body_size=9.6)
    rect(s, M, 6.20, CW, 0.60, fill=CARD2, line=BORDER)
    tf = tb(s, M + 0.22, 6.30, CW - 0.44, 0.42)
    para(tf, "Verification that found what tests missed: the browser "
             "end-to-end run caught a SQLite cross-thread error that 381 "
             "passing Python tests, TestClient and curl all missed — because "
             "only a browser fires an alert's three reads at once.",
         size=9.4, color=BODY, first=True, after=0, line=1.18)

    # ---------------------------------------------- 41 DEMO SCRIPT -------
    s = content_slide(prs, nxt(), "The demo",
                      "The narrative, click by click",
                      "Every number below was produced by "
                      "scripts/rehearse_demo.py against the demo database.")
    table(s, ["Step", "The action", "What the screen shows"],
          [["1", "Sign in as g.ang / analyst-demo",
            "Lands on the Workstation — \u201c5,000 alerts\u201d. Every flow "
            "becomes an alert; two score columns: Detection never changes, "
            "Operational is what analysts move."],
           ["2", "Search AL-00478 and open it",
            "A Tier 2 candidate at 99.89, rank 639. No rule matched. The model "
            "says Web Attack with 99.9% confidence. Ground truth: benign."],
           ["3", "Record verdict: False Positive",
            "The chain reads 99.89 → requested −30.00 → bound → applied −29.89 "
            "→ 70.00, labelled \u201cCapped by a guardrail\u201d, with the "
            "guardrail's own sentence. Band moves Tier 2 candidate → Model "
            "only; rank 639 → 996. Refresh: still 70.00, and the history shows "
            "the verdict in effect."],
           ["4", "Search AL-03086 and confirm it",
            "The attack both detectors missed, at 36.94, bottom band. True "
            "Positive requests +10 and is applied as requested: 36.94 → 46.94. "
            "It leaves the bottom band but climbs only from rank 998 to 997 — "
            "one confirmation moves one band."],
           ["5", "Confirm three members of the Port Scan / port 445 family",
            "The first two say learning did not apply — not enough learning "
            "verdicts. The third says: learning applied, 2 other alerts in "
            "this family moved. AL-03044 and AL-04526 are now Tier 2 "
            "candidates, with no verdict of their own."],
           ["6", "Sign in as admin / admin-demo",
            "The guardrail log shows the cap on AL-00478 with the same "
            "sentence. The audit trail shows every verdict, guardrail action "
            "and family-learning event, exportable as CSV."],
           ["7", "Sign in as evaluator / evaluator-demo",
            "Open the newest evaluation run. Detection metrics are identical "
            "across all three arms. Under the v1.31 severity-first order "
            "precision@50 holds at 1.000 in every arm; the honest cost is the "
            "small mean-rank shift (Δ −0.515) and precision@200 (Δ −0.010)."]],
          M, 1.94, CW, col_w=[0.55, 3.35, 8.19], row_h=0.665, head_h=0.32,
          size=9.2, head_size=9, align_right=(0,))

    # --------------------------------------------------- S6 DIVIDER ------
    divider(prs, nxt(), "06", "Speaker 6 · Part six", "Team, and what comes next",
            "Six people, one trust loop — and the two steps still ahead: the "
            "prefix flow exporter, and the full backend.")
    # --------------------------------------------------- 43 TEAM ---------
    s = content_slide(prs, nxt(), "The team", "Six people, one trust loop")
    members = [
        ("GA", "Glenn Ang Zhen Xiang", "Project Leader, Developer, Tester, "
         "Documentation", ACCENT),
        ("LC", "Liow Chee Kuang", "Lead Developer, Software Tester, "
         "Documentation", ACCENT),
        ("TJ", "Tan Jing Kai", "Lead Documentation, Software Tester, "
         "Developer", ACCENT),
        ("IK", "Isaac Koh Zhi Xian", "Lead Tester, Documentation, Developer",
         GOOD),
        ("TW", "Thian Wen Jun Gene", "QA Engineer, Developer, Documentation",
         GOOD),
        ("ZY", "Zay Yar Naing", "Feedback & Fusion Developer, Documentation",
         GOOD),
    ]
    cw = (CW - 0.26 * 2) / 3
    for i, (initials, name, role, colour) in enumerate(members):
        r, c = divmod(i, 3)
        x = M + c * (cw + 0.26)
        y = 1.70 + r * 1.62
        rect(s, x, y, cw, 1.42, fill=CARD, line=BORDER)
        rect(s, x, y, cw, 0.05, fill=colour)
        rect(s, x + 0.22, y + 0.28, 0.72, 0.72, fill=colour,
             shape=MSO_SHAPE.OVAL)
        tf = tb(s, x + 0.22, y + 0.46, 0.72, 0.36)
        para(tf, initials, size=15, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER, first=True, after=0)
        tf = tb(s, x + 1.08, y + 0.30, cw - 1.30, 1.0)
        para(tf, name, size=12.5, color=INK, bold=True, first=True, after=3,
             line=1.05)
        para(tf, role, size=9.6, color=MUTED, after=0, line=1.18)
    rect(s, M, 4.98, CW, 0.78, fill=NAVY)
    tf = tb(s, M + 0.24, 5.10, CW - 0.48, 0.56)
    para(tf, "Supervisor: Mr Lim Min Han", size=12.5, color=WHITE, bold=True,
         first=True, after=3)
    para(tf, "FYP-26-S3-13  ·  CSIT321 Final Year Project  ·  "
             "github.com/CSIT-321/CSIT321-Human-in-the-loop_IDS",
         size=9.6, color="C3CEDA", after=0)
    tf = tb(s, M, 5.98, CW, 0.7)
    para(tf, "The workplan for this build was the project lead plus delegated "
             "implementation workers; the team roles above are the project's "
             "own allocation.",
         size=9.6, color=MUTED, italic=True, first=True, after=0, line=1.2)

    # -------------------------------------- 40 DEMO PLANNED / CONNECT ----
    s = content_slide(prs, nxt(), "The demo",
                      "What remains planned, and how the pieces connect")
    tf = tb(s, M, 1.60, CW, 0.3)
    para(tf, "NOT YET BUILT — PHASE 6, POST-DEMO", size=9.5, color=ACCENT,
         bold=True, first=True, after=0)
    cards(s, [
        ("S17 — the prefix flow exporter",
         "A capture path for real traffic: the GintsEngelen CICFlowMeter fork "
         "turns PCAP into CIC features, entering the pipeline through the same "
         "FlowSource interface that CSV replay already uses, so nothing "
         "downstream changes. Its exit criterion is strict: if schema "
         "reconciliation against feature-columns.json fails, the step stops "
         "and reports — it never silently coerces a column.", ACCENT),
        ("S18 — the full backend",
         "SQLite moves to PostgreSQL, which the schema was written for in S2. "
         "The remaining TDM endpoints arrive: user management, rule manager, "
         "model version management, fusion weight configuration, bulk "
         "feedback, exports and notifications. Append-only immutability and "
         "the RBAC matrix are re-proven on Postgres.", ACCENT),
    ], y=1.94, cols=2, height=1.68, title_size=11.5, body_size=9.7)
    tf = tb(s, M, 3.80, CW, 0.3)
    para(tf, "ALSO OPEN — RECORDED, NOT SILENTLY DROPPED", size=9.5,
         color=ACCENT, bold=True, first=True, after=0)
    bullets(s, [
        {"t": "The efficiency stress test. The weaker detector is now built and measured — data/stress.db, 600 false positives and 300 false negatives, precision@10 at 0.400 against 1.000 on the pristine queue. The pre-registered run over it is what remains, and it must be reported as its own labelled experiment, never folded into the headline.", "mark": False},
        {"t": "A dismissal-direction sequence, so the guardrails-off arm has something to measure. An oracle analyst over a near-perfect detector produces no dismissals.", "mark": False},
        {"t": "The fine family key as defence in depth, and the queue band names, which currently reuse the evidence-class names.", "mark": False},
    ], M, 4.14, CW, 2.0, size=10, gap=7)
    rect(s, M, 6.02, CW, 0.78, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 6.14, CW - 0.44, 0.56)
    para(tf, "How the pieces connect: the flow exporter becomes a second "
             "implementation of the same FlowSource interface, so detection, "
             "fusion, ranking, guardrails, storage, the API and the console "
             "are untouched. Postgres replaces SQLite behind the same "
             "repository layer.",
         size=10, color=INK, bold=True, first=True, after=2, line=1.16)
    para(tf, "That is why the schema, the contract and the queue order were "
             "fixed early — so the remaining work is additive.",
         size=9.4, color=MUTED, after=0)

    # --------------------------------------------------- S6 PLAN --------
    s = content_slide(prs, nxt(), "The plan",
                      "What happens after the demo")
    tf = tb(s, M, 1.56, CW, 0.28)
    para(tf, "HOW WE GOT HERE, AND WHAT FOLLOWS", size=9.5, color=ACCENT,
         bold=True, first=True, after=0)
    # Phase-level only: the two boundaries are true, and a pitch does not owe
    # anyone a feature-by-feature account of which part landed when.
    strip = [("PHASE 1", "Research and direction", "10 weeks"),
             ("PHASE 2", "The build you have just seen", "to demo day"),
             ("FROM DEMO DAY", "The plan below", "12 weeks")]
    bw = (CW - 2 * 0.22) / 3
    for i, (k, t, d) in enumerate(strip):
        x = M + i * (bw + 0.22)
        hot = i == 2
        rect(s, x, 1.84, bw, 0.78, fill=ACCENT_BG if hot else CARD,
             line=ACCENT if hot else BORDER)
        inner = tb(s, x + 0.16, 1.92, bw - 0.32, 0.62)
        para(inner, k, size=8.8, color=ACCENT if hot else MUTED, bold=True,
             first=True, after=1)
        para(inner, t, size=10.6, color=INK, bold=True, after=1, line=1.05)
        para(inner, d, size=9, color=MUTED, after=0)
    tf = tb(s, M, 2.74, CW, 0.28)
    para(tf, "REMAINING IMPLEMENTATION — SEQUENCED BY DEPENDENCY",
         size=9.5, color=ACCENT, bold=True, first=True, after=0)
    table(s, ["Workstream", "What it delivers", "Window"],
          [["S17 · Prefix flow exporter",
            "PCAP becomes CIC features through the same FlowSource seam CSV "
            "replay already uses, so detection, fusion, ranking, storage and "
            "the console are untouched. It stops and reports if schema "
            "reconciliation fails — it never silently coerces a column.",
            "Weeks 1–3"],
           ["S18 · Full backend",
            "SQLite moves to PostgreSQL, which the schema was written for. The "
            "remaining TDM endpoints land: user, rule and model-version "
            "management, fusion weight configuration, bulk feedback, exports "
            "and notifications. Immutability and the RBAC matrix re-proven.",
            "Weeks 4–9"],
           ["Evaluation follow-ups",
            "The pre-registered stress-test run over the weakened detector, "
            "reported as its own labelled experiment; a dismissal-direction "
            "sequence, so the guardrails-off arm has something to measure.",
            "Throughout"],
           ["Ranking refinements",
            "The fine family key as defence in depth; the queue band names; "
            "automatic Tier 2 escalation, deferred at Q25.",
            "Weeks 10–12"]],
          M, 3.00, CW, col_w=[2.30, 7.62, 2.17], row_h=0.60, head_h=0.30,
          size=9.1, head_size=9)
    rect(s, M, 5.86, CW, 0.78, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 5.96, CW - 0.44, 0.58)
    para(tf, "Sequenced by dependency, not by date: each step's exit "
             "criterion gates the next.", size=10, color=INK, bold=True,
         first=True, after=2, line=1.16)
    para(tf, "That is why the schema, the data contract and the queue order "
             "were fixed early — so everything remaining is additive, and the "
             "exporter and the backend can be built without disturbing what "
             "already works.", size=9.2, color=MUTED, after=0)

    # ------------------------------------------------- 45 FAQ DIVIDER -----
    divider(prs, nxt(), "F", "Appendix — if asked", "Technical FAQ",
            "Everything from here is reference material: architecture, the "
            "dataset and its audit, the notebooks, the fusion and ranking "
            "mathematics, and the evaluation. The pitch and the demo stand "
            "complete without it.")

    # --------------------------------------- 12 DETECTION CORE ------------
    s = content_slide(prs, nxt(), "Workflow",
                      "What are the detection layers?",
                      "Full formulas and worked examples are in "
                      "docs/iteration-2-report.md, section 4.")
    table(s, ["#", "Layer", "What it produces"],
          [["1", "Two views of one flow",
            "16 observable fields for the rules; 82 features for the model."],
           ["2", "Two detectors, side by side",
            "Signature engine: which rules matched, each condition's observed "
            "value → sig. Model: one of 8 classes, ml = 1 − P(Benign), plus a "
            "TreeSHAP explanation."],
           ["3", "Evidence class",
            "corroborated · signature_override · ml_only · none."],
           ["4", "Score",
            "corroborated  min(100, max(sig, ml) × 100 + 5)  ·  override "
            "sig × 100  ·  ml_only and none  ml × 100."],
           ["5", "Severity and flags",
            "One threshold, 80, sets severity Critical, is_critical and the "
            "review flag together, so the three can never disagree. The "
            "override class is always reviewed."],
           ["6", "Explanation and queue place",
            "A plain-language reason — the rule's checkable clauses plus the "
            "model's strongest features — and a queue place by evidence class, "
            "then score."]],
          M, 1.94, CW, col_w=[0.42, 2.95, 8.72], row_h=0.66, head_h=0.32,
          size=9.7, head_size=9, align_right=(0,))
    cards(s, [
        ("Why 1 − P(Benign), not the predicted class's confidence",
         "Confidence understates risk when probability is split between attack "
         "classes: DoS 0.50 + DDoS 0.45 is 0.95 malicious, not 0.50.", ACCENT),
        ("Why the +5 agreement bonus",
         "A precision-1.000 rule and the model agreeing on the class is worth "
         "slightly more than either alone — and it is verifiable by a human.",
         GOOD),
    ], y=5.68, cols=2, height=0.94, title_size=10.8, body_size=9.5)

    # ------------------------------------ 13 FEEDBACK + GUARDRAILS --------
    s = content_slide(prs, nxt(), "Workflow",
                      "What can an analyst do, and what bounds it?")
    table(s, ["Verdict (industry label)", "API category", "Requests",
              "Forces review"],
          [["True Positive", "confirm_true_positive", "+10", "yes"],
           ["False Positive", "mark_false_positive", "−30", "no"],
           ["Benign Positive", "mark_expected_activity", "−15", "no"],
           ["Needs investigation", "needs_investigation", "0", "yes"],
           ["Escalate to Tier 2", "escalate", "+15", "yes"]],
          M, 1.72, CW * 0.505, col_w=[1.72, 2.20, 1.30, 1.05], row_h=0.33,
          head_h=0.34, size=9.5, head_size=9, align_right=(2, 3))
    tf = tb(s, M, 3.80, CW * 0.505, 2.5)
    para(tf, "duplicate is a queue action, not a score change — it links the "
             "alert to its original and suppresses it from the active queue.",
         size=10, color=MUTED, italic=True, first=True, after=10, line=1.2)
    para(tf, "Verdicts do not stack. Each new verdict supersedes the previous "
             "one, so the score is always the detection score plus the guarded "
             "change of the latest verdict. A score can never drift further "
             "than one capped change from what the detectors said.",
         size=10.5, color=BODY, after=0, line=1.22)
    tx = M + CW * 0.505 + 0.28
    tw = CW - CW * 0.505 - 0.28
    tf = tb(s, tx, 1.72, tw, 0.3)
    para(tf, "THE GUARDRAILS, IN ORDER", size=9.5, color=ACCENT, bold=True,
         first=True, after=0)
    g = [
        ("1 · Evidence check", "A disputed rule (signature_override) keeps its "
         "score; the verdict routes to the administrator as a possible rule "
         "regression."),
        ("2 · Cap", "One verdict may move a score by at most −30 or +20."),
        ("3 · Floors", "A Critical alert cannot be pushed below 70; an "
         "Infiltration alert not below 75. A floor never raises a score."),
        ("4 · Outcome", "Every event records the requested change, the change "
         "applied, and whether it was applied, capped or rejected — with the "
         "reason."),
    ]
    y = 2.06
    for title, body in g:
        rect(s, tx, y, tw, 0.80, fill=CARD, line=BORDER)
        rect(s, tx, y, 0.05, 0.80, fill=ACCENT)
        t2 = tb(s, tx + 0.18, y + 0.09, tw - 0.32, 0.62)
        para(t2, title, size=11, color=INK, bold=True, first=True, after=2)
        para(t2, body, size=9.5, color=BODY, after=0, line=1.18)
        y += 0.88
    rect(s, M, 5.62, CW, 1.14, fill=CARD2, line=BORDER)
    tf = tb(s, M + 0.24, 5.76, CW - 0.48, 0.88)
    para(tf, "Worked example — AL-00478, a benign flow the model calls a Web "
             "Attack at 99.89, Critical:",
         size=11.5, color=INK, bold=True, first=True, after=3)
    rt(tf, [("The analyst records False Positive (requests −30). ", False, BODY, False),
            ("99.89 − 30 = 69.89, below the Critical floor, so the score is "
             "held at 70.00", True, BODY, False),
            (". The chain reads 99.89 → requested −30.00 → bound → applied "
             "−29.89 → 70.00, and the guardrail's own sentence says why.",
             False, BODY, False)],
       size=10.3, after=3, line=1.2)
    para(tf, "The verdict is recorded in full. What the guardrail limited is "
             "how far one verdict may move a Critical alert — not the "
             "analyst's finding.",
         size=9.8, color=MUTED, italic=True, after=0)

    # -------------------------------------- 14 SIMILAR-ALERT LEARNING -----
    s = content_slide(prs, nxt(), "Workflow",
                      "How does one verdict affect other alerts?",
                      "A verdict does not only move the alert judged. It "
                      "teaches the family of similar alerts.")
    cards(s, [
        ("The family key",
         "Alerts sharing attack class, destination port, protocol and matched "
         "rule. A flow no detector flagged also keys on its destination. This "
         "is the collaborator's similarity design, reduced to an exact key.",
         ACCENT),
        ("The agreement gate",
         "Nothing reaches the queue until a family has at least 3 learning "
         "verdicts, no tie, and at least 0.67 agreement on one category. Only "
         "the learning that points the agreed way then applies.", HIGH),
        ("The movement",
         "Formula C1: up by +K·w, down by −K·(1 − w), with K = 30 and w = the "
         "attack type's severity ÷ 10. A family moves one queue band at a time "
         "(movement M1).", GOOD),
        ("The precedence rule",
         "An alert with a verdict of its own is placed by that verdict, not by "
         "its family. A disputed-rule alert neither teaches nor learns, and "
         "never leaves its band.", ACCENT),
    ], y=1.66, cols=2, height=1.58, title_size=12, body_size=10.2)
    rect(s, M, 5.16, CW, 1.56, fill=CARD2, line=BORDER)
    tf = tb(s, M + 0.24, 5.30, CW - 0.48, 1.3)
    para(tf, "Why the gate matters more than the formula we chose",
         size=12, color=INK, bold=True, first=True, after=4)
    bullets(s, [
        {"t": "Without a gate, one wrong verdict moved a whole family: thirteen correct dismissals were outweighed by one confirmation, lifting 779 benign flows into Tier 2.", "mark": False},
        {"t": "With the gate on, that failure disappears for every formula tested — the 59 demoted attacks and the 780 misplaced alerts both fall to zero, in every seed.", "mark": False},
        {"t": "The gate counts by category, not by direction, because 2 false positives plus 1 expected-activity verdict is 0.6667 agreement — and the gate correctly stays shut.", "mark": False},
    ], M + 0.24, 5.62, CW - 0.48, 1.0, size=10.2, gap=5)

    # ----------------------------------------------------- 15 DIVIDER ------
    divider(prs, nxt(), "A1", "Appendix · A1", "Architecture and stack",
            "What the system is made of, how the pieces are separated, and the "
            "exact technology stack.")

    # ----------------------------------------- 16 ARCHITECTURE ------------
    s = content_slide(prs, nxt(), "Technical introduction",
                      "How is the system built?")
    layers = [
        ("Interface", "apps/web", "React console — analyst workstation, "
         "overview, entity view, admin, evaluator", ACCENT),
        ("API", "apps/api", "FastAPI service; contract in apps/api/contract "
         "(pure Pydantic), handlers in routes.py, mappers.py", ACCENT),
        ("Persistence", "packages/contracts · pipeline/store.py",
         "SQLite with 13 tables and append-only triggers; repository reads in "
         "store.py", GOOD),
        ("Detection", "packages/detection", "signature/ · ml/ · fusion/ · "
         "ranking/ · feedback/ · guardrail/ · triage/ · pipeline/", HIGH),
        ("Evaluation", "packages/evaluation",
         "truth.py · scenario.py · metrics.py · harness.py — the three-arm "
         "harness", HIGH),
        ("Evidence", "data/processed · models · rules · config",
         "Samples, 8-class model, tuned rule set, versioned severity chart",
         MED),
    ]
    y = 1.58
    for name, path, desc, colour in layers:
        rect(s, M, y, CW, 0.74, fill=CARD, line=BORDER)
        rect(s, M, y, 0.06, 0.74, fill=colour)
        tf = tb(s, M + 0.22, y + 0.08, 1.85, 0.58)
        para(tf, name, size=11.5, color=INK, bold=True, first=True, after=0)
        tf = tb(s, M + 2.16, y + 0.08, CW - 2.4, 0.58)
        rt(tf, [(path + "  —  ", True, colour, True), (desc, False, BODY, False)],
           size=10, first=True, after=0, line=1.16)
        y += 0.81
    tf = tb(s, M, y + 0.08, CW, 0.46)
    para(tf, "Dependency direction is one-way: the interface depends on the "
             "API, which depends on the contract, which depends on nothing. "
             "The contract imports no web framework at all — which is why the "
             "console's client is generated from it and cannot drift.",
         size=10, color=MUTED, italic=True, first=True, after=0, line=1.2)

    # ----------------------------------------- 17 STACK BACKEND -----------
    s = content_slide(prs, nxt(), "Technical introduction",
                      "What is it built with, server-side?",
                      "The exact versions the project is tested with, pinned in "
                      "requirements.txt on Python 3.11.")
    table(s, ["Layer", "Technology", "Version", "Why this one"],
          [["Language", "Python", "3.11.11",
            "The tested set every result was produced on."],
           ["API", "FastAPI", "0.136.0",
            "Typed request and response models, OpenAPI generated from the "
            "contract."],
           ["ASGI", "Starlette · Uvicorn", "1.6.0 · 0.37.0",
            "The ASGI layer and server the API runs on."],
           ["Contracts", "Pydantic", "2.11.9",
            "One definition, enforced again as database CHECK constraints."],
           ["Model", "XGBoost", "3.2.0",
            "8-class classifier with native TreeSHAP at no extra cost."],
           ["ML support", "scikit-learn · NumPy · pandas", "1.7.1 · 2.3.5 · 2.3.3",
            "Metrics, cross-validation, and the analysis notebooks."],
           ["Explainability", "TreeSHAP (native, in-run)", "—",
            "5,000 of 5,000 alerts carry an additivity-verified explanation."],
           ["Storage", "SQLite (PostgreSQL at S18)", "—",
            "The schema was written for Postgres, so the migration is a port."],
           ["Auth", "bcrypt · PyJWT (HS256)", "—",
            "Real sign-in: 8-hour bearer tokens, role carried inside the token."],
           ["Tests / lint", "pytest · ruff", "8+", "445 Python tests, 0 skipped."]],
          M, 1.66, CW, col_w=[1.42, 2.62, 1.55, 6.50], row_h=0.335,
          head_h=0.32, size=9.3, head_size=9)

    # ----------------------------------------- 18 STACK FRONTEND ----------
    s = content_slide(prs, nxt(), "Technical introduction",
                      "What is it built with, client-side?")
    table(s, ["Layer", "Technology", "Version", "Why this one"],
          [["UI framework", "React", "19.3.0",
            "Component model for a dense, keyboard-driven console."],
           ["Build", "Vite", "8.3.0", "Fast dev server with an /api proxy."],
           ["Language", "TypeScript", "5.9.3",
            "No any in src/ — a stated exit criterion."],
           ["Styling", "Tailwind CSS", "4.3.3",
            "Design tokens in one place, under semantic names."],
           ["Routing", "react-router", "7.18.3",
            "One shell, three role-scoped route trees."],
           ["Charts", "Recharts", "3.10.1",
            "Overview and evaluator charts; every chart repeats as a table."],
           ["API client", "openapi-fetch · openapi-typescript", "0.17.0 · 7.13.0",
            "The client is generated from the contract; check:api fails if it "
            "is stale."],
           ["Unit tests", "Vitest · Testing Library", "5.0.0",
            "128 web tests."],
           ["End-to-end", "Playwright", "1.63.0",
            "The demo narrative in a real browser, with three real sign-ins."]],
          M, 1.66, CW, col_w=[1.42, 3.20, 1.55, 5.92], row_h=0.385,
          head_h=0.32, size=9.3, head_size=9)

    # ----------------------------------------------------- 19 DIVIDER ------
    divider(prs, nxt(), "A2", "Appendix · A2",
            "Dataset and technical analysis",
            "What the data actually is, how it was split, and the four "
            "notebooks that decided the project's direction.")

    # ----------------------------------------- 20 DATASET CHOICE ----------
    s = content_slide(prs, nxt(), "Dataset",
                      "What data is this trained and tested on?")
    cards(s, [
        ("The choice",
         "CICIDS2017, as the PRD assumed, was replaced by the corrected "
         "CSE-CIC-IDS2018 release — Engelen et al., IEEE CNS 2022.",
         ACCENT),
        ("Why the correction mattered",
         "The original labels are wrong in ways that invalidate headline "
         "metrics. Published errors were documented in WTMC 2021 and CNS 2022. "
         "Training on the uncorrected labels would have produced a model that "
         "cannot emit two of the classes the demo needs.", ACCENT),
        ("Why 2018 over 2017",
         "The implementation was already weeks ahead on 2018, and the flow "
         "schema matches what a real flow exporter produces. Moving to the "
         "corrected release cost one retrain and pre-empted a dataset-validity "
         "challenge.", GOOD),
        ("Why a flow dataset at all",
         "The system is flow-based, so the features it consumes at training "
         "time must be the features a flow exporter computes in production. "
         "The corrected release was produced by the same tool we would deploy.",
         GOOD),
    ], y=1.66, cols=2, height=1.52, title_size=12, body_size=10.2)
    kpis(s, [("63,195,145", "labelled flows scanned", ACCENT),
             ("10", "capture days", ACCENT),
             ("10.43 GB", "compressed archive, streamed — never extracted",
              ACCENT),
             ("93.92%", "of flows are benign", GOOD),
             ("6.08%", "of flows are attacks", HIGH)],
         y=4.86, height=1.10)
    tf = tb(s, M, 6.14, CW, 0.7)
    para(tf, "The 36 GB of uncompressed CSV is streamed directly from the zip. "
             "Only the two derived samples ever touch disk — an explicit "
             "working rule of the project.",
         size=10.2, color=MUTED, first=True, after=0, line=1.2)

    # ------------------------------------------ 21 DATASET AUDIT ----------
    s = content_slide(prs, nxt(), "Dataset",
                      "Why did the class list change?",
                      "Three findings from the corrected release forced "
                      "decisions, not just numbers.")
    table(s, ["Finding", "The evidence", "Decision it forced"],
          [["Infiltration was never one class",
            "89,374 of 89,691 \u201cInfiltration\u201d flows — 99.6% — are "
            "NMAP Portscan. True infiltration is 317 flows in 63.2 million.",
            "Q19: Port Scan becomes an 8th class. This is why the literature "
            "calls the class unlearnable — the label conflated reconnaissance "
            "with post-compromise activity."],
           ["FTP brute force never succeeded",
            "All 298,844 FTP-BruteForce flows are marked Attempted; 76% of the "
            "whole Brute Force class is attempts.",
            "Q18: attempted attacks are malicious, flagged via is_attempted. "
            "Calling them benign would delete the class and make the IDS "
            "\u201ccorrect\u201d to ignore an in-progress intrusion."],
           ["Web Attack barely exists",
            "283 successful flows in 63,195,145 — 0.0004%. The old 1,000-row "
            "sample held 83 of them, 29.3% of the entire class.",
            "Old sample discarded. Any Web Attack metric from it was computed "
            "on almost the whole population and could not generalise."],
           ["The schema is not what the documents said",
            "91 columns, not 79. Six columns are new in the corrected release, "
            "and \u201cCWE Flag Count\u201d is a typo for \u201cCWR Flag "
            "Count\u201d (TCP Congestion Window Reduced).",
            "All 78 features were re-mapped and verified; the training schema "
            "is regenerated from the corrected release."]],
          M, 1.94, CW, col_w=[2.35, 4.85, 4.89], row_h=1.07, head_h=0.32,
          size=9.2, head_size=9)

    # -------------------------------------------- 22 SPLIT ---------------
    s = content_slide(prs, nxt(), "Dataset",
                      "How was the data split, and what was dropped?",
                      "Two disjoint samples, one seed, and an explicit "
                      "leakage guard.")
    table(s, ["Sample", "Rows", "Composition", "Purpose"],
          [["train_sample.csv", "250,655",
            "Benign 100,000 · Botnet, DoS, DDoS, Port Scan, Brute Force "
            "30,000 each · Web Attack 378 · Infiltration 277",
            "Train the model and validate the rules held-out"],
           ["demo_sample.csv", "5,000",
            "Benign 4,000 · DoS, DDoS, Brute Force 200 each · Botnet, Port "
            "Scan 150 each · Web Attack 60 · Infiltration 40",
            "The detection run, the console, the demo and the evaluation"]],
          M, 1.94, CW * 0.575, col_w=[1.62, 0.78, 3.72, 1.79], row_h=0.66,
          head_h=0.32, size=9, head_size=8.8)
    tf = tb(s, M, 3.66, CW * 0.575, 3.0)
    rt(tf, [("Why two samples. ", True, INK, False),
            ("The previous single 1,000-row sample was 50% attacks — about 15× "
             "more attack-dense than the reality of 6.08%. Separating the two "
             "lets the demo look alive without the training set inheriting a "
             "false prior. Both are drawn with seed 20260911 and asserted "
             "disjoint.", False, BODY, False)],
       size=10, first=True, after=8, line=1.22)
    rt(tf, [("Columns dropped — 11 fields never reach a detector. ",
             True, INK, False),
            ("Attempted Category, Dst IP, Flow ID, Label, Src IP, Src Port, "
             "Timestamp, alert_id, attack_class, id, is_attempted.",
             False, BAD, True)],
       size=10, after=6, line=1.22)
    para(tf, "Attempted Category is the dangerous one: it states whether an "
             "attack succeeded, so it is a label-leakage vector that did not "
             "exist before the corrected release.",
         size=9.5, color=MUTED, after=8, line=1.2)
    para(tf, "Ground truth is kept out of the database schema entirely. The "
             "evaluation reaches it through exactly one join, on "
             "flow_data.source_record_id, and only after prediction.",
         size=9.5, color=MUTED, after=0, line=1.2)
    tx = M + CW * 0.575 + 0.32
    tw = CW - CW * 0.575 - 0.32
    tf = tb(s, tx, 1.94, tw, 0.3)
    para(tf, "91 DATASET COLUMNS → 82 MODEL FEATURES", size=9.5, color=ACCENT,
         bold=True, first=True, after=0)
    table(s, ["From the corrected release", "Handling"],
          [["6 new columns\n(Fwd/Bwd RST Flags, ICMP Code, ICMP Type, Total TCP "
            "Flow Time, Attempted Category)",
            "Not used by the shipped model, which was trained on the 78-feature "
            "set. A retrained model may adopt them."],
           ["8 renamed features",
            "Pinned by hand in scripts/column_map.json — 70 of 78 match "
            "automatically; 8 do not, and a silent mismatch here is "
            "train/serve skew."],
           ["CWE Flag Count", "Corrected to CWR Flag Count by the release itself."]],
          tx, 2.26, tw, col_w=[2.30, 2.66], row_h=1.08, head_h=0.32, size=9,
          head_size=8.8)

    # ----------------------------------------------------- 23 DIVIDER -----
    divider(prs, nxt(), "A3", "Appendix · A3",
            "The technical analysis, notebook by notebook",
            "Notebooks 04 to 07 carry the results that produced the ranking "
            "combination. One of them reversed the project's central claim.")

    # ---------------------------------------------- 24 NB04 REVERSAL ------
    s = content_slide(prs, nxt(), "Notebook 04 — corrected findings",
                      "What did the analysis reverse?")
    tf = tb(s, M, 1.62, CW, 0.6)
    para(tf, "Notebooks 01 to 03 concluded the detectors were complementary — "
             "that the signature layer caught attacks the model confidently "
             "mislabelled — and designed fusion around that idea. Re-measured "
             "on the corrected data, the conclusion reverses.",
         size=11.5, color=BODY, first=True, after=0, line=1.22)
    table(s, ["1,000 malicious flows — caught by", "Old sample (notebooks 01–03)",
              "Corrected sample"],
          [["ML only", "403", "940"],
           ["SIGNATURE only", "8", "0"],
           ["BOTH (agreement)", "0", "54"],
           ["Missed by both", "89", "6"]],
          M, 2.34, CW * 0.46, col_w=[2.30, 2.24, 1.60], row_h=0.40,
          head_h=0.46, size=10, head_size=9, align_right=(1, 2),
          cell_colors={1: {1: (BAD, True), 2: (BAD, True)},
                       2: {1: (BAD, True), 2: (GOOD, True)}})
    tx = M + CW * 0.46 + 0.38
    tw = CW - CW * 0.46 - 0.38
    tf = tb(s, tx, 2.34, tw, 4.0)
    para(tf, "TWO CLAIMS WITHDRAWN", size=9.5, color=ACCENT, bold=True,
         first=True, after=5)
    para(tf, "\u201cThe detectors are complementary.\u201d  Withdrawn: unique "
             "signature coverage is exactly zero on the corrected data.",
         size=10.5, color=BODY, after=9, line=1.2)
    para(tf, "\u201cThere is zero co-occurrence between the detectors.\u201d  "
             "Withdrawn: agreement occurs 200 times after retuning — which is "
             "what makes the corroborated band real.",
         size=10.5, color=BODY, after=9, line=1.2)
    para(tf, "Signature precision and recall did improve — 0.533 → 0.871 and "
             "0.016 → 0.054 — which is why the layer was kept rather than "
             "discarded.",
         size=10.5, color=BODY, after=9, line=1.2)
    para(tf, "Cause, stated plainly: the new model is far stronger, not the "
             "rules. The old 6-class model was trained on mislabelled data and "
             "called SSH brute force \u201cBenign\u201d at 0.78 confidence. A "
             "strong classifier subsumes weak rules.",
         size=10.5, color=INK, bold=True, after=0, line=1.2)
    rect(s, M, 4.82, CW, 1.76, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.24, 4.94, CW - 0.48, 1.5)
    para(tf, "Why this is the most valuable notebook in the project",
         size=12.5, color=INK, bold=True, first=True, after=6)
    bullets(s, [
        {"t": "It was found before anything was built on top of it. Every claim reversed here would otherwise have been reversed later, after being depended on.", "mark": False},
        {"t": "It is recorded rather than erased: notebooks 01 to 03 still exist, carry supersession banners, and are kept as the research record.", "mark": False},
        {"t": "It also records a process error honestly — the earlier redesign was built on the uncorrected sample while a corrected one was known to be pending. Empirical premises must be settled on final data before a design is committed to.", "mark": False},
    ], M + 0.24, 5.32, CW - 0.48, 1.2, size=10, gap=4)

    # ------------------------------------------- 25 NB04 MODEL ------------
    s = content_slide(prs, nxt(), "Notebook 04 — corrected findings",
                      "Why eight classes, and is the accuracy real?")
    table(s, ["Class", "Precision", "Recall", "F1", "Support"],
          [["Benign", "0.999", "1.000", "1.000", "20,000"],
           ["Botnet", "1.000", "1.000", "1.000", "6,000"],
           ["Brute Force", "1.000", "1.000", "1.000", "6,000"],
           ["DDoS", "1.000", "1.000", "1.000", "6,000"],
           ["DoS", "1.000", "1.000", "1.000", "6,000"],
           ["Infiltration", "0.979", "0.855", "0.913", "55"],
           ["Port Scan", "1.000", "1.000", "1.000", "6,000"],
           ["Web Attack", "1.000", "0.987", "0.993", "76"]],
          M, 1.66, 5.05, col_w=[1.65, 0.85, 0.78, 0.78, 0.99], row_h=0.335,
          head_h=0.32, size=9.3, head_size=9, align_right=(1, 2, 3, 4),
          cell_colors={5: {3: (WARN, True)}})
    tx = M + 5.35
    tw = CW - 5.35
    tf = tb(s, tx, 1.66, tw, 0.4)
    para(tf, "macro F1 0.9882  ·  weighted F1 0.9997", size=13, color=INK,
         bold=True, first=True, after=2)
    para(tf, "82 features · trained on 200,524 rows · validated on 50,131 "
             "held-out rows", size=9.8, color=MUTED, after=12)
    para(tf, "TESTING THE OBVIOUS OBJECTION: IS THIS LEAKAGE?", size=9.5,
         color=ACCENT, bold=True, after=6)
    para(tf, "Every attack class in this testbed targets a fixed port — Botnet "
             "100% on 8080, DoS, DDoS and Web Attack 100% on port 80. A "
             "majority-class-per-port lookup alone reaches about 83% accuracy, "
             "so port reading was the obvious explanation.",
         size=10.2, color=BODY, after=8, line=1.22)
    rt(tf, [("The hypothesis was tested by ablation and rejected. ", True, INK, False),
            ("Removing Dst Port and Protocol together costs only −0.0011 macro "
             "F1: 0.9882 → 0.9870.", False, BODY, False)],
       size=10.2, after=8, line=1.22)
    rt(tf, [("The real cause is less flattering to the dataset than to the "
             "model: ", False, BODY, False),
            ("each attack class was generated by a single tool with fixed "
             "configuration, so every class carries a near-constant flow "
             "fingerprint.", True, BAD, False)],
       size=10.2, after=8, line=1.22)
    rect(s, tx, 5.30, tw, 1.20, fill="FDECEA", line=BAD)
    tf = tb(s, tx + 0.18, 5.42, tw - 0.36, 0.98)
    para(tf, "Read this before quoting any model score", size=10.8, color=BAD,
         bold=True, first=True, after=3)
    para(tf, "The 0.9882 macro F1 is a property of this testbed. It is honest "
             "on this data and will not transfer to real traffic. It must "
             "never be presented as a real-world detection capability.",
         size=9.6, color=BODY, after=0, line=1.18)

    # -------------------------------- STRONG MODEL: THE TWO SPLITS -------
    s = content_slide(prs, nxt(), "Dataset and model",
                      "How do we know the model is not memorising?",
                      "The demo sample never trained it, and the held-out rows never fitted it.")
    kpis(s, [("250,655", "rows in the training sample", ACCENT),
             ("200,524", "rows the model fitted on", GOOD),
             ("50,131", "held-out rows it never saw", GOOD),
             ("82", "features, from 91 columns", ACCENT),
             ("8", "classes it can emit", ACCENT)],
         y=1.94, height=1.10)
    cards(s, [
        ("Split 1 — between the two samples (Q20)",
         "train_sample.csv holds 250,655 rows for training; demo_sample.csv holds 5,000 for the "
         "demo. The two files are disjoint, drawn with seed 20260911, and asserted free of "
         "overlap — so the demo can never be a memorisation test.", ACCENT),
        ("Split 2 — the model's own hold-out",
         "Inside the training sample the model fitted on 200,524 rows and was tested on 50,131 it "
         "had never seen: an 80/20 stratified hold-out. Every per-class figure in this deck comes "
         "from that held-out half.", GOOD),
    ], y=3.22, cols=2, height=1.30, title_size=11.5, body_size=10)
    rect(s, M, 4.62, CW, 2.26, fill=CARD2, line=BORDER)
    tf = tb(s, M + 0.24, 4.74, CW - 0.48, 2.00)
    para(tf, "What the held-out half said", size=12, color=INK, bold=True,
         first=True, after=5)
    bullets(s, [
        {"t": "macro F1 0.9882 and weighted F1 0.9997, measured on 50,131 held-out rows the model never fitted on.", "mark": False},
        {"t": "Six of the eight classes score precision 1.000 and recall 1.000. The two that do not are the two the testbed barely contains: Infiltration 0.913 on 55 held-out rows, and Web Attack 0.993 on 76.", "mark": False},
        {"t": "Eleven fields are refused to the model outright — Label, attack_class, is_attempted, Attempted Category, the addresses and ports, Flow ID and Timestamp — so the answer key cannot reach a detector even by accident.", "mark": False},
        {"t": "Near-perfect scores were treated as an accusation: the port-shortcut hypothesis was tested by ablation and rejected, costing only −0.0011 macro F1 to remove Dst Port and Protocol.", "mark": False},
    ], M + 0.24, 5.06, CW - 0.48, 1.72, size=9.8, gap=5)

    # ------------------------------------------ 26 NB04 RULES ------------
    s = content_slide(prs, nxt(), "Notebook 04 — corrected findings",
                      "Why do only two signature rules survive?")
    table(s, ["Rule", "Target class", "Hits now", "Reaches P ≥ 0.90",
              "Best precision", "Best recall"],
          [["SIG-FTP-BRUTE-FORCE", "Brute Force", "0", "YES", "1.0000", "0.7300"],
           ["SIG-SSH-BRUTE-FORCE", "Brute Force", "55", "YES", "1.0000", "0.2700"],
           ["SIG-DOS-HIGH-RATE-FLOW", "DoS", "0", "no", "0.0000", "0.0000"],
           ["SIG-DDOS-HIGH-RATE-FLOW", "DDoS", "0", "no", "0.3423", "0.3800"],
           ["SIG-BOTNET-BEACON-FLOW", "Botnet", "0", "no", "0.0000", "0.0000"],
           ["SIG-WEB-ATTACK-FLOW", "Web Attack", "5", "no", "0.7838", "0.4833"],
           ["SIG-INFILTRATION-LONG-FLOW", "Infiltration", "3", "no", "0.2500",
            "0.0250"]],
          M, 1.68, CW, col_w=[2.95, 1.55, 1.10, 1.72, 1.95, 1.82], row_h=0.315,
          head_h=0.44, size=9.2, head_size=8.8, align_right=(2, 3, 4, 5),
          cell_colors={0: {1: (GOOD, True), 3: (GOOD, True)},
                       1: {1: (GOOD, True), 3: (GOOD, True)},
                       2: {1: (BAD, False)}, 3: {1: (BAD, False)},
                       4: {1: (BAD, False)}, 5: {1: (BAD, False)},
                       6: {1: (BAD, False)}})
    tf = tb(s, M, 4.42, CW * 0.49, 2.5)
    para(tf, "The two rules we kept, and their tuned thresholds",
         size=11.5, color=INK, bold=True, first=True, after=4)
    para(tf, "FTP brute force: TCP, destination port 21, at least 1 forward "
             "packet, and the rule's other original clauses. SSH brute force: "
             "TCP, port 22, flowPacketsPerSecond ≥ 10.66689. Every clause is "
             "checkable by a human against the flow record.",
         size=10, color=BODY, after=7, line=1.2)
    para(tf, "Five rules are retired, not deleted", size=11.5, color=INK,
         bold=True, after=4)
    para(tf, "Their best achievable precision on the observable features has "
             "hard ceilings: DoS 0.000, Botnet 0.000, DDoS 0.342, Infiltration "
             "0.250, Web Attack 0.784. A low-precision \u201chigh-confidence "
             "oracle\u201d destroys the reason the signature layer exists, so "
             "they stay in the file with enabled: false.",
         size=10, color=BODY, after=7, line=1.2)
    para(tf, "Coverage with the retuned set: ml_only 794 · signature_only 0 · "
             "both 200 · missed by both 6, out of 1,000 malicious flows.",
         size=10, color=BODY, after=0, line=1.2)
    tx = M + CW * 0.51
    tw = CW - CW * 0.51
    rect(s, tx, 4.42, tw, 2.34, fill=CARD, line=BORDER)
    tf = tb(s, tx + 0.22, 4.56, tw - 0.44, 2.1)
    para(tf, "Held-out validation — the overfitting risk, closed",
         size=11.5, color=INK, bold=True, first=True, after=5)
    para(tf, "The tuned thresholds were re-tested on 250,655 rows the rules "
             "had never seen — fifty times the tuning set — through the "
             "production engine. 30,025 hits, the same count first reported.",
         size=9.8, color=BODY, after=7, line=1.2)
    rt(tf, [("Any-attack scoring: ", True, BODY, False),
            ("precision 0.9999, recall 0.1993, with 2 false positives.",
             False, BODY, False)], size=9.8, after=5, line=1.2)
    rt(tf, [("Class-correct scoring: ", True, BODY, False),
            ("precision 0.9992, recall 0.1991 — the 23 differing hits are NMAP "
             "probes of TCP/21 labelled FTP brute force.", False, BODY, False)],
       size=9.8, after=7, line=1.2)
    para(tf, "Verdict: retuning made the signature layer good — precision "
             "0.871 → 1.000, recall 5.4% → 20% — but never complementary. "
             "Unique coverage stayed at zero.",
         size=9.8, color=INK, bold=True, after=0, line=1.2)

    # --------------------------------------- 27 NB04 REPOSITIONING -------
    s = content_slide(prs, nxt(), "Notebook 04 — corrected findings",
                      "What are the signature rules actually for?",
                      "If the signature layer adds no unique detections, its "
                      "justification has to be something other than recall.")
    rect(s, M, 1.94, CW, 0.86, fill=NAVY)
    tf = tb(s, M + 0.24, 2.08, CW - 0.48, 0.6)
    para(tf, "When the signature layer fires, it is right 100% of the time — "
             "and a human can check why.",
         size=14, color=WHITE, bold=True, first=True, after=0)
    table(s, ["Evidence class", "Flows", "What it means",
              "Where the analyst's effort goes"],
          [["corroborated", "200", "A verifiable rule and the model agree",
            "Lowest — fast-track these"],
           ["ml_only", "794", "The model alone; no human-checkable reason",
            "Highest — this is where the human belongs"],
           ["signature_only", "0", "A rule fires and the model disagrees",
            "Does not occur on this data"],
           ["missed by both", "6", "The residual blind spot",
            "Feeds rule development"]],
          M, 3.06, CW, col_w=[1.72, 0.85, 5.05, 4.47], row_h=0.46,
          head_h=0.36, size=9.8, head_size=9, align_right=(1,),
          cell_colors={1: {1: (GOOD, True)}, 3: {1: (BAD, True)}})
    cards(s, [
        ("A checkable claim vs an uncheckable one",
         "\u201cSSH on port 22, above 10.67 packets per second, at least 10 "
         "forward packets, under 5 seconds\u201d can be verified against the "
         "flow record. \u201cBwd Packet Length Min contributed +0.31\u201d "
         "cannot — SHAP explains the model, not the traffic.", ACCENT),
        ("The claim the project can defend",
         "The hybrid does not detect more; it tells the analyst where their "
         "attention is worth spending. 20% of malicious flows carry verifiable "
         "corroboration, and 79% rest on model evidence alone — which is "
         "precisely where human review has the most value.", GOOD),
    ], y=5.10, cols=2, height=1.62, title_size=11.8, body_size=10)

    # ------------------------------------------------ 28 NB07 BAKE-OFF ---
    s = content_slide(prs, nxt(), "Notebook 07 — model bake-off",
                      "Is the shipped model family the right one?",
                      "Four families, identical features, identical folds, "
                      "identical protocol — stratified 5-fold cross-validation "
                      "on the committed 5,000-flow sample.")
    table(s, ["Model family", "macro F1 (mean)", "macro F1 (std)", "Accuracy",
              "Fit seconds"],
          [["Logistic Regression", "0.5133", "0.0462", "0.7866", "2.03"],
           ["Random Forest", "0.9618", "0.0137", "0.9928", "0.62"],
           ["HistGradientBoosting", "0.9687", "0.0106", "0.9946", "2.66"],
           ["XGBoost (incumbent family)", "0.9657", "0.0146", "0.9946", "1.26"]],
          M, 1.94, CW * 0.60, col_w=[2.58, 1.55, 1.42, 1.20, 1.22], row_h=0.42,
          head_h=0.44, size=9.6, head_size=9, align_right=(1, 2, 3, 4),
          cell_colors={0: {1: (BAD, True)}, 3: {1: (GOOD, True)}})
    tf = tb(s, M, 3.60, CW * 0.60, 3.2)
    para(tf, "What the comparison measured", size=11.5, color=INK, bold=True,
         first=True, after=6)
    bullets(s, [
        {"t": "A linear baseline collapses exactly where it matters. Logistic Regression reaches 78.7% accuracy — which hides the rare classes — but only 0.51 macro F1, which exposes them. That number is why macro F1 leads the protocol.", "mark": False},
        {"t": "Tree ensembles win, and gradient boosting leads them. Random Forest 0.962; XGBoost 0.966 ± 0.015; HistGradientBoosting 0.969 ± 0.011 — a statistical tie, both clear of bagging.", "mark": False},
        {"t": "The incumbent family is confirmed by measurement, not habit. XGBoost ties its nearest challenger and carries native TreeSHAP at no extra training cost.", "mark": False},
    ], M, 3.90, CW * 0.60, 2.9, size=10, gap=6)
    tx = M + CW * 0.62
    tw = CW - CW * 0.62
    rect(s, tx, 1.94, tw, 4.86, fill=CARD, line=BORDER)
    tf = tb(s, tx + 0.24, 2.12, tw - 0.48, 4.5)
    para(tf, "Why explainability decided the tie", size=12, color=INK,
         bold=True, first=True, after=6)
    para(tf, "TreeSHAP is not bolted on afterwards. It is native to the "
             "incumbent family and it is what produces the towards-and-away "
             "evidence panels the analyst checks against the flow record.",
         size=10, color=BODY, after=10, line=1.22)
    para(tf, "Had XGBoost lost outright, this notebook would say so. It did "
             "not: the two gradient-boosted families trade places across folds, "
             "which is itself the finding — the schema suits boosted trees.",
         size=10, color=BODY, after=10, line=1.22)
    para(tf, "DECISIONS RECORDED", size=9.5, color=ACCENT, bold=True,
         after=5)
    para(tf, "B1 · Model-family comparison recorded; XGBoost retained on a "
             "measured tie plus the explainability tiebreak.",
         size=9.6, color=BODY, after=5, line=1.18)
    para(tf, "B2 · Macro F1, not accuracy, is the protocol's headline.",
         size=9.6, color=BODY, after=5, line=1.18)
    para(tf, "B3 · Explainability stays a deciding property, not a bonus.",
         size=9.6, color=BODY, after=0, line=1.18)

    # ---------------------------------- WEAKER MODEL / STRESS DATA -------
    s = content_slide(prs, nxt(), "Model and ranking",
                      "How do you test with realistic false positives?",
                      "The strong model's queue was so good that analyst feedback had "
                      "nothing to correct.")
    cards(s, [
        ("Why we built one",
         "The demo queue holds 2 false positives in 996 flagged alerts, and precision is 1.000 at "
         "every cut-off to k = 200. There was nothing to fix, so feedback could only disturb a "
         "perfect ordering.", WARN),
        ("What we did",
         "We built a deliberately weaker detector and ran the real pipeline over it, into its own "
         "database, data/stress.db, so the pristine demo database is untouched.", ACCENT),
        ("Why nothing in it is invented",
         "For every degraded flow the builder copies the complete prediction record of a real "
         "attack flow. Every class, probability, confidence, margin and TreeSHAP attribution is an "
         "unfabricated output of the committed model. Only the flow-to-prediction association is "
         "synthetic, which is what a struggling detector means.", GOOD),
    ], y=1.86, cols=3, height=1.62, title_size=10.8, body_size=9.4)
    table(s, ["", "The strong model — demo.db", "The weakened detector — stress.db"],
          [["Flagged alerts", "996", "1,346"],
           ["False positives", "2", "600"],
           ["Precision among flagged", "0.998", "0.554"],
           ["Precision @ 10", "1.000 — nothing to correct",
            "0.400 — 6 of the top 10 are wrong"],
           ["Precision @ 50 / @ 200", "1.000 / 1.000", "0.780 / 0.730"],
           ["Evidence classes present", "corroborated 200 · model-only 796",
            "model-only 1,146 · corroborated 148 · signature override 52"]],
          M, 3.66, CW, col_w=[3.10, 3.90, 5.09], row_h=0.325, head_h=0.34,
          size=9.2, head_size=9, cell_colors={1: {2: (BAD, True)}, 3: {2: (BAD, True)}})
    rect(s, M, 5.98, CW, 1.00, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 6.10, CW - 0.44, 0.78)
    para(tf, "The ranking now has work to do — and the score still cannot do it alone.",
         size=11, color=INK, bold=True, first=True, after=3)
    para(tf, "The top ten went from perfect to 4-of-10 correct, so dismissals finally have "
             "something to correct. Yet 93.2% of the flagged alerts still sit at exactly 100.0, "
             "because a real attack record carries about 1.0 confidence — so the tie-break ranks "
             "the queue, not the score. It also produced 52 signature-override alerts, the evidence "
             "class with zero instances on real data, so invariant I3 becomes testable. Honest "
             "limit: an injected alert's SHAP panel describes its donor flow, so this file is never "
             "presented as a measurement of the model.",
         size=9.3, color=MUTED, after=0, line=1.16)

    # ----------------------------------------------------- 29 DIVIDER -----
    divider(prs, nxt(), "A4", "Appendix · A4",
            "Ranking, fusion and evaluation",
            "How the detection results became a ranking — the mathematics we "
            "tested, the formula we chose, and what the evaluation measured.")

    # --------------------------------------------- 30 FUSION MATH --------
    s = content_slide(prs, nxt(), "Ranking and fusion",
                      "How do the rules and the model combine?")
    table(s, ["Evidence class", "When it applies", "Score (0–100)",
              "Needs review", "Queue priority"],
          [["corroborated",
            "A rule matched AND the model predicts that rule's class",
            "min(100, max(sig, ml) × 100 + 5)", "when score ≥ 80", "0 — first"],
           ["signature_override",
            "A rule matched, but the model disputes its class",
            "sig × 100", "always", "1"],
           ["ml_only", "No rule matched; the model predicts an attack",
            "ml × 100", "when score ≥ 80", "2"],
           ["none", "Neither detector flagged the flow", "ml × 100", "no",
            "3 — last"]],
          M, 1.72, CW, col_w=[1.72, 4.10, 2.62, 1.52, 1.30], row_h=0.62,
          head_h=0.36, size=9.6, head_size=9, align_right=(4,))
    cards(s, [
        ("Where sig and ml come from",
         "sig is the highest severity score among the matching rules — Low "
         "0.40, Medium 0.60, High 0.80, Critical 0.95 — and 0 when no rule "
         "matched. ml is the model's malicious probability, 1 − P(Benign).",
         ACCENT),
        ("Severity, from one threshold",
         "Score ≥ 80 is Critical, and sets is_critical and the review flag at "
         "the same time, so severity, the flag and the floor can never "
         "disagree. 70–80 High, 40–70 Medium, below 40 Low.", ACCENT),
    ], y=4.44, cols=2, height=1.28, title_size=11.5, body_size=9.8)
    rect(s, M, 5.88, CW, 0.9, fill=CARD2, line=BORDER)
    tf = tb(s, M + 0.22, 6.00, CW - 0.44, 0.68)
    para(tf, "On the demo sample the fusion places 200 flows as corroborated "
             "— every one a real attack — 796 as model-only, 4,004 as nothing "
             "flagged, and 0 as signature_override.",
         size=10.2, color=INK, bold=True, first=True, after=3, line=1.15)
    para(tf, "The queue then orders by band first, then score: corroborated → "
             "signature_override → ml_only → none, then combined_score "
             "descending.",
         size=9.6, color=MUTED, after=0)

    # ------------------------------------------ 31 RANKING MATH ----------
    s = content_slide(prs, nxt(), "Ranking and fusion",
                      "How far should one verdict move an alert?")
    cards(s, [
        ("The question we had to answer",
         "How far should a confirmed alert rise, how far should a false "
         "positive fall — and should the attack type change those distances?",
         ACCENT),
        ("Where the ideas came from",
         "Game ranking systems, because they solve the same problem: "
         "repeatedly updating a rating from human-judged outcomes, without "
         "letting one verdict dominate.", ACCENT),
    ], y=1.62, cols=2, height=0.82, title_size=11.5, body_size=9.8,
       gapy=0.14)
    table(s, ["System", "Mechanism", "The lesson for alert ranking"],
          [["Elo (chess)",
            "Update in proportion to the surprise: R′ = R + K·(S − E), with K "
            "capping one step.",
            "Move in proportion to surprise, and let K set the maximum step."],
           ["Glicko-2",
            "Adds a rating deviation — an explicit measure of uncertainty that "
            "shrinks with evidence.",
            "New patterns move fast; well-judged families settle."],
           ["TrueSkill",
            "Ranks players by the conservative estimate μ − 3σ, not the mean.",
            "Do not promote on thin evidence."],
           ["Ranked ladders (LoL)",
            "Tier and division promotion, with a demotion-protection shield "
            "after promotion.",
            "Hysteresis prevents flapping: falling out of a class must be "
            "harder than entering it."]],
          M, 2.62, CW * 0.50, col_w=[1.42, 2.66, 2.01], row_h=0.85, head_h=0.32,
          size=8.8, head_size=8.6)
    tx = M + CW * 0.52
    tw = CW - CW * 0.52
    tf = tb(s, tx, 2.62, tw, 3.9)
    para(tf, "THE MAPPING, AND THE FOUR CANDIDATES", size=9.5, color=ACCENT,
         bold=True, first=True, after=6)
    for label, body in [
        ("Player", "an alert family"),
        ("Match result", "an analyst verdict — confirm or escalate is a win, "
                         "false positive or benign positive is a loss"),
        ("Expected score", "the judged alert's current score ÷ 100"),
        ("K-factor", "the largest movement one verdict can cause, scaled by "
                     "attack-type severity"),
    ]:
        rt(tf, [(label + " — ", True, INK, False), (body, False, BODY, False)],
           size=9.6, after=4, line=1.18)
    para(tf, "Four candidate formulas, with K = 30 and w = severity ÷ 10:",
         size=9.6, color=BODY, bold=True, before=6, after=5, line=1.18)
    for label, body in [
        ("C0 · fixed step", "+10 confirm, −30 false positive, −15 expected, "
                            "+15 escalate. Today's engine; ignores type."),
        ("C1 · severity-weighted", "up by +K·w, down by −K·(1 − w). Severe "
                                   "types rise fast and fall slowly."),
        ("C2 · Elo-style", "Δ = K_dir·(S − E). Moves by surprise, and is "
                           "self-limiting: confirming a 100-point alert "
                           "moves it 0."),
        ("C3 · Elo + uncertainty", "C2 shrunk by family uncertainty. New "
                                   "families respond strongly."),
    ]:
        rt(tf, [(label + " — ", True, ACCENT, False), (body, False, BODY, False)],
           size=9.4, after=4, line=1.16)
    para(tf, "Movement on top of any formula: M1 moves one queue band at a "
             "time with a demotion shield; M2 sends a confirmed alert straight "
             "to the Tier 2 candidate band.",
         size=9.6, color=INK, bold=True, before=7, after=0, line=1.18)

    # ---------------------------------------------- 32 CHOSEN C1 ---------
    s = content_slide(prs, nxt(), "Ranking and fusion",
                      "Which formula, and how was it chosen?")
    rect(s, M, 1.62, CW, 1.10, fill=NAVY)
    tf = tb(s, M + 0.26, 1.74, CW - 0.52, 0.88)
    para(tf, "CHOSEN:  formula C1, movement M1, behind the agreement gate",
         size=11, color="7FB0F5", bold=True, first=True, after=4)
    rt(tf, [("A confirmed alert rises by  K · w.      A false positive falls "
             "by  K · (1 − w).      K = 30 points,  w = severity ÷ 10.",
             False, WHITE, True)],
       size=15, after=3, line=1.0)
    para(tf, "Severe attack types rise fast and fall slowly; mild types the "
             "reverse. That is exactly what the severity requirement asked "
             "for.",
         size=10, color="C3CEDA", after=0)
    tx = M
    tw = CW * 0.485
    tf = tb(s, tx, 2.92, tw, 0.34)
    para(tf, "WHY C1", size=9.5, color=ACCENT, bold=True, first=True, after=0)
    bullets(s, [
        {"t": "It satisfies the severity requirement: the movement must scale with the attack type's severity.", "mark": False},
        {"t": "It leads the field on mean attack position — 0.0828 against 0.0829 for the Elo forms, about a quarter of one queue position.", "mark": False},
        {"t": "It is the simplest of the candidates that scale by severity.", "mark": False},
        {"t": "We state the honest limit: C1's edge rests as much on the requirement and on simplicity as on measured performance. On this testbed the detector is too good for the formulas to separate.", "mark": False},
    ], tx, 3.26, tw, 2.6, size=10, gap=6)
    tx2 = M + CW * 0.515
    tw2 = CW - CW * 0.515
    tf = tb(s, tx2, 2.92, tw2, 0.34)
    para(tf, "WHY M1 — AND WHY THE GATE MATTERS MORE", size=9.5, color=ACCENT,
         bold=True, first=True, after=0)
    bullets(s, [
        {"t": "Moving straight to the top (M2) lets one confirmation override any history. In one seed, a single wrong confirmation outweighed thirteen correct dismissals and lifted 779 benign flows into Tier 2.", "mark": False},
        {"t": "Mean Tier 2 precision under M2 was 0.74, against 1.00 under M1. Under M1 no single verdict can do this.", "mark": False},
        {"t": "So the movement is M1 — but the experiment's real finding is that the risk was single-verdict family learning, not the formula.", "mark": False},
        {"t": "That is why the agreement gate was adopted before the formula was chosen, and it is why every gated arm showed zero harm.", "mark": False},
    ], tx2, 3.26, tw2, 2.6, size=10, gap=6)
    rect(s, M, 5.92, CW, 0.86, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 6.04, CW - 0.44, 0.64)
    para(tf, "One decision remains open and is the project lead's to make: "
             "whether to add the fine family key — which includes the "
             "destination address — as defence in depth.",
         size=10.2, color=INK, bold=True, first=True, after=3, line=1.15)
    para(tf, "The coarse key promoted a benign alert from rank 639 to rank 1 "
             "in the evaluation. The fine key keeps that false positive and the "
             "genuine attacks apart.",
         size=9.6, color=MUTED, after=0, line=1.15)

    # --------------------------------------- 33 GATE + SEVERITY CHART ----
    s = content_slide(prs, nxt(), "Ranking and fusion",
                      "What stops one analyst moving the whole queue?")
    tf = tb(s, M, 1.62, CW, 0.34)
    para(tf, "THE AGREEMENT GATE — PORTED FROM THE COLLABORATOR'S ENGINE",
         size=9.5, color=ACCENT, bold=True, first=True, after=0)
    table(s, ["Condition", "Value", "Why this way"],
          [["Learning verdicts required", "at least 3",
            "One analyst cannot move a family; three who agree can."],
           ["Agreement required", "0.67",
            "2 of 3 rounds to 0.6667 and fails, so three agreeing verdicts are "
            "the true minimum. 0.80 counts as strong."],
           ["Tie", "no tie",
            "An even split teaches nothing and is withheld."],
           ["Counted by", "category, not direction",
            "As the collaborator's engine does: 2 false positives plus 1 "
            "benign-positive verdict is 0.6667 agreement, and the gate stays "
            "shut."]],
          M, 1.96, CW * 0.545, col_w=[1.85, 1.45, 3.65], row_h=0.66,
          head_h=0.32, size=9, head_size=8.8)
    tx = M + CW * 0.565
    tw = CW - CW * 0.565
    tf = tb(s, tx, 1.96, tw, 0.34)
    para(tf, "THE SEVERITY CHART — CONFIGURATION, NOT CODE", size=9.5,
         color=ACCENT, bold=True, first=True, after=0)
    table(s, ["Attack type", "Severity", "Weight w"],
          [["Port Scan", "3.0", "0.30"],
           ["Brute Force (attempted)", "5.0", "0.50"],
           ["Denial of service", "6.5", "0.65"],
           ["Distributed denial of service", "7.5", "0.75"],
           ["Web application attack", "8.0", "0.80"],
           ["Botnet / command and control", "9.0", "0.90"],
           ["Infiltration / lateral movement", "9.5", "0.95"]],
          tx, 2.30, tw, col_w=[2.62, 1.00, 0.93], row_h=0.315, head_h=0.32,
          size=9.2, head_size=8.8, align_right=(1, 2))
    tf = tb(s, M, 4.62, CW * 0.545, 2.3)
    para(tf, "Effect of the gate, measured", size=11.5, color=INK, bold=True,
         first=True, after=5)
    bullets(s, [
        {"t": "Every gated arm — for every formula, movement and family key — demoted 0 attacks and held Tier 2 at precision 1.00, matching the no-feedback control exactly.", "mark": False},
        {"t": "A counterfactual proves the gate did the work: scoring the ungated arms' own learned families with the gate on brings 59 demoted attacks and 780 misplaced benign alerts to zero, in every seed.", "mark": False},
        {"t": "The limit is recorded rather than hidden: under the gate, feedback barely touches the future queue on this data. Only 4 of 32–34 learned families pass, and three of those have no flows in the future half.", "mark": False},
    ], M, 4.94, CW * 0.545, 2.0, size=9.8, gap=6)
    tf = tb(s, tx, 4.52, tw, 2.4)
    para(tf, "How the numbers are defended", size=11.5, color=INK, bold=True,
         first=True, after=5)
    para(tf, "Each value is anchored on three published scales, so any number "
             "can be defended rather than asserted: Suricata's classtype "
             "priority, the MITRE ATT&CK tactic stage, and the CVSS v3.1 "
             "numeric bands.",
         size=9.8, color=BODY, after=8, line=1.2)
    para(tf, "The chart lives in config/severity-chart.json, is versioned "
             "sev-1, is validated on load — every model class exactly once — "
             "and every detection run and experiment records the chart version "
             "it used.",
         size=9.8, color=BODY, after=8, line=1.2)
    para(tf, "Changing a value is a configuration change, never a code change.",
         size=9.8, color=INK, bold=True, after=0, line=1.2)

    # ---------------------------------------- 34 THREE-ARM EVALUATION ---
    s = content_slide(prs, nxt(), "Evaluation",
                      "What did the evaluation actually measure?")
    tf = tb(s, M, 1.60, CW, 0.34)
    para(tf, "NEWEST RUN  ·  PRE-REGISTRATION s15-preregistration-1  ·  "
             "40 VERDICTS  ·  RE-RUN UNDER v1.31",
         size=9.5, color=ACCENT, bold=True, first=True, after=0)
    table(s, ["", "A — control", "B — treatment", "C — guardrails off"],
          [["Verdicts applied", "0", "40", "40"],
           ["Precision @10 / @50 / @200", "1.000 / 1.000 / 1.000",
            "1.000 / 1.000 / 0.990", "1.000 / 1.000 / 0.990"],
           ["False positives in the top 50", "0", "0", "0"],
           ["Critical floor breaches", "0", "0", "0"],
           ["True positives suppressed", "0", "0", "0"],
           ["Detection metrics", "identical", "identical", "identical"]],
          M, 1.94, CW * 0.545, col_w=[2.72, 1.72, 1.60, 1.76], row_h=0.37,
          head_h=0.40, size=9.2, head_size=8.8, align_right=(1, 2, 3),
          cell_colors={1: {2: (WARN, True), 3: (WARN, True)}})
    tf = tb(s, M, 4.42, CW * 0.545, 2.4)
    para(tf, "The design that makes it trustworthy", size=11.5, color=INK,
         bold=True, first=True, after=5)
    bullets(s, [
        {"t": "The arms are byte copies of one detection database, so the dataset, model, rule set and seed are identical by construction — not by promise.", "mark": False},
        {"t": "The feedback sequence is derived by a rule fixed before any arm ran: an oracle analyst over flagged alerts, at most 5 per family, families of 8 or more.", "mark": False},
        {"t": "An earlier plan version instructed strengthening the sequence until it produced the wanted answer. That instruction was struck out, and pre-registration replaced it.", "mark": False},
    ], M, 4.74, CW * 0.545, 2.2, size=9.6, gap=6)
    tx = M + CW * 0.565
    tw = CW - CW * 0.565
    tf = tb(s, tx, 1.94, tw, 0.3)
    para(tf, "WHAT IT FOUND", size=9.5, color=ACCENT, bold=True, first=True,
         after=0)
    findings = [
        ("Learning works and does not leak",
         "All 8 judged families opened their gate at agreement 1.000. Of 805 "
         "untouched members, 205 were adjusted and 198 true positives "
         "promoted. Of 4,155 alerts outside any judged family, 0 were "
         "adjusted.", GOOD),
        ("It promoted two false positives — one to rank 1",
         "A benign flow classified as a Web Attack rose from rank 639 to rank "
         "1, on verdicts given to other members of its family. The cost of a "
         "coarse family key, measured rather than argued.", BAD),
        ("Precision fell because the control had nowhere to go",
         "The control queue was already perfect: precision 1.000 at every "
         "cut-off to 200, with 2 false positives in 996 flagged alerts. "
         "Feedback could only break that ordering.", BAD),
        ("The score is saturated",
         "975 of 996 flagged alerts sit at exactly 100.0, across only 13 "
         "distinct scores. Ordering inside the top band falls to the tie-break, "
         "not to what the analyst said.", WARN),
        ("Arm C had no power, and the rule is why",
         "The oracle analyst over a near-perfect detector produced no "
         "dismissals, and every guardrail that could bind protects against "
         "downward pressure — so switching them off changed nothing.", WARN),
    ]
    y = 2.28
    for title, body, colour in findings:
        rect(s, tx, y, tw, 0.88, fill=CARD, line=BORDER)
        rect(s, tx, y, 0.05, 0.88, fill=colour)
        t2 = tb(s, tx + 0.18, y + 0.10, tw - 0.32, 0.7)
        para(t2, title, size=10.2, color=INK, bold=True, first=True, after=2)
        para(t2, body, size=8.9, color=BODY, after=0, line=1.15)
        y += 0.95

    # --------------------------------------------- 42 LIMITATIONS --------
    s = content_slide(prs, nxt(), "Limitations",
                      "What is out of scope?",
                      "Stated before they are asked. Each is recorded in the "
                      "repository's deviations register.")
    table(s, ["Limitation", "Why it is so"],
          [["The 0.99 macro F1 is a testbed artefact",
            "Each attack class was generated by a single tool with fixed "
            "configuration, so every class carries a near-constant flow "
            "fingerprint. Honest on this data; it will not transfer to real "
            "traffic."],
           ["Feedback could not improve precision on this sample",
            "The control queue was already at precision 1.000 to k = 200, with "
            "2 false positives among 996 flagged alerts. Feedback had nothing "
            "to correct, so it could only disturb a perfect ordering."],
           ["The coarse family key promoted a benign alert to rank 1",
            "A family is keyed by attack class, port, protocol and rule, so a "
            "false positive resembling confirmed attacks inherits their "
            "promotion. The fine key is proposed as defence in depth."],
           ["The guardrails' protective value is untested by the evaluation",
            "Arm C had no power: the pre-registered sequence contained no "
            "dismissals, and every guardrail that could bind protects against "
            "downward pressure."],
           ["Arms and invariants the evaluation could not exercise",
            "signature_override has zero instances on this data, so invariant "
            "I3 is guaranteed by unit tests rather than by the evaluation."],
           ["Infiltration rests on a very small sample",
            "277 training and 55 held-out examples. Its 0.913 F1 should always "
            "be quoted beside the support count."],
           ["Out of scope by the approved project boundary",
            "Live packet capture, automated response or blocking, host-based "
            "IDS and endpoint agents, a full SIEM or SOAR, and online "
            "retraining of the model from feedback."],
           ["Demo-specific honest limits",
            "Detection is an offline batch, so \u201cCheck again\u201d reports "
            "the latest run; accounts are seeded with committed passwords; "
            "tokens live in sessionStorage; and time-to-verdict reflects "
            "session activity, not operational metrics."],
           ["The stress database is a simulation, and it says so",
            "It re-attributes real attack predictions to benign flows, so an "
            "injected alert's TreeSHAP panel describes its donor flow. Every "
            "number in it is a real model output, but it is not a measurement "
            "of the model \u2014 data/demo.db is."]],
          M, 1.94, CW, col_w=[3.95, 8.14], row_h=0.52, head_h=0.32, size=9.2,
          head_size=9)

    # --------------------------------------------------- 44 Q&A ----------
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, SW, SH, fill=NAVY)
    rect(s, 0, 0, 0.10, SH, fill=ACCENT)
    tf = tb(s, M + 0.35, 2.60, CW - 1.2, 1.0)
    para(tf, "Questions & Discussion", size=40, color=WHITE, bold=True,
         first=True, after=0, line=1.0)
    rect(s, M + 0.35, 3.72, 1.5, 0.05, fill=ACCENT)
    tf = tb(s, M + 0.35, 3.98, CW - 2.4, 1.2)
    para(tf, "Human-in-the-Loop Intrusion Detection Dashboard  ·  "
             "FYP-26-S3-13", size=12.5, color="C3CEDA", first=True, after=10)
    para(tf, "Tan Jing Kai · Zay Yar Naing · Glenn Ang Zhen Xiang · "
             "Isaac Koh Zhi Xian · Thian Wen Jun Gene · Liow Chee Kuang",
         size=10.5, color="8FA3B8", after=10, line=1.2)
    para(tf, "Supervisor: Mr Lim Min Han", size=10.5, color="8FA3B8", after=0)
    footer(s, nxt())

    prs.save(out_path)
    return len(prs.slides._sldIdLst)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "FYP-26-S3-13_HITL-IDS_Presentation.pptx")
    try:
        count = build(out)
    except PermissionError:
        # PowerPoint holds an exclusive lock while the deck is open. Write a new copy beside it
        # rather than losing the build; the caller is told which file is current.
        out = os.path.join(here, "FYP-26-S3-13_HITL-IDS_Presentation_v2.pptx")
        count = build(out)
        print("NOTE: the original deck is locked (open in PowerPoint). "
              "Wrote a new copy instead; close PowerPoint and rebuild to replace it.")
    print(f"OK  {count} slides -> {out}")
