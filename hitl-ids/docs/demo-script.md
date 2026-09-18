# Demo script — Human-in-the-Loop IDS (plan step S16)

**What this is.** The narrative the demo performs, click by click, with what the screen will show and
what to say. Every number below was produced by `scripts/rehearse_demo.py` against the demo database —
none is from memory or a slide. If a number here and the screen disagree, the screen is right and this
file is stale: rerun the rehearsal.

**The one-sentence thesis.** The model is confidently wrong, a human overrules it inside guardrails
that explain themselves, and the correction spreads — measurably and within limits — to the alerts
like it.

---

## Before the audience arrives

```
:: terminal 1 — from hitl-ids
.venv\Scripts\activate                     :: the project's Python 3.11; python --version must say 3.11
python scripts/run_detection.py            :: rebuild data/demo.db from scratch: 5,000 flows, ~21 s
python scripts/rehearse_demo.py            :: 46 checks on a throwaway copy; must end "holds end to end"
python -m uvicorn apps.api.main:app        :: API on :8000 — leave this terminal open

:: terminal 2 — from hitl-ids\apps\web
npm run e2e                                :: the same story in a real browser, on its own copy (<1 min)
npm run dev                                :: console on http://localhost:5173
```

**Rebuild `data/demo.db` before every audience.** Verdicts are permanent — the audit trail refuses
`UPDATE` and `DELETE` — so a database that has been demonstrated on is a database that has already been
judged. The rehearsal and the browser test (`npm run e2e`) both run on copies and never touch it.

Python comes from the project environment `hitl-ids\.venv` (3.11). **The `.venv` is not portable** — it
stores absolute paths — so recreate it on a new machine with any Python 3.11 interpreter
(`py -3.11 -m venv .venv`, or the full path to a 3.11 `python.exe`), then `.venv\Scripts\activate` and
`python -m pip install -r requirements.txt`. Do **not** use a bare `py -m venv`, which picks 3.12.
`npm run e2e` starts its own API and needs the interpreter named in terminal 2 —
`set HITL_PYTHON=<hitl-ids>\.venv\Scripts\python.exe` in cmd, `$env:HITL_PYTHON="...\python.exe"` in
PowerShell. It also needs the Chromium test browser once per machine: `npx playwright install chromium`.

---

## The narrative

### 1. Sign in as the analyst — the queue

*Sign in* → username `g.ang`, password `analyst-demo` → lands on the **Workstation** (queue, alert and context in
one view, "5,000 alerts"). Click **Alert Queue** in the sidebar for the full table, "Showing 1–50 of 5,000".

> Every flow becomes an alert — 5,000 of them. They are ranked by severity first (worst at the top),
> then by the operational score. Two score
> columns: *Detection* is what the detectors said and never changes; *Operational* is what analysts
> move. Sign-in is real: three seeded accounts, one per view, and the role travels inside the token.

### 2. `AL-00478` — a confident model that is wrong

Search `AL-00478` → open it. It is a **Tier 2 candidate** at **99.89**, rank 639.

- *Signature rules*: "No rule matched (ML-only alert)."
- *Model prediction*: **Web Attack**, with the features that pushed the model towards it and away.
- *Combined explanation*: why it sits where it does.

> The model is 99.9% sure this is a Web Attack. No rule agrees. **Ground truth says it is benign.**
> The decision is the analyst's.

Choose **False Positive** (requests −30) → **Record verdict**.

The chain reads **99.89 → requested −30.00 → guardrail: Bound → applied −29.89 → 70.00**, labelled
**Capped by a guardrail**, with the guardrail's own sentence: *"This alert is Critical, so its score was
held at the floor of 70."* The band moves **Tier 2 candidate → Model only**; the alert drops from rank
639 to rank 996.

> The verdict is recorded in full. What the guardrail limited is how far one verdict may move a
> Critical alert — not the analyst's finding. And it says so, with the number.

**Refresh the page.** The score is still 70.00, and the history shows the verdict *In effect*.

### 3. `AL-03086` — the attack both detectors missed

Search `AL-03086` → open it. Bottom band, **36.94**, nothing flagged it. **Ground truth: an attempted
Web Attack.**

Choose **True Positive** (requests +10) → **Record verdict** → **Applied as requested**:
36.94 → **46.94**, band **Nothing flagged it → Model only**.

> Say this plainly: it leaves the bottom band, but it only climbs from rank 998 to 997, because it was
> already the highest-scoring unflagged alert. One confirmation moves one band — that is the design (M1).

### 4. The saturation filter — a climb with full headroom

**Alert Queue** → Evidence **Model only** → Detection score **Below 100 — not saturated** → Sort
**Detection score**, **Ascending**. The queue narrows to **21 alerts of 5,000** — every other
flagged alert sits at *exactly* 100.0, where a confirming verdict clamps and no climb is visible.
This is score saturation, a property of the testbed the evaluation already reports (S15,
finding 4). Ascending puts the widest headroom on top: **`AL-00576` at 81.30 is the first row** —
in queue order it would be the last, buried under twelve 99.9xs that read as 100.00.

Search `AL-00576` → open it. **Model only**, detection **81.30** — the widest headroom below 100.

