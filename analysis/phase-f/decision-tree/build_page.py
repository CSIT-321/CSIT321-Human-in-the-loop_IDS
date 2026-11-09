#!/usr/bin/env python3
"""Build D/index.html (decision tree + rules table + per-path walk-throughs).

Reads tree.json and trace/trace.json. Writes one self-contained HTML file.
Standard library only. No network.
"""
import html
import json
import os
import re

D = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.join(D, "tree.json")
TRACE = os.path.join(D, "trace", "trace.json")
OUT = os.path.join(D, "index.html")

# Tallest decision node: 4 branch lines (N1, N10). Box fits id + 1 question line + 4 x 13 px branches.
BOX_W, BOX_H = 250, 112
LAYER_H = 168
TOP = 30
SVG_W = 1150
COL2_GAP = 300


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def wrap(text, width):
    """Greedy word wrap to at most 2 lines; hard-cut the tail."""
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if not lines:
        return [""]
    if len(lines) == 1:
        return lines
    first = lines[0]
    rest = " ".join(lines[1:])
    if len(rest) > width:
        rest = rest[: width - 1] + "\u2026"
    return [first, rest]


def load():
    with open(TREE, encoding="utf-8") as f:
        tree = json.load(f)
    with open(TRACE, encoding="utf-8") as f:
        trace = json.load(f)
    return tree, trace


def compute_layers(nodes, edges):
    """Longest path from the roots, over the edge set."""
    ids = [n["id"] for n in nodes]
    layer = {i: 0 for i in ids}
    indeg = {i: 0 for i in ids}
    for f, t, _ in edges:
        indeg[t] = indeg.get(t, 0) + 1
    queue = [i for i in ids if indeg[i] == 0]
    order = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for f, t, _ in edges:
            if f == cur:
                layer[t] = max(layer[t], layer[cur] + 1)
                indeg[t] -= 1
                if indeg[t] == 0:
                    queue.append(t)
    if len(order) != len(ids):
        raise SystemExit("cycle in graph")
    return layer


def place(nodes, layer):
    """x/y for every node; layers stacked, members of a layer side by side."""
    by_layer = {}
    for n in nodes:
        by_layer.setdefault(layer[n["id"]], []).append(n["id"])
    pos = {}
    for lv in sorted(by_layer):
        members = sorted(by_layer[lv], key=lambda s: int(re.sub(r"\D", "", s)))
        k = len(members)
        y = TOP + lv * LAYER_H
        if k == 1:
            xs = [SVG_W / 2 - BOX_W / 2]
        else:
            span = (k - 1) * (BOX_W + 70)
            start = SVG_W / 2 - span / 2 - BOX_W / 2
            xs = [start + i * (BOX_W + 70) for i in range(k)]
        for i, mid in enumerate(members):
            pos[mid] = (xs[i], y)
    return pos, len(by_layer)
def edge_geom(x0, y0, x1, y1, span, off=None):
    """Cubic from the bottom centre of the source to the top centre of the target."""
    py0 = y0 + BOX_H
    dy = y1 - py0
    if span <= 1:
        c1 = (x0, py0 + dy * 0.45)
        c2 = (x1, y1 - dy * 0.45)
    else:
        if off is None:
            off = 110 + 26 * span
        cx = min(SVG_W - 25, max(x0, x1) + off)
        c1 = (cx, py0 + dy * 0.18)
        c2 = (cx, y1 - dy * 0.18)
    d = "M {:.1f} {:.1f} C {:.1f} {:.1f}, {:.1f} {:.1f}, {:.1f} {:.1f}".format(
        x0, py0, c1[0], c1[1], c2[0], c2[1], x1, y1
    )
    mx = (x0 + 3 * c1[0] + 3 * c2[0] + x1) / 8.0
    my = (py0 + 3 * c1[1] + 3 * c2[1] + y1) / 8.0
    return d, mx, my, ((x0, py0), c1, c2, (x1, y1))


def cubic_pts(ctrl, n=41):
    p0, p1, p2, p3 = ctrl
    pts = []
    for i in range(n):
        t = i / float(n - 1)
        u = 1 - t
        pts.append((
            u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1],
        ))
    return pts


def clips(ctrl, boxes, skip):
    """True if the curve passes inside a box that is not its own source or target."""
    for x, y in cubic_pts(ctrl):
        for bid, bx, by in boxes:
            if bid in skip:
                continue
            if bx + 3 < x < bx + BOX_W - 3 and by + 3 < y < by + BOX_H - 3:
                return True
    return False


