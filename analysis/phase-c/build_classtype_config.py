"""Write config/suricata-classtypes-v1.json from the Suricata install's classification.config.

EVE `alert.category` carries the classtype DESCRIPTION; the severity chart keys on the classtype NAME. This table
joins the two. Source: the local Suricata install (same 43 entries as the ET rules copy, plus
inappropriate-content). The rule priority here is only for reference: the queue uses the alert's own EVE severity,
which a rule can override with its `priority:` keyword.
"""
import json
from pathlib import Path

H = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
SRC = H / ".tools/suricata/PFiles/Suricata/classification.config"

entries = []
for line in SRC.read_text(encoding="utf-8").splitlines():
    if line.startswith("config classification:"):
        name, desc, prio = [x.strip() for x in line.split(":", 1)[1].split(",")]
        entries.append({"description": desc, "classtype": name, "defaultPriority": int(prio)})

out = {
    "version": "suricata-classtypes-v1",
    "source": "Suricata classification.config (https://raw.githubusercontent.com/OISF/suricata/master/etc/classification.config), "
              "copied from the local Suricata install",
    "note": "EVE alert.category is the description; config/severity-chart.json keys on the classtype name.",
    "entries": entries,
}
(H / "config/suricata-classtypes-v1.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(len(entries), "entries written")
