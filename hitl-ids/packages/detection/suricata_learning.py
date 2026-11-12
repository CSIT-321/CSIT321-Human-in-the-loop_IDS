"""Verdict learning for Suricata alerts: the same rerank the flow chain has, read at query time.

The problem it fixes (measured 2026-11-12 on the packet replay): a Suricata verdict changed nothing in the
queue. ``verdict_bridge`` writes the approved engine only for flow alerts, and the queue score reads its delta
through ``legacy_alert_id``, which a Suricata alert does not have. So 399 of 11,196 queue items, including 5 of the
7 critical ones, could not be reranked by any verdict.

What this module adds, and what it reuses unchanged:

* Own verdict. The V2 outcome maps to the approved category (``verdict_bridge.OUTCOME_TO_CATEGORY``), the category
  to its requested change (``feedback.service.FEEDBACK_EFFECTS``: +10 / 0 / -15 / -30), and the change passes
  the approved guardrails (``guardrail.policy.apply_guardrails``: cap, critical floor, 0-100 range).
* Family learning. A family is one signature on one internal asset (config/suricata-learning-v1.json). Its
  members' latest verdicts go through the approved agreement gate and formula (``feedback.learning.learn``: 3
  verdicts, 0.67 agreement, C1). A member with no verdict of its own takes the family's applied adjustment,
  through the same guardrails.
* The base is the routing priority (``operational_priority``), as the flow queue score's base is.

Nothing is stored. The verdicts are already stored, append-only, in ``analyst_verdict_events``; the delta is
derived from them on every read, the same rule the flow queue score follows (apps/api/operational_queue.py C1:
"no second score is stored, so the two stores cannot disagree"). The guardrail settings are the administrator's
live ``guardrail_config``.
"""
from __future__ import annotations

import ipaddress
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from packages.detection.feedback.learning import learn
from packages.detection.feedback.service import FEEDBACK_EFFECTS, load_learning_policy, load_policy
from packages.detection.guardrail.policy import apply_guardrails
from packages.detection.queue_severity import severity_label
from packages.detection.ranking.severity import load_severity_chart
from packages.detection.verdict_bridge import OUTCOME_TO_CATEGORY

CONFIG = Path(__file__).resolve().parents[2] / "config" / "suricata-learning-v1.json"
CLASSTYPES = Path(__file__).resolve().parents[2] / "config" / "suricata-classtypes-v1.json"
# A classtype the severity chart does not list has no CVSS score of its own. Its weight is the lower edge of the
# CVSS v3.1 band that the queue already shows for it (queue_severity.severity_label), so the learning weight and
# the severity the analyst sees come from one rule.
BAND_WEIGHT = {"Informational": 0.0, "Low": 0.1, "Medium": 0.4, "High": 0.7, "Critical": 0.9}

EXTERNAL_ROWS = """SELECT a.id, a.detection_title, a.detection_category, a.native_severity, a.source_ip,
       a.destination_ip, t.operational_priority
  FROM operational_alerts_v2 a JOIN operational_triage_state_v2 t ON t.operational_alert_id = a.id
 WHERE a.source_kind = 'external_nids_alert'"""
LATEST_OUTCOME = """SELECT e.operational_alert_id, json_extract(e.snapshot, '$.outcome')
  FROM analyst_verdict_events e
 WHERE e.revision = (SELECT max(x.revision) FROM analyst_verdict_events x
                      WHERE x.operational_alert_id = e.operational_alert_id)"""


@lru_cache(maxsize=1)
def _config():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    return data["version"], tuple(ipaddress.ip_network(net) for net in data["homeNet"])


@lru_cache(maxsize=1)
def _classtype_weight() -> dict[str, float]:
    """Classtype description (as EVE writes it) -> the chart's weight, severity / 10. Worst entry wins."""
    by_classtype: dict[str, float] = {}
    for entry in load_severity_chart().entries:
        for classtype in entry.suricata_classtypes:
            by_classtype[classtype] = max(by_classtype.get(classtype, 0.0), entry.weight)
    table = json.loads(CLASSTYPES.read_text(encoding="utf-8"))
    return {e["description"].casefold(): by_classtype[e["classtype"]]
            for e in table["entries"] if e["classtype"] in by_classtype}


def _internal(ip: str | None) -> bool:
    try:
        address = ipaddress.ip_address(str(ip))
    except ValueError:
        return False
    return any(address in net for net in _config()[1])


