"""Build the workflow layout page: the dual chain (flow chain + Suricata chain) from one capture to one queue.

Input   trace.json (trace_data.py), which reads the scratch database of one whole Packet Replay.
Output  index.html. Every number on the page comes from trace.json. No external resources.

    hitl-ids/.venv/Scripts/python.exe analysis/phase-f/workflow-layout/build_layout.py
"""
from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
T = json.loads((HERE / "trace.json").read_text(encoding="utf-8"))
TOT, RESULTS, PROGRESS = T["totals"], T["results"], T["progress"]
OUT = HERE / "index.html"


def e(v) -> str:
    return html.escape("—" if v is None else str(v), quote=True)


def n(v) -> str:
    return f"{v:,}" if isinstance(v, int) else e(v)


# Stage ids are used in the diagram, the stage table and the trace cards.
FLOW_STAGES = [
    ("F1", "CICFlowMeter", "packets → one flow record per connection, 81 of 82 model features",
     "data/spike/…/flows/*.csv"),
    ("F2", "Detection", "signature rules + XGBoost score every flow; evidence class corroborated / ml_only / none",
     "alerts, flow_data"),
    ("F3", "Grouping", "flagged flows group by source IP inside the group window; an unflagged flow stays single",
     "alert_groups, alert_group_members"),
    ("F4", "Projection", "each group's first member (or each single flow) becomes one operational alert",
     "operational_alerts_v2"),
    ("F5", "Flow routing", "E1: rule and model agree at score 100 → whole group to Tier 2; otherwise Tier 1",
     "operational_system_routing, operational_triage_state_v2"),
]
SURI_STAGES = [
    ("S1", "Suricata", "packets → eve.json alert per rule match (ET Open); informational signatures are dropped",
     "data/packet-replay/eve.jsonl"),
    ("S2", "Staging", "canonical alert contract; same flow and signature set = one bundle",
     "suricata_eve_records, external_alert_inbox"),
    ("S3", "Eligibility review", "accepted or held, with a reason and an actor",
     "external_eligibility_review"),
    ("S4", "Admission", "becomes an operational alert; priority from native severity",
     "external_operational_admission, operational_alerts_v2"),
    ("S5", "Classification + routing", "signature → attack category; unknown → Tier 2 expert review",
     "operational_system_routing, operational_triage_state_v2"),
]
SHARED = [
    ("Q", "One queue", "both chains, one table, one sort by priority", "Analyst Workstation"),
    ("T1", "Tier 1 review", "claim, read evidence, note, verdict", "analyst_work, analyst_verdict_events"),
    ("T2", "Tier 2 case", "investigation → conclusion → resolved", "tier2_cases, tier2_case_events"),
]


