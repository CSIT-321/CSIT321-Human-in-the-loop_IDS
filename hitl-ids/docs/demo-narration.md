# Demo narration — the words to say

**Read this out loud. Everything in a plain paragraph is yours to say.**

Each part has a **CUE** — the one action that starts it — and a **time**, so you can pace yourself.
The whole run is about **eleven minutes**.

Companion documents: `demo-runbook.md` is the click path and the traps · `demo-run-card.html` is the
printed one-pager · `demo-script.md` holds the terminal setup and the long-form detail. **This file is
only the speaking.** Every number was verified live against `data/demo.db` on 18 September 2026.

---

## The thesis, in one sentence

> The model is confidently wrong. A human overrules it, inside guardrails that explain themselves. And
> the correction spreads — measurably, and within limits — to the alerts that look like it.

Say that once, early. Then let the console prove it.

---

## Pacing

| Part | Time | Optional |
|---|---|---|
| 1 · Opening | 40s | |
| 2 · Sign in | 30s | |
| 3 · The workstation and the queue | 1m | |
| 4 · `AL-00478` — the model that is wrong | 2m | |
| 5 · `AL-03086` — the attack we missed | 1m | |
| 6 · Saturation | 1m | optional |
| 7 · Three verdicts teach a family | 2m | |
| 8 · The administrator | 1m | |
| 9 · The evaluator | 1m 30s | |
| 10 · Closing | 1m | |

---

# Part 1 · Opening

**CUE** — the sign-in page is on screen. Nothing is signed in yet.
**Time** — 40 seconds.

Good morning. This is a human-in-the-loop intrusion detection system. It runs on five thousand
recorded network flows.

Most intrusion detection research stops at the detector. It measures precision and recall and reports
them. Our project starts where that stops. It asks what should happen when the detector is confident
and wrong.

Here is the problem we set out to solve. A machine-learning detector gives you a score. That score is
not a decision. Somebody has to decide. And when they decide, we need to know three things: what they
decided, what changed, and whether the change held.

The system you are about to see answers all three questions. It answers them in the screen, and it
answers them in the database.

There is one more thing before I start. The flow data here is a recording. It is not a live feed. When
you see a number on the screen, that number comes from a recorded file, and I can show you the file.

Let me sign in.

---

# Part 2 · Sign in

**CUE** — sign in. Use `g.ang`. Type the wrong password first, on purpose.
**Time** — 30 seconds.

Watch the password field. I am going to type the wrong password on purpose.

The system refuses it. **Invalid username or password.** That is not a mock-up. The password is
checked against a bcrypt hash, and the server issues a signed token that lasts eight hours.

Now the correct password. I land on the workstation.

Notice what is missing. There is no role picker. There is no drop-down that says "view as
administrator". The role comes from the account. That is deliberate, and it matters later: the
analyst cannot grant themselves administrator rights by clicking something.

---

# Part 3 · The workstation and the queue

**CUE** — you are on `/analyst/workstation`. Point at the three columns, then at the KPI strip.
**Time** — 1 minute.

This is where an analyst spends the shift. Three columns. The alert queue on the left. The selected
alert in the centre. Its context on the right. No page-per-alert. The analyst never loses their place.

Look across the top. One hundred and eighty-five critical, six hundred and forty-four tier-two candidates,
nine hundred ninety-six awaiting review. Five thousand alerts in total. And **Verdicts: zero.** That
zero is the point I want you to remember. Nothing has been judged yet. Everything you see after this
comes from decisions I am about to make.

Now look at the queue. Every flow becomes an alert. All five thousand. Including the four thousand
that nobody flagged.

That is unusual, and it is deliberate. A detector that only shows you what it flagged cannot be
measured honestly. You cannot compute precision without knowing what you rejected. So we keep
everything, and we rank it.

The queue ranks by **severity first**, then by operational score. You can see two score columns.
**Detection score** is what the detectors said. It never changes. **Operational score** is what
analysts move.

Hold on to that distinction. It is the whole design.

Let me show you one alert that the rules caught, so you can see what a checkable reason looks like.

---

# Part 4 · `AL-00478` — the model that is wrong

**CUE** — search `AL-00478`, open it, then walk the panels. Finish by choosing False Positive.
**Time** — 2 minutes.

