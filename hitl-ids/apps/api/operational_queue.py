"""Read projections only: never score, classify, route or materialize an alert."""
from datetime import datetime, timezone

from apps.api.contract.routing import OperationalSummary
from packages.contracts.operational_v2 import POLICY_BAND_STORAGE
from packages.detection.selective_review import effective_review
from packages.detection.queue_severity import severity_rank
from packages.detection.tier1_eligibility import CURRENT_TIER1_SQL


SOURCE = '''FROM operational_alerts_v2 a
    LEFT JOIN operational_triage_state_v2 t ON t.operational_alert_id=a.id
    LEFT JOIN operational_system_routing s ON s.operational_alert_id=a.id
    LEFT JOIN analyst_work w ON w.operational_alert_id=a.id'''
CATEGORY = "json_extract(s.classification, '$.attackCategory')"
ROUTE_CLASS = "json_extract(s.routing_decision, '$.routeClass')"
EXPERT = f"({ROUTE_CLASS}='EXPERT_REVIEW_REQUIRED' OR {CATEGORY}='unknown_needs_expert')"
# Storage uses 'critical' for both legacy critical and the explicitly tagged P1 band.
CRITICAL = "t.priority_band='critical'"
VALID_PRIORITY = "CASE WHEN typeof(t.operational_priority) IN ('integer','real') AND t.operational_priority BETWEEN 0 AND 100 THEN t.operational_priority END"
# Decision D4, condition 2: an unflagged flow (no rule and no model flag; projected as a single routine item) ranks
# below every flagged item of the same severity, whatever its score. Trusted context can add up to +25 to a score,
# so the score alone does not keep it below the flagged groups. External NIDS alerts have no legacy alert, so they
# count as flagged.
UNFLAGGED_LAST = ("CASE WHEN EXISTS (SELECT 1 FROM alerts u WHERE u.id = a.legacy_alert_id AND u.evidence_class = 'none') "
                  "THEN 1 ELSE 0 END")
# C9, settled decision 8 (user decision 2026-11-07): severity first, for every source, so a severe alert is never
# buried because of the detector that raised it. packages/detection/queue_severity.py holds the one scale.
SEVERITY = ("queue_severity_rank(a.source_kind, (SELECT v.severity FROM alerts v WHERE v.id = a.legacy_alert_id), "
            "a.native_severity, a.detection_category)")
QUEUE_ORDER = (f"{SEVERITY} DESC, {UNFLAGGED_LAST} ASC, {VALID_PRIORITY} DESC, queue_occurred_at(a.occurred_at) DESC, "
               "a.operational_alert_ref ASC")


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


def reviewed_ids(conn):
    """Alerts with at least one persisted selective-review decision.

    ``read_review`` returns ``must_review`` for every other alert (no persisted decision), so only these can be
    deferred and only these need the full policy evaluation. Evaluating the policy for every alert cost ~17 SQL
    statements and one config read each, and made the summary take 8.2 s with 996 alerts (review S6-01).
    """
    return {row[0] for row in conn.execute('SELECT DISTINCT operational_alert_id FROM selective_review_events')}


def matching(*, handling_route=None, priority_band=None, work_scope='all',
             route_class=None, attack_category=None, q=None):
    clauses, params = [], []
    if work_scope=='active': clauses.append("(w.status IS NULL OR w.status NOT IN ('completed','escalated'))")
    elif work_scope in ('completed','escalated'):
        clauses.append('w.status=?');params.append(work_scope)
    for value, column in ((handling_route, 't.handling_route'),
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


def queue_page(conn, *, limit, offset, review_required=None, review_disposition=None, reviews=None, **filters):
    where, params = matching(**filters)
    conn.create_function('queue_occurred_at', 1, occurred_key, deterministic=True)
    conn.create_function('queue_severity_rank', 4, severity_rank, deterministic=True)
    if review_required is not None or review_disposition is not None:
        # Attention is derived before pagination. O(matching alerts * review lookup)
        # is deliberate at FYP scale; no stale persisted deferral cache or SQL policy.
        reviews = reviews if reviews is not None else {}
        rows = conn.execute(f'''SELECT a.id,a.operational_alert_ref {SOURCE} {where}
            ORDER BY {QUEUE_ORDER}''', params).fetchall()
        reviewed = reviewed_ids(conn)
        ids = []
        for row in rows:
            if row[0] in reviewed:
                if row[0] not in reviews:
                    reviews[row[0]] = effective_review(conn, row[1])
                required, disposition = reviews[row[0]].review_required, reviews[row[0]].disposition
            else:  # no persisted decision: read_review's answer is always must_review
                required, disposition = True, 'must_review'
            if ((review_required is None or required == review_required)
                    and (review_disposition is None or disposition == review_disposition)):
                ids.append(row[0])
        return len(ids), ids[offset:offset + limit]
    total = conn.execute('SELECT count(*) ' + SOURCE + where, params).fetchone()[0]
    ids = conn.execute(f'''SELECT a.id {SOURCE} {where}
        ORDER BY {QUEUE_ORDER} LIMIT ? OFFSET ?''', [*params, limit, offset]).fetchall()
    return total, [row[0] for row in ids]


def summary(conn):
    row = conn.execute(f'''SELECT count(*) AS total_alerts,
        count(CASE WHEN {CRITICAL} THEN 1 END) AS critical_alerts,
        count(CASE WHEN t.handling_route='tier1_review' AND (w.status IS NULL OR w.status NOT IN ('completed','escalated')) THEN 1 END) AS tier1_review,
        count(CASE WHEN t.handling_route='tier2_case' THEN 1 END) AS tier2_cases,
        count(CASE WHEN {EXPERT} THEN 1 END) AS expert_review
        {SOURCE}''').fetchone()
    open_cases = conn.execute("SELECT count(*) FROM tier2_cases c JOIN tier2_case_state cs ON cs.case_id=c.id WHERE cs.status IN ('open','investigating')").fetchone()[0]
    values = dict(row)
    work=conn.execute(f'''SELECT
        count(CASE WHEN w.status IS NULL OR w.status NOT IN ('completed','escalated') THEN 1 END) AS active_alerts,
        count(CASE WHEN w.status='completed' THEN 1 END) AS completed_work,
        count(CASE WHEN w.status='escalated' THEN 1 END) AS escalated_work,
        count(CASE WHEN w.status='in_review' THEN 1 END) AS in_review_work,
        count(CASE WHEN {CURRENT_TIER1_SQL} AND (w.status IS NULL OR w.status='available') THEN 1 END) AS available_work
        {SOURCE}''').fetchone()
    values.update(dict(work))
    # Available means claim-eligible attention, not an unowned deferred item. Only an alert with a persisted
    # review decision can be deferred, so the policy runs once per such alert, never per alert in the table.
    deferred_ids = {item[0] for item in conn.execute(
        'SELECT DISTINCT a.id, a.operational_alert_ref FROM selective_review_events e '
        'JOIN operational_alerts_v2 a ON a.id = e.operational_alert_id').fetchall()
        if effective_review(conn, item[1]).disposition == 'no_immediate_review'}
    available = {item[0] for item in conn.execute(f"SELECT a.id {SOURCE} WHERE {CURRENT_TIER1_SQL} AND (w.status IS NULL OR w.status='available')")}
    values['available_work'] -= len(available & deferred_ids)
    deferred = len(deferred_ids)
    values.update(no_immediate_review=deferred, review_required=values['total_alerts'] - deferred)
    return OperationalSummary(**values, open_tier2_cases=open_cases)
