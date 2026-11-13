"""Build the workflow layout page: the dual chain (flow chain + Suricata chain) from one capture to one queue.

Input   trace.json (trace_data.py) and families.json (families_data.py). Both read the scratch database of one
        whole Packet Replay. The MEASURED_INSTANCES below come from the live demo (video and API probe).
Output  index.html. Every other number on the page comes from the two JSON files. No external resources.

    hitl-ids/.venv/Scripts/python.exe analysis/phase-f/workflow-layout/build_layout.py
"""
from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
T = json.loads((HERE / "trace.json").read_text(encoding="utf-8"))
TOT, RESULTS, PROGRESS = T["totals"], T["results"], T["progress"]
F = json.loads((HERE / "families.json").read_text(encoding="utf-8"))
SPLIT, COMP, QUEUE, FAM, GUARD = F["split"], F["compression"], F["queue"], F["families"], F["guardrails"]

# Family learning seen working end to end (not in the JSON: these are live runs, each with its source).
MEASURED_INSTANCES = [
    ("Suricata", "ET SCAN Behavioral Unusually fast Terminal Server Traffic … (Inbound)", "172.31.65.56",
     "2 earlier false positives + 1 on screen = quorum", "40 → 10 on every unjudged member",
     "Demo video 2:53–3:28 (frames at 3:06 and 3:26), replay step 160"),
    ("Flow", "XGBoost: Benign · port 443 · tcp", "131.202.240.72 (external server)",
     "2 earlier false positives + 1 on screen = quorum", "36.49 → 6.49 on the unjudged member",
     "Demo video 3:28–3:53 (frame at 3:52), replay step 160"),
    ("Suricata", "ET EXPLOIT Possible ETERNALBLUE Probe MS17-010 (MSF style)", "172.31.65.56",
     "1 false positive (no quorum)", "the judged alert only: 85 → 70 (critical floor); queue place 0 → 3",
     "Live API probe 2026-11-13, replay step 150"),
    ("Suricata + flow", "Terminal Server family / flow family 131.202.240.72", "as above",
     "3 false positives each, recorded through the API", "40 → 10 and 36.49 → 6.49 on unjudged members",
     "Live API probe 2026-11-13 before the video, replay step 150"),
]
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




def rows(items) -> str:
    return "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in items)


