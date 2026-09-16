# Workflow test cases — for the tester

Acceptance tests for the console, written to be performed **by hand, in the browser**, by the
tester. Every case states exactly what to do, what should happen, and what it should look like —
so a failure is either "it does not work" or "it does not look right", and both are recordable.
Companion documents: [`tier1-analyst-workflow.md`](tier1-analyst-workflow.md) (what the workflow
*is*), [`demo-script.md`](demo-script.md) (the presentation narrative), and the automated suites
(427 Python tests, 129 web tests, the e2e narrative) — this file covers what only a human can
judge.

## How to run these

1. Two terminals, both from `hitl-ids` with `.venv` active:
   - `python -m uvicorn apps.api.main:app` (API on :8000)
   - `cd apps/web && npm run dev` (console on :5173)
2. **Rebuild the database before a full pass** — verdicts are permanent:
   delete `data\demo.db` first (a rebuild *appends*, never truncates), then
   `python scripts/run_detection.py` (~21 s).
3. Work the cases in order — later cases depend on earlier verdicts. Sections **L** (looks) can be
   checked at any point.
4. Record each result: **PASS / FAIL / LOOKS-WRONG** plus a note. A case with a wrong number is
   FAIL even if the screen looks fine.

The three accounts: `g.ang`/`analyst-demo` (analyst) · `admin`/`admin-demo` (administrator) ·
`evaluator`/`evaluator-demo` (evaluator).

---

## A. Sign-in and sessions

| # | Steps | Expected |
|---|---|---|
| A1 | Open `http://localhost:5173/analyst/queue` while signed out | Redirected to `/login`; the sign-in card shows the IDS Console heading, Username and Password fields, a Sign in button, and **no role picker of any kind** |
| A2 | Sign in as `g.ang` / `analyst-demo` | Lands on `/analyst/workstation`; the strip reads "5,000 alerts" |
| A3 | Sign in as `g.ang` with a wrong password | Stays on `/login`; a red alert line reads "Invalid username or password"; nothing else changes |
| A4 | While signed in, press F5 | Still signed in, same page — the session survives a refresh |
| A5 | Click **Sign out** (top right) | Lands on `/login`; navigating back to an analyst URL redirects to `/login` again |
| A6 | Sign in as `admin` / `admin-demo` | Lands on `/admin/status` (System Status) |
| A7 | Sign out, sign in as `evaluator` / `evaluator-demo` | Lands on `/evaluator/scenarios` |
| A8 | As `evaluator`, manually open `/analyst/workstation` | Redirected to `/evaluator/scenarios` — an account cannot reach another view's pages |
| A9 | Type into the Password field, then hold the pointer over the **eye** icon inside the field | The typed password is visible as plain text only while the pointer (or a press) is on the eye; the icon switches to a struck-through eye; the password is masked again the instant the pointer leaves — for checking a mistyped password by eye without leaving it revealed |

## B. The workstation shell

| # | Steps | Expected |
|---|---|---|
| B1 | Sign in as `g.ang` | Three columns: queue (left), selected alert (centre), context (right); top bar has the account name, UTC clock, **Sign out** — and **no role-switch dropdown and no amber stub badge** |
| B2 | Read the counts strip | Eight figures: Critical, Tier 2 candidates, Needs review, Unresolved, Verdicts, False positives, Guardrail actions, Total alerts (Total = 5,000 on a fresh build) |
| B3 | Find the "Recorded flows" badge (top left, wider screens) | Present, with its tooltip: scores are recorded lab flows, not a live feed |
| B4 | Sidebar | Exactly six analyst items: Workstation, Overview, Dashboard, Alert Queue, Investigations, Feedback Impact — no admin or evaluator items |

## C. Queue and navigation

