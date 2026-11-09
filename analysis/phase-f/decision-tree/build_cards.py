#!/usr/bin/env python3
"""Render one data-card PNG per trace step into cards/."""

import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE = os.path.join(HERE, "trace", "trace.json")
OUT = os.path.join(HERE, "cards")

W = 900
PAD = 26
FS = 15
LH = 20
VAL_X = PAD + 148
FONT_DIR = "C:/Windows/Fonts"


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


F_LABEL = _font("arial.ttf", FS)
F_VALUE = _font("consola.ttf", FS)
F_CHANGE = _font("arialbd.ttf", FS)
F_TITLE = _font("arialbd.ttf", 16)
F_HEAD = _font("arialbd.ttf", 21)
F_SUB = _font("arial.ttf", 14)
F_TINY = _font("arial.ttf", 12)

INK = (27, 27, 27)
LABEL_C = (90, 96, 102)
MUTED = (134, 142, 150)
ORANGE = (232, 89, 12)
RULE = (213, 218, 224)


def width(text, font):
    return font.getlength(text)


def wrap_text(text, font, maxw):
    """Wrap by pixel width on word boundaries; never drops characters."""
    out = []
    for para in str(text).split("\n"):
        words = para.split(" ")
        cur = ""
        for w in words:
            trial = w if not cur else cur + " " + w
            if width(trial, font) <= maxw or not cur:
                if width(trial, font) > maxw and not cur:
                    # single token longer than the line: hard-split it
                    piece = ""
                    for ch in w:
                        if width(piece + ch, font) > maxw and piece:
                            out.append(piece)
                            piece = ch
                        else:
                            piece += ch
                    cur = piece
                else:
                    cur = trial
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out or [""]


def show(v):
    if v is None:
        return "(none)"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return ("%.4f" % v).rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return str(v)


def same_text(a, b):
    return a == b


def stack(items):
    """Turn abstract items into draw ops plus total height."""
    ops = []
    y = PAD
    for it in items:
        kind = it[0]
        if kind == "head":
            ops.append((PAD, y, it[1], F_HEAD, INK))
            y += 30
        elif kind == "sub":
            ops.append((PAD, y, it[1], F_SUB, MUTED))
            y += 22
        elif kind == "section":
            y += 12
            ops.append((PAD, y, it[1].upper(), F_TITLE, INK))
            y += 24
            ops.append(("rule", PAD, y, W - PAD))
            y += 9
        elif kind == "note":
            # notes sit in the value column, so a reason lines up under the field it belongs to
            for ln in wrap_text(it[1], F_VALUE, W - PAD - VAL_X):
                ops.append((VAL_X, y, ln, F_VALUE, it[2] if len(it) > 2 else INK))
                y += LH
            y += 1
        elif kind == "raw":
            ops.append((PAD + 8, y, it[1], F_TINY, MUTED))
            y += 17
        else:  # row
            label, before, after = it[1], it[2], it[3]
            changed = not same_text(before, after)
            text = f"{before} -> {after}" if changed else after
            font = F_CHANGE if changed else F_VALUE
            color = ORANGE if changed else INK
            ops.append((PAD, y, label, F_LABEL, LABEL_C))
            avail = W - PAD - VAL_X
            for i, ln in enumerate(wrap_text(text, font, avail)):
                ops.append((VAL_X, y, ln, font, color))
                y += LH
            y += 3
    return ops, y + PAD - 6


def draw_card(step, path):
    items = build_items(step)
    ops, height = stack(items)
    img = Image.new("RGB", (W, max(height, 120)), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W - 1, max(height, 120) - 1], outline=RULE, width=1)
    for op in ops:
        if op[0] == "rule":
            d.line([(op[1], op[2]), (op[3], op[2])], fill=RULE, width=1)
        else:
            x, yy, text, font, color = op
            d.text((x, yy), text, font=font, fill=color)
    img.save(path)
    return img.size


def get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def raw_fmt(r):
    if not isinstance(r, dict):
        return "(none)"
    return show(r.get("recordId"))


def flow_fmt(r):
    if not isinstance(r, dict):
        return "(none)"
    return "%s:%s -> %s:%s %s" % (
        r.get("srcIp"), r.get("srcPort"), r.get("dstIp"), r.get("dstPort"),
        r.get("protocol"),
    )


def dur_fmt(v):
    return "(none)" if v is None else "%.6fs" % float(v)


def fb_fmt(f):
    if not isinstance(f, dict):
        return "(none)"
    orig = float(f.get("original_score") or 0)
    act = float(f.get("actual_delta") or 0)
    return "%s: %s -> %s (requested %s, applied %s, %s)" % (
        f.get("category"), show(orig), show(orig + act),
        show(f.get("requested_delta")), show(act),
        f.get("guardrail_action"),
    )


def rule_map(det):
    out = {}
    for r in (det or {}).get("signatureRules") or []:
        out[r.get("rule")] = r
    return out


