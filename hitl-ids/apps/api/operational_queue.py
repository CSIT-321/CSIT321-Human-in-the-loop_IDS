"""Read projections only: never score, classify, route or materialize an alert."""
from datetime import datetime, timezone

from apps.api.contract.routing import OperationalSummary
from packages.contracts.operational_v2 import POLICY_BAND_STORAGE


SOURCE = '''FROM operational_alerts_v2 a
    LEFT JOIN operational_triage_state_v2 t ON t.operational_alert_id=a.id
    LEFT JOIN operational_system_routing s ON s.operational_alert_id=a.id'''
CATEGORY = "json_extract(s.classification, '$.attackCategory')"
ROUTE_CLASS = "json_extract(s.routing_decision, '$.routeClass')"
EXPERT = f"({ROUTE_CLASS}='EXPERT_REVIEW_REQUIRED' OR {CATEGORY}='unknown_needs_expert')"
# Storage uses 'critical' for both legacy critical and the explicitly tagged P1 band.
CRITICAL = "t.priority_band='critical'"
VALID_PRIORITY = "CASE WHEN typeof(t.operational_priority) IN ('integer','real') AND t.operational_priority BETWEEN 0 AND 100 THEN t.operational_priority END"


def occurred_key(value):
    """Compare instants with microsecond precision, including offset-bearing EVE times.

    Old timezone-unspecified captures retain their wall-clock time, interpreted as UTC
    for ordering only. Invalid/missing timestamps sort last; no evidence is rewritten.
    """
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def matching(*, handling_route=None, review_required=None, priority_band=None,
             route_class=None, attack_category=None, q=None):
    clauses, params = [], []
    for value, column in ((handling_route, 't.handling_route'), (review_required, 't.review_required'),
                          (attack_category, CATEGORY)):
        if value is not None:
            clauses.append(f'{column}=?'); params.append(value)
    if priority_band is not None:
        clauses.append('t.priority_band=?'); params.append(POLICY_BAND_STORAGE.get(priority_band, priority_band))
    if route_class == 'EXPERT_REVIEW_REQUIRED':
        clauses.append(EXPERT)
    elif route_class is not None:
        clauses.append(f'{ROUTE_CLASS}=?'); params.append(route_class)
    if q and q.strip():
        clauses.append("instr(lower(a.detection_title || ' ' || a.detector_name || ' ' || a.operational_alert_ref || ' ' || a.source_ip || ' ' || a.destination_ip), lower(?)) > 0")
        params.append(q.strip())
    return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), params


def queue_page(conn, *, limit, offset, **filters):
    where, params = matching(**filters)
    conn.create_function('queue_occurred_at', 1, occurred_key, deterministic=True)
    total = conn.execute('SELECT count(*) ' + SOURCE + where, params).fetchone()[0]
    ids = conn.execute(f'''SELECT a.id {SOURCE} {where}
        ORDER BY {VALID_PRIORITY} DESC, queue_occurred_at(a.occurred_at) DESC,
                 a.operational_alert_ref ASC LIMIT ? OFFSET ?''', [*params, limit, offset]).fetchall()
    return total, [row[0] for row in ids]


def summary(conn):
    row = conn.execute(f'''SELECT count(*) AS total_alerts,
        count(CASE WHEN {CRITICAL} THEN 1 END) AS critical_alerts,
        count(CASE WHEN t.handling_route='tier1_review' THEN 1 END) AS tier1_review,
        count(CASE WHEN t.handling_route='tier2_case' THEN 1 END) AS tier2_cases,
        count(CASE WHEN {EXPERT} THEN 1 END) AS expert_review,
        count(CASE WHEN t.review_required=1 THEN 1 END) AS review_required,
        count(CASE WHEN t.handling_route='no_immediate_review' THEN 1 END) AS no_immediate_review
        {SOURCE}''').fetchone()
    open_cases = conn.execute("SELECT count(*) FROM tier2_cases c JOIN tier2_case_state cs ON cs.case_id=c.id WHERE cs.status IN ('open','investigating')").fetchone()[0]
    return OperationalSummary(**dict(row), open_tier2_cases=open_cases)