def combine_section() -> str:
    by = QUEUE["byChain"]
    fl, su = by["legacy_flow_alert"], by["external_nids_alert"]
    bands = QUEUE["bands"]
    linked = SPLIT["linkedByEvidence"]
    group_rows = rows([[e(g["grouping_key"]), f'<span class="num">{n(g["member_count"])}</span>',
                        e(g["detection_title"]), e(f'{g["first_seen_at"][11:19]} → {g["last_seen_at"][11:19]}'),
                        f'<b>{e(g["handling_route"])}</b> ({e(g["operational_priority"])})',
                        n(g["suricataAlertsOnMembers"])] for g in COMP["groups"]])
    bundle_rows = rows([[f"{k} alert{'s' if k != '1' else ''} on one flow", n(v)] for k, v in SPLIT["alertsPerBundle"].items()])
    tier2 = rows([[e(t["routeClass"]), e(t["reason"]), n(t["cases"])] for t in QUEUE["tier2ByRule"]])
    band_names = ["critical", "high", "medium", "low"]
    band_rows = rows([[b.title(), n(bands["legacy_flow_alert"].get(b, 0)), n(bands["external_nids_alert"].get(b, 0))]
                      for b in band_names])
    return f"""
<h2>3. Where the two chains combine</h2>
<p>The chains run apart from packet to routing. They meet at <b>five</b> points. Each point below gives the
mechanism, the table or file, and what it did on the full capture.</p>

<h3>3.1 One packet, two readings</h3>
<p>Every packet is read twice. CICFlowMeter turns each connection into one flow record. Suricata matches the same
packets against the ET Open rules. The replay builder (<code>scripts/build_packet_replay.py</code>) links each
Suricata alert to the flow record of the same connection (5-tuple and time). That link is the only place where
the two chains point at the same traffic.</p>
<table><tr><th>Suricata alerts (non-informational)</th><th>Linked to a flow record</th>
<th>… that the flow chain did <b>not</b> flag</th><th>… that the flow chain <b>also</b> flagged</th></tr>
<tr><td class="num">{n(SPLIT["suricataAlerts"])}</td><td class="num">{n(sum(linked.values()))}</td>
<td class="num">{n(linked.get("none", 0))}</td><td class="num">{n(SPLIT["linkedToFlagged"])}</td></tr></table>
<div class="note"><b>What this means.</b> The two chains mostly see <b>different</b> threats. Suricata named
{n(linked.get("none", 0))} connections that the model and the flow rules scored as benign (scans, JA3 hashes,
ETERNALBLUE probes). The flow chain flagged {n(COMP["flagged"])} flows (brute force, web attack, infiltration) that
Suricata stayed silent on. Only {n(SPLIT["linkedToFlagged"])} alerts overlap: all are
<i>ET SCAN Potential SSH Scan</i> from 13.58.98.64, inside the flow chain's brute-force group from the same host.
This is the case for running both chains: neither one alone sees the whole capture.</div>

<h3>3.2 Each chain compresses its own alerts first</h3>
<p><b>Flow chain — grouping</b> (<code>packages/detection/flow_queue.py</code>). A flagged flow joins the open group
of its <b>source IP</b> when it arrives within 30 minutes of that group's last member
(<code>config/flow-routing-v1.json</code>, <code>groupWindowMinutes</code>); otherwise it opens a new group. Each group is one queue item: its first member is the representative. An unflagged flow is never grouped
(decision D4): grouping would hide a missed attack among the same host's benign flows.</p>
<table><tr><th>Group key (source IP)</th><th>Flows</th><th>Title</th><th>Time (UTC)</th><th>Route (priority)</th>
<th>Suricata alerts on its members</th></tr>{group_rows}</table>
<p class="mut">{n(COMP["flowsInWindow"])} flows → {n(COMP["flagged"])} flagged → <b>{len(COMP["groups"])}</b> groups;
{n(COMP["unflagged"])} unflagged → {n(COMP["unflagged"])} single items. Flow chain total: {n(fl["items"])} queue items.</p>
<p><b>Suricata chain — bundling</b> (<code>packages/detection/adapters/suricata_bundle.py</code>). Alerts with the
same capture scope and Suricata <code>flow_id</code> become one bundle, so several signatures on one connection are
one queue item. The bundle keeps every signature; the most severe one gives the title.</p>
<table><tr><th>Bundle size</th><th>Bundles</th></tr>{bundle_rows}</table>
<p class="mut">{n(SPLIT["suricataAlerts"])} alerts → <b>{n(SPLIT["bundles"])}</b> bundles → {n(COMP["suricataBundlesAdmitted"])}
admitted → {n(su["items"])} queue items.</p>

<h3>3.3 The join point: one table and one routing audit</h3>
<p>This is where the chains become one product. Both write the same three tables: <code>operational_alerts_v2</code>
(the item), <code>operational_triage_state_v2</code> (priority, band, route, stage) and
<code>operational_system_routing</code> (the routing decision and its reason). A column <code>source_kind</code>
records the chain: <code>legacy_flow_alert</code> or <code>external_nids_alert</code>. Nothing downstream reads a
separate table per chain.</p>
<table><tr><th>Chain</th><th>Queue items</th><th>Tier 1</th><th>Tier 2</th><th>Routed</th></tr>
<tr class="flow"><td>Flow (CICFlowMeter + rules + XGBoost)</td><td class="num">{n(fl["items"])}</td><td class="num">{n(fl["tier1"])}</td>
<td class="num">{n(fl["tier2"])}</td><td class="num">{n(fl["routed"])}</td></tr>
<tr class="suricata"><td>Suricata (ET Open)</td><td class="num">{n(su["items"])}</td><td class="num">{n(su["tier1"])}</td>
<td class="num">{n(su["tier2"])}</td><td class="num">{n(su["routed"])}</td></tr>
<tr class="sum"><td>One queue</td><td class="num">{n(fl["items"] + su["items"])}</td><td class="num">{n(fl["tier1"] + su["tier1"])}</td>
<td class="num">{n(fl["tier2"] + su["tier2"])}</td><td class="num">{n(fl["routed"] + su["routed"])} (unrouted: {n(QUEUE["unrouted"])})</td></tr></table>

<h3>3.4 One severity scale and one sort</h3>
<p>Both chains map to <b>one</b> approved severity chart (<code>config/severity-chart.json</code>): the flow chain by
attack type, Suricata by classtype. The queue then sorts every item with one rule
(<code>apps/api/operational_queue.py</code>, <code>QUEUE_ORDER</code>):</p>
<ol><li>severity band, high first;</li><li>flagged before unflagged;</li>
<li><b>queue score</b> = operational priority + verdict delta (section 4), clamped 0–100, high first;</li>
<li>arrival time, newest first.</li></ol>
<table><tr><th>Band</th><th>Flow items</th><th>Suricata items</th></tr>{band_rows}</table>
<p class="mut">Suricata holds most of the critical and high items; the flow chain holds the long low tail of unflagged
flows. The analyst sees one list, not two.</p>

<h3>3.5 One routing policy, one Tier 2</h3>
<p>Routing is per chain but writes one decision format. The Tier 2 cases on the full capture came from two rules:</p>
<table><tr><th>Route class</th><th>Rule (first reason)</th><th>Cases</th></tr>{tier2}</table>

<div class="warn"><b>Do not claim on demo day.</b> <code>config/flow-routing-v1.json</code> has a cross-chain rule,
<b>E1-suricata</b>: escalate a flow group when a linked Suricata alert of severity ≤ 2 agrees with the model at
score ≥ 80. The rule is in <code>packages/detection/flow_routing.py</code> and has a unit test, but the replay path
(<code>flow_queue.route_flagged</code>) does not pass it the Suricata severities. So on this capture no item was
escalated because the <i>other</i> chain agreed. The chains combine in the queue, the severity scale, routing format and
learning; they do not yet escalate each other.</div>
"""


