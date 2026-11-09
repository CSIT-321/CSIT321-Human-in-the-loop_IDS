"""Render the five per-record end-to-end walkthrough sections for the v2 page.

Every number printed here is read from workings.json, tree2.json or trace/trace.json.
Long arithmetic strings are copied verbatim from the JSON that stores them.
"""
from __future__ import annotations

import html

HEAD = "<h2>Five records, end to end</h2>"

STYLE = """<style>
.rec { margin: 2.4rem 0 3rem; }
.rec h3 { font-size: 1.18rem; margin: 0 0 .3rem; }
.rec-meta { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .78rem; color: #5b6472; }
.rec h4 { font-size: .95rem; margin: 1.2rem 0 .5rem; text-transform: uppercase; letter-spacing: .04em; color: #3c4657; }
.rec-steps { display: grid; gap: .9rem; }
.rec-step { border: 1px solid #dfe3ea; border-radius: 8px; padding: .7rem .8rem; background: #fbfcfe; }
.rec-stephead { font-weight: 600; }
.rec-actor { font-size: .78rem; color: #5b6472; margin-left: .5rem; font-weight: 400; }
.rec-action { margin: .25rem 0 .55rem; }
.rec-shots { display: flex; flex-wrap: wrap; gap: .6rem; }
.rec-shots a { flex: 1 1 260px; display: block; }
.rec-shots img { width: 100%; height: auto; border: 1px solid #d5dae3; border-radius: 6px; display: block; background: #fff; }
.rec table { border-collapse: collapse; width: 100%; font-size: .86rem; }
.rec th, .rec td { border: 1px solid #dfe3ea; padding: .45rem .55rem; vertical-align: top; text-align: left; }
.rec th { background: #eef1f6; }
.rec-st { white-space: nowrap; font-weight: 600; width: 3.2rem; }
.rec-where { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .78rem; white-space: nowrap; }
.rec code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .82rem; }
.rec-arith { display: inline-block; background: #f2f4f8; padding: .15rem .35rem; border-radius: 4px; }
.rec-close { margin-top: .8rem; font-weight: 600; }
</style>"""

STORE = {
    "S1": "flow_data",
    "S2": "alerts.signature_rules",
    "S3": "alerts.ml_*",
    "S4": "alerts.detection_score",
    "S5": "alerts.severity",
    "S6": "alert_groups",
    "S7": "operational_triage_state_v2",
    "S8": "analyst_work / feedback_events",
    "S9": "tier2_case_state",
}


def _e(value) -> str:
    """HTML-escape one value for text or an attribute."""
    return html.escape("" if value is None else str(value), quote=True)