def build_svg(tree, layer, pos, nlayers):
    height = TOP + nlayers * LAYER_H
    node_by_id = {n["id"]: n for n in tree["nodes"]}
    out = []
    out.append(
        '<svg class="tree" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        'role="img" aria-label="Data decision tree" '
        'xmlns="http://www.w3.org/2000/svg">'.format(w=SVG_W, h=height)
    )
    out.append(
        "<defs>"
        '<marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#4a5568"/></marker>'
        "<style>"
        ".node .box{fill:#fff;stroke-width:2}"
        ".node.decision .box{stroke:#d69e2e}"
        ".node.process .box{stroke:#a0aec0}"
        ".node.action .box{stroke:#3182ce}"
        ".node text{font-family:inherit;fill:#1a202c}"
        ".node .nid{font-size:12px;font-weight:700}"
        ".node .q{font-size:11px}"
        ".node .cnt{font-size:10.5px;fill:#4a5568}"
        ".edge path{fill:none;stroke:#4a5568;stroke-width:1.4}"
        ".edge text{font-size:9px;fill:#2d3748;font-family:inherit}"
        "</style></defs>"
    )
    out.append('<g class="edges">')
    boxes = [(nid, x, y) for nid, (x, y) in pos.items()]
    for f, t, lab in tree["edges"]:
        x0, y0 = pos[f]
        x1, y1 = pos[t]
        span = layer[t] - layer[f]
        wpx = max(34, len(lab) * 5.2 + 8) if lab else 0
        hw = wpx / 2 + 6
        off = 110 + 26 * span
        for _ in range(22):
            d, mx, my, ctrl = edge_geom(x0 + BOX_W / 2, y0, x1 + BOX_W / 2, y1, span,
                                        off if span > 1 else None)
            if span <= 1:
                break
            lab_hit = any(mx - hw < bx + BOX_W and mx + hw > bx
                          and my - 8 < by + BOX_H and my + 8 > by
                          for bid, bx, by in boxes if bid not in (f, t))
            if (not lab_hit and not clips(ctrl, boxes, (f, t))) or mx + hw > SVG_W - 6:
                break
            off += 22
        out.append('<g class="edge" data-from="%s" data-to="%s">' % (esc(f), esc(t)))
        out.append('<path d="%s" marker-end="url(#arw)"/>' % d)
        if lab:
            out.append(
                '<rect x="%.1f" y="%.1f" width="%.1f" height="13" rx="2" '
                'fill="#ffffff" opacity="0.92"/>' % (mx - wpx / 2, my - 7, wpx)
            )
            out.append(
                '<text x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
                % (mx, my + 3, esc(lab))
            )
        out.append("</g>")
    out.append("</g>")

    out.append('<g class="nodes">')
    for n in tree["nodes"]:
        x, y = pos[n["id"]]
        kind = n["kind"]
        out.append(
            '<g class="node %s" data-id="%s">' % (esc(kind), esc(n["id"]))
        )
        out.append(
            '<rect class="box" x="%.1f" y="%.1f" width="%d" height="%d" rx="6"/>'
            % (x, y, BOX_W, BOX_H)
        )
        out.append('<text class="nid" x="%.1f" y="%.1f">%s</text>' % (x + 10, y + 18, esc(n["id"])))
        ql = wrap(n["question"], 34)
        for i, line in enumerate(ql[:2]):
            out.append('<text class="q" x="%.1f" y="%.1f">%s</text>' % (x + 10, y + 36 + i * 14, esc(line)))
        if kind == "decision" and n.get("branches"):
            # one branch per line, never cut: every label and count shown in full
            for i, b in enumerate(n["branches"]):
                line = "\u2022 %s%s" % (b["label"], (": " + b["count"]) if b["count"] else "")
                out.append('<text class="cnt" x="%.1f" y="%.1f">%s</text>' % (x + 10, y + 56 + i * 13, esc(line)))
        out.append("</g>")
    out.append("</g>")
    out.append("</svg>")
    return "\n".join(out), height
