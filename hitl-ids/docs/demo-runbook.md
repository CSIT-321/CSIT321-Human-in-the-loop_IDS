# Demo Runbook — for the presenter

**What to click, what you should see, and where it goes wrong.**

`docs/demo-script.md` is what you *say*. **This file is what you *do*.** Every click path, number and
warning below was taken from a live run of the console on 18 Sept 2026, not from the design documents.
Where the two disagree, this file is right.

Read the **five traps** before you start. Four of them will bite you otherwise.

---

## 0 · The thirty-second version

| | |
|---|---|
| **Open** | `http://localhost:5173` |
| **Analyst** | `g.ang` / `analyst-demo` → lands on `/analyst/workstation` |
| **Admin** | `admin` / `admin-demo` → lands on `/admin/status` |
| **Evaluator** | `evaluator` / `evaluator-demo` → lands on `/evaluator/scenarios` |
| **The arc** | one alert you dismiss → one you confirm → three that agree → the family moves two alerts nobody judged |
| **The payoff** | `AL-03044` and `AL-04526` become Tier 2 candidates **with no verdict of their own** |
| **Do not** | record a verdict you did not mean. **Verdicts are permanent.** |

---

## 1 · Before the audience

Run everything Python from the `hitl-ids` folder, and the npm commands from `hitl-ids/apps/web`.

> **The folder must stay named `hitl-ids`.** `packages/detection/ml/inference.py` builds its paths as
> `REPO_ROOT/"hitl-ids"`, so renaming it breaks the rebuild. The *parent* folder name does not matter.

```bash
cd <wherever you put it>/hitl-ids      # the folder holding apps/ packages/ data/ pyproject.toml
source .venv/Scripts/activate          # cmd: .venv\Scripts\activate
python --version                       # must print Python 3.11.x

# DELETE FIRST. run_detection APPENDS — skip this and you get 10,000 alerts and two runs.
rm -f data/demo.db                     # cmd: del data\demo.db
python scripts/run_detection.py        # fresh data/demo.db, 5,000 flows → 5,000 alerts, ~21s
python scripts/rehearse_demo.py        # must close with: The demo narrative holds end to end.

python -m uvicorn apps.api.main:app    # the API on :8000 — leave this terminal open
```

Second terminal, for the console:

```bash
cd <wherever you put it>/hitl-ids/apps/web
npm run dev                            # http://localhost:5173
```

### 1a · First time on a machine that has never run this

Do these nine steps **once**, on the new machine, before the section above.

| # | Step | Command | Why |
|---|---|---|---|
| 1 | Get the code | `git clone <repo>` | The repo root contains `hitl-ids/`. A ZIP download also works |
| 2 | **Keep the folder named `hitl-ids`** | — | `inference.py` resolves `REPO_ROOT/"hitl-ids"`. A rename breaks the rebuild |
| 3 | Check the Python version | `python --version` | **Must be 3.11.** 3.12 fails at startup |
| 4 | Create the environment | `py -3.11 -m venv .venv` | `.venv` is gitignored and **never portable** — it stores absolute paths, so always recreate it. Do not use a bare `py -m venv`; it picks 3.12 |
| 5 | Install Python dependencies | `.venv\Scripts\activate` then `python -m pip install -r requirements.txt` | 12 pinned entries, including `-e .` |
| 6 | Check Node | `node -v` | **18 or newer.** `package.json` declares no `engines`, so npm will not warn you |
| 7 | Install the console dependencies | `cd apps/web` then `npm install` | Uses the committed `package-lock.json` |
| 8 | Install the test browser | `npx playwright install chromium` | **Required for `npm run e2e` only.** No existing document mentions it |
| 9 | Rebuild the database | see section 1 above | `data/*.db` is gitignored, so a clone has none |

**Two things a clone does NOT contain, and you do not need either:**

- `data/demo.db` — step 9 rebuilds it.
- `data/processed/demo_ml_predictions_shap.json` — the rebuild computes TreeSHAP itself.