def families_section() -> str:
    g = GUARD
    fl, su, ff = FAM["flow"], FAM["suricata"], FAM["flowFlagged"]
    effect = rows([["Confirmed malicious", "+10", "raises"], ["Suspicious (needs investigation)", "0", "holds"],
                   ["Expected activity", "−15", "lowers"], ["False positive", "−30", "lowers"]])
    suri_top = rows([[e(t["signature"]), e(t["internalHost"]), f'<span class="num">{n(t["members"])}</span>',
                      e(t["priorityMax"]), e(t.get("weight")), e(t.get("familyDelta")),
                      f'<b>{e(t.get("predictedAfterThreeFP"))}</b>', e(t.get("thirdMemberStep"))]
                     for t in su["top"]])
    flow_top = rows([[e(t["attack"]), e(t["port"]), e(t["protocol"]), e(t["host"] or "— (flagged: no host)"),
                      f'<span class="num">{n(t["members"])}</span>', e(f'{t["priorityMin"]} – {t["priorityMax"]}')]
                     for t in fl["top"]])
    measured = rows([[e(c), e(f), e(h), e(v), f"<b>{e(r)}</b>", e(src)] for c, f, h, v, r, src in MEASURED_INSTANCES])
    cover = rows([
        ["Suricata", "signature + internal host", n(su["items"]), n(su["families"]), n(su["quorumFamilies"]),
         f'{n(su["quorumItems"])} ({100 * su["quorumItems"] / su["items"]:.0f}%)', n(su["singletons"])],
        ["Flow, unflagged", "attack + port + protocol + rule + destination", n(fl["items"] - ff["items"]),
         n(fl["families"] - ff["families"]), n(fl["quorumFamilies"]), f'{n(fl["quorumItems"])}', n(fl["singletons"] - ff["singletons"])],
        ["Flow, flagged groups", "attack + port + protocol + rule", n(ff["items"]), n(ff["families"]),
         n(ff["quorumFamilies"]), n(ff["quorumItems"]), n(ff["singletons"])]])
    return f"""
<h2>4. Family learning: how one verdict teaches many alerts</h2>
<p>A verdict does two things. It moves the <b>judged alert</b> at once, inside the guardrails. And it counts toward
the alert's <b>family</b>: once {e(int(g["aggregation_min_feedback_count"]))} verdicts in one family agree
(agreement ≥ {e(g["aggregation_min_agreement_ratio"])}), every member that <b>nobody judged</b> moves too. The judged
alerts keep their own verdict. Both chains use the same effects, the same guardrails and the same quorum; only the
family key differs.</p>

<h3>4.1 The rule</h3>
<table><tr><th>Verdict</th><th>Effect on the score</th><th>Direction</th></tr>{effect}</table>
<table><tr><th>Guardrail (guardrail_config)</th><th>Value</th></tr>
<tr><td>Largest reduction from one verdict</td><td>{e(g["max_feedback_reduction"])}</td></tr>
<tr><td>Largest increase from one verdict</td><td>{e(g["max_feedback_increase"])}</td></tr>
<tr><td>Critical alert (score ≥ {e(g["critical_alert_threshold"])}) cannot fall below</td><td>{e(g["critical_alert_floor"])}</td></tr>
<tr><td>Infiltration alert cannot fall below</td><td>{e(g["infiltration_alert_floor"])}</td></tr>
<tr><td>Family quorum: agreeing verdicts / agreement ratio</td><td>{e(int(g["aggregation_min_feedback_count"]))} / {e(g["aggregation_min_agreement_ratio"])}</td></tr></table>
<p>The family change is also scaled by the family's <b>severity weight</b> (formula C1): a low-weight signature can
move the full −30; a critical one moves much less. A severe threat is the hardest to talk down.</p>

<h3>4.2 The family key of each chain</h3>
<table><tr><th>Chain</th><th>Family key</th><th>Why this key</th><th>Code</th></tr>
<tr class="flow"><td>Flow</td><td>attack type + destination port + protocol + rule id; for an <b>unflagged</b> flow also the
destination IP</td><td>Same model reading on the same service. The host is added for benign traffic so that one
server's normal traffic does not teach every server.</td><td><code>feedback/learning.py · family_key</code></td></tr>
<tr class="suricata"><td>Suricata</td><td>signature + <b>internal host</b> (the HOME_NET side: destination when inbound,
source when outbound, the pair when internal to internal)</td><td>The cause of a false positive is usually the asset
(a jump host, a scanner, an update server). The source port is left out because it changes on every connection.
HOME_NET = {e(", ".join(F["homeNet"]))} ({e(F["suricataConfig"])}).</td>
<td><code>suricata_learning.py · family_of</code></td></tr></table>

<h3>4.3 How much of the queue can learn (Tier 1 items, full capture)</h3>
<table><tr><th>Chain</th><th>Key</th><th>Tier 1 items</th><th>Families</th><th>Families with ≥ 3 members</th>
<th>Items in those families</th><th>Single-member families</th></tr>{cover}</table>
<p class="mut">A family needs at least 3 members before a quorum is possible. A verdict needs a Tier 1 claim, so
Tier 2 items are left out.</p>

<h3>4.4 Suricata families on the full capture</h3>
<table><tr><th>Signature</th><th>Internal host</th><th>Members</th><th>Priority</th><th>Weight</th>
<th>Family change after 3 FPs</th><th>Unjudged members after</th><th>3rd member arrives at step</th></tr>{suri_top}</table>
<p class="mut">The last three columns are <b>predicted</b>: the product's <code>learn()</code> run on 3 agreeing false
positives, then the critical floor. They were not run on this database. Two of them were run live (section 4.6).</p>

<h3>4.5 Largest flow families on the full capture</h3>
<table><tr><th>Attack</th><th>Port</th><th>Protocol</th><th>Destination</th><th>Members</th><th>Priority range</th></tr>{flow_top}</table>
<p class="mut">The largest flow families are benign infrastructure traffic (DNS to 172.31.0.2, RDP to 172.31.65.56). Their
priority is already near 0, so learning cannot move them much: the guardrails clamp at 0. The flagged flow groups are
{n(ff["items"])} single-member families, so on this capture a flagged flow family cannot reach a quorum.</p>

<h3>4.6 Instances seen working</h3>
<table><tr><th>Chain</th><th>Family</th><th>Host</th><th>Verdicts</th><th>Result</th><th>Source</th></tr>{measured}</table>

<h3>4.7 How to show it on demo day</h3>
<ol><li>Let the replay reach step 24 or later (the flow family is complete at step 24; the Terminal Server family has
its 3rd alert at step 9).</li>
<li>As <code>g.ang</code>, search <b>Terminal Server</b>. Open two rows that are not the top one, and record
<b>False Positive</b> on each (verdicts 1 and 2: nothing else moves yet).</li>
<li>On stage, open a third row and record <b>False Positive</b>. The rows still marked <b>Available</b> drop from 40 to 10.</li>
<li>Search <b>131.202.240.72</b> and repeat on the flow family: the other <b>Available</b> row drops from 36.49 to 6.49.</li>
<li>Optional: one false positive on an ETERNALBLUE alert shows the floor: 85 → 70, never lower.</li></ol>
<div class="warn"><b>Limits to state.</b> The flagged-flow family key has no host, so a quorum would reach every host on
that port (the guardrails bound the size of the move, not its reach). A verdict changes the queue order; it never
changes the detector, the routing route or the Tier 2 decision. The frozen V3.1 evaluation was run before Suricata
reranking existed.</div>
"""


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
h3{margin:22px 0 6px}nav.toc{columns:2;font-size:14px;margin:8px 0 14px}nav.toc a{color:var(--flow)}
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
<p class="lead">The same packets feed two chains in parallel. The flow chain detects and groups; Suricata gives a
second, named opinion. Both arrive in <b>one</b> queue, behind <b>one</b> login, and <b>both</b> learn from analyst
verdicts through the same rule and the same guardrails. Sections 3 and 4 explain where the chains combine and how
a family learns.</p>
<div class="facts">{fact_html}</div>