Choose **True Positive** (requests +10) → **Record verdict** → **Applied as requested**:
81.30 → **91.30**, band **Model only → Tier 2 candidate** — a True Positive on a severity ≥ 7 class
(Infiltration, 9.5) earns Tier 2 by the escalation rule E2.

> Two lessons in one verdict: the score climbs by the full +10 — no clamp — and the same click
> escalates, because confirming a high-severity class is itself an escalation trigger.
>
> **Why `AL-00576` and not `AL-02717`.** Both sit in this 21-alert set with headroom, and the
> ascending sort puts the *widest* headroom first — which is `AL-00576` at 81.30, not `AL-02717` at
> 88.48. And `AL-02717` is **benign** in the capture: confirming it would have the demo assert a
> true positive on a false positive. `AL-00576` is a genuine Infiltration, so the same two lessons
> are shown without the claim being false. `AL-02717` is the right alert for a **dismissal** —
> `system-workflow.md` records it as one, held at the floor of 70. Run
> `python scripts/list_false_positives.py` to see both lists before you present.

### 5. Similar-alert learning — alerts nobody touched move

Confirm three members of the **Port Scan / port 445** family: `AL-01696`, `AL-03873`, `AL-03153`.

- After the first and second: "Similar-alert learning did not apply" — *not enough learning verdicts:
  n of 3 required*.
- After the third: **"Similar-alert learning applied: 2 other alerts in this family moved."**

Search `AL-03044` and `AL-04526`: both are now **Tier 2 candidates**, with **no verdict of their own**.
Ground truth: all five are Port Scans.

**Do not read the count aloud and move on — show the table under it.** Since v1.32 the verdict
response lists the members it moved: each one's **score, band and queue rank before and after**.
Those are alerts nobody opened, let alone judged.

> One analyst cannot move a family. Three who agree can. Nothing outside the family moved.

**Then answer the question the panel is already forming: *what counts as similar?*** The panel under
the verdict shows it as fields, not prose — attack class, destination port, protocol, matched rule.
**Exact match on all of them.** There is no similarity score and no threshold, and the screen says
so. (For a flow no detector flagged, the destination address must match too, so one verdict cannot
spread across all benign traffic on a port.)

**Finally, switch the queue to Group by → Family.** The 5,000-row queue folds into the groups the
learning actually acts on, ordered by each group's best-ranked member — the same queue order, not a
second ranking. The Port Scan family now reads *gate open · 100% agree*, with its unjudged members
carrying the adjustment. Expand it to see them.

**If you want the strongest version of this beat, use a dismissal, not a confirmation.** 975 of the
996 flagged alerts sit at exactly 100.0, so a *confirming* verdict on a flagged family moves the
band but not the score. Dismissing three members of **Botnet · port 8080 · tcp** (150 alerts, none
judged) moves **147** of them `100.0 → 91.0`, `tier2_candidate → corroborated`, and the family's
best position in the queue from **rank 27 to rank 31**. Measured on a copy, 2026-09-18.

### 6. The administrator

**Sign out** → sign in as `admin` / `admin-demo` → *Guardrails*. The guardrail log shows the cap on `AL-00478`
with the same sentence. *Audit Trail* shows every verdict, guardrail action and family-learning event,
exportable as CSV.

### 7. The evaluator — including the result that went the wrong way

**Sign out** → sign in as `evaluator` / `evaluator-demo` → open the **newest** evaluation run
(the list is newest-first, so it is the top row; it is *not* pinned to a fixed run id — the
evaluation re-runs, and a hard-coded id goes stale).

- Detection metrics are **identical across all three arms**: feedback reordered the queue and never
  touched the detector.
- **Precision@50 holds at 1.000 under feedback** (Δ 0.000). The severity-first queue removed the fall
  the old band order caused; the deltas that remain are small and still negative, and the banner shows
  them as measured.

> The control queue was already near-perfect, so feedback had almost nothing to gain — and under the
> severity-first order it no longer costs a top-50 place either. Family learning still promoted a
> benign alert, but only to rank 186. We report the deltas that remain as measured, negatives and all,
> rather than only the ones that flatter the design.

---

## Known limitations — say them before you are asked

| Limitation | Why it is so |
|---|---|
| Accounts are seeded and their passwords are committed | It is an offline demo; real user management is S18 (along with Postgres) |
| Detection is an offline batch; "Check again" reports the latest run | A 21-second job does not belong inside an HTTP request (D3) |
| Families are a coarse key (class, port, protocol, rule) | It is what promoted a benign alert to rank 1 in the evaluation |
| The 0.99 macro F1 is a property of the testbed | Each attack class was generated by a single tool; not a real-world claim |
| Feedback could not improve precision on this sample | The control queue was already at precision 1.000 to k = 200 |
| `AL-03086` climbs one rank | One confirmation moves one band (M1); it was already top of its band |
| A confirming verdict on a saturated (100.0) alert clamps | 975 of 996 flagged alerts sit at exactly 100.0 (S15 finding 4); the not-saturated filter exists to find the 21 that do not |

## Why the narrative changed from the plan's v1.1 text

Plan v1.1 said confirming `AL-03086` would move "four *similar* alerts nobody touched". Its family has
**one member** — the Benign family key includes the destination address — so that step could not be
performed. The rehearsal found a family where it can: `Port Scan / 445`, five members, two of which move.
Recorded in `plan-changelog.md` v1.21 and `deviations.md` E6.