def svg() -> str:
    """Two lanes from one packet source into one queue. Plain SVG, fixed geometry."""
    w, box_w, box_h = 1180, 170, 62
    parts = [f'<svg viewBox="0 0 {w} 470" role="img" aria-label="Dual chain diagram">',
             '<defs><marker id="a" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">'
             '<path d="M0,0 L9,4.5 L0,9 z" fill="#64748b"/></marker></defs>']

    def box(x, y, sid, title, sub, fill, stroke):
        parts.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>'
                     f'<text x="{x+10}" y="{y+22}" font-size="13" font-weight="700" fill="#16202b">{e(sid)} · {e(title)}</text>'
                     f'<text x="{x+10}" y="{y+43}" font-size="12" fill="#475569">{e(sub)}</text>')

    def arrow(x1, y1, x2, y2):
        parts.append(f'<path d="M{x1},{y1} L{x2},{y2}" stroke="#64748b" stroke-width="1.6" fill="none" marker-end="url(#a)"/>')

    # source
    box(10, 204, "P", "Packet capture", "3 pcaps · 2018-02-14", "#fff", "#0f172a")
    # flow lane (top) and Suricata lane (bottom)
    xs = [215, 405, 595, 785]
    flow_sub = [f"{n(TOT['flowsInWindow'])} flows", f"{n(TOT['flaggedFlows'])} flagged",
                f"{n(TOT['groups'])} groups", f"{n(TOT['flowQueueItems'])} items"]
    suri_sub = [f"{n(TOT['suricataAlertsArrived'])} alerts", f"{n(TOT['suricataBundlesAdmitted'])} bundles",
                "accepted by Admin", f"{n(TOT['suricataQueueItems'])} items"]
    flow_ids = [("F1", "CICFlowMeter"), ("F2", "Detection"), ("F3", "Grouping"), ("F4+F5", "Project + route")]
    suri_ids = [("S1", "Suricata"), ("S2", "Staging"), ("S3+S4", "Review + admit"), ("S5", "Classify + route")]
    for i, x in enumerate(xs):
        box(x, 60, *flow_ids[i], flow_sub[i], "#eef6ff", "#0b6bcb")
        box(x, 348, *suri_ids[i], suri_sub[i], "#fff7ed", "#b45309")
        if i:
            arrow(xs[i-1] + box_w, 91, x - 4, 91)
            arrow(xs[i-1] + box_w, 379, x - 4, 379)
    arrow(10 + box_w, 225, 215 - 4, 100)
    arrow(10 + box_w, 245, 215 - 4, 370)
    parts.append('<text x="200" y="40" font-size="13" font-weight="700" fill="#0b6bcb">FLOW CHAIN — detection, grouping, learning</text>'
                 '<text x="200" y="440" font-size="13" font-weight="700" fill="#b45309">SURICATA CHAIN — second, named opinion</text>')
    # link line between the chains
    parts.append('<path d="M480,122 L480,348" stroke="#7c3aed" stroke-width="1.4" stroke-dasharray="5 4" fill="none"/>'
                 '<text x="488" y="238" font-size="12" fill="#7c3aed">same flow: 5-tuple + time</text>')
    # queue and tiers
    box(985, 204, "Q", "One queue", f"{n(TOT['queueItems'])} items", "#f0fdf4", "#15803d")
    arrow(785 + box_w, 91, 985 + 30, 204 - 4)
    arrow(785 + box_w, 379, 985 + 30, 266 + 4)
    box(985, 20, "T1", "Tier 1 review", f"{n(TOT['tier1Items'])} items", "#fff", "#15803d")
    box(985, 388, "T2", "Tier 2 case", f"{n(TOT['tier2Cases'])} cases", "#fff", "#b91c1c")
    arrow(1070, 204 - 2, 1070, 20 + box_h + 4)
    arrow(1070, 266 + 2, 1070, 388 - 4)
    parts.append("</svg>")
    return "".join(parts)


def stage_rows(stages, cls) -> str:
    return "".join(f'<tr class="{cls}"><td><b>{e(s)}</b></td><td>{e(t)}</td><td>{e(d)}</td><td><code>{e(where)}</code></td></tr>'
                   for s, t, d, where in stages)


def results_table() -> str:
    rows = []
    for r in RESULTS:
        tr = r["triage"]
        rows.append(
            f'<tr class="{r["chain"]}"><td><a href="#{r["id"]}"><b>{r["id"]}</b></a></td><td>{e(r["chain"])}</td>'
            f'<td class="num">{n(r["count"])}</td><td>{e(r["title"])}</td>'
            f'<td>{e(r["evidenceClass"] or "external_rule")} · {"group" if r["isGroup"] else "single"}</td>'
            f'<td>{e(r["classification"]["category"] or r["classification"]["status"])}</td>'
            f'<td>{e(r["routing"]["routeClass"])}</td><td>{e(tr["band"])} ({e(tr["priority"])})</td>'
            f'<td><b>{e(tr["route"])}</b></td></tr>')
    total = sum(r["count"] for r in RESULTS)
    rows.append(f'<tr class="sum"><td colspan="2">Total</td><td class="num">{n(total)}</td>'
                f'<td colspan="6">= queue items {n(TOT["queueItems"])} (checked when trace.json was built)</td></tr>')
    return "".join(rows)


def kv(pairs) -> str:
    return "".join(f"<tr><th>{e(k)}</th><td>{v}</td></tr>" for k, v in pairs)


