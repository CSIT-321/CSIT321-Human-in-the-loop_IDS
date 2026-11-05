"""Which capture day does each attack class (and each demo-story alert) come from in demo_sample.csv?"""
import csv
from collections import Counter, defaultdict
from pathlib import Path

CSV = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids\data\processed\demo_sample.csv")
STORY = {"AL-00478": "false positive", "AL-03086": "missed attack", "AL-02717": "climb",
         "AL-01696": "family judged", "AL-03873": "family judged", "AL-03153": "family judged",
         "AL-04526": "family untouched", "AL-03044": "family untouched"}
per_day = defaultdict(Counter)
with CSV.open(newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        day = row["Timestamp"].split(" ")[0]
        per_day[day][row["attack_class"]] += 1
        if row["alert_id"] in STORY:
            print(f"{row['alert_id']} {STORY[row['alert_id']]:<17} day={day} class={row['attack_class']} "
                  f"attempted={row['is_attempted']} dport={row['Dst Port']}")
print()
for day in sorted(per_day):
    c = per_day[day]
    print(f"{day}: total={sum(c.values()):>4}  " + ", ".join(f"{k}={v}" for k, v in c.most_common()))
