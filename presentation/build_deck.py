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


def node(slide, x, y, w, h, title, sub=None, fill=CARD, line=BORDER,
         color=INK, size=10.2, sub_size=8.4, sub_color=MUTED, accent=None,
         mono_sub=False):
    """One box in a decision tree: a label, optionally a second line under it.

    Drawn from primitives rather than SmartArt so the tree stays editable in
    PowerPoint and rebuilds with the deck.
    """
    rect(slide, x, y, w, h, fill=fill, line=line)
    if accent:
        rect(slide, x, y, w, 0.045, fill=accent)
    tf = tb(slide, x + 0.09, y + (0.13 if sub else 0.10), w - 0.18,
            h - 0.18, anchor=MSO_ANCHOR.TOP if sub else MSO_ANCHOR.MIDDLE)
    para(tf, title, size=size, color=color, bold=True, first=True,
         after=1 if sub else 0, align=PP_ALIGN.CENTER, line=1.05)
    if sub:
        para(tf, sub, size=sub_size, color=sub_color, after=0,
             align=PP_ALIGN.CENTER, line=1.1,
             font=MONO_FONT if mono_sub else BODY_FONT)


def elbow(slide, x1, y1, x2, y2, color=BORDER, t=0.014, label=None,
          label_color=MUTED, label_size=7.6):
    """A right-angled connector from (x1, y1) to (x2, y2): across, then down.

    Two thin rectangles rather than a connector shape, because a rectangle
    keeps its geometry when the slide is edited and never re-routes itself.
    """
    mid = x1 + (x2 - x1) / 2
    rect(slide, min(x1, mid), y1 - t / 2, abs(mid - x1), t, fill=color)
    rect(slide, mid - t / 2, min(y1, y2), t, abs(y2 - y1), fill=color)
    rect(slide, min(mid, x2), y2 - t / 2, abs(x2 - mid), t, fill=color)
    if label:
        tf = tb(slide, mid - 0.34, min(y1, y2) + abs(y2 - y1) / 2 - 0.11,
                0.68, 0.22)
        para(tf, label, size=label_size, color=label_color, bold=True,
             align=PP_ALIGN.CENTER, first=True, after=0)


def ba_row(slide, x, y, w, label, before, after, h=0.34, note=None,
           good=True, size=10.2, label_w=2.55):
    """One before -> after line: what it is, what it was, what it became.

    The deck's unit of evidence for anything feedback moves. Before and after
    sit in the same row, in mono, so the change is read rather than described.
    """
    tf = tb(slide, x, y, label_w, h, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, label, size=size, color=BODY, first=True, after=0)
    tf = tb(slide, x + label_w, y, w - label_w, h, anchor=MSO_ANCHOR.MIDDLE)
    # (text, bold, colour, mono) — rt's tuple order.
    rt(tf, [(before, False, MUTED, True), ("   →   ", False, FAINT, True),
            (after, True, GOOD if good else BAD, True)] +
       ([("    " + note, False, MUTED, False)] if note else []),
       size=size, first=True, after=0)


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



# =============================================================== script =====
#: The spoken script, by slide. Written to be read aloud: short sentences, the
#: numbers spelled the way you would say them, and an explicit handoff wherever
#: the speaker changes. Timings are a guide to pace, not a target to hit.
#:
#: Slides 22+ are the technical FAQ. Their notes say what question the slide
#: answers, so a speaker can find the right one while someone is still asking.
SPEAKER_NOTES = {
    1: """SPEAKER 1  ·  ~30 seconds  ·  OPENING

Good morning. We are group FYP-26-S3-13, and this is our Human-in-the-Loop
Intrusion Detection Dashboard.

The short version of the whole project: two detectors disagree about a piece of
network traffic, an analyst decides who is right, and the system carries that
decision to every alert like it — inside limits that explain themselves.

We will take about fifteen minutes, then show you the console running.""",

    2: """SPEAKER 1  ·  ~20 seconds

Six parts, one speaker each. The problem and the research behind it. What we
built and why it is built this way. The workflow end to end. Where we sit
against the commercial tools. The live demo. Then the team and what comes next.

Everything technical — the dataset, the mathematics, the evaluation — is held in
an appendix at the back. If you want any of it, ask and we will go there.""",

    3: """SPEAKER 1  ·  PART ONE

The problem is not that we cannot detect attacks. It is that we detect far more
than anyone can read.""",

    4: """SPEAKER 1  ·  ~60 seconds

A modern network produces more security events than a team can work through.
Most are low value, and they pile up.

Both kinds of detector have the same blind spot. A signature rule knows a
pattern. A machine-learning model knows a shape in the data. Neither knows
whether this particular event is authorised — whether that scan is your own
scheduled scan, whether that transfer is a backup job.

That judgement is organisational knowledge, and it only exists in the analyst's
head. So the bottleneck has moved: detection is no longer the hard part.
Deciding what deserves a human's attention is.""",

    5: """SPEAKER 1  ·  ~60 seconds

We did not assume that — we read the literature, and it shaped specific design
choices.

Analysts accept explanations, but only when the explanation is evidence they can
check, not the model's internals. Recommending relevant context raised accuracy
twenty-one per cent and cut validation time by a quarter — so we show a short
curated evidence panel, not every field. Uncalibrated confidence numbers are
hard to read under pressure. And in a ten-month study of analysts using AI, they
kept decision authority and used it to make sense of things.

That last one is our whole design: the model advises, the analyst decides.

The two papers at the bottom are cited from metadata only. We say so rather than
imply we read them.""",

    6: """SPEAKER 1  ·  ~50 seconds  ·  HANDOFF

So why not just automate it?

A rule is precise and checkable, but blind to anything new. A model finds what
rules cannot express, but it is opaque. And neither can know your operational
context.

The conclusion we draw is not "add more automation". It is: let the machine
narrow the field, let the human supply the context, and — this is the part most
products skip — make the machine tell the analyst where its own evidence is
weak.

Hand over: “That is the premise. [Speaker 2] will show you what we built on
it.”""",

    7: """SPEAKER 2  ·  PART TWO

Our solution, and the one claim we are willing to defend.""",

    8: """SPEAKER 2  ·  ~75 seconds

Four things happen to every flow.

One: two detectors score it, and fusion turns them into a single alert with one
evidence class, one score, one review flag and one explanation.

Two: we show the analyst why — the rule's clauses, the model's prediction, and
which measurements pushed it towards and away.

Three: the analyst gives a verdict. That moves the alert's operational score
through the guardrails, and the screen states exactly how far it moved and what
stopped it.

Four — this is the part that makes it a product rather than a dashboard — the
verdict teaches the alerts like it, but only once at least three verdicts agree.

Read the line at the bottom out loud: we do not claim the hybrid detects more.
It does not, on this data, and our own analysis says so. What it does is tell the
analyst where their attention is worth spending.""",

    9: """SPEAKER 2  ·  ~60 seconds  ·  HANDOFF

Every row here was forced by a measurement, not a preference.

We do not average the two detectors, because their scores are not the same kind
of thing. We tried: a weight sweep left the ranking identical at every setting —
correlation exactly one. Averaging could only hide the problem.

We retuned the signature rules to precision one point zero, and they still added
no unique detections. So we stopped justifying that layer by coverage and
justified it by trust instead: when a rule fires, a human can check why.

And the ranking formula was chosen by running four candidates, not by arguing for
one.

Hand over: “[Speaker 3] will take you through what actually runs.”""",

    10: """SPEAKER 3  ·  PART THREE

From a recorded flow to a re-ranked queue.""",

    11: """SPEAKER 3  ·  ~75 seconds  ·  HANDOFF

Eight stages, left to right. Flow in; both detectors; a detection score; the
analyst; their feedback; the guardrails; an operational priority; a re-ranked
queue.

Two things to notice.

Every alert carries two scores. The detection score is what the detectors
concluded and never changes. The operational score is the one feedback moves. We
keep both deliberately — the gap between them is the measurable effect of human
judgement, and you will see both columns in the demo.

And every flow becomes an alert, including the four thousand nothing flagged.
They are the bottom of the queue and the denominator of our evaluation. We never
quietly drop the traffic that makes the numbers look harder.

Hand over: “[Speaker 4] will place this against the tools you already know.”""",

    12: """SPEAKER 4  ·  PART FOUR

Where we sit among the tools a real security team already runs.""",

    13: """SPEAKER 4  ·  ~60 seconds

Snort and Suricata are mature signature engines. Their matches are explainable,
which is exactly why we kept a rule layer — but every rule hit arrives with the
same standing, and the triage burden passes downstream.

Darktrace and Vectra bring behavioural machine learning at enterprise scale, and
are correspondingly opaque as a decision surface.

The SIEM consoles — Sentinel, Elastic, Splunk — genuinely have good triage
workflow. We copied from them rather than inventing.

The gap in all of them is the same: nothing shows the analyst how their feedback
is supposed to change what they see next.""",

    14: """SPEAKER 4  ·  ~60 seconds  ·  HANDOFF

This is a Tier 1 tool. The queue is a Tier 1 queue and every verdict is a Tier 1
decision.

Our five verdicts are the industry's own words — True Positive, Benign Positive,
False Positive, Needs investigation, Escalate — and they map one-to-one onto the
closing classifications those consoles already require. An analyst who has used
Sentinel does not need retraining.

Be direct about the last box. No live capture, no automated blocking, no agents,
no online retraining. Nothing on the screen is invented for the demo — no
geolocation, no threat feeds, no asset names. The console says "Recorded flows",
because that is what it has.

Hand over: “[Speaker 5] will show it running.”""",

    15: """SPEAKER 5  ·  PART FIVE

The demo — what is built, and then the thing itself.""",

    16: """SPEAKER 5  ·  ~45 seconds

Quickly, what is actually running: five thousand flows become five thousand
alerts; four hundred and sixty-six Python tests and a hundred and fifty-seven web
tests pass; forty-seven rehearsal checks pass against the demo database; and
there are three real accounts, each signing in to its own role — not one user
flipping a dropdown.

The line at the bottom is worth saying. The browser end-to-end test caught a
database threading bug that three hundred and eighty-one passing Python tests
missed, because only a real browser fires three reads at once. That is why we
test in a browser and not only in unit tests.""",

    17: """SPEAKER 5  ·  THE LIVE DEMO  ·  ~8 minutes

SWITCH TO THE CONSOLE NOW. Follow hitl-ids/docs/demo-script.md — this slide is
the fallback if anything fails, and every number on it came from the rehearsal
script, so you can read them straight off.

The five beats: sign in and show the two score columns · AL-00478, where the
model is confidently wrong and the guardrail catches the correction at seventy
— SAY THE WORDING MISMATCH YOURSELF: the sentence reads “this alert is
Critical” while the badge reads High, because the floor triggers on the score
reaching eighty and the badge is capped by the attack type ·
AL-03086, the attack both detectors missed · the family, where the third
agreeing verdict moves alerts nobody judged · then admin and evaluator.

BEFORE YOU START: the API on port 8000 and the console on 5173 must both be
running, and the database should be freshly rebuilt — delete data/demo.db first,
because the script appends rather than replaces. The strip should read zero
verdicts.

If the demo dies: stay on this slide and narrate it. Every number here is real.""",

    18: """SPEAKER 6  ·  PART SIX

The team, and what happens after today.""",

    19: """SPEAKER 6  ·  ~30 seconds

Six of us, with the roles shown. Supervisor Mr Lim Min Han.

Keep this short — the panel can read names. One sentence on how the work was
divided is enough, then move on.""",

    20: """SPEAKER 6  ·  ~60 seconds

Two things are not built, and we would rather say so than be asked.

The flow exporter that turns real captured traffic into the features we consume.
It enters through the same interface the CSV replay already uses, so nothing
downstream changes — and its exit condition is strict: if the columns do not
reconcile, it stops and reports rather than quietly coercing them.

And the full backend: SQLite becomes PostgreSQL, which the schema was written for
from the start.

The open items at the bottom are recorded, not dropped. The stress test is built
and measured; the run over it is what remains, and it will be reported as its own
labelled experiment — never folded into the headline.""",

    21: """SPEAKER 6  ·  ~45 seconds  ·  CLOSING

Twelve weeks, sequenced by dependency rather than by date: the exporter, then the
backend, with evaluation follow-ups throughout.

The reason the remaining work is additive is that we fixed the schema, the data
contract and the queue order early. The exporter and the backend can be built
without disturbing anything you have just seen.

Close with the claim we opened on: the machine narrows the field, the human
supplies the context, and the system carries that decision to the alerts like it
— inside guardrails that explain themselves.

Then: “Thank you. We are happy to take questions, and we have a technical
appendix if you want to go deeper.”""",
}