def build_items(step):
    a = step.get("after") or {}
    b = step.get("before") or {}
    items = [
        ("head", "%s   %s" % (step.get("id"), step.get("label"))),
        ("sub", "%s | %s" % (step.get("actor"), step.get("action"))),
    ]

    ra, rb = a.get("raw"), b.get("raw")
    if ra:
        items.append(("section", "Raw flow"))
        items.append(("row", "record", show(b.get("recordId")) if b else "(none)", show(a.get("recordId"))))
        items.append(("row", "flow", flow_fmt(rb), flow_fmt(ra)))
        items.append(("row", "packets", show(get(rb, "packets")), show(get(ra, "packets"))))
        items.append(("row", "bytes", show(get(rb, "bytes")), show(get(ra, "bytes"))))
        items.append(("row", "duration", dur_fmt(get(rb, "duration")),
                      dur_fmt(get(ra, "duration"))))

    da, db = a.get("detection"), b.get("detection")
    if da:
        items.append(("section", "Detection"))
        rma, rmb = rule_map(da), rule_map(db)
        for rid, rule in rma.items():
            old = rmb.get(rid) or {}
            items.append(("row", "rule", old.get("rule") or "(none)", rid))
            items.append(("row", "name", old.get("name") or "(none)",
                          rule.get("name") or "(none)"))
            ca = rule.get("conditions") or []
            cb = old.get("conditions") or []
            for i, cond in enumerate(ca):
                if i < len(cb) and cb[i] != cond:
                    items.append(("note", "%s -> %s" % (cb[i], cond), ORANGE))
                else:
                    items.append(("note", cond, INK))
        ml_a = "%s %s" % (da.get("mlClass"), show(round(float(da.get("mlProbability") or 0), 4)))
        ml_b = "%s %s" % (db.get("mlClass"), show(round(float(db.get("mlProbability") or 0), 4))) if db else None
        items.append(("row", "model", ml_b or "(none)", ml_a))
        # Detection facts are fixed after detection (migration 23). The score a verdict moves is shown under
        # "Verdict and score"; here only the detection-time score, which never changes.
        for key in ("evidenceClass", "detectionScore", "isCritical"):
            items.append(("row", key, show(get(db, key)), show(get(da, key))))

    ga, gb = a.get("group"), b.get("group")
    if ga:
        items.append(("section", "Group"))
        items.append(("row", "members", show(get(gb, "members")), show(get(ga, "members"))))
        items.append(("row", "key", show(get(gb, "key")), show(get(ga, "key"))))
        win_a = "%s -> %s" % (ga.get("firstSeen"), ga.get("lastSeen"))
        win_b = "%s -> %s" % (gb.get("firstSeen"), gb.get("lastSeen")) if gb else None
        items.append(("row", "window", win_b or "(none)", win_a))

    roa, rob = a.get("routing"), b.get("routing")
    if roa:
        items.append(("section", "Routing"))
        for key in ("route", "stage", "decisionSource", "priority", "band", "tier2Recommended"):
            items.append(("row", key, show(get(rob, key)), show(get(roa, key))))
        for i, why in enumerate(roa.get("reasons") or []):
            old = (rob.get("reasons") or [None] * 99)[i] if rob else None
            if old == why:
                items.append(("note", why))
            else:
                items.append(("note", "%s -> %s" % (old or "(none)", why), ORANGE))
        items.append(("row", "reviewReason", show(get(rob, "reviewReason")),
                      show(get(roa, "reviewReason"))))

    wa, wb = a.get("work"), b.get("work")
    if wa:
        items.append(("section", "Tier 1 work"))
        for key in ("status", "owner", "finishedBy"):
            items.append(("row", key, show(get(wb, key)), show(get(wa, key))))

    if "verdicts" in a or (a.get("legacy") or {}).get("feedback"):
        items.append(("section", "Verdict and score"))
        items.append(("row", "verdicts", show(b.get("verdicts")), show(a.get("verdicts"))))
        la, lb = a.get("legacy") or {}, b.get("legacy") or {}
        items.append(("row", "current score", show(lb.get("combinedScore")),
                      show(la.get("combinedScore"))))
        items.append(("row", "current severity", show(lb.get("severity")), show(la.get("severity"))))
        def qscore(s):
            # DERIVED, not stored: apps/api/operational_queue.py:43 queue score =
            # clamp(routing priority + (current score - detection score), 0, 100)
            try:
                v = float(s["routing"]["priority"]) + float(s["legacy"]["combinedScore"]) - float(s["detection"]["detectionScore"])
                return show(round(max(0.0, min(100.0, v)), 2))
            except (KeyError, TypeError, ValueError):
                return "(n/a)"
        items.append(("row", "queue score (derived)", qscore(b), qscore(a)))
        fbs_a = la.get("feedback") or []
        fbs_b = lb.get("feedback") or []
        for i, f in enumerate(fbs_a):
            old = fbs_b[i] if i < len(fbs_b) else None
            items.append(("row", "feedback", fb_fmt(old), fb_fmt(f)) if old
                         else ("row", "feedback", "(none)", fb_fmt(f)))

    ca, cb = a.get("case"), b.get("case")
    if ca:
        items.append(("section", "Tier 2 case"))
        items.append(("row", "status", show(get(cb, "status")), show(get(ca, "status"))))
        items.append(("row", "decision_source", show(get(cb, "decision_source")),
                      show(get(ca, "decision_source"))))
        items.append(("row", "created_by", show(get(cb, "created_by_actor_id")),
                      show(get(ca, "created_by_actor_id"))))
        items.append(("row", "revision", show(get(cb, "revision")),
                      show(get(ca, "revision"))))

    gta, gtb = a.get("groundTruth"), b.get("groundTruth")
    if gta:
        items.append(("section", "Ground truth (reader only)"))
        for label, cnt in gta.items():
            items.append(("row", label,
                          show((gtb or {}).get(label)), show(cnt)))
    return items


def main():
    with open(TRACE, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    steps = [s for p in data.get("paths") or [] for s in p.get("steps") or []]
    os.makedirs(OUT, exist_ok=True)
    made = []
    for step in steps:
        path = os.path.join(OUT, "%s.png" % step.get("id"))
        size = draw_card(step, path)
        made.append((step.get("id"), size))
    print("cards: %d" % len(made))
    for sid, size in made:
        print("  %-3s %dx%d" % (sid, size[0], size[1]))


if __name__ == "__main__":
    main()
