"""Read-time projection of fixed, durable current HITL event sources.

The selected operational database and the global workspace control database are the
only inputs. This module never creates an audit table or writes a source row.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from apps.api.contract.current_audit import CurrentAuditEvent, CurrentAuditPage


def _json(value: str | None) -> dict[str, Any]:
    parsed = json.loads(value) if value else {}
    return parsed if isinstance(parsed, dict) else {}


def _ref(workspace: str, source: str, identity: str | int, timestamp: str) -> str:
    return str(uuid5(NAMESPACE_URL, f'current-hitl-audit:{workspace}:{source}:{identity}:{timestamp}'))


def _actor(row: sqlite3.Row | dict, source: str) -> dict[str, Any]:
    actor_id = row['actor_id']
    if source == 'admin':
        return dict(actor_type='human', actor_id=None, actor_name=row['actor_name'], decision_source=source)
    if source == 'system_policy' or actor_id is None:
        return dict(actor_type='system', actor_id=None, actor_name=None, decision_source=source)
    return dict(actor_type='human', actor_id=actor_id,
                actor_name=row['actor_name'] or f'User {actor_id}', decision_source=source)


def _event(items: list[CurrentAuditEvent], workspace: str, source: str, identity: str | int,
           timestamp: str, category: str, event_type: str, action: str,
           object_type: str, object_ref: str, summary: str, *,
           actor_id: int | None = None, actor_name: str | None = None,
           decision_source: str = 'analyst', alert_ref: str | None = None,
           case_ref: str | None = None, lesson_ref: str | None = None,
           result: str | None = None, detail: dict[str, Any] | None = None) -> None:
    actor = _actor(dict(actor_id=actor_id, actor_name=actor_name), decision_source)
    items.append(CurrentAuditEvent(event_ref=_ref(workspace, source, identity, timestamp), timestamp=timestamp,
        event_category=category, event_type=event_type, action=action,
        object_type=object_type, object_ref=object_ref, alert_ref=alert_ref,
        case_ref=case_ref, lesson_ref=lesson_ref, workspace=workspace,
        summary=summary, result=result, source_subsystem=source, detail=detail or {}, **actor))


def _workspace_events(items: list[CurrentAuditEvent], control: Path) -> None:
    if not control.exists():
        return
    with closing(sqlite3.connect(control.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute('SELECT id,actor,action,workspace,reason,created_at FROM actions'):
            label = {'workspace_activated': 'Workspace activated', 'replay_prepared': 'Replay prepared',
                     'replay_reset': 'Replay reset'}.get(row['action'], row['action'])
            _event(items, 'global', 'workspace_control', row['id'], row['created_at'],
                'WORKSPACE', row['action'], label, 'workspace', row['workspace'],
                f"{row['actor']} — {label.lower()} ({row['workspace']}).",
                actor_name=row['actor'], decision_source='admin', result=row['workspace'],
                detail={'reason': row['reason'], 'targetWorkspace': row['workspace']})


def _operational_events(items: list[CurrentAuditEvent], conn: sqlite3.Connection, workspace: str) -> None:
    # Every source is fixed below. The client controls neither table names nor database paths.
    users = {row['id']: row['display_name'] for row in conn.execute('SELECT id,display_name FROM users')}
    for row in conn.execute('''SELECT r.*,a.operational_alert_ref alert_ref,u.display_name actor_name
        FROM operational_routing_audit r JOIN operational_alerts_v2 a ON a.id=r.operational_alert_id
        LEFT JOIN users u ON u.id=r.actor_id'''):
        before = _json(row['before_state'])
        after = _json(row['after_state'])
        route = after.get('handlingRoute')
        action = {'system_route': 'System routed alert', 'manual_escalate': 'Manual Tier 2 escalation',
                  'approve_tier2': 'Tier 2 recommendation approved',
                  'reject_tier2': 'Tier 2 recommendation rejected',
                  'admit_tier1': 'Tier 1 review admitted'}[row['action']]
        category = 'TIER2' if (route or '').startswith('tier2') or row['action'] in ('approve_tier2', 'reject_tier2') else 'WORK'
        source = row['decision_source']
        _event(items, workspace, 'operational_routing_audit', row['id'], row['created_at'],
            category, row['event_type'], action, 'alert', row['alert_ref'],
            f"{action} for alert {row['alert_ref']} → {route or 'unknown route'}.",
            actor_id=row['actor_id'], actor_name=row['actor_name'], decision_source=source,
            alert_ref=row['alert_ref'], result=route,
            detail={'reason': row['reason'], 'beforeRoute': before.get('handlingRoute'),
                    'afterRoute': route, 'afterStage': after.get('workflowStage'),
                    'beforeRevision': before.get('revision'), 'afterRevision': after.get('revision')})
    for row in conn.execute('''SELECT e.*, a.operational_alert_ref alert_ref, u.display_name actor_name
        FROM analyst_work_events e JOIN operational_alerts_v2 a ON a.id=e.operational_alert_id
        LEFT JOIN users u ON u.id=e.actor_id'''):
        detail = _json(row['detail'])
        kind = row['event_type']
        action = {'CLAIM_ROUND_STARTED': 'Claim round started', 'CLAIM_INTENT': 'Review requested',
            'CLAIM_FINALIZED': 'Review started', 'CLAIM_CONTENTION': 'Claim conflict',
            'CLAIM_INELIGIBLE': 'Claim ineligible', 'WORK_COMPLETED': 'Work completed',
            'WORK_ESCALATED': 'Work escalated'}.get(kind, kind)
        owner_id = detail.get('ownerActorId')
        names = {actor_id: users.get(actor_id, f'User {actor_id}')
                 for actor_id in detail.get('contenderActorIds', [])}
        if kind == 'CLAIM_INTENT':
            summary = f"{row['actor_name']} requested review of alert {row['alert_ref']}."
        elif kind == 'CLAIM_FINALIZED':
            summary = f"System assigned alert {row['alert_ref']} to {names.get(owner_id, f'User {owner_id}')}."
        elif kind == 'CLAIM_CONTENTION':
            summary = f"{', '.join(names.values())} selected alert {row['alert_ref']} concurrently; no owner assigned."
        elif kind == 'WORK_COMPLETED':
            summary = f"Alert {row['alert_ref']} completed after a Tier 1 Verdict."
        elif kind == 'WORK_ESCALATED':
            summary = f"Alert {row['alert_ref']} escalated to Tier 2 Case {detail.get('caseRef')}."
        else:
            summary = f"{action} for alert {row['alert_ref']}."
        _event(items, workspace, 'analyst_work_events', row['id'], row['created_at'], 'WORK', kind,
            action, 'alert', row['alert_ref'], summary, actor_id=row['actor_id'],
            actor_name=row['actor_name'], decision_source=row['decision_source'],
            alert_ref=row['alert_ref'], case_ref=detail.get('caseRef'),
            result='Owner assigned' if kind == 'CLAIM_FINALIZED' else 'No owner' if kind == 'CLAIM_CONTENTION'
                else 'Completed' if kind == 'WORK_COMPLETED' else 'Escalated' if kind == 'WORK_ESCALATED' else None,
            detail={key: detail[key] for key in ('roundRef', 'policyVersion', 'ownerActorId', 'contenderActorIds',
                'verdictRef', 'outcome', 'caseRef') if key in detail})

    for row in conn.execute('''SELECT v.*,a.operational_alert_ref alert_ref,u.display_name actor_name
        FROM analyst_verdict_events v JOIN operational_alerts_v2 a ON a.id=v.operational_alert_id
        JOIN users u ON u.id=v.actor_id'''):
        snapshot = _json(row['snapshot'])
        outcome = snapshot.get('outcome', 'Unknown')
        action = 'Verdict corrected' if row['supersedes_ref'] else 'Verdict recorded'
        _event(items, workspace, 'analyst_verdict_events', row['verdict_ref'], snapshot['createdAt'],
            'VERDICT', 'TIER1_VERDICT', action, 'alert', row['alert_ref'],
            f"{row['actor_name']} recorded {outcome.replace('_', ' ')} for alert {row['alert_ref']} (revision {row['revision']}).",
            actor_id=row['actor_id'], actor_name=row['actor_name'], alert_ref=row['alert_ref'],
            result=f"{outcome.replace('_', ' ').title()} · revision {row['revision']}",
            detail={'verdictRef': row['verdict_ref'], 'revision': row['revision'],
                    'supersedesRef': row['supersedes_ref'], 'outcome': outcome, 'reason': snapshot.get('reason')})

    for row in conn.execute('''SELECT m.*,l.lesson_ref,u.display_name actor_name
        FROM triage_memory_audit m JOIN triage_memory_lessons l ON l.id=m.lesson_id
        LEFT JOIN users u ON u.id=m.actor_id'''):
        payload = _json(row['payload'])
        evidence = payload.get('evidence') or {}
        state = payload.get('lessonSnapshot') or {}
        kind = row['event_type']
        action = ('Exact evidence recorded' if 'AUTO_CANDIDATE_CREATED' in kind else
            'Conflicting evidence added' if 'CONFLICT_ADDED' in kind else
            'Supporting evidence added' if 'SUPPORT_ADDED' in kind else
            'Lesson auto-activated' if 'AUTO_ACTIVATED' in kind else
            'Lesson activated' if kind.endswith('_ACTIVATED') else
            'Lesson rejected' if 'REJECTED' in kind else
            'Conflict review / guidance withdrawn' if 'CONFLICT_REVIEW' in kind else
            'Expert superseded prior evidence' if 'EXPERT_SUPERSEDED' in kind else kind)
        alert_ref = evidence.get('sourceOperationalAlertRef')
        status = state.get('status')
        source = row['decision_source']
        summary = f"{action} for lesson {row['lesson_ref']}" + (f" from alert {alert_ref}." if alert_ref else '.')
        if 'CONFLICT_ADDED' in kind and status == 'conflict_review':
            summary += ' Guidance withdrawn pending conflict review.'
        _event(items, workspace, 'triage_memory_audit', row['id'], row['created_at'], 'MEMORY',
            kind, action, 'lesson', row['lesson_ref'],
            summary,
            actor_id=row['actor_id'], actor_name=row['actor_name'], decision_source=source,
            alert_ref=alert_ref, lesson_ref=row['lesson_ref'], result=status,
            detail={'reason': payload.get('reason'), 'outcome': evidence.get('outcome'),
                    'relation': evidence.get('relation'), 'sourceKind': evidence.get('sourceKind'),
                    'humanSourceActor': evidence.get('verdictAuthorName') or evidence.get('conclusionAuthorName'),
                    'supportCount': state.get('supportCount'), 'conflictCount': state.get('conflictCount'),
                    'policyVersion': row['policy_version']})

    for row in conn.execute('''SELECT r.*,a.operational_alert_ref alert_ref,u.display_name actor_name
        FROM selective_review_events r JOIN operational_alerts_v2 a ON a.id=r.operational_alert_id
        JOIN users u ON u.id=r.actor_id'''):
        snapshot = _json(row['decision_snapshot'])
        result = snapshot.get('result') or {}
        disposition = result.get('disposition', 'must_review') if row['action'] == 'apply' else 'must_review'
        label = ('Require Human Review' if row['action'] == 'require_review' else
                 disposition.replace('_', ' ').title())
        # An analyst persists/overrides the decision; policy owns the computed disposition.
        source = 'analyst' if row['action'] == 'require_review' else 'system_policy'
        match = result.get('matchedLessonRef') or (snapshot.get('inputs') or {}).get('matchedLessonRef')
        _event(items, workspace, 'selective_review_events', row['event_ref'], row['created_at'],
            'REVIEW', row['event_type'], label, 'alert', row['alert_ref'],
            f"{label} for alert {row['alert_ref']}.", actor_id=row['actor_id'] if source == 'analyst' else None,
            actor_name=row['actor_name'] if source == 'analyst' else None, decision_source=source,
            alert_ref=row['alert_ref'], lesson_ref=match, result=disposition,
            detail={'reason': row['reason'], 'reasonCodes': result.get('reasonCodes'),
                    'matchedLessonRef': match, 'initiatedBy': row['actor_name'],
                    'policyVersion': (snapshot.get('policyConfigSnapshot') or {}).get('version')})

    for row in conn.execute('''SELECT e.*,c.case_ref,a.operational_alert_ref alert_ref,
        linked.operational_alert_ref linked_alert_ref,u.display_name actor_name
        FROM tier2_case_events e JOIN tier2_cases c ON c.id=e.case_id
        JOIN operational_alerts_v2 a ON a.id=c.primary_operational_alert_id
        LEFT JOIN operational_alerts_v2 linked ON linked.id=e.linked_alert_id
        LEFT JOIN users u ON u.id=e.actor_id'''):
        after = _json(row['after_state'])
        before = _json(row['before_state'])
        conclusion = after.get('investigationConclusion') or {}
        action = {'create': 'Tier 2 Case created', 'link': 'Alert linked',
                  'note': 'Investigation note', 'start': 'Investigation started',
                  'finding': 'Investigation Conclusion', 'resolve': 'Case resolved'}[row['action']]
        category = 'RESOLUTION' if row['action'] == 'resolve' else 'TIER2'
        source = row['decision_source']
        _event(items, workspace, 'tier2_case_events', row['id'], row['created_at'], category,
            row['event_type'], action, 'case', row['case_ref'],
            f"{action} for case {row['case_ref']}" +
            (f" — {row['finding']} / {conclusion.get('finalAttackCategory')}." if conclusion else '.'),
            actor_id=row['actor_id'], actor_name=row['actor_name'], decision_source=source,
            alert_ref=row['linked_alert_ref'] or row['alert_ref'], case_ref=row['case_ref'],
            result='Resolved' if row['action'] == 'resolve' else after.get('status'),
            detail={'reason': row['reason'], 'finding': row['finding'],
                    'finalAttackCategory': conclusion.get('finalAttackCategory'),
                    'systemClassification': conclusion.get('systemClassification'),
                    'linkedAlertRef': row['linked_alert_ref'], 'primaryAlertRef': row['alert_ref'],
                    'beforeRevision': before.get('revision'), 'afterRevision': after.get('revision')})

    for row in conn.execute('''SELECT r.*,c.case_ref,a.operational_alert_ref alert_ref,
        u.display_name actor_name FROM response_recommendations r
        JOIN tier2_cases c ON c.id=r.case_id
        JOIN operational_alerts_v2 a ON a.id=c.primary_operational_alert_id
        LEFT JOIN users u ON u.id=r.proposed_by_actor_id'''):
        source = row['proposal_source']
        _event(items, workspace, 'response_recommendations', row['recommendation_ref'], row['created_at'],
            'RESPONSE', row['event_type'], 'Response recommended', 'recommendation', row['recommendation_ref'],
            f"{row['recommendation_type'].replace('_', ' ').title()} recommended for case {row['case_ref']}.",
            actor_id=row['proposed_by_actor_id'] if source == 'analyst' else None,
            actor_name=row['actor_name'] if source == 'analyst' else None, decision_source=source,
            alert_ref=row['alert_ref'], case_ref=row['case_ref'], result='Pending human decision',
            detail={'recommendationType': row['recommendation_type'], 'targetType': row['target_type'],
                    'rationale': row['rationale'], 'reason': row['proposal_reason'],
                    'policyVersion': row['policy_version'],
                    'initiatedBy': row['actor_name'] if source == 'system_policy' else None})

    for row in conn.execute('''SELECT d.*,r.recommendation_ref,c.case_ref,
        a.operational_alert_ref alert_ref,u.display_name actor_name
        FROM response_decisions d JOIN response_recommendations r ON r.id=d.recommendation_id
        JOIN tier2_cases c ON c.id=r.case_id
        JOIN operational_alerts_v2 a ON a.id=c.primary_operational_alert_id
        JOIN users u ON u.id=d.actor_id'''):
        result = 'Approved — Not Executed' if row['decision'] == 'approved' else 'Rejected — Not Executed'
        _event(items, workspace, 'response_decisions', row['id'], row['created_at'], 'RESPONSE',
            row['event_type'], f"Response {row['decision']}", 'recommendation', row['recommendation_ref'],
            f"{row['actor_name']} {row['decision']} response recommendation {row['recommendation_ref']}.",
            actor_id=row['actor_id'], actor_name=row['actor_name'], alert_ref=row['alert_ref'],
            case_ref=row['case_ref'], result=result,
            detail={'reason': row['reason'], 'recommendationRef': row['recommendation_ref']})


def list_current(conn: sqlite3.Connection, control: Path, workspace: str, *,
                 limit: int = 25, offset: int = 0, category: str | None = None,
                 actor: str | None = None, decision_source: str | None = None,
                 object_type: str | None = None, search: str | None = None,
                 event_workspace: str | None = None) -> CurrentAuditPage:
    items: list[CurrentAuditEvent] = []
    _workspace_events(items, control)
    _operational_events(items, conn, workspace)
    if category:
        items = [event for event in items if event.event_category == category]
    if actor:
        needle = actor.casefold()
        items = [event for event in items if needle in (event.actor_name or '').casefold()]
    if decision_source:
        items = [event for event in items if event.decision_source == decision_source]
    if object_type:
        items = [event for event in items if event.object_type == object_type]
    if search:
        needle = search.casefold()
        items = [event for event in items if any(needle in (ref or '').casefold() for ref in
                 (event.alert_ref, event.case_ref, event.lesson_ref, event.object_ref))]
    if event_workspace:
        items = [event for event in items if event.workspace == event_workspace]
    items.sort(key=lambda event: (datetime.fromisoformat(event.timestamp.replace('Z', '+00:00')),
                                  event.event_ref), reverse=True)
    return CurrentAuditPage(items=items[offset:offset + limit], total=len(items), limit=limit,
                            offset=offset, active_workspace=workspace)