> **Do not download the raw dataset.** `data/README.md` describes a pipeline that begins with a 10 GB
> zip. **The demo does not need it.** `run_detection.py` reads four committed things —
> `data/processed/demo_sample.csv`, `data/processed/sample_manifest.json`, `models/` and
> `rules/rule-set-s4b-1.json` — and all four are in the clone. Do **not** pass `--replay`; the file it
> wants is not in the clone, and it is only for a machine without xgboost.

**Environment variables: none are required.** Every one has a committed default, so there is no `.env`
file to create.

| variable | default | used by |
|---|---|---|
| `HITL_IDS_DB` | `hitl-ids/data/demo.db` | the API |
| `HITL_IDS_JWT_SECRET` | a committed demo secret | sign-in |
| `HITL_API_TARGET` | `http://127.0.0.1:8000` | the console's proxy |
| `HITL_PYTHON` | `python` | `npm run e2e` only |

**TreeSHAP needs no extra package.** The rebuild uses xgboost's own `pred_contribs`, not the `shap`
library, so `requirements.txt` is complete as it stands.

**Then check three things, in this order:**

1. `http://localhost:8000/api/health` answers and names `data\demo.db`.
2. The console loads.
3. **The KPI strip reads `VERDICTS 0`.** If it does not, the database is dirty. Rebuild.

> **A dev server may already be running on :5173.** If `npm run dev` exits with *"Port 5173 is already
> in use"*, that is fine — a console is already being served. Do not fight it. Just open the page.
> **The API is the one that matters:** if it is not running, every panel reads *"Cannot reach the API"*.

---

## 2 · The numbers you will be asked for

Quote these. They are what the console shows on a freshly built `data/demo.db`.

| Opening state | | After your five verdicts | |
|---|---|---|---|
| Critical | **185** | Verdicts | **5** |
| Tier 2 candidates | **644** | Guardrail actions | **4** |
| Needs review | **996** | Needs review | **997** |
| Unresolved | **5,000** | Tier 2 flagged | **645** |
| **Verdicts** | **0** | Alerts in the database | 5,000 |
| Total alerts | **5,000** | Flagged | 996 |

**Band counts at start:** Tier 2 candidate 644 · Corroborated **0** · Model only 352 · Nothing flagged 4,004.

> **"Why is Corroborated 0 when 200 alerts have a rule and the model agreeing?"** Because a *band* and an
> *evidence class* are different labels. All 200 rule-plus-model alerts sit in the Tier 2 band, so the
> Corroborated **band** is empty. The band tab reads `RULE + MODEL 200`; the band reads `0`. Both are right.

**Severity spread:** Informational 3,986 · Medium 401 · High 261 · Critical 185 · Low 167.

---

## 3 · The run

### Act 1 — Sign in (`/login`)

| Do | Expect |
|---|---|
| Sign out if a session is open | The sign-in page |
| Username `g.ang`, password **`wrong-password`**, press Enter | Red **"Invalid username or password"** |
| Correct the password to `analyst-demo`, press Enter | Lands on `/analyst/workstation` |

**Say** — *"Sign-in is real: bcrypt hashes, an 8-hour signed token, and no role picker. A wrong password is refused on the spot."*

**Trap:** there is **no role switcher**. To change role you must sign out and sign in as that account.

---

### Act 1b — The workstation (`/analyst/workstation`)

| Do | Expect |
|---|---|
| Look at the middle column | `AL-01707`, Infiltration, **Critical**, opens by itself |
| Click a band tab, e.g. **RULE + MODEL 200** | The queue narrows to 200 alerts; the URL gains `?tab=corroborated` |
| The centre opens `AL-01958` | Badge: **Brute Force · MEDIUM**. The rule panel explains `SIG-FTP-BRUTE-FORCE` with required vs observed |
| Search `AL-00478` | Its card appears |

**Say** — *"The queue, the alert and its context are one screen. The rule panel is why we can show a checkable reason, not just a score."*

