"""Build the SOC demo guide (one HTML page) from soc-packet.spec.ts output: PNGs + pins.json + facts.json.

Pins are an HTML overlay in percent of the 1440x900 shot, from boxes the spec MEASURED with Playwright
boundingBox() at screenshot time. Every number in the step text comes from facts.json (the spec's run).
Usage: python build_soc_guide.py <guide output of the spec> <output dir>
"""
import html
import json
import shutil
import sys
from pathlib import Path

W, H = 1440, 900


def steps(f: dict) -> list[tuple[str, str, str, str, str, str]]:
    """(file, part, title, what to click, what you see, why it matters to a SOC)."""
    five, done, final = f["afterFive"], f["complete"], f["final"]
    ssh, auto, routine = f["suricataSsh"], f["flowAuto"], f["flowRoutine"]
    n = lambda v: f"{v:,}"  # noqa: E731
    return [
        ("00-login", "Admin", "Sign in as the Admin",
         "Type **admin** / **admin-demo** and click **Sign in**.",
         "The Admin pages open. Analysts use the **same** sign-in page. The role decides what each account sees.",
         "There is one front end, one API and one login. No separate login for the flow chain or for Suricata."),
        ("01-prepare", "Admin", "Choose Packet Replay and prepare it",
         "Left menu **Operational Workspace**. In **Replay preparation mode**, choose **Packet Replay**. Click **Prepare Replay**.",
         "The Replay card shows **Mode: Packet Replay** and **Capture steps arrived: 0 / 160**.",
         "The replay is isolated. The Operational workspace and the frozen evaluation do not change."),
        ("02-running", "Admin", "Activate, then start the arrivals",
         "Click **Activate** on the Replay card. Click **Next 5 Steps** for a quick start, then **Start Arrivals**.",
         f"After 5 steps the queue holds **{n(five['queue'])}** items: **{n(five['flow'])}** from the flow chain and "
         f"**{n(five['suricata'])}** from Suricata. **Playback: Running** adds one capture step every 5 seconds. "
         "**Pause**, **Next Step** and **Next 5 Steps** stay available.",
         "The Admin controls the pace of the simulation. Each step is an equal share of the recorded capture time."),
        ("03-arrivals-before", "Analyst", "Sign in as the analyst and watch the queue",
         "In a second browser window, sign in as **g.ang** / **analyst-demo**.",
         f"The header says **Workspace: V3.1 Demo Replay** and **Arrival updates connected**. The Active tab reads "
         f"**{html.escape(f['arrivals']['before'])}**.",
         "Every analyst sees the workspace that the Admin activated. Nothing needs to be selected."),
        ("04-arrivals-after", "Analyst", "New alerts arrive without a reload",
         "Do nothing. Wait for the next capture steps.",
         f"The Active tab changes to **{html.escape(f['arrivals']['after'])}** by itself.",
         "Alerts from both chains enter the queue as the traffic is processed, as in a live SOC shift."),
        ("05-complete", "Admin", "The capture ends",
         "Let the arrivals run to the end (about 13 minutes), or click **Next 5 Steps** to go faster.",
         f"**Capture steps arrived: 160 / 160**, **Playback: Complete**. The queue holds **{n(done['queue'])}** items: "
         f"**{n(done['flow'])}** flow and **{n(done['suricata'])}** Suricata. "
         f"**{n(done['groupMembers'])}** flagged flows became **{n(done['groups'])}** groups. "
         f"**{n(done['autoCases'])}** Tier 2 cases opened by rule.",
         "Grouping turns thousands of flagged flows into a few work items."),
        ("06-both-chains", "Analyst", "Both chains in one queue",
         "Click the **Auto-escalated** tab.",
         f"**{n(done['autoCases'])}** cases. **{n(done['autoFlowCases'])}** are flow brute-force groups, escalated "
         f"because the rule and the model agree at score 100. **{n(done['autoCases'] - done['autoFlowCases'])}** are "
         "Suricata alerts with a signature that the system cannot classify (Expert Review).",
         "The machine routes the clear cases. A human decides the rest."),
        ("07-claimed", "Analyst", "Open a Suricata alert (this claims it)",
         "Open the Tier 1 list and click a Suricata row.",
         f"Here: **{html.escape(ssh['detection_title'])}** from {html.escape(ssh['source_ip'])} to "
         f"{html.escape(ssh['destination_ip'])}:{ssh['destination_port']}. The row says **In Review — You**. "
         "The work panel says **Your Access: Owner**.",
         "Other analysts see who owns it and do not duplicate the work."),
        ("08-suricata-evidence", "Analyst", "Read the Suricata evidence",
         "Open the **Evidence** tab.",
         "The signatures that fired on this flow, their native category and severity, and the Suricata flow id.",
         "The analyst checks the rule evidence, not only a title."),
        ("09-note", "Analyst", "Add a note",
         "Open **History & Notes**, type a note, click **Add note**.",
         f"The note shows with your name and time. Here it records that the flow chain escalated a brute-force group "
         f"from the same source ({html.escape(f['picks']['sshSource'])}, {n(auto['members'])} flows).",
         "A shift lead can follow the reasoning later. The two chains confirm each other."),
        ("10-escalate", "Analyst", "Escalate to Tier 2 with a reason",
         "On **Overview**, type a **Decision reason**. Click **Escalate to Tier 2**.",
         "**Escalate to Tier 2** stays off until a reason is typed.",
         "The system routed this alert to Tier 1. A human overrides it and states why."),
        ("11-escalated", "Analyst", "The alert is escalated",
         "Nothing to click.",
         "**Escalated to Tier 2 — Tier 2 Case created successfully.** The alert leaves the Active list.",
         "Tier 1 is done with it; the expert takes over."),
        ("12-flow-score", "Analyst", "Check a flow group's evidence",
         "Open a flow group from the Tier 1 list, then the **Flow & Score** tab.",
         f"Here: **{html.escape(routine['detection_title'])}**, a group of **{n(routine['members'])}** flows from "
         f"{html.escape(routine['source_ip'])}. Ports, packet counts, rule conditions and the model's top features.",
         "The analyst judges evidence, not only a score."),
        ("13-verdict", "Analyst", "Record a verdict",
         "Open **Analyst Verdict**. Pick an outcome, type a reason, click **Record Verdict**.",
         "Work status **Completed — Reviewed by Glenn Ang**.",
         "A flow verdict feeds the learning loop: each outcome moves the score within the guardrails. "
         "One verdict alone does not re-rank a family (3-vote gate). A Suricata verdict is recorded but does not re-score."),
        ("14-case-list", "Tier 2", "The case list",
         "Left menu: **Tier 2 Cases**.",
         "Default filter Active. Rule cases say **Rule** with the rule sentence. Your case shows **Glenn Ang** and your reason.",
         "The expert sees open work and who or what sent each case."),
        ("15-conclusion", "Tier 2", "Investigate and conclude",
         "Open your case. **Audit Timeline**: reason, **Start investigation**. **Investigation Conclusion**: finding, "
         "class, reason, **Record Investigation Conclusion**.",
         "**Resolve Case** stays off until a conclusion exists. Then it turns on.",
         "A case cannot close without a recorded finding."),
        ("16-resolved", "Tier 2", "Resolve the case",
         "Type a **Resolution Reason**. Click **Resolve Case**.",
         "**Resolved by: Glenn Ang**. All edit buttons go. The case leaves the Active list but stays under Status = Resolved.",
         "The record is fixed for audit."),
        ("17-release", "Analyst", "Release a claim",
         "On an alert you own, click **Release claim**, then **Release**.",
         "The alert is available to others again.",
         "Shift change or wrong pick: work returns to the queue. Idle claims also expire after 15 minutes."),
    ]