| # | Steps | Expected |
|---|---|---|
| C1 | Workstation → band tabs | Tabs read All / Tier 2 / Needs review / Rule + model / Rule only / Model only / Not flagged, each with a count; All = 5,000 |
| C2 | Click the **Tier 2** tab | Only Tier 2 candidate rows remain |
| C3 | Click **Not flagged** | Only unflagged rows — the queue's bottom band |
| C4 | Type `AL-00478` in the search box, press Enter | The list narrows to that alert; click it — the centre pane shows it |
| C5 | Press `j`, then `k` | Selection moves down the queue, then back; the centre pane follows without a click |
| C6 | Open **Alert Queue** (sidebar) | The full table: band, reference, **two score columns** (Detection, Operational), predicted class, flow, rule; filters for band / evidence / severity / class; the chosen filter appears in the address bar |
| C7 | Apply a filter, then F5 | The filtered view survives the refresh |
| C8 | In the queue page click an IP address in a row | The IP entity page for that address opens |
| C9 | Queue page: Evidence **Model only** + Detection score **Below 100 — not saturated** | Exactly **21 of 5,000** alerts — the flagged ones not saturated at 100.0; `AL-02717` (88.48) and `AL-00576` (81.30) are among them; the filter sits in the address bar and survives F5 |

## D. One alert's evidence

| # | Steps | Expected |
|---|---|---|
| D1 | Select `AL-00478` | Header: band **Tier 2 candidate**, evidence **Model only**, severity; three meters — operational 99.89, detection 99.89 (equal: no verdict yet), model confidence high |
| D2 | Read the four panels | **Flow** (addresses, ports, protocol, duration, packets, bytes) · **Signature rules** says no rule matched (ML-only alert) · **Model prediction**: Web Attack with SHAP features **towards and away** · **Combined explanation** in plain sentences |
| D3 | Context rail | The flow drawn, both addresses clickable, and a **family** summary card |
| D4 | Click a source address in the context rail | The IP entity page: alert count, flagged share, first/last seen, bands, classes, verdicts, top peers (each clickable) and ports; a link **All alerts for this address** opens the workstation searched for it |
| D5 | From the queue, open `AL-01958` (Brute Force) | The **Signature rules** panel lists each rule clause beside the value this flow actually had — checkable, not just "matched" |

## E. Status and ownership (workflow, never a score)

| # | Steps | Expected |
|---|---|---|
| E1 | On a fresh alert, click **Claim** | Status becomes *claimed*; the alert shows you as owner; the score does not move |
| E2 | Click **Start work** | Status *in progress*; score still unchanged |
| E3 | Click **Resolve** | Status *resolved*; the alert is closed |
| E4 | On the resolved alert, try to claim it again | Refused — a closed alert reopens only to *in progress* (the button/option is not offered, or the refusal is shown) |
| E5 | Reopen it, then return it to *new* | The alert is released — owner cleared, available to a colleague |
| E6 | Sign in as `admin`, open **Audit Trail**, filter status changes | Every step above is one `ALERT_STATUS_CHANGE` entry, with your account as actor and a timestamp |

## F. Verdicts and the guardrails