This is the centrepiece. `AL-00478`.

Read the badges with me. **Tier 2 candidate. Model only. High. Operational score 99.89.**

Now read the panels. Signature rules: **"No rule matched."** Not one rule fired on this flow.

Model prediction: **Web Attack, confidence 99.9 per cent.** And below that, the model's own working —
the features that pushed it towards Web Attack, and the features that pushed it away. That is a
TreeSHAP explanation, and the system verifies the explanation adds up before it shows it to you.

Combined explanation: only the model flagged this flow. No rule gives a checkable reason.

So we have a machine that is 99.9 per cent certain, and one detector — the model — saying so.

**Ground truth says this flow is benign.**

That is the moment the project is about. The detector is confident. The detector is wrong. And the
score does not tell you that.

So the decision belongs to the analyst. I am the analyst. I am going to record **False Positive**,
which requests a reduction of thirty points.

Watch the chain.

Detection score, 99.89. Requested change, minus thirty. Guardrail: **Bound.** Applied change:
**minus 29.89.** Operational score: **70.00.**

The system did not apply what I asked. It applied minus 29.89, and it tells me why, in a sentence:
*"This alert is Critical, so its score was held at the floor of 70."*

I want to be precise about that word "Critical", because it looks like a mistake and it is not.

The badge above says **High**. The sentence says Critical. Those are two different measures. The badge
is the severity label, and since version 1.29 that label is capped by the attack class — a Web Attack
cannot display above High, no matter how high it scores. The guardrail does not use the label. The
guardrail uses the **score**. `is_critical` means the detection score reached eighty. This alert scored
99.89, so it qualifies.

I checked that against the database. `is_critical` matches "score at or above eighty" on every alert,
with zero mismatches either way. The highest alert that does not qualify scores 42.77.

So the trigger is correct. **Only the sentence is stale**, because it says "Critical" when it means
"above the score threshold". That is a wording defect, and I am telling you about it rather than hiding
it.

Now the important part. The guardrail limited how far one verdict could move the score. It did **not**
overrule my finding. My verdict is recorded in full. The system capped the number, and it kept the
decision.

And look at the queue band. It moved from Tier 2 candidate to Model only. Because the score fell below
the threshold, the alert is no longer a candidate for escalation.

I have just made the system less sure about an alert it was certain of. Let me show you the opposite.

---

# Part 5 · `AL-03086` — the attack we missed

**CUE** — search `AL-03086`, open it, record True Positive.
**Time** — 1 minute.

Now the other direction. `AL-03086`.

Look at the band: **Nothing flagged it.** Not the rules, not the model. This alert sat in the bottom of
the queue at 36.94.

**Ground truth says it is an attempted Web Attack.**

Both detectors missed it. And here is what I want you to notice: nothing on this screen tells me it is
an attack. There is no rule, and the model's confidence is low. The only reason I know is that this is
a recording with labels, and I read the label.

In the real world, this is the alert that gets ignored. It is the bottom of the queue.

I am going to confirm it. **True Positive**, plus ten points.

**Applied as requested. Plus ten. No guardrail intervened.** Operational score, 46.94. The band moves
from "Nothing flagged it" to **Model only**.

Now let me be honest about how far that moved. It climbed one band. It did not leap up the queue. It
was already the highest-ranked unflagged alert, so it only moved one rank.

That is the design. One confirmation moves one band. We are not going to claim that one analyst
clicking once fixes a queue.

Let me show you what does move things.

---

# Part 6 · Saturation — optional

**CUE** — Alert Queue → Evidence "Model only" → Detection score "Below 100" → Sort "Detection score", Ascending.
**Time** — 1 minute. **Skip this if you are short on time.**

Before the next part, one honest measurement.

I am filtering the queue to alerts whose detection score is below one hundred. Twenty-one alerts.
Twenty-one, out of five thousand.

Every other flagged alert — nine hundred and seventy-five of them — sits at **exactly** 100.0.

So when I confirm a saturated alert, the guardrail clamps the change. I ask for plus ten and I get
plus nought-point-nought-four. That is not a bug. That is the testbed. The model's confidence
saturates, and a bounded score cannot climb past its bound.

This matters for the evaluation you will see in a moment, and I will come back to it.

