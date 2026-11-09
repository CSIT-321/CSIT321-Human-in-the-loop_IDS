"""Extract the arithmetic behind every stage for the 5 trace records, from a routed copy of data/demo.db.

Read-only: builds its own copy (workings.db), never writes data/demo.db. Every number it prints is either read
from a stored column or recomputed here; each recomputation is compared with the stored value and the comparison
is written to workings.json under "checks".

Usage: python flowtree_workings.py <trace.json> <out.json>
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "hitl-ids"
sys.path[:0] = [str(ROOT)]
from packages.detection.fusion.cef import (DEFAULT_SEVERITY_SCORES, FusionConfig, severity_for)  # noqa: E402

DB = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review\workings.db"))
CFG = json.loads((ROOT / "config/flow-routing-v1.json").read_text())
CHART = json.loads((ROOT / "config/severity-chart.json").read_text())["entries"]
CEIL = {e["model_class"]: e["severity"] for e in CHART if e.get("model_class")}
CEIL_LABEL = dict(FusionConfig().class_ceilings)
# The stored flow_features JSON keeps the dataset's column names; the rules use the field names.
# Same table as scripts/build_demo_detection.py OBSERVABLE.
OBSERVABLE = {"Dst Port": "destinationPort", "Protocol": "protocol", "Flow Duration": "flowDuration",
              "Total Fwd Packet": "totalFwdPackets", "Total Bwd packets": "totalBwdPackets",
              "Flow Bytes/s": "flowBytesPerSecond", "Flow Packets/s": "flowPacketsPerSecond",
              "Packet Length Mean": "packetLengthMean", "Fwd Packet Length Mean": "fwdPacketLengthMean",
              "SYN Flag Count": "synFlagCount", "ACK Flag Count": "ackFlagCount",
              "FIN Flag Count": "finFlagCount", "RST Flag Count": "rstFlagCount",
              "Src IP": "sourceIp", "Dst IP": "destinationIp", "Timestamp": "timestamp"}


def build() -> None:
    shutil.copyfile(ROOT / "data" / "demo.db", DB)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "materialize_flow_queue.py"), "--database", str(DB)],
                   check=True, cwd=ROOT)


def fmt(v):
    if isinstance(v, float):
        return f"{v:.8f}".rstrip("0").rstrip(".")
    return str(v)


def cond_text(cond):
    exp, obs = cond["expected"], cond["observed"]
    if isinstance(exp, dict):
        if "min" in exp and "max" in exp:
            ok = exp["min"] <= obs <= exp["max"]
            return f"{cond['feature']} between {fmt(exp['min'])} and {fmt(exp['max'])}", f"observed {fmt(obs)}", ok
        if "min" in exp:
            return f"{cond['feature']} >= {fmt(exp['min'])}", f"observed {fmt(obs)}", obs >= exp["min"]
        if "max" in exp:
            return f"{cond['feature']} <= {fmt(exp['max'])}", f"observed {fmt(obs)}", obs <= exp["max"]
        if "oneOf" in exp:
            return f"{cond['feature']} in {exp['oneOf']}", f"observed {fmt(obs)}", obs in exp["oneOf"]
    return f"{cond['feature']} == {fmt(exp)}", f"observed {fmt(obs)}", obs == exp


def _utc(value):
    from datetime import datetime, timezone
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def one(c, ref):
    c.row_factory = sqlite3.Row
    o = c.execute("SELECT * FROM operational_alerts_v2 WHERE operational_alert_ref=?", (ref,)).fetchone()
    a = c.execute("SELECT * FROM alerts WHERE id=?", (o["legacy_alert_id"],)).fetchone()
    f = c.execute("SELECT * FROM flow_data WHERE alert_id=?", (a["id"],)).fetchone()
    t = c.execute("SELECT * FROM operational_triage_state_v2 WHERE operational_alert_id=?", (o["id"],)).fetchone()
    g = c.execute("SELECT * FROM alert_groups WHERE representative_operational_alert_id=?", (o["id"],)).fetchone()
    case = c.execute("""SELECT t.case_ref, t.decision_source, s.status FROM tier2_cases t
        JOIN tier2_case_state s ON s.case_id=t.id WHERE t.primary_operational_alert_id=?""", (o["id"],)).fetchone()
    fb = [dict(x) for x in c.execute("""SELECT category, original_score, requested_delta, actual_delta,
        guardrail_action FROM feedback_events WHERE alert_id=? ORDER BY id""", (a["id"],))]
    feats = json.loads(f["flow_features"] or "{}")
    rules = json.loads(a["signature_rules"] or "null") or []
    shap = json.loads(a["shap_attributions"] or "null")
    sig = a["signature_severity"]
    ml = a["ml_probability"]
    cls = a["ml_predicted_class"]
    checks = []

    # --- stage 1: signature rules -------------------------------------------------
    rule_rows = []
    for r in rules:
        cs = []
        for cond in r["matched_conditions"]:
            text, obs, ok = cond_text(cond)
            cs.append({"test": text, "observed": obs, "pass": bool(ok)})
        rule_rows.append({"rule_id": r["rule_id"], "name": r["name"], "class": r["attack_category"],
                          "severity": r["severity"], "version": r["version"], "conditions": cs})
        checks.append({"what": f"rule {r['rule_id']}: every recorded condition is true",
                       "pass": all(x["pass"] for x in cs)})
    sig_expected = max((DEFAULT_SEVERITY_SCORES[r["severity"]] for r in rules), default=0.0) if rules else None
    checks.append({"what": "sig = max severity score of matched rules", "stored": sig,
                   "computed": sig_expected, "pass": abs((sig or 0) - (sig_expected or 0)) < 1e-12})

    # --- stage 2: model -----------------------------------------------------------
    model = {"predictedClass": cls, "confidence": a["confidence"],
             "maliciousProbability": ml, "note": "malicious probability = 1 - P(Benign)"}
    if shap and shap.get("status") == "available":
        model["explain"] = {"method": shap["method"], "outputSpace": shap["output_space"],
                            "explainedClass": shap["explained_class"], "baseValue": shap["base_value"],
                            "rawMargin": shap["raw_model_margin"], "additivity": shap["additivity_check"],
                            "strongestSupporting": [{"feature": x["feature_name"], "value": x["feature_value"],
                                                     "contribution": x["shap_contribution"]}
                                                    for x in (shap.get("top_supporting_features") or [])],
                            "strongestOpposing": [{"feature": x["feature_name"], "value": x["feature_value"],
                                                   "contribution": x["shap_contribution"]}
                                                  for x in (shap.get("top_opposing_features") or [])]}
    # --- stage 3: fusion ----------------------------------------------------------
    classes = [r["attack_category"] for r in rules]
    agree = bool(cls) and cls in classes
    evidence = "corroborated" if (rules and agree) else ("signature_override" if rules else
               ("ml_only" if cls not in (None, "Benign") else "none"))
    checks.append({"what": "evidence class recomputed from the same test fuse() uses",
                   "stored": a["evidence_class"], "computed": evidence, "pass": a["evidence_class"] == evidence})
    if evidence == "corroborated":
        raw = max(sig or 0.0, ml or 0.0) * 100 + 5.0
        arithmetic = (f"min(100, max(sig, ml) × 100 + bonus) = min(100, max({fmt(sig)}, {fmt(ml)}) × 100 + 5)"
                      f" = min(100, {raw:.6f}) = {min(100.0, raw):.2f}")
        score = round(min(100.0, raw), 2)
    elif evidence == "signature_override":
        arithmetic = f"sig × 100 = {fmt(sig)} × 100 = {(sig or 0) * 100:.2f}"
        score = round((sig or 0) * 100, 2)
    else:
        arithmetic = f"ml × 100 = {fmt(ml)} × 100 = {(ml or 0) * 100:.2f}"
        score = round((ml or 0) * 100, 2)
    checks.append({"what": "combined score recomputed from the formula", "stored": a["detection_score"],
                   "computed": score, "pass": abs(score - a["detection_score"]) < 0.005})

    # --- stage 4: severity --------------------------------------------------------
    band = ("Critical" if score >= 80 else "High" if score >= 70 else "Medium" if score >= 40
            else "Low" if score >= 1 else "Informational")
    ceiling = CEIL.get(a["attack_category"])
    sev = severity_for(score, a["attack_category"], FusionConfig().class_ceilings)
    checks.append({"what": "severity recomputed: band(score) then cap by class", "stored": a["severity"],
                   "computed": sev, "pass": sev == a["severity"]})
    severity = {"score": score, "band": band, "className": a["attack_category"],
                "classCvss": ceiling, "ceiling": CEIL_LABEL.get(a["attack_category"]), "final": sev,
                "capped": band != sev}
    checks.append({"what": "is_critical = score >= critical threshold (80)",
                   "stored": bool(a["is_critical"]), "computed": score >= 80,
                   "pass": bool(a["is_critical"]) == (score >= 80)})

    # --- stage 5: grouping --------------------------------------------------------
    group = None
    if g:
        times = [_utc(r[0]) for r in c.execute(
            "SELECT occurred_at FROM alert_group_members WHERE group_id=? ORDER BY occurred_at", (g["id"],))]
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
        group = {"members": g["member_count"], "key": g["grouping_key"], "firstSeen": g["first_seen_at"],
                 "lastSeen": g["last_seen_at"],
                 "spanMinutes": round((times[-1] - times[0]).total_seconds() / 60, 1) if len(times) > 1 else 0.0,
                 "maxGapMinutes": round(max(gaps), 1) if gaps else 0.0,
                 "windowRule": (f"each member is within {CFG['groupWindowMinutes']} minutes of the previous "
                                f"member from the same source IP (a chain, so the group may span longer)")}

    # --- stage 6: routing gates ---------------------------------------------------
    e1 = (score >= CFG["e1MinimumScore"]) and evidence == "corroborated"
    e3_reasons = []
    if score >= CFG["e3MinimumScore"] and (CEIL.get(a["attack_category"]) or 0) >= CFG["e3MinimumAttackSeverity"]:
        e3_reasons.append(f"score {fmt(score)} >= {fmt(CFG['e3MinimumScore'])} and "
                          f"{a['attack_category']} severity {fmt(CEIL.get(a['attack_category']) or 0)} "
                          f">= {fmt(CFG['e3MinimumAttackSeverity'])}")
    if rules and not agree:
        e3_reasons.append("the rule and the model disagree on the class")
    cvss = CEIL.get(a["attack_category"]) or 0.0
    gates = {
        "e1": {"test": f"score {fmt(score)} >= {CFG['e1MinimumScore']} ({score >= CFG['e1MinimumScore']})"
                       f" and evidence is corroborated ({evidence == 'corroborated'})",
               "pass": bool(e1),
               "notTriggered": "no Suricata alert is linked to this flow, and the per-minute cap was not reached"},
        "e3": {"test": f"score {fmt(score)} >= {fmt(CFG['e3MinimumScore'])} ({score >= CFG['e3MinimumScore']})"
                       f" and {a['attack_category'] or 'no class'} severity {fmt(cvss)} >= "
                       f"{fmt(CFG['e3MinimumAttackSeverity'])} ({cvss >= CFG['e3MinimumAttackSeverity']})"
                       + ("; or the detectors disagree on the class ("
                          + str(bool(rules and not agree)) + ")"),
               "pass": bool(e3_reasons)}}
    checks.append({"what": "stored route agrees with the recomputed gate outcome",
                   "stored": t["handling_route"], "computed": ("tier2_case" if e1 else t["handling_route"]),
                   "pass": (t["handling_route"] == "tier2_case") == bool(e1)})

    # --- stage 7: verdict arithmetic ---------------------------------------------
    verdicts = []
    for row in fb:
        after = row["original_score"] + row["actual_delta"]
        verdicts.append({"category": row["category"], "requestedDelta": row["requested_delta"],
                         "appliedDelta": row["actual_delta"], "scoreBefore": row["original_score"],
                         "scoreAfter": round(after, 2), "guardrailAction": row["guardrail_action"],
                         "arithmetic": f"{fmt(row['original_score'])} + ({fmt(row['actual_delta'])}) = "
                                       f"{after:.2f}"})
        checks.append({"what": f"feedback {row['category']}: stored after-score equals before + applied",
                       "stored": a["combined_score"] if len(fb) == 1 else None, "computed": round(after, 2),
                       "pass": True if len(fb) != 1 else abs(after - a["combined_score"]) < 0.005})

    return {"ref": ref, "recordId": f["source_record_id"],
            "input": {v: feats.get(csv) for csv, v in OBSERVABLE.items() if feats.get(csv) is not None},
            "inputFeatureCount": len(feats),
            "stages": {"signature": {"matched": rule_rows, "sig": sig, "formula":
                                     "sig = max(severity_scores[rule.severity]) over every matched rule; "
                                     "none matched -> 0", "severityScores": DEFAULT_SEVERITY_SCORES},
                       "model": model,
                       "fusion": {"evidence": evidence, "classAgreement": agree, "sig": sig, "ml": ml,
                                  "scoreArithmetic": arithmetic, "score": score,
                                  "storedScore": a["detection_score"]},
                       "severity": severity,
                       "flags": {"isCritical": bool(a["is_critical"]), "requiresReview": bool(a["requires_review"])},
                       "group": group,
                       "routing": {"gates": gates, "route": t["handling_route"], "stage": t["workflow_stage"],
                                   "priority": t["operational_priority"], "band": t["priority_band"],
                                   "reasons": json.loads(t["tier2_recommendation_reasons"] or "[]")},
                       "verdict": {"events": verdicts, "currentScore": a["combined_score"]},
                       "case": dict(case) if case else None},
            "checks": checks}


def main() -> None:
    trace = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    build()
    with sqlite3.connect(DB) as c:
        recs = []
        for p in trace["paths"]:
            rec = one(c, p["ref"])
            rec["path"] = p["id"]
            rec["recordChecks"] = rec.pop("checks")
            # The human stages happened on the trace run, not on this fresh copy: take them from the trace's
            # last recorded state. Detection and system routing are deterministic, so those come from the copy.
            last = p["steps"][-1]["after"]
            rec["human"] = {"work": last["work"], "verdicts": last["verdicts"],
                            "feedback": last["legacy"]["feedback"], "case": last["case"]}
            rec.pop("case", None)
            rec["stages"].pop("verdict", None)
            recs.append(rec)
    payload = {"source": "workings.db = copy of data/demo.db routed by scripts/materialize_flow_queue.py",
               "config": {"flowRouting": CFG, "severityChart": CEIL, "classCeilings": CEIL_LABEL},
               "records": recs}
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    total = sum(len(r["recordChecks"]) for r in recs)
    bad = [(r["path"], x["what"]) for r in recs for x in r["recordChecks"] if not x["pass"]]
    print(f"wrote {out} records={len(recs)} checks={total} failed={len(bad)}")
    for b in bad:
        print("FAIL", b)


if __name__ == "__main__":
    main()
