# The Tier 1 analyst's workflow — the console as a SOC first-liner works it

This document recounts the day-to-day workflow of the system's main user, the **Tier 1 (first-line)
security analyst**, in the terms a real Security Operations Centre uses, and maps every step to what
the console actually shows and does. Every number here is the code's number, not an aspiration:
fusion is `packages/detection/fusion/cef.py`, verdicts and guardrails are
`packages/detection/feedback/service.py`, family learning is `packages/detection/feedback/learning.py`
+ `packages/detection/ranking/formulas.py`, status and notes are `packages/detection/triage.py`.

The analyst signs in as **`g.ang` / `analyst-demo`** (real sign-in since S18a: bcrypt-checked, an
8-hour signed token, no role picker). In SOC terms their mandate is the classic first-line one —
**monitor, triage, escalate, document** — and the console is organised around exactly that loop.

---

## 1. Shift start — take the pulse

The analyst signs in and lands on the **Workstation** (`/analyst/workstation`). Before touching a
single alert, a first-liner takes the pulse of the queue they inherited:

- The **counts strip** across the top: Critical · Tier 2 candidates · Needs review · Unresolved ·
  Verdicts · False positives · Guardrail actions · Total alerts. This is the shift's starting
  posture — how deep the backlog is, how much has already been judged, how much is waiting for a
  human.
- The **Recorded flows** badge: an honesty marker. This console scores a recorded CSE-CIC-IDS2018
  capture, not a live feed — no first-liner should believe they are watching traffic in real time.

From here the analyst can also open the **Dashboard** (`/analyst/dashboard`) for the run-level view —
*Queue composition* (where the 5,000 alerts sit by band), *Needs a human* (the highest-ranked alerts
still awaiting review), and *Moved by feedback* (0 until somebody records a verdict) — or the
**Overview** (`/analyst/overview`) for the capture window: one histogram bar per hour with the
flagged share at its base, the busiest source and destination addresses, busiest destination ports,
alerts by predicted class, the verdicts in force, triage status and guardrail interventions — every
chart repeated as a table.

## 2. Working the queue — rank is triage order

The queue is the work list, and its order *is* the triage policy. Bands, top first:

| Band | What it means | How an alert lands here |
|---|---|---|
| **Tier 2 candidates** | Escalated — see §6 | Automatic criteria, an analyst verdict, or family learning |
| **Corroborated** | A rule and the model agree on the class | Evidence class, ranked by score |
| **Signature override** | A rule fired, the model disagrees — always reviewed | Evidence class (invariant I2) |
| **Model only** | Only the model flagged it | Evidence class |
| **Not flagged** | No detector fired — the queue's denominator | Evidence class |

Tabs above the queue filter it by band (All · Tier 2 · Needs review · Rule + model · Rule only ·
Model only · Not flagged). The search box finds a record id, an address or a rule id; on the full
**Alert Queue** page (`/analyst/queue`) the same table gains filters by band, evidence, severity and
attack class, sorts (queue order, combined score, detection score, severity, created time), and
lives in the address bar so a filtered view survives a refresh.

Two score columns side by side, everywhere: **Detection** — what the detectors produced, frozen; and
**Operational** — what analyst feedback moves. The first-liner's whole job is visible in the gap
between those two numbers.

Keyboard: `j` / `k` walk the list; the centre pane follows.

## 3. The per-alert loop — the heart of first-line work

A Tier 1 analyst works one alert at a time, and the workstation puts everything for that decision in
three columns: **queue (left) · selected alert (centre) · context (right)**.

1. **Open the alert** (click its card or row). The header shows band, evidence class, severity, and
   three meters: the **operational score** (feedback moves it), the **detection score** (fixed), and
   the **model's confidence**.
2. **Read the four evidence panels** — everything the system knows, so the analyst checks rather than
   trusts:
   - **Flow** — what actually crossed the wire (addresses, ports, protocol, duration, packets, bytes).
   - **Signature rules** — the clauses a hand-written rule requires, beside the values this flow
     actually had; when nothing matched, the panel says so instead of showing an empty box.
   - **Model prediction** — the class, the confidence, and the SHAP measurements that pushed the
     prediction towards its class *and away from it* (supporting evidence only would be advocacy).
   - **Combined explanation** — why the alert sits where it does, in a sentence the analyst can
     repeat in a handover.
3. **Read the context rail** — the flow drawn out, what the recording holds about **both addresses**
   (each opens the full IP entity page: alert counts, first/last seen, bands, classes, verdicts, top
   peers and ports — and *All alerts for this address* opens the workstation searched for it), and
   the alert's **family** summary.
