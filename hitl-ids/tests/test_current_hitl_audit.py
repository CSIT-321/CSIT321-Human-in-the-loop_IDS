"""Unified audit reads actual durable decisions without modifying their sources."""
from contextlib import closing
from datetime import datetime
from hashlib import sha256
from time import sleep
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api import auth, workspaces
from apps.api.current_audit import list_current
from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection import analyst_work as work, selective_review as review
from packages.detection.context_store import seed_synthetic_facts
from packages.detection.adapters.operational_v2 import read_triage
from packages.detection.routing import state_version
from packages.detection.tier2_escalation import EscalateCaseRequest, escalate_case
from packages.detection.response_approval import (
    ResponseDecisionRequest, ResponseRequest, decide_response, propose_response,
)
from packages.detection.tier2_cases import CaseCommand, mutate_case
from pre_freeze_fixture import admit_all, event, safe_context, stage, defer
from test_investigation_assistance import admit, automatic_case
from test_safe_memory_auto_activation import verdict, lesson
from test_tier2_human_reclassification import command as conclusion_command, conclude
from work_claim_fixture import claim_work


def _hash(path):
    return sha256(path.read_bytes()).hexdigest()


def _token(conn, actor_id):
    return {'Authorization': 'Bearer ' + auth.encode_token(db.get(conn, m.User, actor_id))}