> **TRAP 1 — the search obeys the active band.** If you searched while `RULE + MODEL` was selected, you
> get **"No alerts match"**, because `AL-00478` is *Model only*. **Click the `ALL 5,000` tab first,**
> then search. The showcase prints these two steps in the wrong order; this order works.

---

### Act 2 — Dashboard and queue (`/analyst/dashboard`, `/analyst/queue`)

| Do | Expect |
|---|---|
| Click **Dashboard** | 5,000 in queue · 996 awaiting review · 644 Tier 2 · **Moved by feedback 0 — no verdicts recorded yet** |
| Scroll to **Alerts by severity** | The full spread, Informational 3,986 down to Critical 185 |
| Click **Alert Queue** | The table: Rank, Alert, Band, Evidence, Severity, Detection, **Operational**, Class, Flow |
| Point at the two score columns | Detection never moves. Operational is what analysts move |

**Say** — *"Detection is what the detectors said, and it never changes. Operational is what analysts move — that is how you see a human's effect."*

> **The queue subtitle now matches the order** (fixed 2026-09-18). It reads *"Ranked by severity,
> then operational score"*, which is what `db.queue_order` does. It is safe to read aloud.

---

### Act 3 — The centrepiece: a confident model that is wrong (`AL-00478`)

| Do | Expect |
|---|---|
| Queue → **Clear filters** → search `AL-00478` → open it | Web Attack · **HIGH** · Tier 2 candidate · Model only · **99.89** |
| Walk the four panels | Flow · **Signature rules: "No rule matched (ML-only alert)"** · Model prediction (TreeSHAP) · Combined explanation |
| Point at **Similar alerts (family)** | `Web Attack · port 80 · tcp` · **61 members** · gate **Closed** |
| Scroll to **Record a verdict** → choose **False Positive** (−30.00) | Helper text: *"The detectors were wrong about this flow."* |
| Scroll down, then click **Record verdict** | **Apply the guardrail story below** |

**Expect exactly this:**

```
Detection 99.89 → Score before 99.89 → Requested −30.00 → Guardrail BOUND → Applied −29.89 → Operational 70.00
```

Badge: **capped by a guardrail**. Text: *"This alert is Critical, so its score was held at the floor of 70."*
Callout: `Critical alert floor · configured 70.00`. Queue band: Tier 2 candidate → **Model only**.

**Say** — *"The model was 99.9% sure and no rule agreed. It is benign. The panels inform the decision; the decision is the analyst's. The guardrail limited how far one verdict may move the score — it did not overrule the finding."*

> **TRAP 3 — the "Record verdict" button moves.** Choosing a verdict makes a paragraph appear above the
> button, which pushes it down about 90px, off the bottom of the screen. **Scroll down, then click.**
> If your click seems to do nothing, you missed the button. Scroll and retry — nothing was recorded.

> **TRAP 4 — the sentence says "Critical" and the badge says HIGH.** The *wording* is wrong; the
> mechanism is right. `is_critical` means **the detection score reached 80**, which this alert did at
> 99.89. The *badge* is capped by the attack class's ceiling (v1.29), so a Web Attack tops out at High.
> The floor tracks the score, the badge tracks the class, and only the sentence conflates them.
> **See §6 for the answer to give.**

---

### Act 4 — The attack both detectors missed (`AL-03086`)

| Do | Expect |
|---|---|
| Alert Queue → search `AL-03086` → open it | Band **Nothing flagged it** · **Nothing flagged** · LOW · **36.94** |
| Point at the family | `Benign · port 80 · tcp · to 172.31.69.28` · **1 member** |
| Point at *What makes these similar* | Includes **DEST. IP** — *"For a flow no detector flagged, the destination address must match too"* |
| Choose **True Positive** → scroll → **Record verdict** | **+10.00 requested, +10.00 applied. No guardrail intervened.** |

**Expect exactly this:**

```
36.94 → 36.94 → Requested +10.00 → Guardrail NONE → Applied +10.00 → Operational 46.94
Queue band: Nothing flagged it → Model only
```

**Say** — *"No guardrail needed to act here. Be honest about how far it moved: one confirmation moves one band, by design."*