4. **Take ownership** before working: **Claim** (or **Start work**) makes the analyst the alert's
   owner. Status and owner are workflow, never judgement — they **cannot move a score**.
5. **Decide** — record a verdict (§4).
6. **Document** — the notes thread (§5).
7. **Close or pass on** — **Resolve** (handled) or **Dismiss** (not worth more time); a closed alert
   can be reopened to *in progress*; returning an alert to *new* releases it for a colleague.

Status transitions are explicit and audited — `new → claimed → in_progress → resolved | dismissed`,
release back to `new`, reopen from closed to `in_progress`; an impossible transition is refused with
a 409, never silently accepted. Every change writes an `ALERT_STATUS_CHANGE` audit entry.

## 4. Recording a verdict — the judgement

Five verdicts, with the closing labels security teams use, each showing the score change it requests
**before** the analyst commits:

| Verdict (button) | Requested change | Forces review | Teaches the family? |
|---|---|---|---|
| **True Positive** | +10 | yes | yes (confirming) |
| **Escalate to Tier 2** | +15 | yes | yes (counts as confirming) |
| **Needs investigation** | 0 | yes | no — teaches nothing |
| **Benign Positive** (expected activity) | −15 | no | yes (dismissing) |
| **False Positive** | −30 | no | yes (dismissing) |

An optional note is recorded with the verdict. A new verdict **replaces** the previous one rather
than stacking (the old one stays in history, superseded) — the score is always *detection score +
the guarded change of the latest verdict*.

### The guardrails — what bounds the request

The request is a request. What actually applies is bounded, and the **score adjustment chain**
shows the whole story: detection score → requested → which guardrail bound it → what was applied →
the resulting operational score, with the guardrail's own sentence:

- A single verdict may move a score by at most **30** points (`max_feedback_reduction`).
- Negative feedback cannot push a **Critical** alert (score ≥ 80) below **70** (`critical_alert_floor`)
  or an **Infiltration** alert below **75** (`infiltration_alert_floor`).
- Where a high-precision rule fired and the model disagrees (`signature_override`), feedback cannot
  lower the score at all — the disagreement is either a rule regression or an analyst error, and
  neither is fixed by quietly editing a number; the alert goes to the administrator instead
  (invariant I3).
- Everything stays inside 0–100.

A capped or refused change is still **recorded in full** — the guardrail limited the *score change*,
not the analyst's finding, and the audit trail gains `FEEDBACK`, `GUARDRAIL_INTERVENTION` and
`SIMILAR_ALERT_LEARNING` entries as they happen.

## 5. Notes — the record a Tier 2 inherits

Every alert keeps a notes thread, author and timestamp on each note, **append-only** (a correction
is a new note — an investigation record that can be edited is not a record). This is what a Tier 2
analyst reads first when an escalation lands on them, and what a shift handover is written from.

## 6. Escalation to Tier 2 — automatic and earned

Escalation is the queue's **Tier 2 candidates** band, which sits above every evidence band. An alert
gets there three ways:

1. **Automatic, at detection time** (`ranking/formulas.py::tier2_candidate`):
   - **E1 — corroborated and Critical**: a rule and the model agree on the class *and* the combined
     score is at or above the critical threshold (**80**). Two independent detectors agreeing at
     critical confidence is not a Tier 1 question.
   - **E3 — score ≥ 90 and severity ≥ 7** on the CVSS-style severity chart.
   These fire with no human in the loop, the moment detection runs.
2. **By the analyst's own verdict (E2)**: choosing **Escalate to Tier 2**, or confirming a **True
   Positive** on an alert whose severity is ≥ 7, makes that alert a Tier 2 candidate. Escalation
   also forces the review flag and requests +15, so an escalated alert cannot sink quietly.
3. **By family learning, after agreement**: once a family holds **at least 3** learning verdicts
   with **no tie** and a dominant direction holding **at least 2/3 (0.67)** of them, its learned
   adjustment reaches every member with no verdict of its own — they are re-scored
   (detection + the family's guarded adjustment, formula **C2**, an Elo-style step chosen by
   experiment) and promoted **one band per confirming verdict** (movement **M1**; two dismissals are
   needed before a demotion — the hysteresis that stops one noisy verdict thrashing the queue).
   This is how the alerts *nobody judged* move into Tier 2: three agreeing analysts teach the queue.