def test_current_audit_normalizes_full_real_hitl_chain_and_is_read_only(tmp_path):
    path = tmp_path / 'operational.db'
    with closing(db.connect(path)) as conn:
        db.create_schema(conn)
        for index, role in enumerate(('security_analyst', 'security_analyst', 'system_admin', 'evaluator'), 1):
            db.insert(conn, m.User(username=f'actor{index}', display_name=f'Actor {index}',
                password_hash='synthetic', email=f'actor{index}@example.test', role=role))
        conn.commit()
        stage(conn, [event(300 + i, 'SYNTHETIC automatic SSH scan', severity=1) for i in range(12)])
        alerts = admit_all(conn)
        for alert in alerts:
            seed_synthetic_facts(conn, alert, safe_context(), m.utc_now())

        # Two different humans request the same available alert within one real claim round.
        contested = alerts[-1]
        with patch.object(work, 'policy', return_value={'version': 'analyst-work-claim-v1',
                                                       'claimArbitrationWindowMs': 100}):
            round_ref, _ = work.register(conn, contested.operational_alert_ref, 1,
                work.ClaimCommand(request_id=uuid4(), expected_revision=0))
            second_ref, _ = work.register(conn, contested.operational_alert_ref, 2,
                work.ClaimCommand(request_id=uuid4(), expected_revision=0))
            assert second_ref == round_ref
            sleep(.11)
            assert work.finish_round(conn, round_ref, 1).outcome == 'contended'

        for alert in alerts[:3]:
            claim_work(conn, alert)
            verdict(conn, alert)
        memory = lesson(conn, alerts[0])
        assert memory.status == 'active' and memory.support_count == 3

        future = next(alert for alert in alerts[3:-1] if
            review.read_review(conn, alert.operational_alert_ref).policy_evaluation.result.disposition == 'no_immediate_review')
        assert defer(conn, future).disposition == 'no_immediate_review'

        # Correction remains append-only and withdraws active guidance on conflict.
        verdict(conn, alerts[0], 'confirmed_malicious')
        assert lesson(conn, alerts[0]).status == 'conflict_review'

        manual = alerts[4]
        claim_work(conn, manual)
        manual_case = escalate_case(conn, manual.operational_alert_ref, actor_id=1,
            request=EscalateCaseRequest(request_id=uuid4(),
                expected_state_version=state_version(read_triage(conn, manual.id)),
                reason='SYNTHETIC analyst Tier 2 handoff')).case
        assert manual_case.primary_operational_alert_ref == manual.operational_alert_ref

        unknown = admit(conn)
        case = automatic_case(conn, unknown)
        case = conclude(conn, case, conclusion_command('confirmed_malicious', 'web_attack', case.revision)).case
        proposed = propose_response(conn, case.case_ref, actor_id=1,
            request=ResponseRequest(request_id=uuid4(), expected_case_revision=case.revision,
                reason='SYNTHETIC policy recommendation')).response
        decided = decide_response(conn, case.case_ref, proposed.proposal.recommendation_ref,
            actor_id=1, decision='approved', request=ResponseDecisionRequest(
                request_id=uuid4(), expected_case_revision=case.revision,
                expected_revision=proposed.revision, reason='SYNTHETIC approval only'))
        assert decided.response.execution_status == 'not_executed'
        case = mutate_case(conn, case.case_ref, actor_id=1, action='resolve', request=CaseCommand(
            request_id=uuid4(), expected_revision=case.revision,
            reason='SYNTHETIC investigation complete')).case
        assert case.status == 'resolved'

        rejected_case = automatic_case(conn, admit(conn, event(9001, 'Unresolved suspicious activity', 'Misc activity', 4)))
        rejected_proposal = propose_response(conn, rejected_case.case_ref, actor_id=1,
            request=ResponseRequest(request_id=uuid4(), expected_case_revision=rejected_case.revision,
                reason='SYNTHETIC investigate plan')).response
        rejected = decide_response(conn, rejected_case.case_ref, rejected_proposal.proposal.recommendation_ref,
            actor_id=1, decision='rejected', request=ResponseDecisionRequest(
                request_id=uuid4(), expected_case_revision=rejected_case.revision,
                expected_revision=rejected_proposal.revision, reason='SYNTHETIC reject plan'))
        assert rejected.response.execution_status == 'not_executed'

        admin = _token(conn, 3)
        analyst = _token(conn, 1)
        evaluator = _token(conn, 4)

    client = TestClient(create_app(path))
    activated = client.post('/api/admin/workspaces/operational/activate',
        headers=admin, json={'reason': 'SYNTHETIC audit attribution'})
    assert activated.status_code == 200, activated.text
    control = path.parent / 'workspaces' / 'control.db'
    replay = path.parent / 'workspaces' / 'v3-1-replay.db'
    with closing(db.connect(replay)) as conn:
        db.create_schema(conn)
    frozen = workspaces.WORKLOAD
    before = {str(item): _hash(item) for item in (path, control, replay, frozen)}

    endpoint = '/api/admin/audit/current'
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers=analyst).status_code == 403
    assert client.get(endpoint, headers=evaluator).status_code == 403
    response = client.get(endpoint, headers=admin, params={'limit': 200})
    assert response.status_code == 200, response.text
    page = response.json()
    assert page['activeWorkspace'] == 'operational'
    assert page['total'] == len(page['items'])
    events = page['items']
    assert events == sorted(events, key=lambda item: (
        datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00')), item['eventRef']), reverse=True)
    assert len({item['eventRef'] for item in events}) == len(events)
    assert {item['eventCategory'] for item in events} == {
        'WORKSPACE', 'WORK', 'VERDICT', 'MEMORY', 'REVIEW', 'TIER2', 'RESPONSE', 'RESOLUTION'}

    def find(category, action):
        return [item for item in events if item['eventCategory'] == category and item['action'] == action]

    assert find('WORKSPACE', 'Workspace activated')[0]['actorName'] == 'actor3'
    assert find('WORKSPACE', 'Workspace activated')[0]['workspace'] == 'global'
    assert find('WORK', 'Review requested')[0]['actorName'] in ('Actor 1', 'Actor 2')
    assert find('WORK', 'Review started')[0]['actorType'] == 'system'
    conflict = find('WORK', 'Claim conflict')[0]
    assert conflict['actorType'] == 'system' and conflict['result'] == 'No owner'
    assert 'Actor 1' in conflict['summary'] and 'Actor 2' in conflict['summary']
    assert find('WORK', 'Work completed')
    assert find('WORK', 'Work escalated')
    verdicts = [item for item in events if item['eventCategory'] == 'VERDICT' and
                item['alertRef'] == str(alerts[0].operational_alert_ref)]
    assert {item['detail']['revision'] for item in verdicts} == {1, 2}
    assert all(item['actorName'] == 'Actor 1' for item in verdicts)
    assert find('VERDICT', 'Verdict corrected')[0]['detail']['supersedesRef']
    evidence = find('MEMORY', 'Exact evidence recorded')[0]
    assert evidence['actorType'] == 'system' and evidence['decisionSource'] == 'system_policy'
    assert evidence['detail']['humanSourceActor'] == 'Actor 1'
    activation = find('MEMORY', 'Lesson auto-activated')[0]
    assert activation['actorType'] == 'system' and activation['result'] == 'active'
    withdrawn = find('MEMORY', 'Conflicting evidence added')[0]
    assert withdrawn['result'] == 'conflict_review' and 'Guidance withdrawn' in withdrawn['summary']
    selective = find('REVIEW', 'No Immediate Review')[0]
    assert selective['actorType'] == 'system' and selective['alertRef'] == str(future.operational_alert_ref)
    assert selective['detail']['initiatedBy'] == 'Actor 1'
    automatic = next(item for item in find('TIER2', 'Tier 2 Case created') if item['caseRef'] == str(case.case_ref))
    assert automatic['actorType'] == 'system' and automatic['decisionSource'] == 'system_policy'
    assert find('TIER2', 'Manual Tier 2 escalation')[0]['actorName'] == 'Actor 1'
    assert any(item['alertRef'] == str(unknown.operational_alert_ref) and item['actorType'] == 'system'
               for item in find('TIER2', 'System routed alert'))
    conclusion = find('TIER2', 'Investigation Conclusion')[0]
    assert conclusion['actorName'] == 'Actor 1'
    assert conclusion['detail']['finding'] == 'confirmed_malicious'
    assert conclusion['detail']['finalAttackCategory'] == 'web_attack'
    assert conclusion['detail']['systemClassification']['attackCategory'] == 'unknown_needs_expert'
    assert find('RESPONSE', 'Response recommended')
    assert find('RESPONSE', 'Response approved')[0]['result'] == 'Approved — Not Executed'
    assert find('RESPONSE', 'Response rejected')[0]['result'] == 'Rejected — Not Executed'
    assert find('RESOLUTION', 'Case resolved')[0]['result'] == 'Resolved'

    for params in ({'category': 'MEMORY', 'limit': 1}, {'decisionSource': 'system_policy'},
                   {'actor': 'Actor 1'}, {'objectType': 'case'},
                   {'search': str(case.case_ref)}, {'workspace': 'global'}):
        filtered = client.get(endpoint, headers=admin, params=params)
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()['total'] > 0
    first = client.get(endpoint, headers=admin, params={'category': 'MEMORY', 'limit': 1}).json()
    second = client.get(endpoint, headers=admin, params={'category': 'MEMORY', 'limit': 1, 'offset': 1}).json()
    assert first['total'] == second['total'] and first['items'][0]['eventRef'] != second['items'][0]['eventRef']
    assert all(item['eventCategory'] == 'MEMORY' for item in first['items'] + second['items'])
    assert client.get(endpoint, headers=admin, params={'category': 'WRONG'}).status_code == 400
    assert {str(item): _hash(item) for item in (path, control, replay, frozen)} == before


def test_selected_workspace_isolation(tmp_path):
    path = tmp_path / 'operational.db'
    replay = tmp_path / 'workspaces' / 'v3-1-replay.db'
    replay.parent.mkdir()
    for target in (path, replay):
        with closing(db.connect(target)) as conn:
            db.create_schema(conn)
    with closing(db.connect(path)) as conn:
        operational = list_current(conn, tmp_path / 'workspaces' / 'control.db', 'operational')
    with closing(db.connect(replay)) as conn:
        other = list_current(conn, tmp_path / 'workspaces' / 'control.db', 'v3-1-replay')
    assert operational.items == other.items == []
    assert operational.active_workspace == 'operational' and other.active_workspace == 'v3-1-replay'
