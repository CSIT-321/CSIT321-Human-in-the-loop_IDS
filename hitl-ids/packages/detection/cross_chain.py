"""Cross-chain join: one queue item per connection, the more severe reading shown.

Both chains read the same packets, so one connection can raise a Suricata alert and a CICFlowMeter flow item.
This module matches the two readings on their Community ID (v1, the Corelight/Zeek/Suricata standard hash of
the 5-tuple) plus time, and records which item the queue shows and which it hides.

Match   the Suricata alert's Community ID equals the flow's; of the flows with that ID, the one that started
        last at or before the alert is the connection (a 5-tuple can repeat: 27,516 flows, 26,328 tuples).
Winner  severity band (packages/detection/queue_severity.py), then route (tier2_case over tier1_review), then
        operational priority. A tie keeps the flow item. Scores are never averaged (deck slide 9, decision C9).
Effect  the weaker item is hidden from the queue (apps/api/operational_queue.py SOURCE), never deleted: its
        row, scores, routing and audit stay, and it opens by ref. Each chain keeps its own score and learning.

Only the Packet Replay calls ``link_new``: it is the one workspace where both chains read one capture.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import sqlite3
from datetime import datetime, timezone

from packages.detection.queue_severity import severity_rank

PROTOCOLS = {"HOPOPT": 0, "ICMP": 1, "TCP": 6, "UDP": 17, "SCTP": 132}
PORTED = {6, 17, 132}
#: Queue items the analyst sees. Every reader that counts or lists the queue selects FROM this.
VISIBLE = ("(SELECT * FROM operational_alerts_v2 WHERE id NOT IN "
           "(SELECT hidden_operational_alert_id FROM cross_chain_links))")


def community_id(src_ip, src_port, dst_ip, dst_port, protocol, seed: int = 0) -> str | None:
    """Community ID v1 (github.com/corelight/community-id-spec). None for a protocol without a number.

    ICMP type/code port mapping is not implemented; this capture's Suricata alerts are TCP and UDP.
    """
    proto = PROTOCOLS.get(str(protocol).upper())
    if proto is None:
        return None
    a, b = ipaddress.ip_address(src_ip).packed, ipaddress.ip_address(dst_ip).packed
    sp, dp = (int(src_port or 0), int(dst_port or 0)) if proto in PORTED else (0, 0)
    if (a, sp) > (b, dp):                       # the spec orders the two endpoints, so both directions agree
        a, b, sp, dp = b, a, dp, sp
    data = seed.to_bytes(2, "big") + a + b + bytes([proto, 0])
    if proto in PORTED:
        data += sp.to_bytes(2, "big") + dp.to_bytes(2, "big")
    return "1:" + base64.b64encode(hashlib.sha1(data).digest()).decode()


def _utc(value: str) -> datetime:
    when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _flow_item(conn, alert_id: int):
    """The queue item that carries one flow alert: its group's representative, or its own single item."""
    row = conn.execute("SELECT g.representative_operational_alert_id FROM alert_group_members m "
                       "JOIN alert_groups g ON g.id=m.group_id WHERE m.legacy_alert_id=?", (alert_id,)).fetchone()
    if row and row[0] is not None:
        return row[0]
    row = conn.execute("SELECT id FROM operational_alerts_v2 WHERE legacy_alert_id=?", (alert_id,)).fetchone()
    return row[0] if row else None


def _strength(conn, item_id: int) -> tuple:
    row = conn.execute(
        "SELECT a.source_kind, (SELECT v.severity FROM alerts v WHERE v.id=a.legacy_alert_id), a.native_severity, "
        "a.detection_category, t.handling_route, t.operational_priority FROM operational_alerts_v2 a "
        "JOIN operational_triage_state_v2 t ON t.operational_alert_id=a.id WHERE a.id=?", (item_id,)).fetchone()
    return (severity_rank(*row[:4]), 1 if row[4] == "tier2_case" else 0, row[5] or 0)


def link_new(conn: sqlite3.Connection, now: str) -> int:
    """Join every admitted Suricata item not yet joined whose connection has a flow item. Returns rows added.

    A Suricata alert with no flow item yet (the flow chain switched off) is retried on the next call.
    """
    added = 0
    pending = conn.execute(
        "SELECT id, source_ip, source_port, destination_ip, destination_port, protocol, occurred_at "
        "FROM operational_alerts_v2 WHERE source_kind='external_nids_alert' AND id NOT IN "
        "(SELECT suricata_operational_alert_id FROM cross_chain_links) ORDER BY id").fetchall()
    for sid, sip, sport, dip, dport, proto, occurred in pending:
        cid = community_id(sip, sport, dip, dport, proto)
        if cid is None:
            continue
        at = _utc(occurred)
        # Pre-filter on the unordered endpoint pair (the inputs of the ID), then require the same ID.
        candidates = [(_utc(json.loads(f)["Timestamp"]), alert_id) for alert_id, f, *t in conn.execute(
            "SELECT alert_id, flow_features, src_ip, src_port, dst_ip, dst_port, protocol FROM flow_data "
            "WHERE protocol=? AND ((src_ip=? AND src_port=? AND dst_ip=? AND dst_port=?) "
            "OR (src_ip=? AND src_port=? AND dst_ip=? AND dst_port=?))",
            (proto, sip, sport, dip, dport, dip, dport, sip, sport))
            if community_id(t[0], t[1], t[2], t[3], t[4]) == cid]
        if not candidates:
            continue
        started = [c for c in candidates if c[0] <= at]
        flow_alert = (max(started) if started else min(candidates))[1]
        flow_item = _flow_item(conn, flow_alert)
        if flow_item is None:
            continue
        suricata_wins = _strength(conn, sid) > _strength(conn, flow_item)
        shown, hidden = (sid, flow_item) if suricata_wins else (flow_item, sid)
        conn.execute(
            "INSERT INTO cross_chain_links (community_id, suricata_operational_alert_id, flow_operational_alert_id, "
            "flow_alert_id, shown_operational_alert_id, hidden_operational_alert_id, reason, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (cid, sid, flow_item, flow_alert, shown, hidden,
             "suricata more severe" if suricata_wins else "flow as severe or more", now))
        added += 1
    return added
