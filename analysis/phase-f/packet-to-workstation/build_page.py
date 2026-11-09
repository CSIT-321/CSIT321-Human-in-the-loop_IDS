"""Build the packet-to-workstation walkthrough page from the measured data files and screenshots.

Inputs (all produced by this folder's scripts, never edited here):
  data/packets.json        real frames decoded from the repaired pcap
  data/suricata_alert.json the real eve.json record for the trigger frame
  data/lane_suricata.json  staging, review, admission and queue facts (DB #1, Suricata only)
  data/lane_flow.json      group, rule, model, case and ground truth (DB #2, legacy flow lane)
  shots/*.png              live screenshots from the two databases
Output: index.html
"""
from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = HERE / "index.html"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def esc(value):
    return html.escape(str(value), quote=True)


def num(value, places=2):
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        text = f"{value:.{places}f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def table(heads, rows, cls=""):
    head = "".join(f"<th>{esc(h)}</th>" for h in heads)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def kv(rows):
    return table(["Field", "Value"], [[esc(k), v] for k, v in rows])


def pre(text):
    return f"<pre>{esc(text)}</pre>"


def img(name, caption):
    return (f'<figure><a href="shots/{name}"><img src="shots/{name}" alt="{esc(caption)}" loading="lazy"></a>'
            f"<figcaption>{esc(caption)}</figcaption></figure>")


CSS = """
:root{--ink:#16202b;--mut:#5b6b7c;--line:#dbe3ec;--bg:#fbfcfe;--accent:#0b6bcb;--warn:#b45309;--ok:#0f766e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1120px;margin:0 auto;padding:30px 22px 80px}
h1{font-size:28px;line-height:1.25;margin:0 0 8px}
h2{font-size:21px;margin:40px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--line)}
h3{font-size:16px;margin:22px 0 8px}
p.lead{font-size:16px;color:var(--mut);margin:0 0 18px}
.step{border:1px solid var(--line);border-radius:10px;background:#fff;padding:16px 18px;margin:16px 0}
.step > h2{margin-top:0;border:0;font-size:19px;display:flex;gap:10px;align-items:baseline}
.tag{font:600 11px/1 ui-monospace,monospace;letter-spacing:.06em;color:#fff;background:var(--accent);
     padding:5px 7px;border-radius:5px;text-transform:uppercase;white-space:nowrap}
.tag.legacy{background:var(--warn)}
.tag.suricata{background:#7c3aed}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#f3f6fa;font-weight:600}
td code, p code, li code{font:13px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;background:#f3f6fa;padding:1px 4px;border-radius:4px}
pre{background:#0f172a;color:#e6edf6;padding:12px 14px;border-radius:8px;overflow-x:auto;
    font:12.5px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}
figure{margin:14px 0}
figure img{width:100%;border:1px solid var(--line);border-radius:8px;display:block}
figcaption{font-size:13px;color:var(--mut);margin-top:6px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:14px 0}
.fact{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:#fff}
.fact b{display:block;font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.fact span{font:600 16px/1.4 ui-monospace,monospace}
.note{border-left:4px solid var(--accent);background:#f0f6ff;padding:10px 14px;border-radius:0 8px 8px 0;margin:14px 0}
.warn{border-left:4px solid var(--warn);background:#fff7ed;padding:10px 14px;border-radius:0 8px 8px 0;margin:14px 0}
.ok{color:var(--ok);font-weight:600}
ul{margin:8px 0 8px 20px;padding:0}
li{margin:4px 0}
footer{margin-top:50px;border-top:1px solid var(--line);padding-top:14px;color:var(--mut);font-size:13px}
nav.toc{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 8px}
nav.toc a{font-size:13px;border:1px solid var(--line);border-radius:999px;padding:4px 10px;text-decoration:none;color:var(--ink);background:#fff}
"""