#: The appendix is reference. Each note says what its slide answers, so a speaker
#: can jump to the right one while the question is still being asked.
FAQ_NOTES = {
    22: "Divider. Say: everything from here is reference — tell us what you want to see.",
    23: "IF ASKED: what data does the system actually read? 91 columns in, 16 checkable fields for the rules, 82 numbers for the model, 11 refused outright.",
    24: "IF ASKED: what does each detector contribute? The rule's clauses are checkable; the model's explanation is not. Same flow, both answers.",
    25: "IF ASKED: how are the two combined? Four paths, no averaging. Worked on the alert from the previous slide.",
    26: "IF ASKED: where do severity and the review flag come from? One threshold at 80, then the attack type caps the label. This is why a 99.89 alert can read High.",
    27: "IF ASKED: what orders the queue? Severity, then score. Also the honest one: 975 of 996 alerts share a score, so feedback re-ranks the band and the deciders behind it, not the number.",
    28: "IF ASKED: what can an analyst do, and what stops them? The five verdicts and the four guardrails, with the real chain: 99.89 down to 70.",
    29: "IF ASKED: how does one verdict move others? The family key, the three-verdict gate, and the 147 alerts one dismissal moved.",
    30: "IF ASKED: how would we verify that? The moved alerts are named with rank before and after, and the queue can be grouped by family.",
    31: "Divider for the evidence half.",
    32: "IF ASKED: why only 250,000 rows out of 63 million? Because 94% is ordinary traffic — and we used 100% of the two rarest attacks.",
    33: "IF ASKED: what did your analysis change? Three dataset findings, plus the claim we withdrew about the detectors being complementary.",
    34: "IF ASKED: how was the model trained and tested? 80/20, stratified, plus a separate demo pile. Precision, recall and F1 in plain words.",
    35: "IF ASKED: is 0.99 real, or leakage? We deleted the port and protocol and retrained — the score barely moved. The real cause is the testbed.",
    36: "IF ASKED: why only two rules? Because the rest cannot reach usable precision. The layer earns its place on trust, not coverage.",
    37: "IF ASKED: how did you pick the movement formula? Four candidates, a rule written down in advance — and an honest limit on how thin the win is.",
    38: "IF ASKED: what did the evaluation measure, and did it work? Learning works and does not leak. It also promoted a false positive to rank 1, and we report that.",
    39: "IF ASKED: what are the limits? Read them out. Every one is in the repository's deviations register.",
    40: "Closing slide.",
}


def attach_notes(prs):
    """Put the script into the deck itself, so it travels with the file."""
    for i, slide in enumerate(prs.slides, 1):
        text = SPEAKER_NOTES.get(i) or FAQ_NOTES.get(i)
        if text:
            slide.notes_slide.notes_text_frame.text = text