<nav class="toc"><a href="#s1">1. Layout</a><br><a href="#s2">2. Stages</a><br>
<a href="#s3">3. Where the two chains combine</a><br><a href="#s4">4. Family learning</a><br>
<a href="#s5">5. Every unique end result</a><br><a href="#s6">6. Data trace for each end result</a><br>
<a href="#s7">7. Arrival during the replay</a><br><a href="#s8">8. Run it</a><br><a href="#s9">9. What this page does not show</a></nav>

<h2 id="s1">1. Layout</h2>
{svg()}
<div class="note">One sign-in page, one API, one database per workspace. The Admin chooses the workspace:
<b>Operational</b> or <b>Replay</b>. Every analyst then sees that workspace's single queue.</div>

<h2 id="s2">2. Stages</h2>
<table><tr><th>Id</th><th>Stage</th><th>What happens</th><th>Stored in</th></tr>
<tr><td colspan="4"><b>P · Packet capture</b> — 3 pcaps of capture day 2018-02-14, replayed in {TOT["steps"]} equal time steps</td></tr>
{stage_rows(FLOW_STAGES, "flow")}{stage_rows(SURI_STAGES, "suricata")}{stage_rows(SHARED, "")}</table>

<div id="s3"></div>{combine_section()}<div id="s4"></div>{families_section()}