---

### Act 5 — Three agreeing verdicts open the family (`AL-01696`, `AL-03873`, `AL-03153`)

Search each, open it, choose **True Positive**, scroll, **Record verdict**. Watch the family panel change:

| Alert | After recording, the family panel reads |
|---|---|
| `AL-01696` | *"not enough learning verdicts: **1 of 3** required"* |
| `AL-03873` | Agreement **100.0%** · dominant **True Positive** · *"**2 of 3** required"* |
| `AL-03153` | Gate **OPEN** · *"**3 of 3** verdicts agree: confirm_true_positive"* |

**Do not be alarmed by the applied change.** All three sit near the ceiling, so the guardrail clamps:

| Alert | Requested | **Applied** |
|---|---|---|
| AL-01696 | +10.00 | **+0.04** |
| AL-03873 | +10.00 | **+0.03** |
| AL-03153 | +10.00 | **+0.01** |

**Say** — *"Ask for +10 and you get +0.04. 975 of the 996 flagged alerts already sit at exactly 100, so there is nowhere to climb. That is the saturation we report, and it is why the evaluation's guardrail arms came out identical."*

**Then show the payoff.** After the third verdict the family reads:

```
APPLIED ADJUSTMENT +20.00 · BAND OFFSET −3
"Similar alerts have been judged, so this alert carries its family's learned adjustment
 even where it has no verdict of its own."
```

**Search `AL-03044`, then `AL-04526`.** Both are now **Tier 2 candidate** — and **neither has a verdict of its own**.

**Say** — *"One analyst cannot move a family; three who agree can. Nothing outside the family moved. And two alerts no analyst ever judged were promoted by what the other three taught. The same mechanism can go wrong — and the evaluator view is where we show that."*

**The whole family, after the gate opens:**

| Alert | Band | Own verdicts |
|---|---|---|
| AL-01696 | signature_override | 1 |
| **AL-03044** | **tier2_candidate** | **0** |
| AL-03153 | signature_override | 1 |
| AL-03873 | signature_override | 1 |
| **AL-04526** | **tier2_candidate** | **0** |

---

### Act 7 — Administrator (`admin / admin-demo`)

| Do | Expect |
|---|---|
| **Sign out** → sign in as `admin` | Nav changes: System Status · Guardrails · Audit Trail · **IP Security Report** |
| **System Status** | **Verdicts 5 · Guardrail actions 4** · Needs review 997 · Tier 2 flagged 645 · *"API answering"* |
| **Audit Trail** | **15 entries**, newest first: 5 Feedback · 4 Guardrail intervention · 5 Similar alert learning · 1 Detection run |

**Say** — *"The administrator sees everything the guardrails did, and why. This table refuses UPDATE and DELETE — the trail cannot be edited."*

**A detail worth pointing out:** a *Guardrail intervention* row appears against exactly the four capped verdicts, and **not** against `AL-03086`, which needed none. The figures match the work you just did.

---

### Act 8 — Evaluator (`evaluator / evaluator-demo`)

| Do | Expect |
|---|---|
| **Sign out** → sign in as `evaluator` | Nav: Scenarios · Detection Metrics |
| **Scenarios** | Newest run **`20260916T073220Z`** is the top row |
| Point at **Pre-registration** | Rule `s15-preregistration-1` · **size 40** · *"fixed before the arms were run"* |
| Click **Open run →** | The honesty banner, then the figures |

**Read the banner aloud — it is the strongest thing in the deck:**

> *"Deltas are shown as measured, including those that went the wrong way. Precision fell under feedback on this sample: the control queue was already near-perfect, so feedback could only disturb it."*

**Then the arms.** Precision@50 is **1.000 in all three arms**. The small negative move is in **mean rank: 511.09 (control) → 511.51 (treatment)**.

> **TRAP 5 — the showcase's Act 8 step text is stale.** It claims precision@50 shows *"its −0.020 fall
> against control"*. The console shows **±0.000**. Do not read that step. The negative move is in mean
> rank, and the banner already describes it correctly.