def other_chain_flow(other) -> str:
    if not other:
        return '<span class="mut">No Suricata alert on this flow.</span>'
    return "; ".join(f'{e(o["signature"])} (sid {e(o["sid"])}, severity {e(o["severity"])})' for o in other)


def other_chain_suri(other) -> str:
    if not other:
        return '<span class="mut">No flow record linked.</span>'
    flagged = other["evidenceClass"] != "none"
    verdict = "flagged" if flagged else "not flagged"
    group = f', group of {n(other["groupMembers"])} flows' if other.get("groupMembers") else ""
    return (f'<b>{verdict}</b> — flow alert {e(other["flowAlertId"])}: evidence {e(other["evidenceClass"])}, '
            f'model {e(other["modelClass"])} p={e(other["modelProbability"])}, score {e(other["combinedScore"])}{group}')


def card(r) -> str:
    t, tr, cl, rd = r["trace"], r["triage"], r["classification"], r["routing"]
    if r["chain"] == "flow":
        f, d, g = t["flow"], t["detection"], t["group"]
        steps = [
            ("P → F1", f'flow <code>{e(f["record"])}</code> at {e(f["time"])} — {e(f["srcIp"])}:{e(f["srcPort"])} → '
                       f'{e(f["dstIp"])}:{e(f["dstPort"])} {e(f["protocol"])}, {e(f["packets"])} packets, '
                       f'{e(f["bytes"])} bytes, {e(f["durationSeconds"])} s'),
            ("F2", f'rules {e(", ".join(d["rules"]) or "none")}; model {e(d["modelClass"])} p={e(d["modelProbability"])}; '
                   f'score {e(d["combinedScore"])}; evidence <b>{e(d["evidenceClass"])}</b>'),
            ("F3", (f'group key {e(g["key"])}: {n(g["members"])} flows, {e(g["firstSeen"])} → {e(g["lastSeen"])}; '
                    f'{n(g["membersWithSuricataAlert"])} members also have a Suricata alert')
                   if g else 'not grouped — an unflagged flow is its own queue item'),
            ("F4", f'operational alert {e(r["operationalId"])} <code>{e(r["alertRef"])}</code> “{e(r["title"])}”'),
            ("F5", f'classification {e(cl["status"])} / {e(cl["category"])} — {e(cl["reasons"][0])}<br>'
                   f'route <b>{e(rd["routeClass"])} → {e(rd["route"])}</b> ({e(rd["policyVersion"])}) — {e(tr["reason"])}'),
            ("Other chain", other_chain_flow(t["otherChain"])),
        ]
    else:
        v, s, rv, ad = t["eve"], t["staging"], t["review"], t["admission"]
        steps = [
            ("P → S1", f'{e(v["time"])} — {e(v["srcIp"])}:{e(v["srcPort"])} → {e(v["dstIp"])}:{e(v["dstPort"])} '
                       f'{e(v["protocol"])}; “{e(v["signature"])}”; category “{e(v["category"])}”; severity {e(v["severity"])}; '
                       f'sids {e(", ".join(map(str, v["sids"])))}; flow_id {e(v["flowId"])}'),
            ("S2", f'inbox {e(s["inboxId"])}: {n(v["alertsInBundle"])} eve alert{"" if v["alertsInBundle"] == 1 else "s"} in one bundle; '
                   f'{e(s["decision"])} under {e(s["policyVersion"])}; evidence {e(s["evidenceClass"])}'),
            ("S3", f'{e(rv["decision"])} by <b>{e(rv["actor"])}</b> — {e(rv["reason"])}'),
            ("S4", f'{e(ad["event"])} → operational alert {e(r["operationalId"])} <code>{e(r["alertRef"])}</code>'),
            ("S5", f'classification {e(cl["status"])} / {e(cl["category"])} — {e(cl["reasons"][0])}<br>'
                   f'route <b>{e(rd["routeClass"])} → {e(rd["route"])}</b> ({e(rd["policyVersion"])}) — {e(rd["reasons"][0])}'),
            ("Other chain", other_chain_suri(t["otherChain"])),
        ]
    steps.append(("Queue", f'priority {e(tr["priority"])} · band <b>{e(tr["band"])}</b> · route <b>{e(tr["route"])}</b> · '
                           f'stage {e(tr["stage"])}' + (f' · case <code>{e(r["caseRef"])}</code>' if r["caseRef"] else "")))
    body = "".join(f'<tr><th>{e(k)}</th><td>{v}</td></tr>' for k, v in steps)
    return (f'<section class="card {r["chain"]}" id="{r["id"]}"><h3>{r["id"]} · {e(r["chain"])} chain · '
            f'{n(r["count"])} queue item{"" if r["count"] == 1 else "s"} end here</h3><p class="mut">Example record shown. All {n(r["count"])} '
            f'items share this end result.</p><table class="trace">{body}</table></section>')


