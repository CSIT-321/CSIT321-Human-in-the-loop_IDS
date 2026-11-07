"""What would E1-suricata add on the replay window? Measured against the engine's own scores (spike.db) and the
release labels (truth.json). Read-only.

For every window flow linked to a Suricata alert of severity <= 2 (policy e1SuricataMaximumSeverity):
  - does the model call it an attack (E1-suricata needs the model to agree)?
  - is the flow already E1 by the flow rule (corroborated, score >= 80)?
  - what is its label?
"""
import json
import sqlite3
from collections import Counter
from pathlib import Path

BASE = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids\data\spike"
            r"\Wednesday-14-02-2018")
WIN = BASE / "replay-window"
truth = json.loads((WIN / "truth.json").read_text(encoding="utf-8"))
sev, sig = {}, {}
for line in (WIN / "eve.jsonl").open(encoding="utf-8"):
    e = json.loads(line)
    ref, s = e["linked_alert_id"], e["alert"]["severity"]
    if s < sev.get(ref, 9):
        sev[ref], sig[ref] = s, e["alert"]["signature"]
db = sqlite3.connect(f"file:{BASE / 'spike.db'}?mode=ro", uri=True)
rows = {ref: (ev, score, ml, cat) for ref, ev, score, ml, cat in db.execute(
    "SELECT f.source_record_id, a.evidence_class, a.combined_score, a.ml_predicted_class, a.attack_category "
    "FROM alerts a JOIN flow_data f ON f.alert_id = a.id")}
out = Counter()
detail = []
for ref, s in sev.items():
    if s > 2:
        continue
    ev, score, ml, cat = rows.get(ref, ("?", 0, None, None))
    model_attack = ml not in (None, "Benign")
    e1_flow = ev == "corroborated" and score >= 80
    e1_sur = model_attack and score >= 80
    label = truth.get(ref) or "unlabelled"
    out[(sig[ref][:40], s, "model:" + str(ml), "E1-flow" if e1_flow else "-", "E1-sur" if e1_sur else "-", label)] += 1
print("Suricata-linked flows at severity <= 2:", sum(out.values()))
for k, n in out.most_common():
    print(f"{n:>4}  {k}")
new_only = sum(n for k, n in out.items() if k[4] == "E1-sur" and k[3] == "-")
print("E1-suricata escalations that E1-flow-rule does not already make:", new_only)
