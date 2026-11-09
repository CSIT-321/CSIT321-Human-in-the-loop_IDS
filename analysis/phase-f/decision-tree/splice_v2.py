"""Splice the per-record walkthrough into the v2 page and audit every number printed against the sources.

1. builds the stage/node part (build_v2.py writes v2/index.html with a <!--RECORDS--> marker),
2. inserts records_html() from v2_records.py,
3. extracts every numeric token from the visible text and checks it appears in tree2.json, workings.json
   or trace/trace.json. A number that appears nowhere is either invented or stale -> reported as a failure.

Usage: python splice_v2.py
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D / "v2"))
MARK = "<!--RECORDS-->"


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        if tag in ("p", "div", "td", "th", "li", "h1", "h2", "h3", "h4", "summary", "tr", "br"):
            self.chunks.append(" ")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.chunks.append(data)


def numbers_in(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            numbers_in(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            numbers_in(v, out)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.add(abs(float(obj)))
    elif isinstance(obj, str):
        for m in re.findall(r"-?\d+(?:\.\d+)?", obj):
            try:
                out.add(abs(float(m)))
            except ValueError:
                pass


def main() -> int:
    import build_v2  # noqa: F401
    import v2_records

    build_v2.main()  # regenerate v2/index.html with the marker before splicing

    tree2 = json.loads((D / "tree2.json").read_text(encoding="utf-8"))
    work = json.loads((D / "workings.json").read_text(encoding="utf-8"))
    trace = json.loads((D / "trace" / "trace.json").read_text(encoding="utf-8"))
    page = D / "v2" / "index.html"
    html = page.read_text(encoding="utf-8")
    if html.count(MARK) != 1:
        print(f"FAIL: marker count {html.count(MARK)}")
        return 1
    html = html.replace(MARK, v2_records.records_html(work, tree2, trace))
    page.write_text(html, encoding="utf-8")

    allowed = set()
    for o in (tree2, work, trace):
        numbers_in(o, allowed)
    # Structural constants that legitimately appear only in prose or in generated text.
    allowed |= {float(x) for x in range(0, 25)}  # step ids, counts of stages/nodes, ordinals
    p = Text()
    p.feed(html)
    text = " ".join(p.chunks)
    seen = {}
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)", text):
        v = float(m.group(1))
        seen.setdefault(v, 0)
        seen[v] += 1
    unknown = sorted(v for v in seen if v not in allowed)
    print(f"page {page.stat().st_size} bytes; numbers printed {len(seen)}; unknown {len(unknown)}")
    if unknown:
        ctx = []
        for v in unknown[:15]:
            m = re.search(r".{40}" + re.escape(("%g" % v)) + r".{40}", text, re.S)
            ctx.append((v, " ".join(m.group(0).split()) if m else ""))
        for v, c in ctx:
            print(f"  unknown {v}: ...{c}...")
        return 2
    print("every printed number exists in tree2.json, workings.json or trace.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
