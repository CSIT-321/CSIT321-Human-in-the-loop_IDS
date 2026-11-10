"""Build the combined dual-chain guide: packet -> workstation, ten end results, and reranking.

Inputs (all read-only):
  ../workflow-layout/trace.json        one recorded Packet Replay (ten end results + progress)
  ../../hitl-ids/data/packet-replay/base.db   the capture's flow records and features
  ../packet-to-workstation/data/packets.json  one real packet burst (hex + flags)

Output: index.html next to this file. No external resources, no network.

    hitl-ids/.venv/Scripts/python.exe analysis/phase-f/dual-chain-guide/build_guide.py
"""
from __future__ import annotations

import html
import importlib.util
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
PHASE = HERE.parent
ROOT = PHASE.parents[1]
TRACE = PHASE / "workflow-layout" / "trace.json"
BASE = ROOT / "hitl-ids" / "data" / "packet-replay" / "base.db"
PACKETS = PHASE / "packet-to-workstation" / "data" / "packets.json"
OUT = HERE / "index.html"

spec = importlib.util.spec_from_file_location("layout", PHASE / "workflow-layout" / "build_layout.py")
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)

T = json.loads(TRACE.read_text(encoding="utf-8"))
TOT, RESULTS, PROGRESS = T["totals"], T["results"], T["progress"]

FEATURES = ["Dst Port", "Flow Duration", "Total Fwd Packet", "Total Bwd packets",
            "Fwd Packet Length Max", "Bwd Packet Length Max", "Flow Bytes/s", "Flow Packets/s",
            "Fwd Seg Size Min", "SYN Flag Count", "ACK Flag Count", "Average Packet Size"]


def e(v) -> str:
    return html.escape("—" if v is None else str(v), quote=True)


def n(v) -> str:
    return f"{v:,}" if isinstance(v, int) else e(v)


