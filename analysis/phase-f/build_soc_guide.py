"""Build the SOC demo guide (one HTML page) from soc-flow.spec.ts output: the PNGs + pins.json.

Pins are an HTML overlay positioned in percent of the 1440x900 shot, from boxes the spec MEASURED with
Playwright boundingBox() at screenshot time. No coordinate is guessed. The PNGs are copied, not edited.
Usage: python build_soc_guide.py <soc-guide dir> <output dir>
"""
import html
import json
import shutil
import sys
from pathlib import Path

W, H = 1440, 900

# step text: (file, title, what to click, what you should see, why it matters to a SOC)
STEPS = [
    ("00-login", "Sign in", "Type the analyst account (g.ang / analyst-demo) and click **Sign in**.",
     "The Analyst Workstation opens.", "Each action is recorded under your name."),
    ("01-queue-views", "Pick your tier view", "Look at the view tabs. Click **Tier 2 candidates** or **Tier 1**.",
     "Counts per view. Tier 1 shows groups and singles apart. Auto-escalated = 3.",
     "Tier 1 and Tier 2 staff each open their own list in one click. 996 flagged alerts became 81 items."),
    ("02-claimed", "Open an alert (this claims it)", "Click a row in the list.",
     "The row says **In Review — You**. The work panel says **Your Access: Owner**.",
     "Other analysts see who owns it and do not duplicate the work."),
    ("03-note", "Add a note", "Open **History & Notes**, type a note, click **Add note**.",
     "The note shows with your name and time. It cannot be edited or deleted.",
     "A shift lead can follow the reasoning later."),
    ("04-why-tier2", "Read why Tier 2 is recommended, then decide", "Read the brown panel. Type a short **Reason**. Click **Escalate to Tier 2** or **Keep in Tier 1**.",
     "The reason the system gives (here: score 100, Infiltration, severity 9.5, 6 of 49 members). Escalate stays off until you type a reason.",
     "The machine recommends; a human decides and states why."),
    ("05-escalated", "The alert is escalated", "Nothing to click.",
     "Work status **Escalated**. A Tier 2 case now exists. The alert leaves the Active list.",
     "Tier 1 is done with it; the expert takes over."),
    ("06-flow-score", "Check the flow evidence", "Open a routine group, then the **Flow & Score** tab.",
     "Ports, packet counts, rule conditions and the model's top features.",
     "The analyst judges evidence, not only a score."),
    ("07-verdict", "Record a verdict", "Open **Analyst Verdict**. Pick an outcome, type a reason, click **Record Verdict**.",
     "Work status **Completed — Reviewed by Glenn Ang**.",
     "Each outcome moves the score within the guardrails. One verdict alone does not re-rank a family (3-vote gate)."),
    ("08-case-list", "Tier 2: the case list", "Left menu: **Tier 2 Cases**.",
     "Default filter Active. 3 cases say **Rule** with the rule sentence (auto-escalated). Your case shows **Glenn Ang** and your reason.",
     "The expert sees open work and who or what sent each case."),
    ("09-conclusion", "Investigate and conclude", "Open your case. **Audit Timeline**: reason, **Start investigation**. **Investigation Conclusion**: finding, class, reason, **Record Investigation Conclusion**.",
     "**Resolve Case** stays off until a conclusion exists. Then it turns on.",
     "A case cannot close without a recorded finding."),
    ("10-resolved", "Resolve the case", "Type a **Resolution Reason**. Click **Resolve Case**.",
     "**Resolved by: Glenn Ang**. All edit buttons go. A resolved case leaves the Active list but stays under Status = Resolved.",
     "The record is fixed for audit. Approving a response plan never executes it."),
    ("11-release", "Release a claim", "On an alert you own, click **Release claim**, then **Release**.",
     "The alert is available to others again.",
     "Shift change or wrong pick: work returns to the queue. Idle claims also expire after 15 minutes."),
]


def bold(text: str) -> str:
    parts = html.escape(text).split("**")
    return "".join(f"<strong>{p}</strong>" if i % 2 else p for i, p in enumerate(parts))


def main(src: Path, out: Path) -> None:
    pins = json.loads((src / "pins.json").read_text(encoding="utf-8"))
    (out / "img").mkdir(parents=True, exist_ok=True)
    cards = []
    for n, (name, title, click, see, why) in enumerate(STEPS, 1):
        shutil.copyfile(src / f"{name}.png", out / "img" / f"{name}.png")
        marks, legend = [], []
        for k, pin in enumerate(pins.get(name, []), 1):
            box = pin["box"]
            if not box:            # target not on screen at shot time: say so, place no pin
                legend.append(f"<li class=missing>{k}. {html.escape(pin['label'])} (not visible in this shot)</li>")
                continue
            left, top = 100 * box["x"] / W, 100 * box["y"] / H
            wid, hei = 100 * box["width"] / W, 100 * box["height"] / H
            if box["y"] + box["height"] > H or box["x"] + box["width"] > W or box["y"] < 0 or box["x"] < 0:
                # partly or fully outside the 1440x900 shot: do not draw a misleading pin at the edge
                legend.append(f"<li class=missing>{k}. {html.escape(pin['label'])} (below the visible area — scroll down)</li>")
                continue
            marks.append(f'<span class=box style="left:{left:.2f}%;top:{top:.2f}%;width:{wid:.2f}%;height:{hei:.2f}%"></span>'
                         f'<span class=pin style="left:{left:.2f}%;top:{max(top, 0):.2f}%">{k}</span>')
            legend.append(f"<li>{k}. {html.escape(pin['label'])}</li>")
        cards.append(f"""<section class=step id="s{n}">
<h2>Step {n}. {html.escape(title)}</h2>
<div class=shot><img src="img/{name}.png" alt="{html.escape(title)}">{''.join(marks)}</div>
<ol class=legend>{''.join(legend)}</ol>
<p><b>Click:</b> {bold(click)}</p><p><b>You see:</b> {bold(see)}</p><p class=why><b>Why (SOC):</b> {bold(why)}</p>
</section>""")
    page = f"""<!doctype html><html lang=en><meta charset=utf-8><title>HITL IDS — SOC demo guide</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#111}}
h1{{font-size:24px}} h2{{font-size:18px;margin:28px 0 8px}}
.shot{{position:relative;border:1px solid #ccc}} .shot img{{display:block;width:100%}}
.box{{position:absolute;border:3px solid #e8590c;border-radius:4px;box-sizing:border-box}}
.pin{{position:absolute;transform:translate(-50%,-50%);background:#e8590c;color:#fff;font:700 13px/24px system-ui;
 width:24px;height:24px;border-radius:50%;text-align:center}}
.legend{{list-style:none;padding:0;display:flex;gap:16px;flex-wrap:wrap;color:#e8590c;font-weight:600}}
.legend .missing{{color:#888;font-weight:400}} .why{{color:#444}}
</style>
<h1>HITL IDS — SOC demo guide (Tier 1 to Tier 2)</h1>
<p>Built from an automated run of <code>soc-flow.spec.ts</code> on a copy of the demo data. Every screenshot is
from that run, and the run checked the database after each step. Orange boxes mark what to click or read;
their positions were measured by the browser, not drawn by hand.</p>
{''.join(cards)}
</html>"""
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote {out / 'index.html'}: {len(cards)} steps, {sum(len(v) for v in pins.values())} pins")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