A family is a coarse key — attack class, destination port, protocol, first matched rule (plus the
destination address for unflagged flows, so a verdict on one benign flow cannot spread across a
port). Learning never crosses families, and `signature_override` alerts neither teach nor learn.

**The Tier 1 counter-decision**: a dismissing verdict (False Positive / Benign Positive) on an alert
**withdraws its Tier 2 candidacy** — that is the first-liner saying "this does not need Tier 2" —
but moves it no lower, because clearing an alert is a judgement, not a reason to bury its neighbours.

What Tier 2 receives: the alert in the top band, its full verdict history and adjustment chain, the
notes thread, its family context, and the audit trail behind all of it.

## 7. Keeping watch during the shift

- **Dashboard** — queue composition, *Needs a human*, *Moved by feedback*: is the backlog draining,
  and is feedback visibly reordering the queue?
- **Overview** — capture-window behaviour: talkers, ports, class mix, verdicts in force, triage
  status, guardrail interventions.
- **Investigations** (`/analyst/investigations`) — every verdict recorded, newest first.
- **Feedback Impact** (`/analyst/feedback-impact`) — which families learned, which alerts moved, and
  what the guardrails stopped.
- **IP entity pages** — one address's whole story; peers open their own pages.

## 8. Shift end — the handover

The state the next shift inherits is the state the system keeps: every alert's status and owner,
every verdict (superseded ones included, oldest-first history intact), every note, every guardrail
intervention and every family-learning event — all append-only, all attributed to a signed-in
account, all visible to the administrator in the **Audit Trail**. Nothing is edited, nothing is
deleted.

## 9. Honest boundaries

This console models first-line triage, not the whole SOC: detection is an offline batch over a
recorded capture (there is no live feed, and "Check again" reports the latest run); there is no
ticketing integration, no case management beyond status/owner/notes, and no chat between tiers.
The accounts are seeded (`g.ang`, `admin`, `evaluator`) with committed demo passwords because it is
an offline demonstration.

---

## Appendix — every control the Tier 1 analyst sees or clicks

| Screen | Control / element | What it does |
|---|---|---|
| Sign-in | Username, Password (hold the **eye** to peek at it — masked again the moment the pointer leaves), **Sign in** | Real authentication; lands on the workstation |
| Top bar | avatar, account name, UTC clock, **Sign out** | Identity; no role switch exists — another view is another account |
| Sidebar | Workstation · Overview · Dashboard · Alert Queue · Investigations · Feedback Impact | The analyst's six pages |
| Workstation | Counts strip (8 figures) | Shift posture at a glance |
| Workstation | Band tabs (All / Tier 2 / Needs review / Rule + model / Rule only / Model only / Not flagged) | Filter the queue list |
| Workstation | Search box | Find a record id, address or rule id |
| Workstation | `j` / `k` | Walk the queue; the centre pane follows |
| Workstation queue card | band, ref, scores, class, flow, rule | One alert's summary; click to select |
| Alert header | band, evidence, severity + 3 meters (operational / detection / confidence) | The decision's frame |
| Alert panels | Flow · Signature rules · Model prediction (SHAP both ways) · Combined explanation | The evidence, checkable |
| Context rail | flow diagram · both addresses (click → IP page) · family summary | The neighbourhood |
| Alert actions | **Claim** · **Start work** · **Resolve** · **Dismiss** (+ release / reopen per the transition table) | Status and owner; never a score |
| Verdict form | **True Positive** (+10) · **Escalate to Tier 2** (+15) · **Needs investigation** (0) · **Benign Positive** (−15) · **False Positive** (−30), note field, **Record verdict** | The judgement; deltas shown before commit |
| Outcome region | score adjustment chain + guardrail sentence + family effect | What actually happened, and why |
| Notes | note box, **Add note**, thread with author + time | Append-only record |
| Alert detail page | the four panels + verdict history (oldest first, superseded kept) | The full record |
| Alert Queue page | the full table + filters (band, evidence, severity, class, detection-score ceiling), sorts, URL-persisted filters, paging | Deep triage |
| IP entity page | counts, bands, classes, verdicts, top peers (clickable), ports, **All alerts for this address** | One address's story |
| Dashboard | Queue composition · Needs a human · Moved by feedback | The run at a glance |
| Overview | hourly histogram, talkers, ports, class mix, verdicts, triage status, guardrail actions | The capture window |
| Investigations | verdict list, newest first | What the shift judged |
| Feedback Impact | families that learned, alerts moved, guardrail interventions | What feedback changed |