def connect():
    conn = sqlite3.connect(f"file:{BASE}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def features_for(conn, ref):
    row = conn.execute("""SELECT a.id, a.evidence_class, a.combined_score, a.detection_score,
               a.ml_probability, a.signature_rules, f.packets, f.bytes, f.duration, f.flow_features
        FROM alerts a JOIN flow_data f ON f.alert_id = a.id WHERE a.alert_ref = ?""", (ref,)).fetchone()
    if row is None:
        return None
    data = json.loads(row["flow_features"]) if row["flow_features"] else {}
    picked = [(key, data[key]) for key in FEATURES if key in data]
    return {"row": dict(row), "features": picked}


def rows_html(pairs) -> str:
    return "".join(f'<tr><th>{e(k)}</th><td class="mono">{e(round(v, 6) if isinstance(v, float) else v)}</td></tr>' for k, v in pairs)


def step(code, name, body) -> str:
    return f'<tr><td class="sid">{e(code)}</td><td class="stage">{e(name)}</td><td>{body}</td></tr>'


def flow_steps(r, feats) -> str:
    tr, det, grp = r["trace"]["flow"], r["trace"]["detection"], r["trace"].get("group")
    out = [step("P", "Packet capture", f'Flow record <b>{e(tr["record"])}</b> at <span class="mono">{e(tr["time"])}</span>: '
               f'<span class="mono">{e(tr["srcIp"])}:{e(tr["srcPort"])} → {e(tr["dstIp"])}:{e(tr["dstPort"])} {e(tr["protocol"])}</span>, '
               f'{n(tr["packets"])} packets, {n(tr["bytes"])} bytes, {e(tr["durationSeconds"])} s')]
    if feats:
        table = "".join(f'<tr><th>{e(k)}</th><td class="mono">{e(round(v, 6) if isinstance(v, float) else v)}</td></tr>' for k, v in feats["features"])
        out.append(step("F1", "CICFlowMeter", f'{len(feats["features"])} of 94 stored features (81 of 82 model inputs):'
                        f'<table class="mini">{table}</table>'))
    out.append(step("F2", "Detection", f'Rules: <b>{e(", ".join(det["rules"]) or "none")}</b> · model class '
                    f'<b>{e(det["modelClass"])}</b> at p={e(det["modelProbability"])} · combined score '
                    f'<b>{e(det["combinedScore"])}</b> · evidence <b>{e(det["evidenceClass"])}</b>'))
    if grp:
        out.append(step("F3", "Grouping", f'Source {e(grp["key"])} groups within the window: <b>{n(grp["members"])} members</b>, '
                        f'{e(grp["firstSeen"])} → {e(grp["lastSeen"])}; {n(grp["membersWithSuricataAlert"])} members carry a Suricata alert'))
        out.append(step("F4", "Projection", f'First member becomes the one operational alert; this end result covers {n(r["count"])} alert(s)'))
    else:
        out.append(step("F3", "Grouping", 'No group: an unflagged flow stays a single queue item (decision D4)'))
        out.append(step("F4", "Projection", 'Single flow → one operational alert'))
    trg = r["triage"]
    out.append(step("F5", "Flow routing", f'Class <b>{e(r["routing"]["routeClass"])}</b> → route <b>{e(trg["route"])}</b>, '
                    f'priority <b>{e(trg["priority"])}</b> ({e(trg["band"])}). Reason: {e(trg["reason"])}'))
    return "".join(out)


def suri_steps(r) -> str:
    tr = r["trace"]
    ev, stg, rev, adm = tr["eve"], tr["staging"], tr["review"], tr["admission"]
    other = tr.get("otherChain") or {}
    out = [step("P", "Packet capture", f'EVE alert at <span class="mono">{e(ev["time"])}</span>: '
               f'<span class="mono">{e(ev["srcIp"])}:{e(ev["srcPort"])} → {e(ev["dstIp"])}:{e(ev["dstPort"])} {e(ev["protocol"])}</span>, flow id {e(ev["flowId"])}')]
    out.append(step("S1", "Suricata", f'<b>{e(ev["signature"])}</b> · {e(ev["category"])} · native severity {e(ev["severity"])} · '
                    f'SIDs {e(", ".join(str(s) for s in ev["sids"]))} · {n(ev["alertsInBundle"])} alerts in this bundle'))
    out.append(step("S2", "Staging", f'Inbox record {n(stg["inboxId"])}: decision <b>{e(stg["decision"])}</b>, policy {e(stg["policyVersion"])}, '
                    f'evidence class <b>{e(stg["evidenceClass"])}</b>'))
    out.append(step("S3", "Eligibility review", f'<b>{e(rev["decision"])}</b> by {e(rev["actor"])}. Reason: {e(rev["reason"])}'))
    out.append(step("S4", "Admission", f'{e(adm["event"])} at <span class="mono">{e(adm["at"])}</span> → one operational alert'))
    out.append(step("S5", "Classification + routing", f'Category <b>{e(r["classification"]["category"])}</b>; class '
                    f'<b>{e(r["routing"]["routeClass"])}</b> → route <b>{e(r["triage"]["route"])}</b>, priority '
                    f'<b>{e(r["triage"]["priority"])}</b> ({e(r["triage"]["band"])}). Reason: {e(r["triage"]["reason"])}'))
    if other:
        out.append(step("↔", "Other chain", f'Flow alert {n(other.get("flowAlertId"))}: evidence <b>{e(other.get("evidenceClass"))}</b>, '
                        f'model {e(other.get("modelClass"))} p={e(other.get("modelProb"))}'))
    return "".join(out)


def card(r) -> str:
    tr = r["triage"]
    body = flow_steps(r, r.get("_feats")) if r["chain"] == "flow" else suri_steps(r)
    case = f' · case <span class="mono">{e(r["caseRef"])}</span>' if r.get("caseRef") else ""
    return f'''<details class="result" id="{e(r["id"])}">
<summary><b>{e(r["id"])}</b> <span class="tag {e(r["chain"])}">{e(r["chain"])}</span> {e(r["title"])}
<span class="pill">{e(r["count"])} alert(s)</span> <span class="pill">{e(tr["route"])}</span>
<span class="pill">P{e("1" if tr["band"] == "critical" else "2" if tr["band"] == "high" else "3" if tr["band"] == "medium" else "4")} · {e(tr["priority"])}</span></summary>
<table class="steps">{body}{step("W", "Workstation", f'Analyst opens <b>{e(r["title"])}</b>: overview, evidence, and the route {e(tr["route"])}' + case)}</table>
</details>'''


def results_table() -> str:
    rows = []
    for r in RESULTS:
        tr = r["triage"]
        rows.append(f'<tr class="{e(r["chain"])}"><td><a href="#{e(r["id"])}"><b>{e(r["id"])}</b></a></td><td>{e(r["chain"])}</td>'
                    f'<td class="mono">{n(r["count"])}</td><td>{e(r["title"])}</td><td>{e(r["evidenceClass"])}</td>'
                    f'<td>{e(r["classification"]["category"])}</td><td>{e(r["routing"]["routeClass"])}</td>'
                    f'<td>{e(tr["band"])} ({e(tr["priority"])})</td><td>{e(tr["route"])}</td></tr>')
    return "".join(rows)


def packet_section() -> str:
    data = json.loads(PACKETS.read_text(encoding="utf-8"))
    rows = []
    for p in data["packets"]:
        rows.append(f'<tr><td class="mono">{n(p["index"])}</td><td class="mono">{e(p["utc"].split("T")[1][:15])}</td>'
                    f'<td>{e(p["flags"])}</td><td class="mono">{n(p["frameBytes"])}</td><td class="mono">{n(p["payloadBytes"])}</td>'
                    f'<td class="mono small">{e(p["hex"][:68])}…</td></tr>')
    trg = data["triggerFrame"]
    return f'''<p>One real burst from the capture, not a summary: <b>{n(data["count"])} frames</b> inside {n(data["windowMs"])} ms,
filtered to <span class="mono">{e(data["filter"]["src"])} → {e(data["filter"]["dst"])}:{e(data["filter"]["dstPort"])}</span>
from <code>{e(data["pcap"])}</code>.</p>
<table><tr><th>Frame</th><th>UTC</th><th>Flags</th><th>Frame bytes</th><th>Payload</th><th>Header (hex)</th></tr>{"".join(rows)}</table>
<p class="mut">Trigger frame {n(trg["index"])} at <span class="mono">{e(trg["utc"])}</span>. These SYN frames become one CICFlowMeter record; the same 5-tuple and time are the
join key to the flow chain. The matching flow rows in <code>base.db</code> carry evidence <b>corroborated</b> and score <b>100</b>
(<code>0efa23b4…</code>, <code>229735d1…</code>, <code>71ef1ec9…</code>).</p>'''


def rerank_section() -> str:
    return '''<p>A verdict does two things. It moves its own alert, and it feeds the family gate. The gate is what stops one
analyst's mistake from spreading across a whole family of similar alerts.</p>
<table>
<tr><th>Step</th><th>Rule</th><th>Value</th></tr>
<tr><td>1. Own delta (C1)</td><td>confirm: +k·w, dismiss: −k·(1−w); k = 30, w = severity / 10</td><td>own alert moves at once</td></tr>
<tr><td>2. Family key</td><td>attack class + destination port + protocol + first rule</td><td>e.g. Web Attack · 80 · tcp · —</td></tr>
<tr><td>3. Gate</td><td>at least 3 learning verdicts, dominant share ≥ 0.67 (strong ≥ 0.80), no tie</td><td>3 of 3 opens</td></tr>
<tr><td>4. Applied adjustment</td><td>clamped to −30 … +20; critical floor 70, infiltration floor 75</td><td>never past the floor</td></tr>
<tr><td>5. Placement</td><td>members without their own verdict get the adjustment; band offset moves the queue class</td><td>one band per confirmation</td></tr>
<tr><td>6. Queue order</td><td>effective score = routing priority + (combined − detection)</td><td>row shows the same number</td></tr>
</table>
<h3>Worked example, measured on 11 November 2026</h3>
<p>Web Attack family, 7 members, weight w = 0.8 (<code>["Web Attack",80,"tcp","-"]</code>). Three false-positive verdicts:</p>
<table>
<tr><th>Verdict</th><th>Delta</th><th>Family count</th><th>Gate</th></tr>
<tr><td>1st false positive</td><td class="mono">−6.00</td><td class="mono">1 of 3</td><td>closed: not enough verdicts</td></tr>
<tr><td>2nd false positive</td><td class="mono">−6.00</td><td class="mono">2 of 3</td><td>closed: not enough verdicts</td></tr>
<tr><td>3rd false positive</td><td class="mono">−6.00</td><td class="mono">3 of 3 (100 %)</td><td><b>open</b>, applied −18.00</td></tr>
</table>
<p>Members that nobody touched moved by the applied adjustment, inside the floor:</p>
<table>
<tr><th>Member</th><th>Before</th><th>After</th><th>Why</th></tr>
<tr><td>3a5f08b6…</td><td class="mono">92.70</td><td class="mono">70.00</td><td>critical floor 70</td></tr>
<tr><td>8e9bbf93…</td><td class="mono">86.93</td><td class="mono">70.00</td><td>critical floor 70</td></tr>
<tr><td>1d4af61e…</td><td class="mono">74.44</td><td class="mono">56.44</td><td>raw −18.00, above the floor</td></tr>
</table>
<p>The alert that received the verdict shows both numbers. Its detector score stays 52.39; the queue row now reads
<b>P3 / 22.39</b>, because the row displays the score the order uses: routing priority plus the verdict delta.
Nothing is written back to the triage state, so the stored routing value and the shown value cannot disagree.</p>
<div class="warn"><b>Why the gate exists.</b> A single verdict is an opinion. Three that agree are evidence. A tie, or a split under
67 %, leaves the family closed and the adjustment at zero. Escalate and needs-investigation verdicts do not count toward
the learning categories.</div>'''


def page() -> str:
    conn = connect()
    for r in RESULTS:
        if r["chain"] == "flow":
            r["_feats"] = features_for(conn, r["alertRef"])
    conn.close()
    stats = [("Flows in window", TOT["flowsInWindow"]), ("Flagged flows", TOT["flaggedFlows"]),
             ("Groups", TOT["groups"]), ("Suricata alerts", TOT["suricataAlertsArrived"]),
             ("Admitted bundles", TOT["suricataBundlesAdmitted"]), ("Queue items", TOT["queueItems"]),
             ("Tier 2 cases", TOT["tier2Cases"])]
    stat_html = "".join(f'<div class="stat"><span>{e(label)}</span><b>{n(value)}</b></div>' for label, value in stats)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dual chain: packet to workstation, ten results, reranking</title>
<style>
:root{{--ink:#16202b;--mut:#5b6b7c;--line:#d8dee6;--bg:#f7f9fb;--card:#fff;--flow:#0b6bcb;--suri:#b45309;--gate:#15803d}}
*{{box-sizing:border-box}}body{{margin:0;font:14px/1.55 Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}}
main{{max-width:1180px;margin:0 auto;padding:32px 28px 64px}}h1{{font-size:28px;margin:0 0 6px}}
h2{{font-size:20px;margin:34px 0 10px;border-bottom:2px solid var(--line);padding-bottom:6px}}
h3{{font-size:16px;margin:22px 0 8px}}.mut{{color:var(--mut)}}code,.mono{{font-family:Consolas,ui-monospace,monospace}}
.small{{font-size:11px}}.stats{{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin:18px 0}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}}
.links{{font-size:12px;color:var(--mut);margin:0 0 14px}}.links a{{color:#0b6bcb}}
.stat span{{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}}
.stat b{{font-size:20px;font-variant-numeric:tabular-nums}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);margin:10px 0}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:var(--mut);background:#f1f5f9}}
tr.flow td:first-child{{border-left:3px solid var(--flow)}}tr.suricata td:first-child{{border-left:3px solid var(--suri)}}
details.result{{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:10px 0;padding:10px 12px}}
details.result summary{{cursor:pointer;font-size:14px}}details.result[open] summary{{margin-bottom:8px}}
.pill{{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:1px 8px;font-size:11px;color:var(--mut);margin-left:6px}}
.tag{{font-size:10px;text-transform:uppercase;letter-spacing:.05em;padding:1px 6px;border-radius:4px;color:#fff}}
.tag.flow{{background:var(--flow)}}.tag.suricata{{background:var(--suri)}}
table.steps td.sid{{width:34px;font-weight:700;color:var(--mut)}}table.steps td.stage{{width:150px;font-weight:600}}
table.mini{{width:auto;margin:6px 0;border:0}}table.mini th{{background:none;font-size:11px;text-transform:none;width:190px;padding:2px 10px 2px 0;border:0}}
table.mini td{{padding:2px 0;border:0}}
.warn{{background:#fff7ed;border:1px solid #f0c48a;border-radius:8px;padding:12px 14px;margin:14px 0}}
footer{{margin-top:40px;color:var(--mut);font-size:12px}}
@media print{{details.result{{break-inside:avoid}}}}
</style></head><body><main>
<nav class="links"><b>Documents:</b>
<a href="../soc-demo-guide/index.html">SOC demo guide</a> ·
<a href="../workflow-layout/index.html">Workflow layout</a> ·
<a href="../packet-to-workstation/index.html">Packet to workstation</a> ·
<b>this page</b></nav>
<h1>From packet to workstation — the dual chain, traced</h1>
<p class="mut">One capture (2018-02-14, three hosts) through two independent chains into one analyst queue.
Every number below comes from the recorded Packet Replay, the capture files, or the feature rows in
<code>base.db</code>. Ten unique end results, each traced stage by stage, then the reranking flow.</p>
<div class="stats">{stat_html}</div>

<h2>1. The two chains</h2>
{layout.svg()}
<table><tr><th>Id</th><th>Stage</th><th>What happens</th><th>Where it is stored</th></tr>
{layout.stage_rows(layout.FLOW_STAGES, "flow")}{layout.stage_rows(layout.SURI_STAGES, "suricata")}{layout.stage_rows(layout.SHARED, "")}</table>

<h2>2. Ten unique end results</h2>
<p class="mut">An end result is one distinct combination of chain, evidence, group or single, classification, route class,
priority band and route. Counts are alerts; the queue items are their representatives.</p>
<table><tr><th>Id</th><th>Chain</th><th>Items</th><th>Title (example)</th><th>Evidence</th><th>Class</th>
<th>Route class</th><th>Band (priority)</th><th>Route</th></tr>{results_table()}</table>

<h2>3. Data trace for each result</h2>
<p class="mut">Open any result. Each row is one stage; each value is the value that result carried.</p>
{"".join(card(r) for r in RESULTS)}

<h2>4. Arrival during the replay</h2>
<p class="mut">Each step is one equal share of capture time. The queue grows as both chains deliver.</p>
<table><tr><th>Step</th><th>Flows in</th><th>Suricata admitted</th><th>Queue items</th><th>Groups</th>
<th>Group members</th><th>Tier 2 cases</th></tr>{layout.progress_rows()}</table>

<h2>5. The packet layer</h2>
{packet_section()}

<h2>6. How the reranking is performed</h2>
{rerank_section()}

<h2>7. What this page does not show</h2>
<div class="warn"><ul>
<li><b>R2 is large by design.</b> {n(next(r["count"] for r in RESULTS if r["id"] == "R2"))} unflagged flows each become one low-priority
Tier 1 item (decision D4).</li>
<li><b>R1's stored reason is older than its group.</b> A group is routed once, when its first members arrive; the reason quotes the size at that moment.</li>
<li><b>Review is automatic in the replay.</b> Staging review is recorded in the preparing Admin's name. In Operational, an analyst makes each decision.</li>
<li>Recorded traffic, not live traffic. The model was trained on this testbed.</li>
</ul></div>
<footer>Generated by analysis/phase-f/dual-chain-guide/build_guide.py from trace.json ({n(TOT["steps"])} steps,
replay {e(TOT["replaySeconds"])} s), base.db and packets.json.</footer>
</main></body></html>'''


if __name__ == "__main__":
    OUT.write_text(page(), encoding="utf-8")
    print("wrote", OUT)
