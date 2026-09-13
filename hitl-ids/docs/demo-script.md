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
cd hitl-ids
python scripts/run_detection.py            # rebuild data/demo.db from scratch: 5,000 flows, ~21 s
python scripts/rehearse_demo.py            # 41 checks on a throwaway copy; must end "holds end to end"
cd apps/web && npm run e2e && cd ../..     # the same story in a real browser, on its own copy (~45 s)
python -m uvicorn apps.api.main:app        # API on :8000
cd apps/web && npm run dev                 # console on http://localhost:5173
```

**Rebuild `data/demo.db` before every audience.** Verdicts are permanent — the audit trail refuses
`UPDATE` and `DELETE` — so a database that has been demonstrated on is a database that has already been
judged. The rehearsal and the browser test (`npm run e2e`) both run on copies and never touch it.

Use Python 3.11 (`C:/ProgramData/miniconda3/python.exe` on the development machine).

---

## The narrative

### 1. Sign in as the analyst — the queue

*Sign in* → username `g.ang`, choose **Analyst** → lands on **Alert Queue**, "Showing 1–50 of 5,000".

> Every flow becomes an alert — 5,000 of them. They are ranked by band first, then by score. Two score
> columns: *Detection* is what the detectors said and never changes; *Operational* is what analysts
> move. The amber badge is honest: sign-in is a stub in the demo build.

### 2. `AL-00478` — a confident model that is wrong

Search `AL-00478` → open it. It is a **Tier 2 candidate** at **99.89**, rank 639.

- *Signature rules*: "No rule matched (ML-only alert)."
- *Model prediction*: **Web Attack**, with the features that pushed the model towards it and away.
- *Combined explanation*: why it sits where it does.

> The model is 99.9% sure this is a Web Attack. No rule agrees. **Ground truth says it is benign.**
> The decision is the analyst's.

Choose **Mark false positive** (requests −30) → **Record verdict**.

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

Choose **Confirm true positive** (requests +10) → **Record verdict** → **Applied as requested**:
36.94 → **46.94**, band **Nothing flagged it → Model only**.

> Say this plainly: it leaves the bottom band, but it only climbs from rank 998 to 997, because it was
> already the highest-scoring unflagged alert. One confirmation moves one band — that is the design (M1).

### 4. Similar-alert learning — alerts nobody touched move

Confirm three members of the **Port Scan / port 445** family: `AL-01696`, `AL-03873`, `AL-03153`.

- After the first and second: "Similar-alert learning did not apply" — *not enough learning verdicts:
  n of 3 required*.
- After the third: **"Similar-alert learning applied: 2 other alerts in this family moved."**

Search `AL-03044` and `AL-04526`: both are now **Tier 2 candidates**, with **no verdict of their own**.
Ground truth: all five are Port Scans.

> One analyst cannot move a family. Three who agree can. Nothing outside the family moved.

### 5. The administrator

Switch role → **System Administrator** → *Guardrails*. The guardrail log shows the cap on `AL-00478`
with the same sentence. *Audit Trail* shows every verdict, guardrail action and family-learning event,
exportable as CSV.

### 6. The evaluator — including the result that went the wrong way

Switch role → **Evaluator** → run `20260912T032022Z`.

- Detection metrics are **identical across all three arms**: feedback reordered the queue and never
  touched the detector.
- **Precision@50 fell from 1.000 to 0.980 under feedback** (Δ −0.020). The banner says so.

> The control queue was already near-perfect, so feedback could only disturb it — and in the recorded
> run, family learning promoted a benign alert to rank 1. We report that, rather than only the deltas
> that flatter the design.

---

## Known limitations — say them before you are asked

| Limitation | Why it is so |
|---|---|
| Authentication is a role-switch stub | Deferred to S18 (JWT, bcrypt, RBAC) by the demo-first decision |
| Detection is an offline batch; "Check again" reports the latest run | A 21-second job does not belong inside an HTTP request (D3) |
| Families are a coarse key (class, port, protocol, rule) | It is what promoted a benign alert to rank 1 in the evaluation |
| The 0.99 macro F1 is a property of the testbed | Each attack class was generated by a single tool; not a real-world claim |
| Feedback could not improve precision on this sample | The control queue was already at precision 1.000 to k = 200 |
| `AL-03086` climbs one rank | One confirmation moves one band (M1); it was already top of its band |

## Why the narrative changed from the plan's v1.1 text

Plan v1.1 said confirming `AL-03086` would move "four *similar* alerts nobody touched". Its family has
**one member** — the Benign family key includes the destination address — so that step could not be
performed. The rehearsal found a family where it can: `Port Scan / 445`, five members, two of which move.
Recorded in `plan-changelog.md` v1.21 and `deviations.md` E6.
