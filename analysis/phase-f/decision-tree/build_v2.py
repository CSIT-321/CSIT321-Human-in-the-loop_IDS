#!/usr/bin/env python3
"""Build D/v2/index.html: the stage and decision sections of the v2 page.

Reads tree2.json and workings.json. Writes one self-contained HTML file.
Standard library only. No network. The <!--RECORDS--> marker is left for
splice_v2.py to fill.
"""
import html
import json
import os
from decimal import Decimal

D = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(D, "v2")
OUT = os.path.join(OUT_DIR, "index.html")
MARK = "<!--RECORDS-->"

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; background: #fbfbfd; color: #17191f;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 15px; line-height: 1.5; }
main { max-width: 1200px; margin: 0 auto; padding: 32px 24px 64px; }
h1 { font-size: 30px; line-height: 1.25; margin: 0 0 12px; letter-spacing: -0.01em; }
h2 { font-size: 22px; margin: 44px 0 6px; padding-bottom: 6px; border-bottom: 1px solid #dfe2e8; }
h3 { font-size: 17px; margin: 0 0 8px; }
h4 { font-size: 14px; margin: 18px 0 6px; text-transform: uppercase;
  letter-spacing: 0.06em; color: #5c6270; }
p { margin: 0 0 10px; }
.sub { font-size: 17px; color: #3a3f4b; margin: 0 0 14px; }
.src { font-size: 13px; color: #5c6270; background: #f2f4f8;
  border-left: 3px solid #b9c0cc; padding: 10px 12px; margin: 0 0 18px; }
.lead { color: #4b5160; margin: 6px 0 18px; }
details { background: #fff; border: 1px solid #dfe2e8; border-radius: 8px;
  margin: 0 0 10px; padding: 0 16px; }
details[open] { padding-bottom: 16px; }
summary { cursor: pointer; padding: 12px 0; font-weight: 600; font-size: 15px;
  list-style-position: outside; }
summary::marker { color: #8a91a0; }
summary .sid { display: inline-block; min-width: 46px; color: #2b5bd7; }
summary .q { font-weight: 400; color: #5c6270; }
.badge { display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: 0.07em;
  text-transform: uppercase; padding: 2px 7px; border-radius: 999px;
  background: #e8ecf6; color: #2b4f9e; margin-left: 6px; vertical-align: 1px; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 12px; font-size: 14px; }
th, td { border: 1px solid #e2e5ec; padding: 6px 9px; text-align: left; vertical-align: top; }
th { background: #f4f6fa; font-weight: 600; font-size: 13px; color: #3a3f4b; }
td.k { width: 230px; color: #4b5160; background: #fafbfd; }
pre { background: #f5f6f9; border: 1px solid #e5e8ee; border-radius: 6px;
  padding: 10px 12px; overflow-x: auto; margin: 4px 0 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
ol, ul { margin: 4px 0 12px; padding-left: 24px; }
li { margin: 0 0 5px; }
.ok { color: #147a44; font-weight: 600; }
.bad { color: #b3261e; font-weight: 600; }
.muted { color: #868c9a; }
.note { font-size: 13px; color: #5c6270; font-style: italic; }
.sub-block { background: #fff; border: 1px solid #dfe2e8; border-radius: 8px;
  padding: 16px 18px; margin: 0 0 14px; }
.tag { font-size: 12px; color: #5c6270; }
footer { margin-top: 44px; padding-top: 14px; border-top: 1px solid #dfe2e8;
  font-size: 12.5px; color: #5c6270; }
"""


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def num(v):
    """Render a stored number without inventing or rounding it."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        r = repr(v)
        if "e" in r or "E" in r:
            return format(Decimal(r), "f")
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return r
    return esc(v)


def val(v):
    if v is None:
        return '<span class="muted">none</span>'
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (dict, list)):
        return "<code>" + esc(json.dumps(v, ensure_ascii=False)) + "</code>"
    if isinstance(v, (int, float)):
        return num(v)
    return esc(v)


def mark(b):
    return '<span class="ok">&#10003; pass</span>' if b else '<span class="bad">&#10007; fail</span>'


def gate_mark(b):
    return ('<span class="ok">&#10003; pass</span>' if b
            else '<span class="muted">&#10007; pass = false</span>')


def table(heads, rows, widths=None):
    out = ["<table>", "<thead><tr>"]
    for i, h in enumerate(heads):
        w = f' style="width:{widths[i]}"' if widths and widths[i] else ""
        out.append(f"<th{w}>{esc(h)}</th>")
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def kv(rows):
    out = ["<table><tbody>"]
    for k, v in rows:
        out.append(f'<tr><td class="k">{esc(k)}</td><td>{v}</td></tr>')
    out.append("</tbody></table>")
    return "\n".join(out)


def ul(items):
    return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"


def ol(items):
    return "<ol>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ol>"


def pre(lines):
    if isinstance(lines, str):
        lines = [lines]
    return "<pre>" + esc("\n".join(lines)) + "</pre>"


# ---------------------------------------------------------------- data helpers

STAGES = None
NODES = None
RECS = {}


def rec(path):
    return RECS[path]


def fb_fields(f):
    """Read a feedback event, tolerating either naming used in the sources."""
    before = f.get("scoreBefore", f.get("original_score"))
    req = f.get("requestedDelta", f.get("requested_delta"))
    applied = f.get("appliedDelta", f.get("actual_delta"))
    action = f.get("guardrailAction", f.get("guardrail_action"))
    after = f.get("scoreAfter", f.get("score_after"))
    if after is None and before is not None and applied is not None:
        after = round(float(before) + float(applied), 2)
    return before, req, applied, action, after


def signed(v):
    if v is None:
        return "null"
    s = num(v)
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return "+" + s
    return s


def arithmetic(f):
    """The applied change, written only with the stored numbers."""
    before, req, applied, action, after = fb_fields(f)
    left = "0" if before is None else num(before)
    delta = "0" if applied is None else num(applied)
    right = "null" if after is None else num(after)
    op = "+" if applied is not None and applied >= 0 else "-"
    if applied is not None and applied < 0:
        delta = num(abs(applied))
    line = f"{left} {op} {delta} = {right}"
    if req is not None:
        line += f"   (requested {signed(req)}; guardrailAction {esc(action) if action else 'null'})"
    return line


def stage_card(s):
    open_attr = " open" if s["id"] in ("S4", "S5") else ""
    parts = [f'<details id="{s["id"].lower()}"{open_attr}>',
             f'<summary><span class="sid">{esc(s["id"])}</span>{esc(s["name"])}'
             f' <span class="q">&mdash; {esc(s["question"])}</span></summary>']
    parts.append("<h4>Input</h4><p>" + esc(s["input"]) + "</p>")
    parts.append("<h4>Analysis</h4>" + ol(s["algorithm"]))
    parts.append("<h4>Formula</h4>" + pre(s["formula"]))
    parts.append("<h4>Output</h4><p>" + esc(s["output"]) + "</p>")
    parts.append("<h4>Stored in</h4><p>" + esc(s["stored"]) + "</p>")
    parts.append("<h4>Limits</h4>" + ul(s["limits"]))
    if s.get("thresholds"):
        parts.append("<h4>Class ceilings</h4>")
        parts.append(table(["Attack class", "CVSS v3.1", "Ceiling"],
                           [[esc(t["className"]), num(t["cvss"]), esc(t["ceiling"])]
                            for t in s["thresholds"]]))
    parts.append("</details>")
    return "\n".join(parts)


def an_open(sid, label):
    s = next(x for x in STAGES if x["id"] == sid)
    return (f'<div class="sub-block" id="{sid.lower()}a">\n'
            f'<h3>{esc(sid)} &middot; {esc(s["name"])}</h3>\n'
            f'<p class="tag">{esc(label)}</p>')


def block(sid, label, body):
    return an_open(sid, label) + "\n" + body + "\n</div>"


def a1():
    r = rec("A")
    rows = [[esc(k), val(v)] for k, v in r["input"].items()]
    rows.append(["inputFeatureCount", num(r["inputFeatureCount"])])
    rows.append(["recordId", esc(r["recordId"])])
    rows.append(["ref", esc(r["ref"])])
    return block("S1", f'Record {r["path"]} ({r["recordId"]}) input, as stored', kv(rows))


def a2():
    r = rec("A")
    sig = r["stages"]["signature"]
    out = []
    for m in sig["matched"]:
        out.append(f'<h4>Rule {esc(m["rule_id"])} &mdash; {esc(m["name"])}</h4>')
        out.append(kv([["rule_id", "<code>" + esc(m["rule_id"]) + "</code>"],
                       ["class", esc(m["class"])],
                       ["severity", esc(m["severity"])],
                       ["version", esc(m.get("version", ""))]]))
        out.append(table(["condition test", "observed", "result"],
                         [[esc(c["test"]), esc(c["observed"]), mark(c["pass"])]
                          for c in m["conditions"]]))
    if not sig["matched"]:
        out.append('<p class="note">No rule matched this flow.</p>')
    out.append(f'<p><strong>sig = {num(sig["sig"])}</strong> &mdash; '
               + esc(sig["formula"]) + "</p>")
    out.append(pre([f'{k} = {num(v)}' for k, v in sig["severityScores"].items()]))
    return block("S2", f'Record {r["path"]} ({r["recordId"]}) signature match', "\n".join(out))


def a3():
    r = rec("A")
    m = r["stages"]["model"]
    out = [kv([["predictedClass", esc(m["predictedClass"])],
               ["confidence", num(m["confidence"])],
               ["maliciousProbability", num(m["maliciousProbability"])],
               ["note", esc(m.get("note", ""))]])]
    ex = m.get("explain")
    if not ex:
        out.append('<p class="note">no explanation stored for this record</p>')
        return block("S3", f'Record {r["path"]} ({r["recordId"]}) model output', "\n".join(out))
    out.append("<h4>Explanation (SHAP, raw margin)</h4>")
    out.append(kv([["method", esc(ex["method"])],
                   ["outputSpace", esc(ex["outputSpace"])],
                   ["explainedClass", esc(ex["explainedClass"])],
                   ["baseValue", num(ex["baseValue"])],
                   ["rawMargin", num(ex["rawMargin"])]]))
    ad = ex["additivity"]
    out.append(table(["additivity", "value"],
                     [["difference", num(ad["difference"])],
                      ["passed", mark(ad["passed"])],
                      ["tolerance", num(ad["tolerance"])]]))
    for key, title in (("strongestSupporting", "Strongest supporting features"),
                       ("strongestOpposing", "Strongest opposing features")):
        out.append(f"<h4>{title}</h4>")
        out.append(table(["feature", "value", "contribution"],
                         [[esc(f["feature"]), num(f["value"]), num(f["contribution"])]
                          for f in ex[key]]))
    return block("S3", f'Record {r["path"]} ({r["recordId"]}) model output', "\n".join(out))


def a4():
    r = rec("A")
    f = r["stages"]["fusion"]
    out = ["<h4>Score arithmetic, verbatim</h4>", pre(f["scoreArithmetic"])]
    out.append(kv([["Evidence class", esc(f["evidence"])],
                   ["Rule class equals model class", val(f["classAgreement"])],
                   ["sig: rule strength, 0 to 1", num(f["sig"])],
                   ["ml: 1 - P(Benign), 0 to 1", num(f["ml"])],
                   ["Score computed here", num(f["score"])],
                   ["Score the product stored", num(f.get("storedScore"))]]))
    out.append(f"<p>The two detectors agree, so the fusing step takes the larger of {num(f['sig'])} and "
               f"{num(f['ml'])}, scales it by 100, adds the agreement bonus and clips the result at 100. "
               f"The product stored {num(f.get('storedScore'))}; the recomputation gives {num(f['score'])}.</p>")
    return block("S4", f'Record {r["path"]} ({r["recordId"]}) fusion', "\n".join(out))


def threshold_source():
    for s in STAGES:
        if s.get("thresholds"):
            return s["id"], s["thresholds"]
    for n in NODES:
        if n.get("thresholds"):
            return n["id"], n["thresholds"]
    return None, []


def a5():
    r = rec("A")
    sev = r["stages"]["severity"]
    labels = {"score": "Score", "band": "Band from the score", "className": "Attack class",
              "classCvss": "Class CVSS v3.1", "ceiling": "Class ceiling", "final": "Final severity",
              "capped": "Was the band capped"}
    rows = [[labels[k], val(sev.get(k))] for k in labels]
    out = [table(["Step", "Value"], rows)]
    cap = ("The band is above the ceiling, so the ceiling wins." if sev.get("capped")
           else "The band is inside the ceiling, so the band wins.")
    out.append(f"<p>Score {num(sev['score'])} falls in the {esc(sev['band'])} band. "
               f"{esc(sev['className'])} carries CVSS {num(sev['classCvss'])}, which allows at most "
               f"{esc(sev['ceiling'])}. {cap} Final severity: <strong>{esc(sev['final'])}</strong>.</p>")
    tid, th = threshold_source()
    if th:
        out.append(f"<h4>Class ceiling: the worst severity each attack class can reach (config/severity-chart.json)</h4>")
        out.append(table(["Attack class", "CVSS v3.1", "Ceiling"],
                         [[esc(t["className"]), num(t["cvss"]), esc(t["ceiling"])] for t in th]))
    return block("S5", f'Record {r["path"]} ({r["recordId"]}) severity', "\n".join(out))


def a6():
    r = rec("A")
    g = r["stages"]["group"]
    out = [kv([["members", num(g["members"])],
               ["key (source IP)", esc(g["key"])],
               ["spanMinutes", num(g["spanMinutes"])],
               ["maxGapMinutes", num(g["maxGapMinutes"])],
               ["firstSeen", esc(g["firstSeen"])],
               ["lastSeen", esc(g["lastSeen"])]])]
    out.append("<p><strong>windowRule:</strong> " + esc(g["windowRule"]) + "</p>")
    return block("S6", f'Record {r["path"]} ({r["recordId"]}) group', "\n".join(out))


def a7():
    r = rec("A")
    ro = r["stages"]["routing"]
    g = ro["gates"]
    out = [kv([["e1.test", "<code>" + esc(g["e1"]["test"]) + "</code>"],
               ["e1.pass", gate_mark(g["e1"]["pass"])],
               ["e1.notTriggered", esc(g["e1"]["notTriggered"])],
               ["e3.test", "<code>" + esc(g["e3"]["test"]) + "</code>"],
               ["e3.pass", gate_mark(g["e3"]["pass"])],
               ["route", "<code>" + esc(ro["route"]) + "</code>"],
               ["stage", esc(ro["stage"])],
               ["priority", num(ro["priority"])],
               ["band", esc(ro["band"])]])]
    return block("S7", f'Record {r["path"]} ({r["recordId"]}) routing gates', "\n".join(out))


def a8():
    r = rec("B")
    h = r["human"]
    work = h.get("work") or {}
    out = ["<h4>Tier 1 work</h4>",
           kv([["status", esc(work.get("status", ""))],
               ["owner", esc(work.get("owner", ""))],
               ["finishedBy", esc(work.get("finishedBy", ""))],
               ["recordId", esc(r["recordId"])]])]
    fbs = h.get("feedback") or []
    if not fbs:
        out.append('<p class="note">No feedback event is stored for this record.</p>')
    for f in fbs:
        before, req, applied, action, after = fb_fields(f)
        out.append("<h4>Feedback event</h4>")
        out.append(kv([["category", "<code>" + esc(f["category"]) + "</code>"],
                       ["scoreBefore", num(before)],
                       ["requestedDelta", signed(req)],
                       ["appliedDelta", signed(applied)],
                       ["scoreAfter", num(after)],
                       ["guardrailAction", "<code>" + esc(action) + "</code>"]]))
        out.append("<h4>Arithmetic</h4>" + pre(arithmetic(f)))
    out.append('<p class="note">workings.json stores no arithmetic string for this event, '
               'so the line above repeats the stored values in one equation.</p>')
    return block("S8", f'Record {r["path"]} ({r["recordId"]})', "\n".join(out))


def a9():
    rows = []
    for p in ("B", "C", "D", "E"):
        r = rec(p)
        for f in (r["human"].get("feedback") or []):
            before, req, applied, action, after = fb_fields(f)
            rows.append([f'{esc(p)} ({esc(r["recordId"])})',
                         "<code>" + esc(f["category"]) + "</code>",
                         num(before), signed(req), signed(applied), num(after),
                         "<code>" + esc(action) + "</code>"])
    body = table(["record", "category", "scoreBefore", "requestedDelta",
                  "appliedDelta", "scoreAfter", "guardrailAction"], rows)
    body += ('<p class="note">Each row is one stored feedback event. '
             'scoreAfter is scoreBefore plus appliedDelta, computed only from those two stored fields.</p>')
    return block("S9", "Records B, C, D and E feedback, side by side", body)


def a10():
    r = rec("A")
    c = r["human"].get("case")
    if not c:
        body = '<p class="note">No Tier 2 case is stored for this record.</p>'
    else:
        body = kv([[k, val(v)] for k, v in c.items()])
    return block("S10", f'Record {r["path"]} ({r["recordId"]}) Tier 2 case', body)


def a11():
    s = next(x for x in STAGES if x["id"] == "S11")
    body = ("<p><strong>Queue order, verbatim from the formula:</strong></p>"
            + pre(s["formula"][0])
            + "<p>The row prints the stored current score. This stage adds no number of its own.</p>")
    return block("S11", "No numbers at this stage", body)


def node_card(n):
    open_attr = " open" if n["id"] in ("N2", "N11") else ""
    ids = {s["id"] for s in STAGES}
    stage_txt = "&ndash;".join(
        (f'<a href="#{p.lower()}">{esc(p)}</a>' if p in ids else esc(p))
        for p in n["stage"].split("-"))
    parts = [f'<details id="{n["id"].lower()}"{open_attr}>',
             f'<summary><span class="sid">{esc(n["id"])}</span>{esc(n["question"])}'
             f'<span class="badge">{esc(n["kind"])}</span></summary>',
             f'<p class="tag">dataType {esc(n["dataType"])} &middot; stage {stage_txt}</p>',
             "<h4>Formula</h4>" + pre(n["formula"]),
             "<h4>Algorithm</h4>" + ol(n["algorithm"]),
             "<h4>Code</h4>" + pre(n["code"]),
             "<h4>Why a SOC needs this</h4><p>" + esc(n["why"]) + "</p>",
             "<h4>If the other branch is taken</h4><p>" + esc(n["ifFalse"]) + "</p>",
             "<h4>Watch out</h4><p>" + esc(n["watchOut"]) + "</p>",
             "<h4>Evidence</h4><p>" + esc(n["evidence"]) + "</p>"]
    if n.get("thresholds"):
        parts.append("<h4>Thresholds</h4>")
        parts.append(table(["Attack class", "CVSS v3.1", "Ceiling"],
                           [[esc(t["className"]), num(t["cvss"]), esc(t["ceiling"])]
                            for t in n["thresholds"]]))
    parts.append("</details>")
    return "\n".join(parts)


def verification_section():
    rows = []
    total = 0
    passed = 0
    for r in RECORDS:
        for c in (r.get("recordChecks") or []):
            total += 1
            passed += 1 if c.get("pass") else 0
            rows.append([f'{esc(r["path"])} ({esc(r["recordId"])})',
                         esc(c.get("what", "")),
                         val(c.get("stored")),
                         val(c.get("computed")),
                         mark(c.get("pass"))])
    body = table(["path", "what", "stored", "computed", "pass"], rows)
    body += (f'<p><strong>Checks:</strong> {total}. '
             f'<strong>Passed:</strong> {passed}. '
             f'<strong>Failed:</strong> {total - passed}.</p>')
    return body


def main():
    global STAGES, NODES, RECORDS
    tree = json.load(open(os.path.join(D, "tree2.json"), encoding="utf-8"))
    work = json.load(open(os.path.join(D, "workings.json"), encoding="utf-8"))
    STAGES = tree["stages"]
    NODES = tree["nodes"]
    RECORDS = work["records"]
    for r in RECORDS:
        RECS[r["path"]] = r

    h = ['<!DOCTYPE html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         "<title>" + esc(tree["title"]) + "</title>",
         "<style>" + CSS + "</style>", "</head>", "<body>", "<main>"]

    h.append("<h1>" + esc(tree["title"]) + "</h1>")
    h.append('<p class="sub">' + esc(tree["subtitle"]) + "</p>")
    h.append('<p class="src">' + esc(tree["source"]) + "</p>")

    h.append("<h2>How to read the numbers</h2>")
    h.append('<p class="lead">The same words are used in every card below. '
             "Read this table first.</p>")
    h.append(table(["term", "meaning", "example"],
                   [[esc(x["term"]), esc(x["meaning"]), esc(x["example"])]
                    for x in tree["howToRead"]]))

    h.append("<h2>The eleven stages</h2>")
    h.append('<p class="lead">A flow passes these stages in order. Each card shows the '
             "input, the analysis steps, the formula, the output and where the result is stored.</p>")
    for s in STAGES:
        h.append(stage_card(s))

    h.append("<h2>The analysis, with real numbers</h2>")
    h.append('<p class="lead">Every value below is copied from workings.json for the record '
             "named in the card. Nothing is rounded and nothing is added.</p>")
    for fn in (a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11):
        h.append(fn())

    h.append("<h2>The thirteen decisions</h2>")
    h.append('<p class="lead">Each decision is one branch point in the tree. The stage line '
             "links back to the stage card above.</p>")
    for n in NODES:
        h.append(node_card(n))

    h.append(MARK)

    h.append("<h2>Verification</h2>")
    h.append('<p class="lead">Each record was recomputed from the routed copy of the database '
             "and compared with the value the product stored.</p>")
    h.append(verification_section())

    h.append("<footer>Built from tree2.json and workings.json by build_v2.py.<br>"
             + esc(work["source"]) + "</footer>")
    h.append("</main></body></html>")

    page = "\n".join(h)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print(f"wrote {OUT} ({len(page.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