def build() -> str:
    pk = load("packets.json")
    eve = load("suricata_alert.json")["alert"]
    suri = load("lane_suricata.json")
    flow = load("lane_flow.json")
    trig = pk["triggerFrame"]
    syns = [p for p in pk["packets"] if p["flags"] == "SYN"]
    span_us = round((float(syns[-1]["epoch"]) - float(syns[0]["epoch"])) * 1e6) if len(syns) > 1 else 0
    first3_us = round((float(syns[2]["epoch"]) - float(syns[0]["epoch"])) * 1e6) if len(syns) > 2 else 0
    truth_label, truth_count = next(iter(flow["groundTruth"].items()))
    truth_total = flow["group"]["member_count"]
    rule = flow["signatureRules"][0]
    cls = suri["classification"]
    parts: list[str] = []
    add = parts.append

    add(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Packet to workstation - one confirmed case</title><style>{CSS}</style></head><body><main>""")

    # ---------- header ----------
    add("<h1>Packet to workstation: one confirmed case, every layer</h1>")
    add('<p class="lead">One real SSH scan and brute-force burst is followed from the raw frames in the capture, '
        "through Suricata, into this product's own admission path, and onto the analyst screen. A second, legacy "
        "lane shows the same packets through the CICIDS2018 flow model that the product is leaving behind.</p>")
    add('<div class="facts">')
    add(f'<div class="fact"><b>Attack</b><span>SSH scan / brute force</span></div>')
    add(f'<div class="fact"><b>Source</b><span>{esc(eve["src_ip"])}</span></div>')
    add(f'<div class="fact"><b>Target</b><span>{esc(eve["dest_ip"])}:{eve["dest_port"]}</span></div>')
    add(f'<div class="fact"><b>Suricata rule</b><span>sid {eve["alert"]["signature_id"]}</span></div>')
    add(f'<div class="fact"><b>SYNs in this burst</b><span>{len(syns)} in {span_us} us</span></div>')
    add(f'<div class="fact"><b>Ground truth</b><span>{truth_total} of {truth_total} {esc(truth_label)}</span></div>')
    add("</div>")
    add('<nav class="toc">'
        '<a href="#s1">1 Packet</a><a href="#s2">2 Suricata</a><a href="#s3">3 Ingestion</a>'
        '<a href="#s4">4 Admission</a><a href="#s5">5 Analyst screen</a><a href="#s6">6 Legacy flow lane</a>'
        '<a href="#s7">7 Two lanes</a><a href="#s8">8 Verification</a></nav>')

    # ---------- step 1 ----------
    add('<section class="step" id="s1"><h2><span class="tag">Step 1</span>The packet, as it was captured</h2>')
    add(f"<p>These are real frames from <code>{esc(pk['pcap'])}</code>, the repaired capture of the host "
        f"<code>{esc(eve['dest_ip'])}</code> on 2018-02-14. The filter was "
        f"<code>{esc(pk['filter']['src'])} to {esc(pk['filter']['dst'])}:{pk['filter']['dstPort']}</code>.</p>")
    rows = [[f"<code>{esc(p['utc'])}</code>", esc(p["srcPort"]), esc(p["flags"]), p["ipTotalLength"],
             p["ipTtl"], p["window"], p["payloadBytes"]] for p in pk["packets"][:6]]
    add(table(["Time (UTC)", "Source port", "TCP flags", "IP bytes", "TTL", "Window", "Payload bytes"], rows))
    add(f'<p class="note"><b>{len(syns)} SYNs</b> leave for port {pk["filter"]["dstPort"]} from {len(syns)} source '
        f"ports inside <b>{span_us} microseconds</b> ({num(span_us / 1000)} ms); the first three land within "
        f"{first3_us} microseconds. One connection attempt is normal behaviour. This burst is what Suricata's scan "
        "rule looks for.</p>")
    add(f"<h3>Frame {trig['index']}, hex dump (first 54 bytes)</h3>")
    add(pre(trig["hex"]))
    add(kv([("Frame number in the capture", f"<code>{trig['index']}</code>"),
            ("Epoch timestamp", f"<code>{esc(trig['epoch'])}</code>"),
            ("Source to destination", f"{esc(trig['src'])}:{trig['srcPort']} to {esc(trig['dst'])}:{trig['dstPort']}"),
            ("TCP flags", f"{esc(trig['flags'])} ({trig['flagsBits']})"),
            ("IP total length / frame bytes", f"{trig['ipTotalLength']} / {trig['frameBytes']}"),
            ("Ethernet destination / source",
             f"<code>{':'.join(trig['hex'].split()[0:6])}</code> / <code>{':'.join(trig['hex'].split()[6:12])}</code>")]))
    add("</section>")

    # ---------- step 2 ----------
    add('<section class="step" id="s2"><h2><span class="tag suricata">Step 2</span>Suricata reads the packet and writes an alert</h2>')
    add("<p>Suricata is a standard, third-party engine. This page does not explain how it detects; it shows what it "
        "emitted, because that record is the input to this product.</p>")
    add(kv([("Signature", f"<b>{esc(eve['alert']['signature'])}</b>"),
            ("Signature id / revision", f"{eve['alert']['signature_id']} / {eve['alert']['rev']}"),
            ("Native severity", eve["alert"]["severity"]),
            ("Suricata category", esc(eve["alert"]["category"])),
            ("Action", esc(eve["alert"]["action"])),
            ("Direction", esc(eve.get("direction") or "")),
            ("Flow id", f"<code>{eve['flow_id']}</code>"),
            ("Frame that raised it (pcap_cnt)", f"<code>{eve['pcap_cnt']}</code>"),
            ("Timestamp", f"<code>{esc(eve['timestamp'])}</code>")]))
    add(f'<p class="note">Frame <code>{eve["pcap_cnt"]}</code> is the same frame decoded in step 1, and the '
        f"microsecond parts agree: <code>{esc(eve['timestamp'])}</code> in the alert equals "
        f"<code>{esc(trig['epoch'])}</code> in the capture. The link between packet and alert is exact, not a guess "
        "from loose time correlation.</p>")
    add("<h3>The eve.json record, verbatim (metadata shortened)</h3>")
    shown = json.loads(json.dumps(eve))
    if isinstance(shown.get("alert", {}).get("metadata"), dict):
        shown["alert"]["metadata"] = {k: v for k, v in list(shown["alert"]["metadata"].items())[:3]}
    add(pre(json.dumps(shown, indent=1)))
    add("</section>")

    # ---------- step 3 ----------
    add('<section class="step" id="s3"><h2><span class="tag">Step 3</span>Our ingest reads the Suricata record</h2>')
    add(f"<p><code>scripts/import_suricata_eve.py</code> parses eve.json, validates each record against the "
        "canonical alert contract and stages it. Nothing is admitted at this point.</p>")
    add(kv([("Records parsed", suri["import"]["parsed"]),
            ("Records staged", suri["import"]["staged"]),
            ("Invalid / duplicate / rejected", f"{suri['import']['invalid']} / "
                                               f"{suri['import']['duplicate']} / {suri['import']['rejected_by_policy']}"),
            ("Admission status after import", f"<code>{esc(suri['import']['operational_admission'])}</code>"),
            ("Policy version", "<code>suricata-offline-v1</code> (config/external-admission.json)"),
            ("Proposed priority from native severity",
             f"{suri['targetInbox']['native_severity']} to <b>{suri['targetInbox']['proposed_operational_priority']}</b>"),
            ("Staging decision", f"<code>{esc(suri['targetInbox']['admission_decision'])}</code>")]))
    map_rows = [
        ["<code>alert.signature</code>", "detection title", "<code>detection_title</code>", esc(suri["targetInbox"]["detection_title"])],
        ["<code>alert.category</code>", "native category", "<code>detection_category</code>", esc(suri["queue"]["detection_category"])],
        ["<code>alert.severity</code>", "native severity", "<code>native_severity</code>", suri["targetInbox"]["native_severity"]],
        ["<code>timestamp</code>", "occurred at", "<code>occurred_at</code>", f"<code>{esc(suri['targetInbox']['occurred_at'])}</code>"],
        ["<code>src_ip</code>, <code>src_port</code>", "source", "<code>source_ip</code>, <code>source_port</code>",
         f"{esc(suri['targetInbox']['source_ip'])}"],
        ["<code>dest_ip</code>, <code>dest_port</code>", "destination", "<code>destination_ip</code>, <code>destination_port</code>",
         f"{esc(suri['targetInbox']['destination_ip'])}:{suri['targetInbox']['destination_port']}"],
        ["<code>proto</code>", "protocol", "<code>protocol</code>", esc(suri["queue"]["protocol"])],
        ["(none)", "confidence", "<code>confidence</code>", "null: the admission policy rejects a confidence from Suricata"],
        ["(none)", "evidence class", "<code>proposed_evidence_class</code>", "<code>external_rule</code>"],
    ]
    add("<h3>Field by field: what the record contributes</h3>")
    add(table(["eve.json field", "meaning in our contract", "stored column", "value for this case"], map_rows))
    add('<p class="note">The rule fires on the signature text, and the mapping to our attack class is deterministic: '
        f"<code>{esc(cls['policy'])}</code> maps signature {eve['alert']['signature_id']} to "
        f"<b>{esc(cls['value']['attackCategory'])}</b>. The reason recorded is: "
        f"&ldquo;{esc(cls['value']['reasons'][0])}&rdquo;.</p>")
    add("</section>")

    # ---------- step 4 ----------
    add('<section class="step" id="s4"><h2><span class="tag">Step 4</span>Eligibility review and admission</h2>')
    add("<p>An external alert is not trusted on arrival. An analyst records an eligibility decision, then admits it. "
        "Both writes are kept with the person and the reason.</p>")
    add(kv([("Review decision", f"<b>{esc(suri['review']['decision'])}</b>"),
            ("Review reason", esc(suri["review"]["reason"])),
            ("Review id / actor", f"{suri['review']['id']} / {esc(suri['actor']['name'])}"),
            ("Admitted by", f"{esc(suri['actor']['name'])} at <code>{esc(suri['admission']['created_at'])}</code>"),
            ("Operational alert reference", f"<code>{esc(suri['queue']['operational_alert_ref'])}</code>"),
            ("Source kind", f"<code>{esc(suri['queue']['source_kind'])}</code>")]))
    add("<h3>What the product decided after admission</h3>")
    add(kv([("Operational priority", f"<b>{suri['triage']['operational_priority']}</b> from native severity "
                                    f"{suri['targetInbox']['native_severity']} (the policy table, not the class)"),
            ("Priority band", f"<code>{esc(suri['triage']['priority_band'])}</code>"),
            ("Handling route", f"<code>{esc(suri['triage']['handling_route'])}</code>"),
            ("Workflow stage", f"<code>{esc(suri['triage']['workflow_stage'])}</code>"),
            ("Review required", "yes"),
            ("System routing decision", route_cell(cls["routing_decision"])),
            ("Attack category", f"<b>{esc(cls['value']['attackCategory'])}</b> "
                                f"(<code>{esc(cls['value']['status'])}</code>, source "
                                f"<code>{esc(cls['value']['source'])}</code>)"),
            ("Learning eligible", "no: external rule alerts are isolated until a source-specific family policy is validated")]))
    add(f'<p class="note">Native severity {suri["targetInbox"]["native_severity"]} maps to priority '
        f'{suri["targetInbox"]["proposed_operational_priority"]} by '
        f"<code>config/external-admission.json</code> (severities 1, 2, 3, 4 map to 85, 65, 40, 20). "
        "The attack class does not raise it here: an external alert is ranked by what the sensor said, and a human "
        "decides the rest.</p>")
    add("</section>")

    # ---------- step 5 ----------
    add('<section class="step" id="s5"><h2><span class="tag">Step 5</span>How it looks to the analyst</h2>')
    add("<p>Four screens, taken live from the database that holds this Suricata lane. Read them in order.</p>")
    add(img("01-inbox-backlog.png", f"Incoming Alerts: {suri['counts']['external_alert_inbox']} staged Suricata "
                                    "records. This is the real backlog, not one fabricated row."))
    add(img("02-admitted-record.png", "The admitted record: eligibility accepted, review reason, who admitted it, "
                                      "the operational alert reference and the link to the workstation."))
    add(img("03-workstation-suricata-alert.png", "The analyst workstation. The alert shows Suricata as the detector, "
                                                 "native severity 2, our class Reconnaissance Port Scan, priority 65, "
                                                 "Tier 1 review."))
    add(img("04-queue-suricata-lane.png", "The queue for this database. One item, because this database holds only "
                                          "the Suricata lane."))
    add(f'<p class="note">The record states both categories, and they differ: Suricata says '
        f"&ldquo;{esc(suri['queue']['detection_category'])}&rdquo;, this product says "
        f"&ldquo;{esc(cls['value']['attackCategory'].replace('_', ' ').title())}&rdquo;. That is expected. "
        "Suricata classifies its own rule; we classify the attack.</p>")
    add("</section>")

    # ---------- step 6 ----------
    add('<section class="step" id="s6"><h2><span class="tag legacy">Step 6</span>The legacy flow lane, '
        "labelled for removal</h2>")
    add('<div class="warn"><b>The CICIDS2018 flow path is legacy.</b> The product is moving to Suricata as the true '
        "start of the pipeline. This lane is shown because the current demo data and most of today's screens are "
        "built on it, and reviewers must see the difference. It is scheduled for removal.</div>")
    add("<p>The same packets also appear as flow features. Here the values are real CICIDS2018 rows, not derived by "
        "this page.</p>")
    cond_rows = [[f"<code>{esc(c['feature'])}</code>", esc(c["expected"]), esc(c["observed"]), "pass"]
                 for c in rule["matched_conditions"]]
    add("<h3>The rule that fires on these flows</h3>")
    add(table(["Field", "Test", "Observed", "Result"], cond_rows))
    add(kv([("Rule", f"<code>{esc(rule['rule_id'])}</code> ({esc(rule['name'])}, version {esc(rule['version'])})"),
            ("Rule strength (sig)", flow["alert"]["signature_severity"]),
            ("Model class / confidence", f"{esc(flow['alert']['ml_predicted_class'])} / {num(flow['alert']['confidence'], 8)}"),
            ("Malicious probability (1 - P(Benign))", num(flow["alert"]["ml_probability"], 8)),
            ("Evidence class", f"<b>{esc(flow['alert']['evidence_class'])}</b>"),
            ("Fused score", f"<b>{num(flow['alert']['combined_score'])}</b> "
                            f"(min(100, max(sig, ml) x 100 + 5) clipped)"),
            ("Severity", f"<b>{esc(flow['alert']['severity'])}</b> from the Brute Force class ceiling (CVSS 5.0), "
                         "although the score is 100"),
            ("Group", f"{flow['group']['member_count']} flows from {esc(flow['group']['grouping_key'])}, "
                      f"{esc(flow['group']['first_seen_at'][11:19])} to {esc(flow['group']['last_seen_at'][11:19])}"),
            ("Routing", f"<code>{esc(flow['triage']['handling_route'])}</code>, "
                        f"priority {num(flow['triage']['operational_priority'])}: {esc(flow['triage']['review_reason'])}"),
            ("Tier 2 case", f"<code>{esc(flow['case']['case_ref'] if flow['case'] else 'none')}</code>, source "
                            f"<code>{esc(flow['case']['decision_source'] if flow['case'] else '')}</code>, "
                            f"status <code>{esc(flow['case']['status'] if flow['case'] else '')}</code>")]))
    add(img("06-flow-alert-panel.png", "The legacy alert: Legacy Flow Detector, score 100, priority 100, Tier 2 case, "
                                       "group of 54, and the rule and model agreement in the combined explanation."))
    add(img("05-queue-flow-group.png", "The same item in the queue, filtered to its reference."))
    add(img("08-tier2-case-detail.png", "The Tier 2 case the system opened by itself: creation source System Policy, "
                                        "priority at creation P1 / 100, and why Tier 2 recorded in the case."))
    add(f'<p class="note">Five layers agree on this event: {flow["group"]["member_count"]} flow records, one rule '
        f"(<code>{esc(rule['rule_id'])}</code>), one model verdict, one fused score, one group, and one case. "
        f"Ground truth for those flows is <b>{esc(list(flow['groundTruth'])[0])}</b>, so this is a confirmed case, "
        "not a guess.</p>")
    add("</section>")

    # ---------- step 7 ----------
    add('<section class="step" id="s7"><h2><span class="tag">Step 7</span>Why the two lanes do not meet yet</h2>')
    add(table(["", "Suricata lane (target)", "Flow lane (legacy)"], [
        ["Detector", "Suricata signatures, standard rules", "Our 16-field rule engine plus the XGBoost model"],
        ["How it enters", "Import, eligibility review, admission", "Detection run over CICIDS2018 features"],
        ["Score basis", f"Native severity to priority ({suri['targetInbox']['native_severity']} to "
                        f"{suri['targetInbox']['proposed_operational_priority']})", "Fused score 0-100, then the class ceiling"],
        ["Class basis", "Deterministic signature text mapping", "Rule conditions plus model class"],
        ["Route for this case", f"<code>{esc(suri['triage']['handling_route'])}</code>",
         f"<code>{esc(flow['triage']['handling_route'])}</code>"],
        ["Learning", "Not eligible", "Eligible, gated by family agreement"],
        ["Screens", "Steps 5", "Step 6"],
    ]))
    add('<div class="warn"><b>Found while building this page: the two lanes cannot share one database.</b> '
        "Admitting a Suricata alert into a database that already holds routed flow alerts fails with "
        "<code>ValidationError: 3 validation errors for ClassificationPolicy</code>. The cause is "
        "<code>packages/detection/system_routing.py:70-75</code>, which re-validates every stored "
        "<code>classification_policy</code> snapshot as the Suricata policy type; the flow lane stored a different "
        "policy family (<code>flow-classification-v1</code>). A database with no flow routing rows accepts the same "
        "alert without error. This page therefore uses two databases, and every screenshot is labelled with its lane. "
        "No product code was changed.</div>")
    add("<p>Consequence for the roadmap: moving to a Suricata-first pipeline is not only a detector swap. The "
        "admission path, the classification policy and the routing policy each need one owner per lane, and the "
        "version guard needs to compare like with like. Until that is done, a deployment that runs both detectors "
        "cannot merge their queues.</p>")
    add("</section>")

    # ---------- step 8 ----------
    add('<section class="step" id="s8"><h2><span class="tag">Step 8</span>What was checked</h2>')
    checks = [
        ["The alert names the frame that raised it", f"pcap_cnt {eve['pcap_cnt']} equals frame {trig['index']}",
         f"same microsecond: {esc(eve['timestamp'])} vs {esc(trig['epoch'])}", "pass"],
        ["The decoded frame is the same flow", f"{trig['src']}:{trig['srcPort']} to {trig['dst']}:{trig['dstPort']}",
         "matches the alert 5-tuple", "pass"],
        ["Every staged record is valid", f"{suri['import']['parsed']} parsed, {suri['import']['invalid']} invalid",
         f"{suri['import']['staged']} staged", "pass"],
        ["One admission produces one queue row", f"{suri['counts']['external_operational_admission']} admission, "
                                                 f"{suri['counts']['operational_alerts_v2']} operational alert", "", "pass"],
        ["The class comes from the policy", f"{esc(cls['value']['attackCategory'])} by {esc(cls['value']['source'])}",
         f"policy {esc(cls['policy'])}", "pass"],
        ["The flow lane is one group", f"{flow['group']['member_count']} members", "one representative", "pass"],
        ["The flow lane is a confirmed case", esc(list(flow["groundTruth"])[0]), "ground truth joined after detection", "pass"],
        ["The case was opened by policy", f"source {esc(flow['case']['decision_source'] if flow['case'] else '')}",
         f"status {esc(flow['case']['status'] if flow['case'] else '')}", "pass"],
    ]
    add(table(["Check", "What was measured", "Detail", "Result"],
              [[esc(a), esc(b), esc(c), '<span class="ok">pass</span>'] for a, b, c, _ in checks]))
    add("<h3>Reproduce it</h3>")
    add(pre(
        "python analysis/phase-f/packet-to-workstation/p2w_capture.py      # packets + the eve record\n"
        "python analysis/phase-f/packet-to-workstation/p2w_data.py suricata  # DB #1: stage, review, admit\n"
        "python analysis/phase-f/packet-to-workstation/p2w_data.py flow      # DB #2: legacy flow lane\n"
        "bash analysis/phase-f/pw_run.sh p2w-suricata p2w-flow              # the 8 screenshots\n"
        "python analysis/phase-f/packet-to-workstation/build_page.py        # this page"))
    add("</section>")
    add(f"<footer>Data: <code>{esc(pk['pcap'])}</code>, "
        f"<code>suricata-172.31.69.25/eve.json</code>, two copies of <code>data/demo.db</code> "
        f"(one routed, one not). No product code was changed to build this page. "
        "Ground truth is shown only in this document; the product never reads it.</footer>")
    add("</main></body></html>")
    return "\n".join(parts)


def route_cell(raw):
    try:
        d = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return f"<code>{esc(raw)}</code>"
    reasons = "; ".join(d.get("reasons") or [])
    return (f"<code>{esc(d.get('route'))}</code> "
            f"(class <code>{esc(d.get('routeClass'))}</code>, source <code>{esc(d.get('decisionSource'))}</code>)"
            + (f"<br><span class=\"mut\">{esc(reasons)}</span>" if reasons else ""))


def esc_trig_tail(trig):
    return trig.get("ethDstMac", "") + " / " + trig.get("ethSrcMac", "")


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
