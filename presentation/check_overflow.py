#!/usr/bin/env python3
"""Estimate text overflow in a .pptx without rendering it.

For every text frame and every table cell, estimate the wrapped line count
from the box width and font size, then compare the required height with the
available height. Reports the worst offenders per slide.

This is a proxy for a visual render: it catches gross overflow (text far
larger than its box) but not subtle crowding.
"""
from __future__ import annotations

import math
import sys

from pptx import Presentation
from pptx.util import Emu

EMU_IN = 914400.0
# Average glyph width as a fraction of the font size, per font family.
WIDTH_FACTOR = {"Consolas": 0.55, "Segoe UI": 0.485, "default": 0.50}
LINE_FACTOR = 1.22          # typical line box height / font size
MIN_LINE = 11.0             # points


def width_factor(font_name: str | None) -> float:
    if not font_name:
        return WIDTH_FACTOR["default"]
    for key, val in WIDTH_FACTOR.items():
        if key.lower() in font_name.lower():
            return val
    return WIDTH_FACTOR["default"]


def frame_need(tf, avail_w_pt, avail_h_pt, label):
    """Return (needed_pt, available_pt, worst_text) for one text frame."""
    needed = 0.0
    worst = ""
    ml = (tf.margin_left or 0) / EMU_IN * 72
    mr = (tf.margin_right or 0) / EMU_IN * 72
    mt = (tf.margin_top or 0) / EMU_IN * 72
    mb = (tf.margin_bottom or 0) / EMU_IN * 72
    usable_w = max(avail_w_pt - ml - mr, 12)
    for p in tf.paragraphs:
        text = "".join(r.text for r in p.runs)
        sizes = [r.font.size.pt for r in p.runs if r.font.size]
        size = max(sizes) if sizes else 18.0
        mono = any(r.font.name and "consol" in r.font.name.lower()
                   for r in p.runs)
        factor = 0.55 if mono else 0.485
        ls = p.line_spacing if isinstance(p.line_spacing, float) else 1.0
        sb = (p.space_before.pt if p.space_before else 0.0)
        sa = (p.space_after.pt if p.space_after else 0.0)
        cpl = max(usable_w / (factor * size), 4.0)
        lines = 0
        for chunk in (text.split("\n") if text else [""]):
            lines += max(1, math.ceil(len(chunk) / cpl))
        line_h = max(size * LINE_FACTOR * (ls if ls else 1.0), MIN_LINE)
        needed += lines * line_h + sb + sa
        if len(text) > len(worst):
            worst = text
    needed += mt + mb
    return needed, avail_h_pt, worst


def check(path: str) -> int:
    prs = Presentation(path)
    problems = []
    for idx, slide in enumerate(prs.slides, start=1):
        for shape in slide.shapes:
            if shape.has_table:
                tbl = shape.table
                for r, row in enumerate(tbl.rows):
                    row_h = row.height / EMU_IN * 72
                    for c, cell in enumerate(row.cells):
                        col_w = tbl.columns[c].width / EMU_IN * 72
                        need, avail, worst = frame_need(
                            cell.text_frame, col_w, row_h, "cell")
                        if need > avail + 1.0:
                            problems.append(
                                (idx, f"table r{r}c{c}", need, avail, worst[:64]))
            elif shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if not text:
                    continue
                w = shape.width / EMU_IN * 72
                h = shape.height / EMU_IN * 72
                need, avail, worst = frame_need(
                    shape.text_frame, w, h, "shape")
                if need > avail + 1.0:
                    problems.append(
                        (idx, "textbox", need, avail, worst[:64]))
    print(f"slides: {len(prs.slides.__iter__.__self__._sldIdLst)}")
    if not problems:
        print("no estimated overflow")
        return 0
    print(f"estimated overflow in {len(problems)} boxes\n")
    worst_by_slide: dict[int, tuple] = {}
    for idx, where, need, avail, txt in problems:
        over = need - avail
        if idx not in worst_by_slide or over > worst_by_slide[idx][0]:
            worst_by_slide[idx] = (over, where, need, avail, txt)
    for idx in sorted(worst_by_slide):
        over, where, need, avail, txt = worst_by_slide[idx]
        print(f"slide {idx:>2}  {where:<9} need {need:6.1f}pt  avail "
              f"{avail:6.1f}pt  over {over:+6.1f}pt  | {txt}")
    return 1


if __name__ == "__main__":
    sys.exit(check(sys.argv[1]))