def bold(text: str) -> str:
    parts = text.split("**")
    return "".join(f"<strong>{p}</strong>" if i % 2 else p for i, p in enumerate(parts))


def main(src: Path, out: Path) -> None:
    pins = json.loads((src / "pins.json").read_text(encoding="utf-8"))
    facts = json.loads((src / "facts.json").read_text(encoding="utf-8"))
    img = out / "img"
    if img.exists():
        shutil.rmtree(img)
    img.mkdir(parents=True)
    cards, part = [], None
    for n, (name, section, title, click, see, why) in enumerate(steps(facts), 1):
        shutil.copyfile(src / f"{name}.png", img / f"{name}.png")
        marks, legend = [], []
        for k, pin in enumerate(pins.get(name, []), 1):
            box = pin["box"]
            if not box:
                legend.append(f"<li class=missing>{k}. {html.escape(pin['label'])} (not visible in this shot)</li>")
                continue
            left, top = 100 * box["x"] / W, 100 * box["y"] / H
            wid, hei = 100 * box["width"] / W, 100 * box["height"] / H
            if box["y"] + box["height"] > H or box["x"] + box["width"] > W or box["y"] < 0 or box["x"] < 0:
                legend.append(f"<li class=missing>{k}. {html.escape(pin['label'])} (outside the visible area — scroll)</li>")
                continue
            marks.append(f'<span class=box style="left:{left:.2f}%;top:{top:.2f}%;width:{wid:.2f}%;height:{hei:.2f}%"></span>'
                         f'<span class=pin style="left:{left:.2f}%;top:{top:.2f}%">{k}</span>')
            legend.append(f"<li>{k}. {html.escape(pin['label'])}</li>")
        if section != part:
            cards.append(f'<h2 class=part>{html.escape(section)}</h2>')
            part = section
        cards.append(f"""<section class=step id="s{n}">
<h3>Step {n}. {html.escape(title)}</h3>
<div class=shot><img src="img/{name}.png" alt="{html.escape(title)}">{''.join(marks)}</div>
<ol class=legend>{''.join(legend)}</ol>
<p><b>Click:</b> {bold(click)}</p><p><b>You see:</b> {bold(see)}</p><p class=why><b>Why (SOC):</b> {bold(why)}</p>
</section>""")
    d = facts["complete"]
    page = f"""<!doctype html><html lang=en><meta charset=utf-8><title>HITL IDS — SOC demo guide (Packet Replay)</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#111}}
h1{{font-size:24px}} h2.part{{font-size:20px;margin:34px 0 4px;padding-bottom:4px;border-bottom:2px solid #ddd}}
h3{{font-size:17px;margin:24px 0 8px}}
.shot{{position:relative;border:1px solid #ccc}} .shot img{{display:block;width:100%}}
.box{{position:absolute;border:3px solid #e8590c;border-radius:4px;box-sizing:border-box}}
.pin{{position:absolute;transform:translate(-50%,-50%);background:#e8590c;color:#fff;font:700 13px/24px system-ui;
 width:24px;height:24px;border-radius:50%;text-align:center}}
.legend{{list-style:none;padding:0;display:flex;gap:16px;flex-wrap:wrap;color:#e8590c;font-weight:600}}
.legend .missing{{color:#888;font-weight:400}} .why{{color:#444}}
.note{{border-left:4px solid #0b6bcb;background:#f0f6ff;padding:10px 14px;margin:14px 0}}
table{{border-collapse:collapse}} td,th{{border:1px solid #ddd;padding:4px 10px;text-align:left}}
</style>
<h1>HITL IDS — SOC demo guide: Packet Replay, Tier 1 to Tier 2</h1>
<p>One recorded capture (CSE-CIC-IDS2018, 2018-02-14) feeds <b>two</b> detection chains: the flow chain
(CICFlowMeter, signature rules and XGBoost, grouping, learning) and Suricata. Both arrive in <b>one</b> queue,
behind <b>one</b> login. The Admin controls the replay; the analyst works the queue as it fills.</p>
<div class=note><b>Accounts.</b> <code>admin</code> / <code>admin-demo</code> — runs the replay.
<code>g.ang</code> / <code>analyst-demo</code> — Tier 1 and Tier 2 work. Use two browser windows (or one normal and
one private window), because one browser keeps one session.<br>
<b>Full capture</b>: {d['queue']:,} queue items ({d['flow']:,} flow, {d['suricata']:,} Suricata),
{d['groups']} flow groups, {d['tier2Cases'] if 'tier2Cases' in d else d['autoCases']} Tier 2 cases opened by rule.
Data flow per stage: see <code>analysis/phase-f/workflow-layout/index.html</code>.</div>
<p>Built from an automated run of <code>soc-packet.spec.ts</code> on a copy of the demo data. Every screenshot is
from that run, and the run checked the database after each write. Orange boxes mark what to click or read; their
positions were measured by the browser. The run fast-forwards the replay after step 4; in a demo, let it play.</p>
{''.join(cards)}
</html>"""
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote {out / 'index.html'}: {len(steps(facts))} steps, {sum(len(v) for v in pins.values())} pins")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