CSS = """
:root{--ink:#1a202c;--mut:#4a5568;--line:#e2e8f0;--bg:#fbfbfd}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
 line-height:1.5;font-size:15px}
main{max-width:1200px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:26px;margin:0 0 6px}
h2{font-size:20px;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:16px;margin:0 0 4px}
p{margin:6px 0}
.src{color:var(--mut);font-size:13px;max-width:900px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef2f7;font-weight:600}
td code,code{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.wrap{overflow-x:auto}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.btns button{font:inherit;font-size:13px;padding:6px 14px;border:1px solid #cbd5e0;
 background:#fff;border-radius:6px;cursor:pointer}
.btns button:hover{background:#edf2f7}
.btns button[aria-pressed="true"]{background:#2b6cb0;color:#fff;border-color:#2b6cb0}
.story{border-left:3px solid #2b6cb0;background:#f2f7fd;padding:8px 12px;font-size:14px;
 min-height:58px;border-radius:0 4px 4px 0}
.story .bt{font-size:12px;color:var(--mut);margin-top:6px}
.node .box,.node text{transition:opacity .15s}
.node.dim,.edge.dim{opacity:.28}
.node.on .box{stroke-width:3.4}
.step{border:1px solid var(--line);border-radius:8px;background:#fff;padding:12px 14px;margin:14px 0}
.step .meta{font-size:13px;color:var(--mut)}
.shots{display:flex;gap:2%;margin-top:10px}
.shots figure{margin:0;max-width:49%;flex:1 1 49%}
.shots img{width:100%;border:1px solid var(--line);border-radius:4px;display:block}
.shots figcaption{font-size:11px;color:var(--mut);margin-top:4px;word-break:break-all}
.paths{list-style:none;padding:0;font-size:13px}
.paths li{padding:2px 0}
footer{margin-top:44px;padding-top:12px;border-top:1px solid var(--line);
 font-size:12px;color:var(--mut)}
"""