def progress_rows() -> str:
    return "".join(f'<tr><td class="num">{p["step"]+1}</td><td class="num">{n(p["flows"])}</td>'
                   f'<td class="num">{n(p["suricataAdmitted"])}</td><td class="num">{n(p["queue"])}</td>'
                   f'<td class="num">{n(p["groups"])}</td><td class="num">{n(p["groupMembers"])}</td>'
                   f'<td class="num">{n(p["tier2Cases"])}</td></tr>' for p in PROGRESS)


CSS = """
:root{--ink:#16202b;--mut:#5b6b7c;--line:#dbe3ec;--bg:#fbfcfe;--flow:#0b6bcb;--suri:#b45309}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,"Segoe UI",Roboto,sans-serif}
main{max-width:1220px;margin:0 auto;padding:28px 22px 70px}h1{font-size:27px;margin:0 0 6px}
h2{font-size:20px;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--line)}h3{margin:0 0 4px;font-size:16px}
p.lead{color:var(--mut);margin:0 0 16px;font-size:16px}.mut{color:var(--mut)}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13.5px}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{background:#f3f6fa;white-space:nowrap}
td.num{text-align:right;font-variant-numeric:tabular-nums}tr.sum td{font-weight:700;background:#f8fafc}
tr.flow td:first-child{border-left:4px solid var(--flow)}tr.suricata td:first-child{border-left:4px solid var(--suri)}
code{font:12.5px/1.4 ui-monospace,Consolas,monospace;background:#f3f6fa;padding:1px 4px;border-radius:4px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:10px;margin:14px 0}
.fact{border:1px solid var(--line);border-radius:8px;padding:9px 12px;background:#fff}
.fact b{display:block;font-size:11.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.fact span{font:600 18px/1.4 ui-monospace,monospace}
.card{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:14px 0;background:#fff}
.card.flow{border-left:5px solid var(--flow)}.card.suricata{border-left:5px solid var(--suri)}
table.trace th{width:110px}
.note{border-left:4px solid var(--flow);background:#f0f6ff;padding:10px 14px;border-radius:0 8px 8px 0;margin:14px 0}
.warn{border-left:4px solid var(--suri);background:#fff7ed;padding:10px 14px;border-radius:0 8px 8px 0;margin:14px 0}
svg{width:100%;height:auto;display:block;margin:8px 0;background:#fff;border:1px solid var(--line);border-radius:10px}
ol li{margin:3px 0}footer{margin-top:40px;border-top:1px solid var(--line);padding-top:12px;color:var(--mut);font-size:13px}
"""


def page() -> str:
    facts = [("Flows in capture window", TOT["flowsInWindow"]), ("Suricata alerts (non-info)", TOT["suricataAlertsArrived"]),
             ("Queue items", TOT["queueItems"]), ("Flow chain items", TOT["flowQueueItems"]),
             ("Suricata chain items", TOT["suricataQueueItems"]), ("Tier 1 items", TOT["tier1Items"]),
             ("Tier 2 cases", f'{TOT["tier2Cases"]} ({TOT["tier2CasesFlow"]} flow)'), ("Unique end results", len(RESULTS)),
             ("Unrouted items", TOT["unrouted"])]
    fact_html = "".join(f'<div class="fact"><b>{e(k)}</b><span>{n(v)}</span></div>' for k, v in facts)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Dual chain workflow — packet to analyst</title>
