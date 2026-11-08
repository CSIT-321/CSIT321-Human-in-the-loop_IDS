# Self-test checklist — try the SOC flow yourself (before the user documentation)

Purpose: repeat, by hand, what `soc-flow.spec.ts` proves automatically. Work on a **copy** of the data.
Every action you take is stored for good; a judged database cannot be "un-judged".

Time: about 20 minutes. Accounts: `g.ang` / `analyst-demo` (analyst), `admin` / `admin-demo`.

## A. Set up a disposable copy (once)

Open Git Bash in `hitl-ids`.

1. Copy the demo data:
   `cp data/demo.db "$LOCALAPPDATA/Temp/hitl-review/selftest.db"`
2. Group and route the copy (about 45 s):
   `.venv/Scripts/python.exe scripts/materialize_flow_queue.py --database "$LOCALAPPDATA/Temp/hitl-review/selftest.db"`
   Expected last lines: `routed: ...` and `routed unflagged: ...`.
3. Start the API on the copy:
   `HITL_IDS_DB="$(cygpath -m "$LOCALAPPDATA/Temp/hitl-review/selftest.db")" .venv/Scripts/python.exe -m uvicorn apps.api.main:app --port 8000`
4. In a second Git Bash, start the console: `cd apps/web && npm run dev`
5. Open `http://localhost:5173` and sign in as `g.ang`.

Check before you start: run `curl -s localhost:8000/api/health` and confirm the API window shows no error.
The console does not show which database file the API opened. If you skipped step 3's `HITL_IDS_DB`, the
API opens the real `data/demo.db` — so always start it with the exact command above.

## B. Checklist

Tick each line only when you see the expected result. Write what you saw if it differs.

| # | Do this | Expected result | Seen? |
|---|---|---|---|
| 1 | Look at the queue view tabs | Tabs include Active, Tier 1 "78 groups · 4,004 single", Tier 2 candidates 74, Auto-escalated 3 | ☐ |
| 2 | Click **Tier 2 candidates**, then click the first row | The row says "In Review — You"; the work panel says "Your Access: Owner" | ☐ |
| 3 | Open **History & Notes**, type a note, click **Add note** | The note shows with your name "Glenn Ang". There is no Edit or Delete | ☐ |
| 4 | Open **Overview** | A brown "Why Tier 2 is recommended" panel shows the reason (e.g. "E3: score 100 and Infiltration …") | ☐ |
| 5 | Click **Escalate to Tier 2** with the reason field empty | The button stays off — a reason is required | ☐ |
| 6 | Type a short reason, click **Escalate to Tier 2** | The work status becomes "Escalated"; the alert leaves the Active list | ☐ |
| 7 | Click **Tier 1**, open a routine group, open **Flow & Score** | Flow cards show ports, packet counts and the score explanation | ☐ |
| 8 | Open **Analyst Verdict**, pick "Confirmed Malicious", type a reason, click **Record Verdict** | Status "Completed — Reviewed by Glenn Ang" | ☐ |
| 9 | Click **Auto-escalated** | 3 Brute Force groups. You cannot claim them — the system already sent them to Tier 2 | ☐ |
| 10 | Left menu → **Tier 2 Cases** | Status filter shows "Active (open + investigating)". 4 cases: 3 say "Rule" with the E1 sentence; 1 says "Glenn Ang" with your reason | ☐ |
| 11 | Open your case → **Audit Timeline** → reason → **Start investigation** | Case status "investigating" | ☐ |
| 12 | Scroll to **Case Resolution** before a conclusion | **Resolve Case** is off | ☐ |
| 13 | **Investigation Conclusion** → "Confirmed Malicious", "Infiltration", reason → **Record Investigation Conclusion** | "Latest Finding: confirmed malicious" | ☐ |
| 14 | Type a resolution reason → **Resolve Case** | "Resolved by: Glenn Ang / #1"; all edit buttons are gone | ☐ |
| 15 | **All Tier 2 cases** | Your case is not in the Active list. Set Status to "Resolved": it is there | ☐ |
| 16 | Back to the workstation, open another Tier 2 candidate, click **Release claim** → **Release** | The row is free again ("Available") | ☐ |
| 17 | Sign out, sign in as `admin`, open **Overview** | "Claimed alerts" lists open claims; admin Release needs a reason | ☐ |
| 18 | Anywhere above: look for "Actor #" or "User #" | It never shows; names show instead | ☐ |

## C. What to report back

- Any row you could not tick, with what you saw (a screenshot is best).
- Any step that felt slow or unclear for a SOC analyst — these become notes in the user manual.
- Any label you had to guess the meaning of.

## D. Clean up

1. Stop both servers (Ctrl+C in each window).
2. Delete `"$LOCALAPPDATA/Temp/hitl-review/selftest.db"` (and its `-wal` / `-shm` files if present).
3. `data/demo.db` was never opened for writing; nothing to restore.