def data_types_table(tree):
    rows = []
    for d in tree["dataTypes"]:
        rows.append(
            "<tr><td><code>%s</code></td><td>%s</td><td><code>%s</code></td><td>%s</td><td><code>%s</code></td></tr>"
            % (esc(d["id"]), esc(d["name"]), esc(d["table"]), esc(d["holds"]), esc(d["source"]))
        )
    return (
        '<div class="wrap"><table><thead><tr><th>id</th><th>Data type</th><th>Table</th>'
        "<th>What it holds</th><th>Source</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def controls_and_story(tree):
    paths = tree["paths"]
    keys = sorted(paths)
    btns = ['<div class="btns" id="pathbtns">']
    for k in keys:
        btns.append('<button type="button" data-path="%s">Path %s</button>' % (esc(k), esc(k)))
    btns.append('<button type="button" data-path="ALL">All</button></div>')
    data = {k: {"nodes": paths[k]["nodes"], "branchTaken": paths[k]["branchTaken"],
                "story": paths[k]["story"]} for k in keys}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    js = """
<script>
var P = %s;
function clearAll(){
  document.querySelectorAll('.node,.edge').forEach(function(el){
    el.classList.remove('on'); el.classList.remove('dim');});
  document.querySelectorAll('#pathbtns button').forEach(function(b){
    b.setAttribute('aria-pressed','false');});
}
function show(key){
  clearAll();
  var out = document.getElementById('story');
  out.textContent = '';
  if(key === 'ALL'){
    var d0 = document.createElement('div');
    d0.textContent = 'All 13 nodes and 15 edges of the decision tree.';
    out.appendChild(d0);
    return;
  }
  var p = P[key];
  var btn = document.querySelector('#pathbtns button[data-path="'+key+'"]');
  if(btn) btn.setAttribute('aria-pressed','true');
  var on = {};
  p.nodes.forEach(function(id){ on[id] = 1; });
  document.querySelectorAll('.node').forEach(function(el){
    var id = el.getAttribute('data-id');
    if(on[id]){ el.classList.add('on'); } else { el.classList.add('dim'); }
  });
  var pair = {};
  for(var i=0;i<p.nodes.length-1;i++){ pair[p.nodes[i]+'|'+p.nodes[i+1]] = 1; }
  document.querySelectorAll('.edge').forEach(function(el){
    var k = el.getAttribute('data-from')+'|'+el.getAttribute('data-to');
    if(pair[k]){ el.classList.add('on'); } else { el.classList.add('dim'); }
  });
  var bt = Object.keys(p.branchTaken).map(function(n){
    return n + ': ' + p.branchTaken[n]; }).join(' \u00b7 ');
  var d1 = document.createElement('div');
  d1.textContent = p.story;
  var d2 = document.createElement('div');
  d2.className = 'bt';
  d2.textContent = 'Branches taken \u2014 ' + bt;
  out.appendChild(d1);
  out.appendChild(d2);
}
document.querySelectorAll('#pathbtns button').forEach(function(b){
  b.addEventListener('click', function(){ show(b.getAttribute('data-path')); });
});
show('ALL');
</script>
""" % payload
    return "".join(btns) + '<div class="story" id="story"></div>' + js
def rules_table(tree):
    rows = []
    for n in tree["nodes"]:
        br = "<br>".join(
            "%s &mdash; %s" % (esc(b["label"]), esc(b["count"])) for b in n.get("branches") or []
        ) or "&mdash;"
        rows.append(
            "<tr><td><code>%s</code><br><span style=\"font-size:11px;color:#4a5568\">%s</span></td>"
            "<td>%s</td><td>%s</td><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                esc(n["id"]), esc(n["kind"]), esc(n["question"]), esc(n["rule"]),
                esc(n["code"]), esc(n.get("why", "")), esc(n.get("evidence", "")), br,
            )
        )
    return (
        '<div class="wrap"><table><thead><tr><th>id</th><th>Question</th><th>Rule (SOC)</th>'
        "<th>Code</th><th>Why (SOC)</th><th>Evidence</th><th>Branches / counts</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def path_section(tree, trace, key):
    path = tree["paths"][key]
    tp = next((p for p in trace["paths"] if p["id"] == key), None)
    title = tp["title"] if tp else "Path " + key
    out = ['<section class="path" id="path-%s">' % esc(key)]
    out.append("<h2>Path %s &mdash; %s</h2>" % (esc(key), esc(title)))
    out.append('<p class="src">%s</p>' % esc(path["story"]))
    out.append('<h3>Nodes on this path</h3><ol class="paths">')
    for i, nid in enumerate(path["nodes"]):
        nx = i + 1
        bt = path["branchTaken"].get(nid)
        if bt:
            out.append(
                "<li><code>%s</code> &mdash; %s</li>" % (esc(nid), esc(bt))
            )
        else:
            out.append("<li><code>%s</code></li>" % esc(nid))
    out.append("</ol>")
    if tp:
        out.append("<h3>Steps</h3>")
        for s in tp["steps"]:
            sid = s["id"]
            shot = s.get("shot", "")
            out.append('<div class="step" id="step-%s">' % esc(sid))
            out.append("<h3>%s &mdash; %s</h3>" % (esc(sid), esc(s.get("label", ""))))
            out.append('<div class="meta">%s &middot; %s</div>' % (esc(s.get("actor", "")), esc(s.get("action", ""))))
            out.append('<div class="shots">')
            out.append(
                '<figure><a href="cards/%s.png"><img src="cards/%s.png" alt="%s card"></a>'
                "<figcaption>cards/%s.png</figcaption></figure>"
                % (esc(sid), esc(sid), esc(sid), esc(sid))
            )
            if shot:
                out.append(
                    '<figure><a href="trace/%s"><img src="trace/%s" alt="%s screenshot"></a>'
                    "<figcaption>trace/%s</figcaption></figure>"
                    % (esc(shot), esc(shot), esc(shot), esc(shot))
                )
            out.append("</div></div>")
    out.append("</section>")
    return "".join(out)


def main():
    tree, trace = load()
    layer = compute_layers(tree["nodes"], tree["edges"])
    pos, nlayers = place(tree["nodes"], layer)
    svg, height = build_svg(tree, layer, pos, nlayers)
    parts = [
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>%s</title><style>%s</style></head><body><main>" % (esc(tree["title"]), CSS),
        "<h1>%s</h1>" % esc(tree["title"]),
        '<p class="src">%s</p>' % esc(tree["source"]),
        "<h2>Data types</h2>",
        data_types_table(tree),
        "<h2>Decision tree</h2>",
        '<p class="src">Pick a path to highlight its nodes and edges.</p>',
        controls_and_story(tree),
        '<div class="wrap">%s</div>' % svg,
        "<h2>Decision rules</h2>",
        rules_table(tree),
        "<h2>Paths</h2>",
    ]
    for key in sorted(tree["paths"]):
        parts.append(path_section(tree, trace, key))
    parts.append(
        '<footer>Trace generated at %s. Tree source: %s</footer>'
        % (esc(trace.get("generatedAt", "")), esc(tree.get("source", "")[:80]))
    )
    parts.append("</main></body></html>")
    doc = "\n".join(parts)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print("wrote", OUT, len(doc), "bytes, svg height", height, "layers", nlayers)


if __name__ == "__main__":
    main()