<h2 id="s5">5. Every unique end result on the dashboard</h2>
<p>An end result is one distinct combination of chain, evidence, group or single, classification, route class,
priority band and route. The whole replay produces {len(RESULTS)}. Their counts add up to the queue.</p>
<table><tr><th>Id</th><th>Chain</th><th>Items</th><th>Title (example)</th><th>Evidence</th><th>Class</th>
<th>Route class</th><th>Band (priority)</th><th>Route</th></tr>{results_table()}</table>

<h2 id="s6">6. Data trace for each end result</h2>
<p class="mut">For each end result: one real record, every stage it passed, and what the other chain said about the same flow.</p>
{"".join(card(r) for r in RESULTS)}

<h2 id="s7">7. Arrival during the replay (every 10 steps)</h2>
<table><tr><th>Step</th><th>Flows in</th><th>Suricata admitted</th><th>Queue items</th><th>Groups</th>
<th>Group members</th><th>Tier 2 cases</th></tr>{progress_rows()}</table>

<h2 id="s8">8. Run it</h2>
<ol>
<li>Build the replay input once: <code>python scripts/build_packet_replay.py</code>.</li>
<li>Open <code>http://127.0.0.1:5173</code>. Sign in as <code>admin</code> / <code>admin-demo</code>. Open <b>Operational Workspace</b>.</li>
<li>To start from 0 alerts: click <b>Reset Replay</b> (it works while Replay is active and while analysts hold
claims; analysts move to Operational).</li>
<li>Choose <b>Packet Replay</b>. Click <b>Prepare Replay</b>, then <b>Activate</b>.</li>
<li>Click <b>Start Arrivals</b> for one step every 5 seconds (160 steps ≈ 13 minutes), or <b>Next Step</b> / <b>Next 5 Steps</b>.</li>
<li>Sign in as <code>g.ang</code> / <code>analyst-demo</code> in a second browser. New items arrive in the queue as the steps run.</li>
</ol>

<h2 id="s9">9. What this page does not show</h2>
<div class="warn"><ul>
<li><b>R2 is large.</b> {n(next(r["count"] for r in RESULTS if r["id"] == "R2"))} unflagged flows each become one low-priority
Tier 1 item (decision D4). This is product behaviour, not a replay artefact.</li>
<li><b>Stale reason text on R1.</b> A group is routed once, when its first members arrive. The stored reason gives the group
size at that time. The group then grows (to 5,100 and 11,613 flows).</li>
<li><b>Review is automatic in the replay.</b> S3 is recorded in the preparing Admin's name with a fixed reason.
In Operational, an analyst makes each S3 decision.</li>
<li>Recorded traffic, not live traffic. The model was trained on this testbed's dataset.</li>
<li>The other-chain link is by 5-tuple and time. It is shown here; the product does not yet show it in the alert panel.</li>
<li>The cross-chain escalation rule E1-suricata is not wired into the replay path (section 3.5).</li>
<li>Family predictions in 4.4 are computed with the product's functions, not run; the runs are in 4.6.</li>
</ul></div>
<footer>Generated by analysis/phase-f/workflow-layout/build_layout.py from trace.json and families.json
({n(TOT["steps"])} steps, replay {e(TOT["replaySeconds"])} s on a scratch database).</footer>
</main></body></html>"""


if __name__ == "__main__":
    OUT.write_text(page(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes), {len(RESULTS)} end results")
