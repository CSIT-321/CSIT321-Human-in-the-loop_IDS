"""Build the workflow layout page: the Suricata-first chain, and the retired CICIDS2018 flow lane.

Reads data/lane_suricata_full.json when it exists (population counts). Writes index.html.
No product code is described that does not exist; every stage names its file or table.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "packet-to-workstation" / "data" / "lane_suricata_full.json"
OUT = HERE / "index.html"

STAGES = [
    ("S0", "Packet capture", "Raw frames on the sensor",
     "A capture file or a live interface. Nothing is interpreted yet.",
     "pcap", "sensor / file"),
    ("S1", "Suricata", "Raw frames",
     "A standard third-party engine matches its rule set and writes one eve.json record per alert.",
     "eve.json alert record", "Suricata (external)"),
    ("S2", "Import and staging", "eve.json lines",
     "scripts/import_suricata_eve.py validates each record against the canonical alert contract, maps the "
     "fields and stages it. Admission is a separate, later step.",
     "suricata_eve_records + external_alert_inbox", "Incoming Alerts"),
    ("S3", "Eligibility review", "Staged inbox record",
     "An analyst reads the evidence and records accepted or held, with a reason. Nothing reaches the queue "
     "without this decision.",
     "external_eligibility_review", "Incoming Alerts"),
    ("S4", "Admission", "Reviewed inbox record",
     "The record becomes an operational alert. Priority comes from the native severity table, not from the "
     "attack class. Learning is not eligible for external rules.",
     "external_operational_admission + operational_alerts_v2", "Analyst Workstation"),
    ("S5", "Classification", "Operational alert",
     "config/suricata-classification-v3.json maps signature text to one attack category. A signature that "
     "matches no rule becomes unknown and goes to expert review.",
     "operational_system_routing.classification", "alert panel"),
    ("S6", "Triage and routing", "Classification + priority + trusted context",
     "config/system-routing-v1.json decides tier1_review or tier2_case: unknown class, unresolved context, "
     "confirmed malicious with response required, high priority on a critical asset, or a repeated campaign.",
     "operational_triage_state_v2", "queue row, routing panel"),
    ("S7", "Tier 1 work", "Queue item",
     "The analyst claims the row, reads evidence, adds notes and records a verdict. External alerts are not "
     "learning-eligible, so a verdict does not re-score anything.",
     "analyst_work, analyst_notes, analyst_verdict_events", "Analyst Workstation"),
    ("S8", "Tier 2 case", "A tier2_case route",
     "Start investigation, record the conclusion, resolve. The case is read-only after resolution.",
     "tier2_cases, tier2_case_state, tier2_case_events", "Tier 2 Cases"),
]

CSS = """
:root{--ink:#16202b;--mut:#5b6b7c;--line:#dbe3ec;--bg:#fbfcfe;--accent:#0b6bcb;--warn:#b45309;--dead:#94a3b8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1120px;margin:0 auto;padding:30px 22px 70px}
h1{font-size:27px;margin:0 0 8px}h2{font-size:20px;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--line)}
p.lead{color:var(--mut);margin:0 0 18px;font-size:16px}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}th{background:#f3f6fa}
code{font:13px/1.4 ui-monospace,Consolas,monospace;background:#f3f6fa;padding:1px 4px;border-radius:4px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:14px 0}
.fact{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:#fff}
.fact b{display:block;font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.fact span{font:600 17px/1.4 ui-monospace,monospace}
.dead{border:2px dashed var(--dead);border-radius:10px;padding:14px 16px;background:#f8fafc;color:#475569}
.dead h3{margin:0 0 6px;color:#475569}.dead s{color:#64748b}
.note{border-left:4px solid var(--accent);background:#f0f6ff;padding:10px 14px;border-radius:0 8px 8px 0;margin:14px 0}
.warn{border-left:4px solid var(--warn);background:#fff7ed;padding:10px 14px;border-radius:0 8px 8px 0;margin:14px 0}
footer{margin-top:40px;border-top:1px solid var(--line);padding-top:12px;color:var(--mut);font-size:13px}
svg{width:780px;max-width:100%;height:auto;display:block;margin:8px 0}
"""


def esc(v):
    return html.escape(str(v), quote=True)


def chain_svg() -> str:
    """Vertical chain of stages, with the retired lane drawn beside it and struck out."""
    row_h, box_w, x = 96, 720, 20
    height = len(STAGES) * row_h + 30
    out = [f'<svg viewBox="0 0 {box_w + 60} {height}" role="img" aria-label="Suricata-first workflow">']
    out.append('<defs><marker id="a" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">'
               '<path d="M0,0 L10,4 L0,8 z" fill="#0b6bcb"/></marker></defs>')
    for i, (sid, name, inp, what, out_store, screen) in enumerate(STAGES):
        y = 10 + i * row_h
        fill = "#eef4ff" if i < 7 else "#f1f7f4"
        stroke = "#0b6bcb" if i < 7 else "#0f766e"
        out.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="74" rx="9" fill="{fill}" stroke="{stroke}"/>')
        out.append(f'<text x="{x+14}" y="{y+24}" font-size="13" font-weight="700" fill="{stroke}">{sid}</text>')
        out.append(f'<text x="{x+52}" y="{y+24}" font-size="15" font-weight="600" fill="#16202b">{esc(name)}</text>')
        out.append(f'<text x="{x+14}" y="{y+45}" font-size="12" fill="#5b6b7c">in: {esc(inp)}</text>')
        out.append(f'<text x="{x+14}" y="{y+62}" font-size="12" fill="#334155">stored: {esc(out_store)}</text>')
        out.append(f'<text x="{x+box_w-12}" y="{y+62}" font-size="11" fill="#7c8b9c" text-anchor="end">{esc(screen)}</text>')
        if i + 1 < len(STAGES):
            out.append(f'<line x1="{x+box_w/2}" y1="{y+74}" x2="{x+box_w/2}" y2="{y+row_h}" '
                       'stroke="#0b6bcb" stroke-width="2" marker-end="url(#a)"/>')
    out.append("</svg>")
    return "".join(out)


def live_counts(pop):
    """Counts read from the populated database now, so the page cannot show a stale number."""
    import sqlite3
    if not pop or not Path(pop["db"]).exists():
        return pop
    c = sqlite3.connect(f"file:{pop['db']}?mode=ro", uri=True)
    q = lambda s: c.execute(s).fetchone()[0]
    pop["counts"] = {t: q(f"SELECT count(*) FROM {t}") for t in
                     ("suricata_eve_records", "external_alert_inbox", "external_eligibility_review",
                      "external_operational_admission", "operational_alerts_v2", "tier2_cases",
                      "operational_system_routing")}
    pop["routes"] = dict(c.execute("SELECT handling_route, count(*) FROM operational_triage_state_v2 GROUP BY 1"))
    pop["classes"] = {}
    for raw, n in c.execute("SELECT classification, count(*) FROM operational_system_routing GROUP BY 1"):
        try:
            pop["classes"][json.loads(raw)["attackCategory"]] = pop["classes"].get(json.loads(raw)["attackCategory"], 0) + n
        except Exception:
            pop["classes"]["unparsed"] = pop["classes"].get("unparsed", 0) + n
    pop["bands"] = dict(c.execute("SELECT priority_band, count(*) FROM operational_triage_state_v2 GROUP BY 1"))
    pop["staged"] = q("SELECT count(*) FROM external_alert_inbox WHERE import_status='staged'")
    c.close()
    return pop


def main() -> None:
    pop = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else None
    pop = live_counts(pop)
    h = [f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
         f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>Workflow layout</title>'
         f"<style>{CSS}</style></head><body><main>"]
    h.append("<h1>Current workflow layout: Suricata-first</h1>")
    h.append('<p class="lead">One chain, from packet to analyst screen. The CICIDS2018 flow lane is no longer part '
             "of the demo and must not be shown. The code for it still exists in the repository; nothing in this "
             "page depends on it.</p>")

    if pop:
        c = pop["counts"]
        h.append('<div class="facts">')
        for label, value in (("Suricata alerts imported", f'{c["suricata_eve_records"]:,}'),
                             ("Inbox records", f'{c["external_alert_inbox"]:,}'),
                             ("Still staged (backlog)", f'{pop.get("staged", 0):,}'),
                             ("Admitted to queue", f'{c["operational_alerts_v2"]:,}'),
                             ("Tier 1 items", f'{pop["routes"].get("tier1_review", 0):,}'),
                             ("Tier 2 cases", f'{pop["tier2Cases"]:,}'),
                             ("Queue rows", f'{c["operational_alerts_v2"]:,}')):
            h.append(f'<div class="fact"><b>{esc(label)}</b><span>{esc(value)}</span></div>')
        h.append("</div>")

    h.append("<h2>The chain</h2>")
    h.append(chain_svg())
    h.append('<p class="note">Each box names the stage, its input, the table it writes, and the screen where an '
             "analyst sees it. Priority comes from the native severity table at admission; the attack class only "
             "decides who handles the alert.</p>")

    h.append("<h2>Stage detail</h2>")
    rows = [[f"<b>{esc(sid)}</b>", esc(name), esc(inp), esc(what), f"<code>{esc(out_store)}</code>", esc(screen)]
            for sid, name, inp, what, out_store, screen in STAGES]
    h.append('<table><thead><tr><th>Stage</th><th>Name</th><th>Input</th><th>What happens</th>'
             '<th>Stored as</th><th>Screen</th></tr></thead><tbody>'
             + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>")

    if pop:
        h.append("<h2>What the Suricata-only database holds</h2>")
        h.append(f"<p>Population rule: {esc(pop['rule'])}. Import result: {pop['import']['parsed']:,} parsed, "
                 f"{pop['import']['staged']:,} staged, {pop['import']['invalid']:,} invalid, "
                 f"{pop['import']['rejected_by_policy']:,} rejected by policy.</p>")
        route_rows = "".join(f"<tr><td><code>{esc(k)}</code></td><td>{v:,}</td></tr>"
                             for k, v in pop["routes"].items())
        class_rows = "".join(f"<tr><td><code>{esc(k)}</code></td><td>{v:,}</td></tr>"
                             for k, v in sorted(pop["classes"].items(), key=lambda kv: -kv[1]))
        band_rows = "".join(f"<tr><td><code>{esc(k)}</code></td><td>{v:,}</td></tr>"
                            for k, v in pop["bands"].items())
        h.append('<table style="width:auto"><thead><tr><th>Route</th><th>Alerts</th></tr></thead><tbody>'
                 + route_rows + "</tbody></table>")
        h.append('<table style="width:auto"><thead><tr><th>Attack class from the signature policy</th><th>Alerts</th>'
                 "</tr></thead><tbody>" + class_rows + "</tbody></table>")
        h.append('<table style="width:auto"><thead><tr><th>Priority band</th><th>Alerts</th></tr></thead><tbody>'
                 + band_rows + "</tbody></table>")
        if pop["failedCount"]:
            h.append(f'<div class="warn">{pop["failedCount"]} admissions failed. First error: '
                     f'<code>{esc(pop["failed"][0]["error"])}</code></div>')

    h.append("<h2>Retired from the demo</h2>")
    h.append('<div class="dead"><h3>CICIDS2018 flow lane (code present, not used)</h3>'
             "<p><s>CSV flow records, CICFlowMeter features, XGBoost scoring, fusion, alert groups, E1/E3 routing.</s></p>"
             "<p>Why it is out: it starts from a labelled research dataset, not from packets. Its scores are model "
             "opinions about research features, and its demo screens show alert groups that Suricata never produced. "
             "Keeping both lanes doubled every count and made two versions of the same event.</p>"
             "<p>What remains in the repository: <code>packages/detection/fusion/</code>, "
             "<code>flow_routing.py</code>, <code>scripts/materialize_flow_queue.py</code> and their tests. They are "
             "not part of this workflow and must not appear in the demo or the guide.</p></div>")

    h.append('<p class="warn"><b>One consequence to decide:</b> the product currently refuses to hold both lanes in '
             "one database (<code>packages/detection/system_routing.py:70-75</code>). A Suricata-only database is "
             "unaffected, so the demo can now be a single database. The mixed-lane case must be resolved before any "
             "deployment runs both detectors.</p>")

    h.append("<h2>What an analyst can do at each screen</h2>")
    h.append('<table><thead><tr><th>Screen</th><th>Route</th><th>Actions</th></tr></thead><tbody>'
             "<tr><td>Incoming Alerts</td><td><code>/analyst/external-admission</code></td>"
             "<td>read a staged Suricata alert, record the eligibility review, admit it, follow the link to the "
             "workstation</td></tr>"
             "<tr><td>Analyst Workstation</td><td><code>/analyst/operations</code></td>"
             "<td>claim, read evidence, add notes, record a verdict, see routing and classification</td></tr>"
             "<tr><td>Tier 2 Cases</td><td><code>/analyst/tier2-cases</code></td>"
             "<td>start the investigation, record the conclusion, resolve</td></tr>"
             "<tr><td>Admin surfaces</td><td><code>/admin/*</code></td>"
             "<td>users, governance, audit, guardrails, admission, reports</td></tr>"
             "</tbody></table>")
    h.append("<footer>Sources: <code>scripts/import_suricata_eve.py</code>, "
             "<code>packages/detection/external_admission.py</code>, "
             "<code>packages/detection/attack_classification.py</code>, "
             "<code>packages/detection/system_routing.py</code>, <code>config/suricata-classification-v3.json</code>, "
             "<code>config/system-routing-v1.json</code>, <code>config/external-admission.json</code>.</footer>")
    h.append("</main></body></html>")
    OUT.write_text("\n".join(h), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