def _num(value) -> str:
    """Print a stored number without adding digits: bools, ints, floats, small floats."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == 0:
            return "0"
        if abs(value) < 1e-4:
            return f"{value:.1e}"
        return repr(value)
    return _e(value)


def _stage_rows(rec: dict) -> list:
    """One (stage, produced HTML, stored-in) row per stage S1..S9 for this record."""
    st = rec["stages"]
    sig, model, fus, sev = st["signature"], st["model"], st["fusion"], st["severity"]
    rows = []

    rows.append(("S1", f"{_num(rec['inputFeatureCount'])} flow attributes stored; "
                       f"{_num(len(rec['input']))} named fields the rules read"))

    if sig["matched"]:
        parts = [f"<code>{_e(m['rule_id'])}</code> ({_e(m['class'])}, {_e(m['severity'])}): "
                 f"every recorded condition true" for m in sig["matched"]]
        rows.append(("S2", "; ".join(parts)))
    else:
        rows.append(("S2", "no rule matched"))

    s3 = (f"predicted <b>{_e(model['predictedClass'])}</b> with confidence {_num(model['confidence'])}; "
          f"malicious probability {_num(model['maliciousProbability'])}")
    ex = model.get("explain")
    if ex:
        add = ex.get("additivity") or {}
        diff, tol = add.get("difference"), add.get("tolerance")
        if isinstance(diff, (int, float)) and isinstance(tol, (int, float)) and abs(diff) < tol:
            # The stored difference is far below the tolerance, so the tolerance is the readable bound.
            gap = f"within the {_num(tol)} tolerance"
        else:
            gap = f"{_num(diff)}"
        s3 += (f"; margin {_num(ex['rawMargin'])} = base {_num(ex['baseValue'])} + contributions "
               f"(additivity difference {gap}, passed {_num(add.get('passed'))})")
    rows.append(("S3", s3))

    rows.append(("S4", f"evidence <b>{_e(fus['evidence'])}</b><br>"
                       f"<code class='rec-arith'>{_e(fus['scoreArithmetic'])}</code>"))

    if sev.get("className"):
        s5 = (f"score {_num(sev['score'])} &rarr; band {_e(sev['band'])}; {_e(sev['className'])} ceiling "
              f"{_e(sev['ceiling'])} (CVSS {_num(sev['classCvss'])}); final {_e(sev['final'])}; "
              f"capped {_num(bool(sev['capped']))}")
    else:
        s5 = (f"score {_num(sev['score'])} &rarr; band {_e(sev['band'])}; no class, so no ceiling and no CVSS; "
              f"final {_e(sev['final'])}; capped {_num(bool(sev['capped']))}")
    rows.append(("S5", s5))

    grp = st.get("group")
    if grp:
        unit = "member" if grp["members"] == 1 else "members"
        s6 = (f"{_num(grp['members'])} {unit} keyed on {_e(grp['key'])}; span "
              f"{_num(grp['spanMinutes'])} minutes, largest gap {_num(grp['maxGapMinutes'])} minutes")
    else:
        s6 = "not grouped (unflagged flows are never grouped)"
    rows.append(("S6", s6))

    route = st["routing"]
    gates = route["gates"]
    rows.append(("S7", f"E1: {_e(gates['e1']['test'])} (pass {_num(bool(gates['e1']['pass']))})<br>"
                       f"E3: {_e(gates['e3']['test'])} (pass {_num(bool(gates['e3']['pass']))})<br>"
                       f"route <code>{_e(route['route'])}</code>, stage {_e(route['stage'])}, "
                       f"priority {_num(route['priority'])}, band {_e(route['band'])}"))

    human = rec["human"]
    work = human.get("work")
    if work:
        s8 = (f"{_e(work['status'])} by {_e(work.get('finishedBy') or work.get('owner'))} "
              f"(owner {_e(work.get('owner'))})")
    else:
        s8 = "no analyst work recorded"
    events = human.get("feedback") or []
    if events:
        chunks = []
        for fb in events:
            before, applied = fb["original_score"], fb["actual_delta"]
            after = fb["scoreAfter"] if "scoreAfter" in fb else round(before + applied, 2)
            # Verbatim when the record stores the string; otherwise the same expression it was built from.
            arith = fb.get("arithmetic") or f"{_num(before)} + ({_num(applied)}) = {_num(after)}"
            chunks.append(f"<div>{_e(fb['category'])}: {_num(before)} &rarr; {_num(after)}; "
                          f"requested {_num(fb['requested_delta'])}, applied {_num(applied)}; "
                          f"guardrail {_e(fb['guardrail_action'])}; "
                          f"<code class='rec-arith'>{_e(arith)}</code></div>")
        s8 += "<br>" + "".join(chunks)
    else:
        s8 += "; no feedback events"
    rows.append(("S8", s8))

    case = human.get("case")
    if case:
        s9 = (f"status {_e(case.get('status'))}; decision {_e(case.get('decision_source'))}")
        if case.get("revision") is not None:
            s9 += f"; revision {_num(case['revision'])}"
    else:
        s9 = "no case"
    rows.append(("S9", s9))

    return [(stage, produced, STORE[stage]) for stage, produced in rows]


def _steps(tpath: dict) -> str:
    """Every step of one trace path, with its card and its screen capture side by side."""
    out = ['<div class="rec-steps">']
    for step in tpath.get("steps", []):
        sid, shot, label = step["id"], step["shot"], step["label"]
        out.append(
            '<div class="rec-step">'
            f'<div class="rec-stephead">{_e(sid)} {_e(label)}'
            f'<span class="rec-actor">{_e(step["actor"])}</span></div>'
            f'<div class="rec-action">{_e(step["action"])}</div>'
            '<div class="rec-shots">'
            f'<a href="../cards/{_e(sid)}.png"><img src="../cards/{_e(sid)}.png" '
            f'alt="{_e(label)}" loading="lazy"></a>'
            f'<a href="../trace/{_e(shot)}"><img src="../trace/{_e(shot)}" '
            f'alt="{_e(label)}" loading="lazy"></a>'
            "</div></div>")
    out.append("</div>")
    return "".join(out)


def _table(rec: dict) -> str:
    head = ("<tr><th class='rec-st'>Stage</th><th>What the analysis produced</th>"
            "<th>Where it is stored</th></tr>")
    body = "".join(
        f"<tr><td class='rec-st'>{_e(stage)}</td><td>{produced}</td>"
        f"<td class='rec-where'>{_e(where)}</td></tr>"
        for stage, produced, where in _stage_rows(rec))
    return f"<table><thead>{head}</thead><tbody>{body}</tbody></table>"


def _closing(rec: dict) -> str:
    """The last line: the score the record now carries, and the severity stored with it."""
    events = rec["human"].get("feedback") or []
    if events:
        last = events[-1]
        score = last["scoreAfter"] if "scoreAfter" in last else round(
            last["original_score"] + last["actual_delta"], 2)
    else:
        score = rec["stages"]["fusion"]["storedScore"]
    final = rec["stages"]["severity"]["final"]
    return (f"<p class='rec-close'>Final score {_num(score)}, severity {_e(final)}; "
            f"ground truth is not shown here.</p>")


def _section(letter: str, rec: dict, tree2: dict, trace: dict) -> str:
    tpath = next((p for p in trace.get("paths", []) if p.get("id") == letter), {"steps": []})
    title = ((tree2.get("paths") or {}).get(letter) or {}).get("title", "")
    prefix = f"{letter} - "
    if title.startswith(prefix):
        title = title[len(prefix):]
    parts = [
        f"<section class=\"rec\" id=\"rec-{_e(letter)}\">",
        f"<h3>{_e(letter)} {_e(title)}</h3>",
        f"<div class='rec-meta'>{_e(rec['recordId'])} &middot; {_e(rec['ref'])}</div>",
        "<h4>Step by step</h4>",
        _steps(tpath),
        "<h4>The arithmetic at each stage</h4>",
        _table(rec),
        _closing(rec),
        "</section>",
    ]
    return "".join(parts)


def records_html(workings: dict, tree2: dict, trace: dict) -> str:
    """Render the five per-record sections, in path order A..E."""
    parts = [HEAD, STYLE]
    for letter in ("A", "B", "C", "D", "E"):
        rec = next((r for r in workings.get("records", []) if r.get("path") == letter), None)
        if rec is not None:
            parts.append(_section(letter, rec, tree2, trace))
    return "\n".join(parts)