def internal_host(source_ip: str | None, destination_ip: str | None) -> str:
    """The protected asset of one alert: the HOME_NET side. Inbound -> destination, outbound -> source,
    internal to internal -> the pair. With neither side internal the destination is the target."""
    src, dst = _internal(source_ip), _internal(destination_ip)
    if src and dst:
        return f"{source_ip}>{destination_ip}"
    if src:
        return str(source_ip)
    return str(destination_ip)


def family_of(title: str | None, source_ip: str | None, destination_ip: str | None) -> tuple[str, str]:
    return str(title or ""), internal_host(source_ip, destination_ip)


def weight_of(category: str | None, native_severity) -> float:
    found = _classtype_weight().get((category or "").strip().casefold())
    if found is not None:
        return found
    return BAND_WEIGHT[severity_label("external_nids_alert", None, native_severity, category)]


def _subject(base: float, policy):
    """The fields ``apply_guardrails`` reads. A Suricata alert is never a disputed rule (I3) and has no model
    class, so only the cap, the critical floor and the range apply. Critical = the routing priority reached the
    administrator's critical threshold, the flow chain's own predicate."""
    return SimpleNamespace(detection_score=base, evidence_class="external", attack_category=None,
                           is_critical=base >= policy.critical_alert_threshold, signature_rules=[])


def _base(row) -> float | None:
    value = row["operational_priority"]
    return float(value) if isinstance(value, (int, float)) and 0 <= value <= 100 else None


def compute(conn, rows) -> dict[int, float]:
    """{operational alert id: verdict delta} for the given external rows. Pure read."""
    rows = list(rows)
    if not rows:
        return {}
    policy, learning = load_policy(conn), load_learning_policy(conn)
    outcomes = dict(conn.execute(LATEST_OUTCOME).fetchall())
    families: dict[tuple[str, str], list] = defaultdict(list)
    for row in rows:
        families[family_of(row["detection_title"], row["source_ip"], row["destination_ip"])].append(row)
    deltas: dict[int, float] = {}
    for members in families.values():
        weight = weight_of(members[0]["detection_category"], members[0]["native_severity"])
        judged = [m for m in members if outcomes.get(m["id"]) in OUTCOME_TO_CATEGORY]
        # Oldest first, the order the approved engine replays a family's verdicts in.
        judged.sort(key=lambda m: m["id"])
        family = learn((OUTCOME_TO_CATEGORY[outcomes[m["id"]]] for m in judged), weight, policy, learning)
        for member in members:
            base = _base(member)
            if base is None:
                continue
            outcome = outcomes.get(member["id"])
            if outcome in OUTCOME_TO_CATEGORY:
                requested = FEEDBACK_EFFECTS[OUTCOME_TO_CATEGORY[outcome]].requested_delta
            else:
                requested = family.applied_adjustment
            if not requested:
                continue
            delta = apply_guardrails(_subject(base, policy), requested, policy).actual_delta
            if delta:
                deltas[member["id"]] = float(delta)
    return deltas


def _any_external_verdict(conn) -> bool:
    """False when no Suricata alert has a verdict. Then every delta is 0 and the queue reads nothing more; this
    also keeps a database without the verdict table (older schemas, minimal test schemas) on the old path."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='analyst_verdict_events'").fetchone() is None:
        return False
    return conn.execute("""SELECT 1 FROM analyst_verdict_events e
        JOIN operational_alerts_v2 a ON a.id = e.operational_alert_id
        WHERE a.source_kind = 'external_nids_alert' LIMIT 1""").fetchone() is not None


def all_deltas(conn) -> dict[int, float]:
    """Every external alert's delta, for one queue read."""
    if not _any_external_verdict(conn):
        return {}
    return compute(conn, conn.execute(EXTERNAL_ROWS).fetchall())


def delta_for(conn, operational_alert_id: int) -> float:
    """One external alert's delta. Reads only its signature's alerts: the family key starts with the title."""
    if not _any_external_verdict(conn):
        return 0.0
    row = conn.execute(EXTERNAL_ROWS + " AND a.id = ?", (operational_alert_id,)).fetchone()
    if row is None:
        return 0.0
    same_title = conn.execute(EXTERNAL_ROWS + " AND a.detection_title = ?", (row["detection_title"],)).fetchall()
    return compute(conn, same_title).get(operational_alert_id, 0.0)