The one alert here with real headroom is `AL-00576`, an Infiltration at 81.30. In the normal queue
order it is buried. That is why this filter exists — so you can find the alerts where a human decision
is visible.

---

# Part 7 · Three verdicts teach a family

**CUE** — search and confirm `AL-01696`, then `AL-03873`, then `AL-03153`. Watch the family panel after each one.
**Time** — 2 minutes.

This is the part of the project I am most proud of.

Every alert has a **family**. The family is not a similarity guess. It is an exact match on four
fields: attack class, destination port, protocol, and the rule that matched. No similarity score. No
threshold. The screen says that in plain words.

This alert, `AL-01696`, is in the family **Port Scan, port 445**. Five members.

Right now the gate is **Closed**, and the panel explains why. *"Not enough learning verdicts: one of
three required."*

I confirm it. **True Positive.** The gate stays closed. One of three.

Now the second member, `AL-03873`. Same verdict. The panel updates: **two of three.**

And the third, `AL-03153`. Same verdict.

Watch the panel now. The gate is **Open**. *"Three of three verdicts agree."* And the family now
carries an **applied adjustment of plus twenty**, with a band offset of minus three.

Here is the sentence I want you to read with me: *"Similar alerts have been judged, so this alert
carries its family's learned adjustment even where it has no verdict of its own."*

**No verdict of its own.**

Let me prove that. I am going to open two alerts that nobody has touched. `AL-03044`. And `AL-04526`.

Neither has a verdict. Neither analyst has ever opened them. Both are now **Tier 2 candidates.**

Two alerts moved, and no human judged either one. They moved because three other alerts — in the same
family — were judged the same way.

And notice what did **not** happen. Nothing outside this family moved. The Web Attack family I touched
earlier stayed closed, at one of three. The Benign family stayed closed too.

That is the control. Three agreeing analysts can move a family. One cannot. And the blast radius is
the family, and nothing else.

Now — you should be asking what happens when three people are confidently wrong together. That is a
fair question, and the evaluator view is where I answer it.

---

# Part 8 · The administrator

**CUE** — sign out. Sign in as `admin` / `admin-demo`. Show System Status, then Guardrails, then Audit Trail.
**Time** — 1 minute.

The analyst cannot do everything. Let me sign in as the administrator.

The navigation changed. Analysts can no longer reach these pages, and I cannot reach the analyst
pages from here.

**System Status.** Verdicts recorded: **five**. Guardrail actions: **four**. Those four are the
verdicts the guardrails capped — the dismissal that hit the floor, and the three confirmations that hit
the score ceiling. The other one, `AL-03086`, needed no guardrail, and you can see that here as a
number, not as a claim.

**Guardrails.** These are the settings that bound what a verdict can do. The system will not let me
change one without giving a reason. I type a value, I submit, and it stops me and asks why. That
reason goes into a log that nobody can edit.

**Audit Trail.** Every run, every verdict, every guardrail action, every family-learning event. The
table refuses updates and deletes at the database level. A correction to the record is a new record.

That is the accountability half of human-in-the-loop. A human is in the loop, so there is a record of
what the human did.

---

# Part 9 · The evaluator

**CUE** — sign out. Sign in as `evaluator` / `evaluator-demo`. Show the newest run, then the arms.
**Time** — 1 minute 30 seconds.

Last view. The evaluator.

This is the part where I tell you what did not work.

The system ran three arms over the same data, the same model, the same rules, and the same seed. Only
two things differ: whether analyst feedback is on, and whether the guardrails are on.

Arm A is the control. No feedback. Arm B has feedback. Arm C has feedback with the guardrails
switched off.

**Detection is identical in all three arms.** That is the first result, and it is the one that matters
most. Feedback reorders the queue. It never touches the detector. The detector is not learning from
the humans in this build.

Now precision at fifty. **One point zero zero zero in all three arms.** Zero false positives in the
top fifty.

And now the honest part. **Feedback did not improve precision.** It could not. The control queue was
already at perfect precision down to rank two hundred. There was nothing to gain.

There is a result here that used to go the wrong way. Under our **old** queue order, feedback pushed a
benign alert into the top fifty, and precision fell from 1.000 to 0.980. That is a minus nought-point-
nought-two delta, and it was a real regression.