| # | Steps | Expected |
|---|---|---|
| F1 | On `AL-00478` (99.89, Critical), choose **False Positive** | The form shows the requested change (**−30**) **before** you commit |
| F2 | Click **Record verdict** | The outcome region appears: chain reads **99.89 → requested −30 → guardrail: Bound → applied −29.89 → 70.00**, labelled **Capped by a guardrail**, with the sentence *"This alert is Critical, so its score was held at the floor of 70."* The band changes **Tier 2 candidate → Model only** and the alert drops down the queue |
| F3 | Press F5 | The adjusted score and chain persist (the S12 check) |
| F4 | Record **True Positive** on `AL-03086` (36.94, both detectors missed it) | Applied as requested (+10); the alert climbs **one band**, out of the bottom |
| F5 | Record **Benign Positive** on another alert | Requested −15 applied (or bounded, with the guardrail's sentence if it is) |
| F6 | Record **Needs investigation** on another alert | Zero change; the alert is flagged for review |
| F7 | Record **Escalate to Tier 2** on a mid-queue alert | Requested +15, forces review, and the alert appears in the **Tier 2** tab |
| F8 | On any judged alert, record a *different* verdict | The new verdict **replaces** the old one (does not stack); the history shows both, the latest in effect |
| F9 | Open the alert's verdict history | Every verdict, oldest first, superseded ones included; nothing edited or deleted |

## G. Notes

| # | Steps | Expected |
|---|---|---|
| G1 | On any alert, write a note and add it | The note appears in the thread with your account name and a timestamp |
| G2 | Add a second note | The thread stays oldest-first; the first note is unchanged — append-only |
| G3 | Try to submit an empty note | Refused |

## H. Escalation — the three routes

| # | Steps | Expected |
|---|---|---|
| H1 | Fresh build, Tier 2 tab | 644 Tier 2 candidates exist **before anyone acts** — automatic escalation (corroborated-and-Critical, or score ≥ 90 with severity ≥ 7) |
| H2 | Needs review tab | Exactly the review-flagged alerts: Critical corroborated/model-only, signature overrides, and any verdict that forces review |
| H3 | Record **Escalate to Tier 2** (F7) | The alert joins the Tier 2 band — the analyst-driven route |
| H4 | Family learning: record **True Positive** on `AL-01696`, `AL-03873` (Port Scan / 445 family) | Each says similar-alert learning did **not** apply yet (the gate needs three) |
| H5 | Record **True Positive** on `AL-03153` (the third) | "Similar-alert learning applied: 2 other alerts moved." `AL-03044` and `AL-04526` — never judged by anyone — are now **Tier 2 candidates** with no verdict of their own: three agreeing analysts taught the queue |
| H6 | Record **False Positive** on an escalated alert | Its Tier 2 candidacy is **withdrawn** — and it does not drop below where it was |

## I. The watching pages

| # | Steps | Expected |
|---|---|---|
| I1 | **Dashboard** | Queue composition by band; *Needs a human* lists top unjudged alerts; *Moved by feedback* is non-zero after F/H cases |
| I2 | **Overview** | Hourly histogram of the capture with flagged share; top source/destination addresses, destination ports, predicted classes, verdicts in force, triage status, guardrail interventions — every chart also a table |
| I3 | **Investigations** | Every verdict you recorded, newest first, attributed to your account |
| I4 | **Feedback Impact** | The Port Scan / 445 family shows as learned, with the members that moved; guardrail interventions listed |

## J. Persistence and honesty

| # | Steps | Expected |
|---|---|---|
| J1 | Sign out mid-shift and sign back in as `g.ang` | Everything persisted: statuses, owners, verdicts, notes, moved alerts |
| J2 | Dashboard *Check again* (admin) | Reports the latest run; a new run is never started from the browser |
| J3 | Open the API directly: `http://localhost:8000/api/alerts?limit=1` | **401 with the error envelope** — the API trusts nobody without a token |

## K. Administrator and evaluator (the other accounts)

| # | Steps | Expected |
|---|---|---|
| K1 | As `admin` → **Guardrails**: change Critical alert floor and save **without** a reason | Refused — a written reason is required |
| K2 | Supply a reason and save a valid change | Applied; the Audit Trail records what changed and why |
| K3 | Try an inconsistent change (floor above the critical threshold) | Refused by the form before it is sent |
| K4 | As `admin`, try to open `/analyst/workstation` | Redirected to `/admin/status` |
| K5 | As `evaluator` → the newest run (`20260916T063856Z`) | The three arms; false positives in the top 50 is **0** in every arm, and the remaining deltas are still shown as measured (precision@200 −0.010, mean true-positive rank −0.515) |
| K6 | As `evaluator`, try to record a verdict or claim an alert | No analyst actions are offered anywhere in the evaluator view |

## L. Looks — how it should look

| # | Where | Expected look |
|---|---|---|
| L1 | Sign-in page | One centered card, the accent square, no role chips, no stub notices, no amber styling anywhere |
| L2 | Top bar | Clean: console mark, *Recorded flows* badge, clock, avatar initials, account name, Sign out — nothing that says "demo stub" |
| L3 | Workstation | Dense, three columns, monospace numbers aligned; counts strip reads as one line |
| L4 | Queue rows | Band chip, reference, two score columns clearly labelled Detection and Operational; hover states on rows and links |
| L5 | Verdict form | Five options each showing its delta; selected option clearly highlighted; **Record verdict** disabled until a choice is made |
| L6 | Guardrail outcome | The chain reads left-to-right as a story; the guardrail sentence is prose, not a code |
| L7 | Empty/error states | A page with no data says so plainly; no raw JSON, no stack traces, no unstyled elements |
| L8 | Narrow window (~tablet) | Layout degrades gracefully: columns stack, no horizontal scroll of the page body |
| L9 | Whole session | Consistent type, spacing and colour throughout; nothing flashes or shifts on load after data arrives |

---

**Result summary** — record per section: A __ · B __ · C __ · D __ · E __ · F __ · G __ · H __ ·
I __ · J __ · K __ · L __ · Tester ____________ · Date ________ · Build/commit ____________