---

## 4 · The five traps, together

1. **The search obeys the active band.** Click `ALL 5,000` before searching.
2. **The queue subtitle is stale.** It says "band, then operational score". The order is severity-first.
3. **The "Record verdict" button moves down** after you pick a verdict. Scroll, then click.
4. **"This alert is Critical" prints on Medium, High and Low alerts.** Two measures are being mixed.
   The floor triggers on the **score** reaching 80; the badge is capped by the attack class. Wording only
   — see the answer in §6. **Do not call the trigger wrong.**

**Two more, from automation, that will not affect you at a keyboard:**

- **Do not type URLs into the address bar.** A deep link gets overridden by the remembered view — entering
  `/analyst/queue?queueClass=ml_only` landed back on `/analyst/workstation?group=family`. **Navigate by clicking.**
- **The Band, Evidence, Severity, Attack class and Sort controls are native `<select>`s.** They open
  normally for a human. They do not open from synthetic clicks.

---

## 5 · If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Every panel says *"Cannot reach the API"* | The API is not running | Restart `uvicorn apps.api.main:app` |
| `npm run dev` says *"Port 5173 is already in use"* | A console is already served | Harmless. Open the page |
| `No module named 'apps'` | Wrong folder | `cd` to the `hitl-ids` folder first |
| `VERDICTS` is not 0 at the start | The database is dirty | `rm -f data/demo.db` and rebuild |
| A search returns nothing | A band tab is filtering | Click `ALL 5,000` |
| **Record verdict** does nothing | You missed the button after it moved | Scroll down and click again — nothing was recorded |
| 10,000 alerts and two runs | You rebuilt without deleting | Rebuild with `rm -f data/demo.db` first |
| You recorded the wrong verdict | **It is permanent** | Rebuild the database. The audit trail refuses DELETE |

---

## 6 · The two questions you will be asked

### "Was `AL-00478` really Critical? The badge says HIGH."

**It reached the critical *score*; its *badge* is capped by attack type.** Answer it straight:

> *"Two different things are being measured. `is_critical` means the detection score reached 80 — this
> alert scored 99.89, so it qualifies, and that is what the floor triggers on. The badge is capped by the
> attack class's ceiling, which we added in v1.29, so a Web Attack cannot display above High however high
> it scores. The floor tracks the score; the badge tracks the class. What is wrong is only the sentence,
> which asserts the badge — and that is logged."*

**Do not say the trigger is too wide.** It is not: `is_critical = 1` matches `combined_score ≥ 80`
exactly — 996 alerts, with zero mismatches in either direction (verified against `data/demo.db`,
2026-09-18). It *coincides* with the 996 flagged alerts because every flagged alert scores 80 or more
and the highest unflagged one is 42.77. A coincidence on this sample, not the rule.

**If pressed on whether it goes stale:** it is not recomputed after feedback, and that is protective.
If it flipped to false at 70, a second dismissal would apply −30 and land at 40 — the floor would be
defeated by repetition. It cannot under-protect on this data either: the highest non-critical score is
42.77 and the largest positive adjustment is +20, so nothing can cross 80 through feedback.

### "Why did 975 alerts not move when you confirmed them?"

> *"Because they already sit at the maximum score of 100, and scores are bounded. Confirming one applies
> +0.04 instead of +10. It is why our evaluation's two guardrail arms came out identical: no policy bound
> on that sequence — the 100 ceiling did, on all 40 verdicts."*

---

## 7 · Afterwards

**Rebuild before the next audience.** A demonstrated database has already been judged.

```bash
rm -f data/demo.db && python scripts/run_detection.py
python scripts/rehearse_demo.py        # must close with: The demo narrative holds end to end.
```

To re-check the whole story without touching `data/demo.db`, in `apps/web`:

```bash
npm run e2e        # plays the story in a real browser against its own copy, under a minute
```

---

*Written 18 Sept 2026 from a verified live run of the console. Every number, click path and warning above
was observed, not inferred.*