<style>{CSS}</style></head><body><main>
<h1>Dual chain workflow: one capture, two detectors, one queue</h1>
<p class="lead">The same packets feed two chains in parallel. The flow chain detects, groups and learns from analyst
verdicts. Suricata gives a second, named opinion. Both arrive in <b>one</b> queue, behind <b>one</b> login.</p>
<div class="facts">{fact_html}</div>

<h2>1. Layout</h2>
{svg()}
<div class="note">One sign-in page, one API, one database per workspace. The Admin chooses the workspace:
<b>Operational</b> or <b>Replay</b>. Every analyst then sees that workspace's single queue.</div>

<h2>2. Stages</h2>
<table><tr><th>Id</th><th>Stage</th><th>What happens</th><th>Stored in</th></tr>
<tr><td colspan="4"><b>P · Packet capture</b> — 3 pcaps of capture day 2018-02-14, replayed in {TOT["steps"]} equal time steps</td></tr>
{stage_rows(FLOW_STAGES, "flow")}{stage_rows(SURI_STAGES, "suricata")}{stage_rows(SHARED, "")}</table>

<h2>3. Every unique end result on the dashboard</h2>
<p>An end result is one distinct combination of chain, evidence, group or single, classification, route class,
priority band and route. The whole replay produces {len(RESULTS)}. Their counts add up to the queue.</p>
<table><tr><th>Id</th><th>Chain</th><th>Items</th><th>Title (example)</th><th>Evidence</th><th>Class</th>
<th>Route class</th><th>Band (priority)</th><th>Route</th></tr>{results_table()}</table>

<h2>4. Data trace for each end result</h2>
<p class="mut">For each end result: one real record, every stage it passed, and what the other chain said about the same flow.</p>
{"".join(card(r) for r in RESULTS)}

<h2>5. Arrival during the replay (every 10 steps)</h2>
<table><tr><th>Step</th><th>Flows in</th><th>Suricata admitted</th><th>Queue items</th><th>Groups</th>
<th>Group members</th><th>Tier 2 cases</th></tr>{progress_rows()}</table>

<h2>6. Run it</h2>
<ol>
<li>Build the replay input once: <code>python scripts/build_packet_replay.py</code>.</li>
<li>Sign in as <code>admin</code>. Open <b>Workspaces</b>.</li>
<li>Choose <b>Packet Replay</b>. Click <b>Prepare</b>, then <b>Activate</b>.</li>
<li>Click <b>Start</b> for one step every 5 seconds, or <b>Next Step</b> / <b>Next 5 Steps</b>.</li>
<li>Sign in as <code>g.ang</code> in a second browser. New items arrive in the queue as the steps run.</li>
</ol>

<h2>7. What this page does not show</h2>
<div class="warn"><ul>
<li><b>R2 is large.</b> {n(next(r["count"] for r in RESULTS if r["id"] == "R2"))} unflagged flows each become one low-priority
Tier 1 item (decision D4). This is product behaviour, not a replay artefact.</li>
<li><b>Stale reason text on R1.</b> A group is routed once, when its first members arrive. The stored reason gives the group
size at that time. The group then grows (to 5,100 and 11,613 flows).</li>
<li><b>Review is automatic in the replay.</b> S3 is recorded in the preparing Admin's name with a fixed reason.
In Operational, an analyst makes each S3 decision.</li>
<li>Recorded traffic, not live traffic. The model was trained on this testbed's dataset.</li>
<li>The other-chain link is by 5-tuple and time. It is shown here; the product does not yet show it in the alert panel.</li>
</ul></div>
<footer>Generated by analysis/phase-f/workflow-layout/build_layout.py from trace.json
({n(TOT["steps"])} steps, replay {e(TOT["replaySeconds"])} s on a scratch database).</footer>
</main></body></html>"""


if __name__ == "__main__":
    OUT.write_text(page(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes), {len(RESULTS)} end results")
