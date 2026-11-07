"""Compare the two local classification.config copies (ET rules vs the Suricata install). Read-only."""
from pathlib import Path

H = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")


def load(p):
    out = {}
    for line in (H / p).read_text(encoding="utf-8").splitlines():
        if line.startswith("config classification:"):
            name, desc, prio = [x.strip() for x in line.split(":", 1)[1].split(",")]
            out[name] = (desc, int(prio))
    return out


et = load(".tools/et/rules/classification.config")
su = load(".tools/suricata/PFiles/Suricata/classification.config")
print("only in ET:", {k: et[k] for k in et.keys() - su.keys()})
print("only in Suricata:", {k: su[k] for k in su.keys() - et.keys()})
print("different:", {k: (et[k], su[k]) for k in et.keys() & su.keys() if et[k] != su[k]})
descs = [d for d, _ in su.values()]
print("duplicate descriptions:", sorted({d for d in descs if descs.count(d) > 1}))