def write_script(path):
    """The same script as a document, for anyone who would rather hold paper."""
    out = ["# FYP-26-S3-13 — presentation script", "",
           "Generated by `build_deck.py`. The same text is in each slide's speaker",
           "notes, so the two cannot drift apart.", "",
           "Slides 1–21 are the presentation. Slides 22–40 are the technical",
           "appendix, used only if asked.", ""]
    for i in sorted(SPEAKER_NOTES):
        out += [f"## Slide {i}", "", SPEAKER_NOTES[i], ""]
    out += ["---", "", "## Appendix — what each slide answers", ""]
    out += [f"- **Slide {i}** — {FAQ_NOTES[i]}" for i in sorted(FAQ_NOTES)]
    out.append("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out))


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
             ("466", "Python tests, 0 skipped", GOOD),
             ("157", "web tests", GOOD),
             ("47/47", "rehearsal checks", GOOD),
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

    # =========================================================================
    # THE TECHNICAL APPENDIX — one flow, followed all the way.
    #
    # Rebuilt 2026-09-18 from 28 slides to 15. The old appendix answered
    # twelve questions on twelve slides and never showed a single flow being
    # processed; this one carries AL-01958 and AL-00478 from raw record to
    # re-ranked queue, and lets the worked example answer the questions.
    #
    # Every figure below is read from data/demo.db, models/training-metrics.json
    # or the committed notebooks. Where a number is a property of this testbed
    # rather than of the method, the slide says so.
    # =========================================================================

    # ------------------------------------------- T1 ONE FLOW ---------------
    s = content_slide(prs, nxt(), "Worked example · 1 of 8",
                      "What does the system actually receive?",
                      "One real record from the demo sample — AL-01958 — "
                      "followed from here to the re-ranked queue.")
    rect(s, M, 1.92, CW, 0.92, fill=NAVY)
    tf = tb(s, M + 0.24, 2.02, CW - 0.48, 0.74)
    para(tf, "AL-01958   18.221.219.4  →  172.31.69.25 : 21 / TCP",
         size=15, color=WHITE, bold=True, first=True, after=3, font=MONO_FONT)
    para(tf, "captured 2018-02-14 · one flow record out of 63,195,145 in "
             "the corrected CSE-CIC-IDS2018 release",
         size=9.4, color="9FC3F0", after=0)
    table(s, ["The record holds", "Count", "Example values", "Who reads it"],
          [["Columns in the source release", "91",
            "Dst Port 21 · Protocol 6 · Flow Duration 3 · "
            "Total Fwd Packet 1", "—"],
           ["Observable fields (rules)", "16",
            "destinationPort 21 · protocol TCP · totalFwdPackets 1 "
            "· flowPacketsPerSecond 666,666.67",
            "The signature engine — every field human-checkable"],
           ["Model features", "82",
            "Fwd Seg Size Min 40 · Flow IAT Min 3 · Bwd Packet "
            "Length Std …", "The XGBoost classifier"],
           ["Refused to both detectors", "11",
            "Label · attack_class · is_attempted · Attempted "
            "Category · src/dst IP · ports · Flow ID · "
            "Timestamp", "Nobody — the leakage guard"]],
          M, 3.02, CW, col_w=[2.55, 0.78, 5.35, 3.41], row_h=0.58,
          head_h=0.32, size=9.3, head_size=9, align_right=(1,), mono_cols=(2,))
    cards(s, [
        ("Two views of one flow, on purpose",
         "The rules read a small, named, checkable view; the model reads the "
         "full vector. Neither sees the answer — the 11 refused fields "
         "include Attempted Category, which states whether an attack "
         "succeeded.", ACCENT),
        ("A 3-microsecond flow with one packet — what brute force is "
         "that?",
         "One probe of a campaign. A single flow is not the attack; the "
         "campaign is the family — see “how does one verdict "
         "move the alerts nobody judged?”. This is why feedback is "
         "applied to families rather than to alerts one at a time.", GOOD),
    ], y=5.58, cols=2, height=1.16, title_size=10.6, body_size=9.3)

    # ------------------------------------------- T2 TWO DETECTORS ----------
    s = content_slide(prs, nxt(), "Worked example · 2 of 8",
                      "What does each detector say about it?",
                      "The same flow, read twice — once by a rule that "
                      "can be checked, once by a model that cannot.")
    rect(s, M, 1.92, CW / 2 - 0.16, 0.42, fill=ACCENT)
    tf = tb(s, M + 0.16, 1.96, CW / 2 - 0.5, 0.34, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, "SIGNATURE ENGINE  ·  every clause checkable", size=10,
         color=WHITE, bold=True, first=True, after=0)
    table(s, ["Clause", "Observed", "Pass"],
          [["protocol == TCP", "TCP", "yes"],
           ["destinationPort == 21", "21", "yes"],
           ["totalFwdPackets >= 1", "1", "yes"],
           ["+ the rule's other original clauses", "—", "yes"]],
          M, 2.40, CW / 2 - 0.16, col_w=[3.05, 1.55, 1.34], row_h=0.32,
          head_h=0.30, size=9.2, head_size=8.6, mono_cols=(0, 1))
    rect(s, M, 3.92, CW / 2 - 0.16, 0.56, fill=CARD, line=BORDER)
    tf = tb(s, M + 0.16, 4.02, CW / 2 - 0.5, 0.42)
    rt(tf, [("SIG-FTP-BRUTE-FORCE", True, INK, True),
            ("  matched  ·  severity Medium  →  ", False, BODY,
             False),
            ("sig = 0.60", True, ACCENT, True)], size=9.6, first=True, after=0)
    x2 = M + CW / 2 + 0.16
    rect(s, x2, 1.92, CW / 2 - 0.16, 0.42, fill=NAVY)
    tf = tb(s, x2 + 0.16, 1.96, CW / 2 - 0.5, 0.34, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, "XGBOOST MODEL  ·  explanation, not proof", size=10,
         color=WHITE, bold=True, first=True, after=0)
    table(s, ["What pushed the model’s answer", "Value", "Push"],
          [["Dst Port", "21.0", "+6.416"],
           ["Fwd Seg Size Min", "40.0", "+0.967"],
           ["Flow IAT Min", "3.0", "+0.670"],
           ["the explanation adds up", "checked", "5,000/5,000"]],
          x2, 2.40, CW / 2 - 0.16, col_w=[3.05, 1.35, 1.54], row_h=0.32,
          head_h=0.30, size=9.2, head_size=8.6, mono_cols=(0, 1, 2),
          align_right=(2,))
    rect(s, x2, 3.92, CW / 2 - 0.16, 0.56, fill=CARD, line=BORDER)
    tf = tb(s, x2 + 0.16, 4.02, CW / 2 - 0.5, 0.42)
    rt(tf, [("Brute Force", True, INK, False),
            ("   99.999921% sure   →   ", False, BODY, True),
            ("not-normal score = 1.000", True, ACCENT, True)],
       size=9.6, first=True, after=0)
    cards(s, [
        ("The claim a human can audit",
         "“TCP, port 21, at least one forward packet” can be checked "
         "against the flow record in seconds. That is what the signature layer "
         "is for — not coverage.", GOOD),
        ("The claim a human cannot audit",
         "“Destination port contributed +6.416” explains the model, "
         "not the "
         "traffic. And note it reads the port — which is why the "
         "port-shortcut hypothesis had to be tested rather than "
         "dismissed; see “is the model’s accuracy real?”.", WARN),
        ("Why we score “how sure it is this is not normal”",
         "Rather than how sure it is of one attack name. Split confidence "
         "is still an attack: 50% denial-of-service plus 45% distributed "
         "denial-of-service is 95% malicious, not 50%.", ACCENT),
    ], y=4.66, cols=3, height=1.32, title_size=10.4, body_size=9.2)

    # ------------------------------------------- T3 BAND DECISION TREE -----
    s = content_slide(prs, nxt(), "Worked example · 3 of 8",
                      "How are the two answers combined?",
                      "Every flow takes exactly one of four paths. No "
                      "weighted sum: scores from different evidence are not "
                      "commensurable.")
    root_x, col2_x, leaf_x = M + 0.10, M + 2.62, M + 5.70
    node(s, root_x, 3.38, 2.20, 0.66, "A rule matched?",
         fill=NAVY, color=WHITE, line=NAVY)
    node(s, col2_x, 2.36, 2.55, 0.62, "Model agrees on the class?",
         fill=CARD2, size=9.6)
    node(s, col2_x, 4.46, 2.55, 0.62, "Model flags an attack?",
         fill=CARD2, size=9.6)
    elbow(s, root_x + 2.20, 3.71, col2_x, 2.67, label="yes")
    elbow(s, root_x + 2.20, 3.71, col2_x, 4.77, label="no")
    leaves = [
        (1.78, "Rule and model agree", "corroborated · 200 flows",
         "min(100, max(sig, ml) × 100 + 5)", GOOD),
        (2.84, "Rule fired, model disagrees",
         "signature_override · 0 flows", "sig × 100  ·  always reviewed",
         WARN),
        (4.10, "Model only, no rule", "ml_only · 796 flows", "ml × 100",
         ACCENT),
        (5.16, "Nothing flagged it", "none · 4,004 flows",
         "ml × 100  ·  bottom of the queue", MUTED),
    ]
    for y, name, count, formula, colour in leaves:
        node(s, leaf_x, y, 4.10, 0.86, name, count + "\n" + formula,
             accent=colour, size=10.4, sub_size=8.4, mono_sub=True)
    elbow(s, col2_x + 2.55, 2.67, leaf_x, 2.21, label="yes")
    elbow(s, col2_x + 2.55, 2.67, leaf_x, 3.27, label="no")
    elbow(s, col2_x + 2.55, 4.77, leaf_x, 4.53, label="yes")
    elbow(s, col2_x + 2.55, 4.77, leaf_x, 5.59, label="no")
    rect(s, M, 6.20, CW, 0.82, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 6.30, CW - 0.44, 0.64)
    rt(tf, [("AL-01958 takes the top path:  ", False, INK, False),
            ("min(100, max(0.60, 1.000) × 100 + 5) = 100.0",
             True, INK, True),
            ("  — clamped by the min, and corroborated because a "
             "precision-1.000 rule and the model name the same class.",
             False, INK, False)], size=10.2, first=True, after=2)
    para(tf, "The second case never happens on this data — 0 flows — so the "
             "rule we never break for it (a disputed rule is frozen and sent "
             "to the administrator, not re-scored) is proven by unit tests.",
         size=8.8, color=MUTED, after=0)

    # ------------------------------------------- T4 SEVERITY TREE ----------
    s = content_slide(prs, nxt(), "Worked example · 4 of 8",
                      "How does a score become a severity and a flag?",
                      "One threshold sets three things at once — then the "
                      "attack class caps the label. This is where a 99.89 "
                      "alert becomes “High”.")
    node(s, M + 0.10, 2.40, 2.35, 0.62, "combined_score", "0 – 100",
         fill=NAVY, color=WHITE, line=NAVY, sub_color="9FC3F0", mono_sub=True)
    node(s, M + 2.95, 2.40, 2.45, 0.62, "score ≥ 80 ?", fill=CARD2)
    elbow(s, M + 2.45, 2.71, M + 2.95, 2.71)
    node(s, M + 5.90, 1.88, 2.95, 0.62, "Treated as critical",
         "must be reviewed · floor 70 applies", accent=CRIT, size=10,
         sub_size=8.2)
    node(s, M + 5.90, 3.06, 2.95, 0.62, "Not treated as critical",
         "reviewed only if a rule disputes it", accent=MUTED, size=10,
         sub_size=8.2)
    elbow(s, M + 5.40, 2.71, M + 5.90, 2.19, label="yes")
    elbow(s, M + 5.40, 2.71, M + 5.90, 3.37, label="no")
    node(s, M + 9.30, 2.40, 2.65, 0.62, "then the class ceiling",
         "caps the displayed label", accent=WARN, size=10, sub_size=8.2)
    elbow(s, M + 8.85, 2.19, M + 9.30, 2.71)
    elbow(s, M + 8.85, 3.37, M + 9.30, 2.71)
    table(s, ["Alert", "Score", "is_critical", "Class ceiling",
              "Label shown", "What binds a verdict"],
          [["AL-01958  Brute Force", "100.00", "true", "Medium (sev 5.0)",
            "Medium", "Critical floor 70 — it keys off is_critical"],
           ["AL-00478  Web Attack", "99.89", "true", "High (sev 8.0)",
            "High", "Critical floor 70 — same, despite the label"],
           ["AL-03086  not flagged", "36.94", "false", "—",
            "Medium", "nothing — no floor applies"]],
          M, 3.86, CW, col_w=[2.75, 1.05, 1.15, 1.95, 1.35, 3.84],
          row_h=0.40, head_h=0.32, size=9.3, head_size=8.8,
          mono_cols=(1, 2), align_right=(1,))
    rect(s, M, 5.64, CW, 1.04, fill=CARD, line=BORDER)
    rect(s, M, 5.64, 0.055, 1.04, fill=WARN)
    tf = tb(s, M + 0.24, 5.74, CW - 0.48, 0.86)
    para(tf, "Expect this question: “why is a High alert protected by a "
             "Critical floor?”", size=11, color=INK, bold=True,
         first=True, after=2)
    para(tf, "Because the floor triggers on is_critical — score ≥ 80 "
             "— while the displayed severity is capped by the attack "
             "class's ceiling from config/severity-chart.json. A Brute Force "
             "alert at 100.0 is protected and still reads “Medium”: "
             "the protection tracks the score, the label tracks the class. "
             "Both are deliberate, and the chart is configuration, not code.",
         size=9.4, color=BODY, after=0, line=1.2)

    # ------------------------------------------- T5 THE QUEUE --------------
    s = content_slide(prs, nxt(), "Worked example · 5 of 8",
                      "What decides where it sits in the queue?",
                      "Severity first, then the operational score. The "
                      "evidence band is a label on the row, not the sort key.")
    rect(s, M, 1.94, CW, 0.62, fill=NAVY)
    tf = tb(s, M + 0.24, 2.00, CW - 0.48, 0.50, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, "ORDER BY   severity DESC,   combined_score DESC,   id ASC",
         size=12.5, color=WHITE, bold=True, first=True, after=0,
         font=MONO_FONT)
    cards(s, [
        ("v1.31 — the band stopped ordering the queue",
         "It used to lead with the evidence band, then the score. Measured "
         "on the demo database, that "
         "put a Tier 2 group that is not severe above everything else — "
         "the whole top 50 was Medium. Severity worst-first is what a Tier 1 "
         "analyst should work down.", ACCENT),
        ("What the band is now",
         "A label, and the tab set. Tier 2 candidacy is still computed and "
         "shown; it no longer decides the order. The old rule that a "
         "disputed rule outranks a more severe finding was retired with "
         "it.", GOOD),
    ], y=2.76, cols=2, height=1.10, title_size=10.6, body_size=9.4)
    kpis(s, [("996", "flagged alerts", ACCENT),
             ("975", "of them at exactly 100.0", BAD),
             ("13", "distinct scores among flagged", BAD),
             ("644", "Tier 2 candidates", WARN),
             ("1,315", "similar-alert families", GOOD)],
         y=4.10, height=1.06, value_size=21)
    rect(s, M, 5.42, CW, 1.26, fill=CARD, line=BORDER)
    rect(s, M, 5.42, 0.055, 1.26, fill=BAD)
    tf = tb(s, M + 0.24, 5.52, CW - 0.48, 1.08)
    para(tf, "The honest consequence, stated before it is found: the score "
             "cannot rank the top band.", size=11, color=INK, bold=True,
         first=True, after=2)
    para(tf, "“how sure it is this is not normal” comes out at "
             "0.99999854 on this testbed, so × 100 rounds to 100.00 and the "
             "agreement bonus is clamped away. 975 of 996 flagged alerts "
             "therefore share "
             "one score. When scores tie, the order falls to the deciders "
             "behind them — what kind of evidence, whether review is "
             "needed, when the traffic was captured — so what feedback "
             "actually re-ranks is the severity and those deciders, not the "
             "number. Spreading the scores out again would change an agreed "
             "design decision, so it is written down as open rather than "
             "quietly changed.", size=9.3, color=BODY, after=0, line=1.2)

    # ------------------------------------------- T6 ONE VERDICT ------------
    s = content_slide(prs, nxt(), "Worked example · 6 of 8",
                      "What happens when the analyst disagrees?",
                      "AL-00478 — a benign flow the model calls a Web "
                      "Attack at 99.89. The analyst is right, and the "
                      "guardrail still binds.")
    steps = [("99.89", "detection score", MUTED),
             ("−30.00", "requested", ACCENT),
             ("floor 70", "bound by", WARN),
             ("−29.89", "applied", ACCENT),
             ("70.00", "final score", GOOD)]
    cw2 = (CW - 0.18 * 4) / 5
    for i, (val, label, colour) in enumerate(steps):
        x = M + i * (cw2 + 0.18)
        rect(s, x, 1.96, cw2, 0.94, fill=CARD, line=BORDER)
        rect(s, x, 1.96, cw2, 0.05, fill=colour)
        tf = tb(s, x + 0.10, 2.12, cw2 - 0.20, 0.72)
        para(tf, val, size=17, color=colour, bold=True, align=PP_ALIGN.CENTER,
             first=True, after=1, line=1.0, font=MONO_FONT)
        para(tf, label, size=8.8, color=MUTED, align=PP_ALIGN.CENTER, after=0)
        if i < 4:
            tf = tb(s, x + cw2 + 0.015, 2.28, 0.15, 0.3)
            para(tf, "›", size=15, color=FAINT, bold=True,
                 align=PP_ALIGN.CENTER, first=True, after=0)
    table(s, ["Verdict (what the analyst clicks)", "API category", "Requests",
              "Forces review", "Teaches its family"],
          [["True Positive", "confirm_true_positive", "+10", "yes",
            "yes — as a confirmation"],
           ["Escalate to Tier 2", "escalate", "+15", "yes",
            "yes — counts as a confirmation (v1.14)"],
           ["Needs investigation", "needs_investigation", "0", "yes",
            "no — teaches nothing"],
           ["Benign Positive", "mark_expected_activity", "−15", "no",
            "only past a stricter gate, off by default"],
           ["False Positive", "mark_false_positive", "−30", "no",
            "yes — as a dismissal"]],
          M, 3.12, CW, col_w=[3.05, 2.65, 1.05, 1.35, 3.99], row_h=0.36,
          head_h=0.32, size=9.3, head_size=8.8, mono_cols=(1, 2),
          align_right=(2,))
    cards(s, [
        ("The guardrails, in order",
         "1 · a disputed rule keeps its score and routes to the "
         "administrator.  2 · one verdict may move a score by at most "
         "−30 or +20.  3 · floors: Critical not below 70, "
         "Infiltration not below 75, and a floor never raises a score.  "
         "4 · the outcome is recorded with its reason.", ACCENT),
        ("What was limited — and what was not",
         "The verdict is recorded in full and the alert is marked a false "
         "positive. What the floor limited is how far one verdict may move a "
         "score the detectors called critical. Verdicts do not stack: a new "
         "verdict supersedes the last, so a score is never more than one "
         "capped step from what detection said.", GOOD),
    ], y=5.28, cols=2, height=1.32, title_size=10.6, body_size=9.3)

    # ------------------------------------------- T7 THE FAMILY -------------
    s = content_slide(prs, nxt(), "Worked example · 7 of 8",
                      "How does one verdict move the alerts nobody judged?",
                      "The product's central claim, as a measurement rather "
                      "than a description.")
    rect(s, M, 1.90, CW, 0.50, fill=NAVY)
    tf = tb(s, M + 0.22, 1.94, CW - 0.44, 0.42, anchor=MSO_ANCHOR.MIDDLE)
    rt(tf, [("WHAT COUNTS AS “SIMILAR”    ", True, "9FC3F0", False),
            ("[\"Brute Force\", 21, \"tcp\", \"SIG-FTP-BRUTE-FORCE\"]",
             True, WHITE, True),
            ("     exact match on every field — no similarity score, no "
             "threshold", False, "9FC3F0", False)],
       size=10.2, first=True, after=0)
    table(s, ["Field", "Must match", "Why it is in the key"],
          [["attack class", "exactly",
            "Two different attacks are not each other's evidence."],
           ["destination port", "exactly",
            "The service under attack. Same class, different port, different "
            "campaign."],
           ["protocol", "exactly",
            "Canonicalised as the collaborator's engine does: 6 → tcp."],
           ["first matched rule", "exactly, or both absent",
            "A checkable reason and a model-only guess are not alike."],
           ["destination address", "only when nothing flagged the flow",
            "Without it one verdict would spread across every benign flow on "
            "that port."]],
          M, 2.52, CW * 0.52, col_w=[1.62, 2.05, 2.62], row_h=0.42,
          head_h=0.30, size=8.9, head_size=8.4)
    x3 = M + CW * 0.545
    tf = tb(s, x3, 2.48, CW * 0.455, 0.3)
    para(tf, "THREE DISMISSALS IN ONE FAMILY — MEASURED", size=9.6,
         color=ACCENT, bold=True, first=True, after=0)
    ba_row(s, x3, 2.80, CW * 0.455, "verdict 1  gate shut", "0 moved",
           "0 moved", note="1 of 3 required", good=False, size=9.4,
           label_w=2.25)
    ba_row(s, x3, 3.16, CW * 0.455, "verdict 2  gate shut", "0 moved",
           "0 moved", note="2 of 3 required", good=False, size=9.4,
           label_w=2.25)
    ba_row(s, x3, 3.52, CW * 0.455, "verdict 3  gate OPENS", "0 moved",
           "147 moved", note="3 of 3 agree", size=9.4, label_w=2.25)
    rect(s, x3, 3.94, CW * 0.455, 1.00, fill=CARD, line=BORDER)
    tf = tb(s, x3 + 0.16, 4.02, CW * 0.455 - 0.32, 0.3)
    para(tf, "Each of those 147, before → after", size=9.4, color=INK,
         bold=True, first=True, after=0)
    ba_row(s, x3 + 0.16, 4.28, CW * 0.455 - 0.32, "score", "100.0", "91.0",
           good=False, size=9.3, label_w=1.15, h=0.22)
    ba_row(s, x3 + 0.16, 4.50, CW * 0.455 - 0.32, "band", "tier2_candidate",
           "corroborated", good=False, size=9.3, label_w=1.15, h=0.22)
    ba_row(s, x3 + 0.16, 4.72, CW * 0.455 - 0.32, "family rank", "27", "31",
           good=False, size=9.3, label_w=1.15, h=0.22)
    cards(s, [
        ("The gate is what makes it safe",
         "3 learning verdicts, no tie, ≥ 0.67 agreement on one category "
         "— counted by category, so 2 false positives plus 1 "
         "benign-positive is 0.6667 and stays shut. One analyst cannot move "
         "a family; three who agree can.", GOOD),
        ("Ungated, one verdict did real damage",
         "In the experiment a single wrong confirmation outweighed thirteen "
         "correct dismissals and lifted 779 benign flows into Tier 2. With the "
         "gate on that failure disappears for every formula tested — 59 "
         "demoted attacks and 780 misplaced alerts both fall to zero.", BAD),
        ("An alert's own verdict wins",
         "A member judged directly is placed by its own verdict, never by its "
         "family. A disputed-rule alert neither teaches nor learns, and never "
         "leaves its band (I3).", ACCENT),
    ], y=5.06, cols=3, height=1.42, title_size=10.4, body_size=9.1)

    # ------------------------------------------- T8 SEEING IT --------------
    s = content_slide(prs, nxt(), "Worked example · 8 of 8",
                      "How would anyone check that claim?",
                      "A count cannot be audited. Since v1.32 the verdict "
                      "names the alerts it moved, and the queue groups by the "
                      "families the learning acts on.")
    cards(s, [
        ("The verdict returns the members, not a number",
         "Each moved alert with its score, band and queue rank before and "
         "after. Rank is the one that carries the claim: a score change nobody "
         "can locate in a 5,000-row queue demonstrates nothing. It is measured "
         "either side of the same transaction.", ACCENT),
        ("The audit entry names them too",
         "SIMILAR_ALERT_LEARNING records the family's state before and after, "
         "the exact count, and the moved members themselves. A score no "
         "analyst ever touched is exactly the change that has to stay "
         "traceable.", GOOD),
        ("Group by Family, in the queue",
         "5,000 alerts fold into 1,315 groups, ordered by each group's "
         "best-ranked member — grouping, not a second ranking. A learned "
         "family reads: gate open · 100% agree · 147 unjudged alerts "
         "carry this.", WARN),
    ], y=2.10, cols=3, height=1.46, title_size=10.6, body_size=9.3)
    table(s, ["Alert", "Score", "Band", "Queue rank", "Judged by anyone?"],
          [["AL-00932", "100.0 → 91.0",
            "tier2_candidate → corroborated", "32 → 35", "no"],
           ["AL-01914", "100.0 → 91.0",
            "tier2_candidate → corroborated", "33 → 36", "no"],
           ["AL-01618", "100.0 → 91.0",
            "tier2_candidate → corroborated", "34 → 37", "no"],
           ["… and 144 more", "100.0 → 91.0",
            "tier2_candidate → corroborated",
            "family best 27 → 31", "no"]],
          M, 3.86, CW, col_w=[1.75, 2.15, 4.35, 2.35, 1.49], row_h=0.38,
          head_h=0.32, size=9.4, head_size=8.8, mono_cols=(0, 1, 2, 3))
    rect(s, M, 5.70, CW, 1.04, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 5.80, CW - 0.44, 0.86)
    para(tf, "Why this example dismisses rather than confirms", size=10.8,
         color=INK, bold=True, first=True, after=2)
    para(tf, "975 of the 996 flagged alerts sit at exactly 100.0, so a "
             "confirming verdict on a flagged family moves the band and leaves "
             "the score where it was. The movement above is visible because it "
             "is downward. Both directions are the same mechanism; only one of "
             "them is visible on this sample — the same crowding of "
             "scores at 100 shown earlier, turning up again where it "
             "matters.",
         size=9.3, color=BODY, after=0, line=1.2)

    # ----------------------------------------------------- A2 DIVIDER -----
    divider(prs, nxt(), "A2", "Appendix · A2",
            "The evidence behind the numbers",
            "Where the data came from, what the analysis reversed, why the "
            "model is trusted, and what the evaluation measured. Each slide "
            "answers one question the worked example raises.")

    # ------------------------------------------- T9 DATASET ----------------
    s = content_slide(prs, nxt(), "Dataset",
                      "Why use 250,000 rows out of 63 million?",
                      "Because the 63 million is not 63 million of anything "
                      "useful \u2014 and for the two rarest attacks we took "
                      "every row that exists.")
    table(s, ["Kind of traffic", "In the whole capture", "We used",
              "Share of it", "Why that many"],
          [["Ordinary traffic", "59,353,486", "104,000", "0.18%",
            "It is 94% of the capture. Use it all and the model learns to "
            "answer \u201cnormal\u201d and score 94%."],
           ["Denial of service", "1,840,877", "30,200", "1.64%",
            "Capped. One tool made them all, so more rows repeat what the "
            "model already has."],
           ["Distributed denial of service", "1,374,399", "30,200", "2.20%",
            "Capped, same reason."],
           ["Password guessing", "393,071", "30,200", "7.68%", "Capped."],
           ["Botnet", "143,183", "30,150", "21.06%", "Capped."],
           ["Port scanning", "89,374", "30,150", "33.73%", "Capped."],
           ["Web attacks", "438", "438", "100%",
            "Everything there is \u2014 438 rows in 63 million."],
           ["Infiltration", "317", "317", "100%",
            "Everything there is \u2014 317 rows in 63 million."]],
          M, 1.96, CW, col_w=[2.45, 1.75, 1.05, 1.15, 5.69], row_h=0.40,
          head_h=0.34, size=9.2, head_size=8.6, mono_cols=(1, 2, 3),
          align_right=(1, 2, 3),
          cell_colors={6: {3: (GOOD, True)}, 7: {3: (GOOD, True)}})
    cards(s, [
        ("Balance matters more than volume",
         "Train on the real proportions and a model that answers "
         "\u201cnormal\u201d to everything scores 94% and is useless. We "
         "measured exactly that: the simplest model reaches 78.7% "
         "\u201caccuracy\u201d and still fails on every rare attack.",
         ACCENT),
        ("The rare attacks set the ceiling, not us",
         "There are 438 web attacks and 317 infiltration flows in the whole "
         "ten-day capture. We used all of them. That is why those two are our "
         "weakest classes \u2014 the data runs out, not the method.", GOOD),
        ("What we did not check, and say so",
         "We capped the common attacks at 30,000 each because they repeat, "
         "but we did not plot a curve to prove 30,000 is the point where more "
         "rows stop helping. A reasoned choice, not a measured one.", WARN),
    ], y=5.30, cols=3, height=1.28, title_size=10.5, body_size=9.2)
    rect(s, M, 6.64, CW, 0.38, fill=CARD, line=BORDER)
    tf = tb(s, M + 0.22, 6.69, CW - 0.44, 0.28, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, "Both samples are drawn with the same fixed seed (20260911) and "
             "checked to share no rows, so the demo can never be the model "
             "repeating something it memorised.", size=9.2, color=BODY,
         first=True, after=0)

    # ------------------------------------------- T10 THE REVERSAL ----------
    s = content_slide(prs, nxt(), "Dataset",
                      "What did the analysis force us to change?",
                      "Three findings from the corrected release changed the "
                      "class list — and one notebook reversed the "
                      "project's central claim.")
    table(s, ["Finding", "The evidence", "What it forced"],
          [["Infiltration was never one class",
            "89,374 of 89,691 “Infiltration” flows — 99.6% "
            "— are NMAP Portscan. True infiltration is 317 flows in "
            "63.2 million.",
            "Q19: Port Scan becomes an 8th class. This is why the literature "
            "calls the class unlearnable."],
           ["FTP brute force never succeeded",
            "All 298,844 FTP-BruteForce flows are marked Attempted; 76% of "
            "the whole Brute Force class is attempts.",
            "Q18: attempted attacks are malicious. Calling them benign would "
            "make the IDS “correct” to ignore an intrusion in "
            "progress."],
           ["Web Attack barely exists",
            "283 successful flows in 63,195,145 — 0.0004%. The old "
            "1,000-row sample held 83 of them: 29.3% of the entire class.",
            "The old sample was discarded. Any Web Attack metric from it was "
            "computed on almost the whole population."],
           ["The detectors are not complementary",
            "Re-measured on corrected data, signature-only coverage is exactly "
            "0. Two claims withdrawn, including “zero co-occurrence” "
            "— agreement occurs 200 times.",
            "Fusion re-specified around evidence classes, and the signature "
            "layer re-justified as trust, not coverage."]],
          M, 2.06, CW, col_w=[2.55, 4.65, 4.89], row_h=0.74, head_h=0.32,
          size=9.1, head_size=8.8)
    cards(s, [
        ("Why this is the most valuable analysis in the project",
         "It was found before anything was built on top of it. Every claim "
         "reversed here would otherwise have been reversed later — after "
         "being depended on. Notebooks 01–03 still exist, carry "
         "supersession banners, and are kept as the research record.", GOOD),
        ("It also records our own process error",
         "The earlier redesign was built on the uncorrected sample while a "
         "corrected one was known to be pending. Empirical premises must be "
         "settled on final data before a design is committed to. That is "
         "written down rather than quietly fixed.", WARN),
    ], y=5.34, cols=2, height=1.26, title_size=10.6, body_size=9.3)

    # ------------------------------------- T10b TRAINED AND TESTED --------
    s = content_slide(prs, nxt(), "Model",
                      "How was the model trained and tested?",
                      "Three piles of flows, one exam, and the two numbers we "
                      "lead with.")
    # The split as three boxes: what the model learned from, what it was
    # examined on, and the pile it never touched at all.
    splits = [("200,524", "80%  of the training sample",
               "The model LEARNS from these \u2014 answers included", GOOD),
              ("50,131", "20%  held out",
               "The EXAM \u2014 never seen during training. Every score we "
               "quote comes from here", ACCENT),
              ("5,000", "a separate pile",
               "The DEMO \u2014 in neither of the other two, so nothing on "
               "screen is memorised", WARN)]
    cw3 = (CW - 0.22 * 2) / 3
    for i, (big, label, body, colour) in enumerate(splits):
        x = M + i * (cw3 + 0.22)
        rect(s, x, 1.94, cw3, 1.06, fill=CARD, line=BORDER)
        rect(s, x, 1.94, cw3, 0.05, fill=colour)
        tf = tb(s, x + 0.16, 2.06, cw3 - 0.32, 0.92)
        rt(tf, [(big + "   ", True, colour, True),
                (label, False, MUTED, False)], size=15, first=True, after=2)
        para(tf, body, size=9.2, color=BODY, after=0, line=1.15)
    tf = tb(s, M, 3.08, CW, 0.30)
    para(tf, "Both splits use seed 20260911. The 80/20 is stratified, so the "
             "rare attack types appear in the same proportion on both sides "
             "\u2014 and the two samples are asserted disjoint, not assumed "
             "to be.", size=9.2, color=MUTED, first=True, after=0)

    cards(s, [
        ("Precision \u2014 \u201chow often is the alarm right?\u201d",
         "Of everything the model called an attack, how much really was one. "
         "Low precision means crying wolf.", ACCENT),
        ("Recall \u2014 \u201chow much did we catch?\u201d",
         "Of the attacks that were actually there, how many the model found. "
         "Low recall means things get through.", ACCENT),
        ("F1 \u2014 one number for both",
         "You can always trade one for the other: alarm at everything, or "
         "never alarm. F1 stops that trade being hidden.", GOOD),
    ], y=3.44, cols=3, height=0.94, title_size=10.4, body_size=9.2)

    head = ["Attack type", "Really there", "Caught", "Missed", "False alarms"]
    widths = [1.95, 1.15, 0.95, 0.95, 1.04]
    table(s, head,
          [["Botnet", "6,000", "6,000", "0", "0"],
           ["Brute Force", "6,000", "6,000", "0", "0"],
           ["DDoS", "6,000", "6,000", "0", "0"],
           ["DoS", "6,000", "5,999", "1", "0"]],
          M, 4.60, CW / 2 - 0.16, col_w=widths, row_h=0.33, head_h=0.30,
          size=9.3, head_size=8.6, mono_cols=(1, 2, 3, 4),
          align_right=(1, 2, 3, 4))
    table(s, head,
          [["Port Scan", "6,000", "5,999", "1", "2"],
           ["Web Attack", "76", "75", "1", "0"],
           ["Infiltration", "55", "47", "8", "1"],
           ["Benign traffic", "20,000", "19,997", "3", "11"]],
          M + CW / 2 + 0.16, 4.60, CW / 2 - 0.16, col_w=widths, row_h=0.33,
          head_h=0.30, size=9.3, head_size=8.6, mono_cols=(1, 2, 3, 4),
          align_right=(1, 2, 3, 4),
          cell_colors={1: {3: (WARN, True)}, 2: {3: (BAD, True)}})

    rect(s, M, 6.04, CW, 0.92, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 6.14, CW - 0.44, 0.74)
    rt(tf, [("Out of 50,131 flows it had never seen, it got ", False, INK,
             False), ("14 wrong", True, INK, False),
            (".     macro F1 ", False, INK, False),
            ("0.9882", True, INK, True),
            ("  \u00b7  weighted F1 ", False, INK, False),
            ("0.9997", True, MUTED, True)], size=11.5, first=True, after=2)
    para(tf, "We lead with macro F1 because it counts every attack type "
             "equally, so Infiltration\u2019s 8 misses out of 55 pull it "
             "down. Weighted F1 is the same results weighted by how common "
             "each class is \u2014 dominated by the 20,000 benign flows, it "
             "looks better and hides the class we are weakest on.",
         size=9.2, color=BODY, after=0, line=1.18)

    # ------------------------------------------- T11 IS THE MODEL REAL -----
    s = content_slide(prs, nxt(), "Model",
                      "Is the model's accuracy real?",
                      "Near-perfect scores were treated as an accusation, not "
                      "a result.")
    table(s, ["Class", "Precision", "Recall", "F1", "Support"],
          [["Benign", "0.999", "1.000", "1.000", "20,000"],
           ["Botnet · Brute Force · DDoS · DoS · Port Scan",
            "1.000", "1.000", "1.000", "6,000 ea"],
           ["Web Attack", "1.000", "0.987", "0.993", "76"],
           ["Infiltration", "0.979", "0.855", "0.913", "55"]],
          M, 2.06, CW * 0.56, col_w=[3.15, 0.95, 0.85, 0.75, 1.07],
          row_h=0.42, head_h=0.32, size=9.2, head_size=8.6,
          align_right=(1, 2, 3, 4), mono_cols=(1, 2, 3, 4))
    tf = tb(s, M, 4.10, CW * 0.56, 0.46)
    rt(tf, [("macro F1 0.9882", True, INK, True),
            ("  ·  weighted F1 0.9997  ·  82 features  ·  "
             "fitted on 200,524 rows  ·  tested on 50,131 never seen",
             False, MUTED, False)], size=8.8, first=True, after=0)
    x4 = M + CW * 0.585
    cards(s, [
        ("The obvious objection: is this port leakage?",
         "Every attack class in this testbed targets a fixed port — "
         "Botnet 100% on 8080, DoS, DDoS and Web Attack 100% on port 80. A "
         "majority-class-per-port lookup alone reaches about 83% accuracy.",
         WARN),
        ("We deleted those columns and retrained",
         "With the port and protocol removed entirely the score barely "
         "moves: 0.9882 → 0.9870. So the model was not leaning on the "
         "port after all.", GOOD),
        ("The real cause, which flatters the model less",
         "Each attack class was generated by a single tool with a fixed "
         "configuration, so every class carries a near-constant flow "
         "fingerprint. The 0.9882 is a property of this testbed: honest here, "
         "and it will not transfer. It must never be quoted as a real-world "
         "detection capability.", BAD),
    ], y=2.06, cols=1, height=1.32, left=x4, width=CW * 0.415,
        title_size=10.4, body_size=9.2)
    table(s, ["Model family", "macro F1", "std", "Accuracy", "Fit s"],
          [["Logistic Regression", "0.5133", "0.0462", "0.7866", "2.03"],
           ["Random Forest", "0.9618", "0.0137", "0.9928", "0.62"],
           ["HistGradientBoosting", "0.9687", "0.0106", "0.9946", "2.66"],
           ["XGBoost  (incumbent)", "0.9657", "0.0146", "0.9946", "1.26"]],
          M, 4.62, CW * 0.56, col_w=[2.45, 1.05, 0.85, 1.05, 1.02],
          row_h=0.36, head_h=0.32, size=9.2, head_size=8.6,
          align_right=(1, 2, 3, 4), mono_cols=(1, 2, 3, 4))
    tf = tb(s, M, 6.30, CW * 0.56, 0.8)
    para(tf, "Four families, identical features, folds and protocol "
             "(stratified 5-fold). A linear baseline collapses exactly where "
             "it matters: 78.7% accuracy hides the rare classes, 0.51 macro F1 "
             "exposes them — which is why macro F1 leads. XGBoost and "
             "HistGB are a statistical tie; the incumbent is kept on the "
             "explainability tiebreak: this family can explain its own "
             "answers without extra machinery.",
         size=8.6, color=MUTED, first=True, after=0, line=1.18)

    # ------------------------------------------- T12 THE RULES -------------
    s = content_slide(prs, nxt(), "Signature layer",
                      "Why do only two rules survive — and what is the "
                      "layer for?",
                      "If the signature layer adds no unique detections, its "
                      "justification has to be something other than recall.")
    table(s, ["Rule", "Target class", "Best precision", "Best recall",
              "Kept?"],
          [["SIG-FTP-BRUTE-FORCE", "Brute Force", "1.0000", "0.7300", "yes"],
           ["SIG-SSH-BRUTE-FORCE", "Brute Force", "1.0000", "0.2700", "yes"],
           ["SIG-WEB-ATTACK-FLOW", "Web Attack", "0.7838", "0.4833",
            "retired"],
           ["SIG-DDOS-HIGH-RATE-FLOW", "DDoS", "0.3423", "0.3800", "retired"],
           ["SIG-INFILTRATION-LONG-FLOW", "Infiltration", "0.2500", "0.0250",
            "retired"],
           ["SIG-DOS-HIGH-RATE · SIG-BOTNET-BEACON", "DoS · Botnet",
            "0.0000", "0.0000", "retired"]],
          M, 2.20, CW * 0.60, col_w=[3.15, 1.55, 1.25, 1.15, 0.95],
          row_h=0.38, head_h=0.32, size=9.1, head_size=8.6,
          mono_cols=(2, 3), align_right=(2, 3))
    x5 = M + CW * 0.625
    cards(s, [
        ("Retired, not deleted",
         "They stay in rules/rule-set-s4b-1.json with enabled: false. A "
         "low-precision “high-confidence oracle” destroys the reason "
         "the layer exists.", MUTED),
        ("Held-out: the overfitting risk, closed",
         "Re-tested on 250,655 rows the rules never saw — 50× the "
         "tuning set. 30,025 hits, precision 0.9999. Say which scoring: "
         "class-correct is 0.9992.", GOOD),
    ], y=2.20, cols=1, height=1.06, left=x5, width=CW * 0.375,
        title_size=10.4, body_size=9.1)
    tf = tb(s, M, 4.56, CW, 0.3)
    para(tf, "COVERAGE AFTER RETUNING — 1,000 MALICIOUS FLOWS   "
             "(pre-retune the split was ML-only 940 · both 54 · "
             "signature-only 0)", size=8.8, color=MUTED, bold=True,
         first=True, after=0)
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
          M, 4.88, CW, col_w=[1.95, 0.85, 4.25, 4.44], row_h=0.36,
          head_h=0.32, size=9.2, head_size=8.8, align_right=(1,))
    rect(s, M, 6.46, CW, 0.62, fill=ACCENT_BG, line=ACCENT)
    tf = tb(s, M + 0.22, 6.54, CW - 0.44, 0.46, anchor=MSO_ANCHOR.MIDDLE)
    rt(tf, [("The claim the project defends: ", True, INK, False),
            ("the hybrid does not detect more — it tells the analyst "
             "where their attention is worth spending. 20% of malicious flows "
             "carry verifiable corroboration; 79% rest on model evidence "
             "alone, which is precisely where human review has the most "
             "value.", False, INK, False)], size=9.8, first=True, after=0)

    # ------------------------------------------- T13 THE FORMULA -----------
    s = content_slide(prs, nxt(), "Ranking",
                      "How far should one verdict move an alert?",
                      "Four candidate formulas, chosen by a rule fixed before "
                      "the results were seen.")
    cards(s, [
        ("C0 · fixed step",
         "+10 confirm, −30 false positive, −15 expected, +15 "
         "escalate. Today's engine; ignores the attack type.", MUTED),
        ("C1 · severity-weighted — CHOSEN",
         "Up by +K·w, down by −K·(1−w), K = 30 and "
         "w = severity ÷ 10. Severe types rise fast and fall slowly.",
         GOOD),
        ("C2 · Elo-style",
         "Δ = K_dir·(S − E). Moves by surprise and is "
         "self-limiting: confirming a 100-point alert moves it 0.", MUTED),
        ("C3 · Elo + uncertainty",
         "C2 shrunk by family uncertainty, after Glicko-2. New families "
         "respond strongly, settled ones barely move.", MUTED),
    ], y=1.98, cols=4, height=1.24, title_size=10.2, body_size=9.0)
    cards(s, [
        ("Why C1",
         "It is the simplest candidate that satisfies the severity "
         "requirement (Q27), and it leads on mean attack position — "
         "0.0828 against 0.0829 for the Elo forms.", ACCENT),
        ("The honest limit on that win",
         "0.0001 is about a quarter of one queue position, and the "
         "no-feedback control is 0.0829. C0 would rank first on raw "
         "performance and is ruled out only by the requirement we set in "
         "advance. The honest claim is “chosen by a rule we wrote down "
         "beforehand”, never “measured best”.", BAD),
        ("Why M1 — and why the gate matters more",
         "M2 sends a confirmed alert straight to Tier 2, so one confirmation "
         "can override any history: Tier 2 precision 0.74 under M2 against "
         "1.00 under M1. The real finding is that the risk was "
         "single-verdict learning, not the formula.", WARN),
    ], y=3.44, cols=3, height=1.60, title_size=10.5, body_size=9.2)
    table(s, ["Attack type", "Severity", "w", "Attack type", "Severity", "w"],
          [["Port Scan", "3.0", "0.30", "Web application attack", "8.0",
            "0.80"],
           ["Brute Force (attempted)", "5.0", "0.50", "Botnet / C2", "9.0",
            "0.90"],
           ["Denial of service", "6.5", "0.65", "Infiltration / lateral",
            "9.5", "0.95"],
           ["Distributed denial of service", "7.5", "0.75", "", "", ""]],
          M, 5.18, CW, col_w=[3.05, 1.05, 0.85, 3.05, 1.05, 3.04],
          row_h=0.34, head_h=0.32, size=9.2, head_size=8.6,
          mono_cols=(1, 2, 4, 5), align_right=(1, 2, 4, 5))
    tf = tb(s, M, 6.68, CW, 0.5)
    para(tf, "The chart is configuration, not code: config/severity-chart.json, "
             "versioned sev-1, validated on load, and every run records the "
             "version it used. Each value is anchored on three published "
             "scales — Suricata classtype priority, the MITRE ATT&CK "
             "tactic stage, and the CVSS v3.1 bands — so any number can "
             "be defended rather than asserted.",
         size=8.7, color=MUTED, first=True, after=0, line=1.18)

    # ------------------------------------------- T14 EVALUATION ------------
    s = content_slide(prs, nxt(), "Evaluation",
                      "What did the evaluation actually measure?",
                      "Three runs of the same database — one left alone, "
                      "two given the same 40 analyst verdicts, chosen by a "
                      "rule written down before we ran anything.")
    table(s, ["", "A — control", "B — treatment",
              "C — guardrails off"],
          [["Verdicts applied", "0", "40", "40"],
           ["Precision @10 / @50 / @200", "1.000 / 1.000 / 1.000",
            "1.000 / 1.000 / 0.990", "1.000 / 1.000 / 0.990"],
           ["False positives in the top 50", "0", "0", "0"],
           ["Critical floor breaches", "0", "0", "0"],
           ["True positives suppressed", "0", "0", "0"],
           ["Detection metrics", "identical", "identical", "identical"]],
          M, 2.06, CW, col_w=[3.55, 2.85, 2.85, 2.84], row_h=0.36,
          head_h=0.32, size=9.4, head_size=8.8, mono_cols=(1, 2, 3))
    cards(s, [
        ("What makes it trustworthy",
         "The arms are byte copies of one database, so dataset, model, rules "
         "and seed are identical by construction. The sequence comes from a "
         "rule written down before any run — an earlier plan version said "
         "to strengthen it until it gave the wanted answer, and that was "
         "struck out.", GOOD),
        ("Learning works and does not leak",
         "All 8 judged families opened at agreement 1.000. Of 805 untouched "
         "members, 205 were adjusted and 198 true positives promoted. Of the "
         "4,155 alerts outside any judged family, 0 were adjusted.", ACCENT),
        ("And it promoted a false positive to rank 1",
         "A benign flow classified as a Web Attack rose from rank 639 to rank "
         "1, on verdicts given to other members of its family. That is the "
         "measured cost of the coarse family key — reported, not argued "
         "away. The fine key is proposed as defence in depth.", BAD),
    ], y=4.52, cols=3, height=1.54, title_size=10.5, body_size=9.2)
    rect(s, M, 6.24, CW, 0.80, fill=CARD, line=BORDER)
    rect(s, M, 6.24, 0.055, 0.80, fill=WARN)
    tf = tb(s, M + 0.24, 6.32, CW - 0.48, 0.64)
    para(tf, "Why precision fell — and why arm C proved nothing",
         size=10.4, color=INK, bold=True, first=True, after=2)
    para(tf, "The control queue was already perfect — precision 1.000 to "
             "k = 200, 2 false positives in 996 flagged alerts — so "
             "feedback could only disturb it. And the oracle analyst produced "
             "no dismissals, while every guardrail that can bind protects "
             "against downward pressure, so arm C changed nothing. Both are "
             "limits of the sample, reported as measured.",
         size=9.1, color=BODY, after=0, line=1.18)

    # ------------------------------------------- T15 LIMITATIONS -----------
    s = content_slide(prs, nxt(), "Limitations",
                      "What is out of scope, and what do we not claim?",
                      "Stated before they are asked. Each is recorded in the "
                      "repository's deviations register.")
    table(s, ["Limitation", "Why it is so"],
          [["The 0.9882 macro F1 is a testbed artefact",
            "Each attack class was generated by a single tool with fixed "
            "configuration, so every class carries a near-constant flow "
            "fingerprint. Honest on this data; it will not transfer."],
           ["Feedback could not improve precision on this sample",
            "The control queue was already at precision 1.000 to k = 200. "
            "Feedback had nothing to correct, so it could only disturb a "
            "perfect ordering."],
           ["The coarse family key promoted a benign alert to rank 1",
            "A family is keyed by class, port, protocol and rule, so a false "
            "positive resembling confirmed attacks inherits their promotion."],
           ["The guardrails' protective value is untested by the evaluation",
            "The third run had nothing to prove: the fixed sequence of "
            "verdicts contained no "
            "dismissals, and every guardrail that can bind protects against "
            "downward pressure."],
           ["The frozen-rule protection is proven by unit tests, not by "
            "the evaluation",
            "The “rule fired, model disagrees” case has zero "
            "instances on this data, so the evaluation could not exercise "
            "it."],
           ["The guardrail sentence says “Critical” on a High badge",
            "The Critical floor triggers on the detection score reaching 80; "
            "the displayed severity is capped by the attack class’s ceiling "
            "(v1.29). Both are deliberate, but the sentence asserts the badge "
            "rather than the score. Wording only — logged, not yet fixed."],
           ["Infiltration rests on a very small sample",
            "277 training and 55 held-out examples. Its 0.913 F1 should always "
            "be quoted beside the support count."],
           ["Out of scope by the approved project boundary",
            "Live packet capture, automated response or blocking, host-based "
            "IDS and endpoint agents, a full SIEM or SOAR, and online "
            "retraining from feedback."],
           ["Demo-specific honest limits",
            "Detection is an offline batch, so “Check again” reports "
            "the latest run; accounts are seeded with committed passwords; "
            "tokens live in sessionStorage; time-to-verdict reflects session "
            "activity, not operational metrics."]],
          M, 2.06, CW, col_w=[4.05, 8.04], row_h=0.54, head_h=0.32, size=9.2,
          head_size=8.8)

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

    attach_notes(prs)
    write_script(os.path.join(os.path.dirname(os.path.abspath(out_path)),
                              "speaker-script.md"))
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
