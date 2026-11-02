"""Disposable browser fixture: real domain commands, current policies, no frozen writes."""
import json
import sys
from uuid import uuid4

from packages.contracts import db, models as m
from packages.detection import selective_review as review, triage_memory as memory
from packages.detection.analyst_verdict import VerdictCommand, read_verdict, record_verdict
from packages.detection.context_store import seed_synthetic_facts
from packages.detection.response_approval import (
    ResponseDecisionRequest, ResponseRequest, decide_response, propose_response,
)
from packages.detection.tier2_cases import CaseCommand, InvestigationConclusionRequest, mutate_case, read_case
from pre_freeze_fixture import admit_all, event, safe_context, stage
from work_claim_fixture import claim_work


def prepare(path: str) -> dict[str, str]:
    conn = db.connect(path)
    try:
        analyst = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        stage(conn, [event(880000 + i, 'SYNTHETIC audit browser SSH scan', severity=1)
                     for i in range(12)], scope='current-audit-browser-' + str(uuid4()))
        alerts = admit_all(conn, actor=analyst)
        for alert in alerts:
            seed_synthetic_facts(conn, alert, safe_context(), m.utc_now())
        for alert in alerts[:3]:
            claim_work(conn, alert, analyst)
            view = read_verdict(conn, alert.operational_alert_ref, analyst)
            record_verdict(conn, alert.operational_alert_ref, actor_id=analyst, request=VerdictCommand(
                request_id=uuid4(), expected_revision=view.revision,
                expected_state_version=view.source_state_version, outcome='expected_activity',
                reason='SYNTHETIC browser audit learning evidence'))
        lesson = memory.verdict_memory_state(conn, alerts[0].operational_alert_ref).memory
        assert lesson.status == 'active' and lesson.support_count == 3
        future = next(alert for alert in alerts[3:] if
            review.read_review(conn, alert.operational_alert_ref).policy_evaluation.result.disposition == 'no_immediate_review')
        current = review.read_review(conn, future.operational_alert_ref)
        decision = review.decide_review(conn, future.operational_alert_ref, actor_id=analyst,
            action='apply', request=review.ReviewCommand(request_id=uuid4(),
                expected_version=current.version, reason='SYNTHETIC browser audit future evaluation'))
        assert decision.view.disposition == 'no_immediate_review'

        stage(conn, [event(990001, 'Unresolved suspicious activity', 'Misc activity', 4)],
              scope='current-audit-browser-unknown-' + str(uuid4()))
        unknown = admit_all(conn, actor=analyst)[0]
        case_ref = conn.execute('SELECT case_ref FROM tier2_cases WHERE primary_operational_alert_id=?',
                                (unknown.id,)).fetchone()[0]
        case = read_case(conn, case_ref)
        case = mutate_case(conn, case.case_ref, actor_id=analyst, action='finding',
            request=InvestigationConclusionRequest(request_id=uuid4(), expected_revision=case.revision,
                finding='confirmed_malicious', final_attack_category='web_attack',
                reason='SYNTHETIC browser audit expert conclusion')).case
        proposal = propose_response(conn, case.case_ref, actor_id=analyst,
            request=ResponseRequest(request_id=uuid4(), expected_case_revision=case.revision,
                reason='SYNTHETIC browser audit recommendation')).response
        decide_response(conn, case.case_ref, proposal.proposal.recommendation_ref, actor_id=analyst,
            decision='approved', request=ResponseDecisionRequest(request_id=uuid4(),
                expected_case_revision=case.revision, expected_revision=proposal.revision,
                reason='SYNTHETIC browser audit approval only'))
        case = mutate_case(conn, case.case_ref, actor_id=analyst, action='resolve',
            request=CaseCommand(request_id=uuid4(), expected_revision=case.revision,
                reason='SYNTHETIC browser audit closure')).case
        return {'alertRef': str(alerts[0].operational_alert_ref), 'futureRef': str(future.operational_alert_ref),
                'lessonRef': str(lesson.lesson.lesson_ref), 'caseRef': str(case.case_ref),
                'unknownRef': str(unknown.operational_alert_ref)}
    finally:
        conn.close()


if __name__ == '__main__':
    print(json.dumps(prepare(sys.argv[1])))