We changed the queue order in version 1.31, and re-ran the whole evaluation. Under the new order,
**that regression is gone.** Precision holds at 1.000.

What remains is small and still negative. Precision at two hundred moves by minus nought-point-
nought-one. Mean true-positive rank moves by minus a half. I am showing you those because they are
measured, not because they flatter us.

And one more result that is not a win. The score ceiling bound all forty verdicts in the evaluation,
because nine hundred and seventy-five of the nine hundred and ninety-six flagged alerts already sit at
the maximum score. That is why the two guardrail arms came out identical. The ceiling applied whether
the guardrails were on or off.

That is a negative result, and we report it as one.

---

# Part 10 · Closing

**CUE** — sign out, or leave the evaluator view. Stop clicking.
**Time** — 1 minute.

Let me finish with what this project actually claims.

It claims that a detector's confidence is not a decision, and that the distance between them should be
visible. You saw that in `AL-00478`: 99.9 per cent confident, and wrong.

It claims that when a human decides, the system should bound the decision and **explain the bound**.
You saw that in the guardrail sentence, with the number in it.

It claims that a correction should spread to the alerts that resemble the corrected one, and **only**
those. You saw that: two alerts moved, and nothing outside the family did.

It claims that the system should be able to say what a human changed. You saw that in the two score
columns.

And it claims that the evaluation reports the results that went the wrong way. You saw that too.

The limits are real, and I would rather tell you them than have you find them.

The accounts are seeded, and the passwords are in the repository. This is an offline demonstration.

The detection is a batch job, not a live feed. There is no live traffic here.

Families use a coarse key. The destination port and the protocol are part of it. That coarseness
promoted a benign alert in our evaluation. We know, because we measured it.

The 0.99 F1 score is a property of this testbed. A single tool generated each attack class. It is not a
claim about the real world.

And the score saturates at 100, which hides a human's effect on most of the flagged queue.

That last one is the honest headline. **On this data, a human's decision is often invisible in the
number.** The system shows the decision anyway, in the guardrail chain and in the audit trail, even
when the score has nowhere left to move.

The model is confident. The human decides. The system proves what the human did, and what it changed.

Thank you.

---

# The questions you will be asked

**"Was `AL-00478` really Critical? The badge says High."**

Two different measures, and only the sentence mixes them. The floor triggers on the **score**:
`is_critical` means the detection score reached **eighty**, and this alert scored 99.89. The badge is
capped by the attack class — since version 1.29 a Web Attack cannot display above High. I measured it:
`is_critical` matches "score at or above eighty" on every alert, with zero mismatches. The trigger is
right. **The sentence is stale.** Do not say the trigger is too wide.

**"Why did the score barely move when you confirmed that alert?"**

Because it was already at the maximum of one hundred, and scores are bounded. Asking for plus ten
applies plus nought-point-nought-four. Nine hundred and seventy-five of the nine hundred and
ninety-six flagged alerts are at exactly one hundred. That is why the evaluation's two guardrail arms
are identical.

**"Corroborated reads zero, but two hundred alerts have a rule and the model agreeing?"**

A band and an evidence class are different labels. All two hundred of those alerts sit in the Tier 2
band, so the Corroborated **band** is empty. The tab reads "Rule plus model: 200". Both numbers are
correct.

**"What counts as similar? Is there a threshold?"**

No threshold. An exact match on four fields: attack class, destination port, protocol, and matched
rule. For a flow that no detector flagged, the destination address must match as well, so one verdict
cannot spread across all benign traffic on a port.

**"Could three analysts be wrong together and move innocent alerts?"**

Yes. That is a real risk, and our evaluation shows a benign alert being promoted by family learning.
The guardrails bound the size of the movement, and the audit trail records it, but the mechanism can be
wrong. We report it as a limitation rather than a solved problem.

**"Did the feedback improve the detector?"**

No. Detection is identical in all three arms. Feedback reorders the queue and cannot touch the
detector. That is by design in this build, and it is stated as a result.

---

# Two habits that make this run land

**Pause after every score change.** The chain is the evidence. Let the panel read
`−30.00 → Bound → −29.89 → 70.00` before you speak again.

**Name the control out loud.** When the family moves two alerts, say immediately that nothing outside
the family moved. A claim about precision is stronger when you also show the thing that did not happen.
