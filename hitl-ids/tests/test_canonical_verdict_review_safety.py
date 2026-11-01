"""Canonical outcomes recall source attention independently of optional learning."""
from datetime import timedelta
import pytest
from test_pre_freeze_review_fixes import conn, api, assert_attention
from pre_freeze_fixture import review_scenario, defer
from test_verdict_memory import verdict, contribute
from test_investigation_assistance import escalate
from test_tier2_human_reclassification import conclude, command
from packages.contracts import models as m
from packages.detection import selective_review as review


@pytest.mark.parametrize('outcome,unsafe', [('confirmed_malicious',1),('suspicious',1),('expected_activity',0),('false_positive',0)])
def test_canonical_verdict_recall_without_contribution(conn,api,outcome,unsafe):
    alerts=review_scenario(conn);a=alerts[3];ref=a.operational_alert_ref
    before=review.read_review(conn,ref);assert before.disposition=='no_immediate_review'
    original_events=[tuple(r) for r in conn.execute('SELECT * FROM selective_review_events')]
    v=verdict(conn,a,outcome)
    snapshot='\n'.join(conn.iterdump())
    conn.execute('PRAGMA query_only=ON')
    current=review.read_review(conn,ref)
    assert current.disposition=='must_review' and current.recalled and current.version!=before.version
    inputs=current.policy_evaluation.inputs
    assert inputs.human_verdict_present
    assert inputs.canonical_verdict.verdict_ref==v.verdict_ref
    assert inputs.canonical_verdict.revision==1 and inputs.canonical_verdict.outcome==outcome
    assert 'EXISTING_HUMAN_VERDICT' in current.reason_codes
    assert review.review_metrics(conn).unsafe_suppression_count==unsafe
    assert '\n'.join(conn.iterdump())==snapshot
    conn.execute('PRAGMA query_only=OFF')
    assert_attention(conn,api,alerts,2)
    assert api.get('/api/v2/selective-review/metrics').json()['unsafeSuppressionCount']==unsafe
    assert '\n'.join(conn.iterdump())==snapshot
    assert not conn.execute('SELECT 1 FROM verdict_memory_contributions WHERE source_alert_id=?',(a.id,)).fetchone()
    assert [tuple(r) for r in conn.execute('SELECT * FROM selective_review_events')]==original_events
    assert review.read_review(conn,alerts[4].operational_alert_ref).disposition=='no_immediate_review'


@pytest.mark.parametrize('initial',['confirmed_malicious','suspicious'])
def test_correction_latest_identity_and_metric(conn,initial):
    a=review_scenario(conn)[3];first=verdict(conn,a,initial)
    old=review.read_review(conn,a.operational_alert_ref)
    assert review.unsafe_suppression_count(conn)==1
    latest=verdict(conn,a,'expected_activity');current=review.read_review(conn,a.operational_alert_ref)
    assert latest.supersedes_ref==first.verdict_ref
    assert current.version!=old.version and current.disposition=='must_review'
    assert current.policy_evaluation.inputs.canonical_verdict.model_dump()==dict(verdict_ref=latest.verdict_ref,revision=2,outcome='expected_activity')
    assert review.unsafe_suppression_count(conn)==0
    assert conn.execute('SELECT count(*) FROM analyst_verdict_events WHERE operational_alert_id=?',(a.id,)).fetchone()[0]==2


def test_distinct_alerts_multiple_deferrals_and_optional_contribution(conn):
    alerts=review_scenario(conn);a,b=alerts[3:5]
    assert defer(conn,a).disposition=='no_immediate_review'
    verdict(conn,a,'suspicious');v=verdict(conn,a,'confirmed_malicious')
    assert review.unsafe_suppression_count(conn)==1
    verdict(conn,b,'confirmed_malicious')
    assert review.unsafe_suppression_count(conn)==2
    contribute(conn,a,v)
    assert review.unsafe_suppression_count(conn)==2


@pytest.mark.parametrize('tier1,expert,category,unsafe',[
    ('expected_activity','confirmed_malicious','web_attack',1),
    ('confirmed_malicious','expected_activity',None,0),
    ('suspicious','inconclusive',None,0),
])
def test_latest_expert_supersedes_tier1_without_contribution(conn,tier1,expert,category,unsafe):
    a=review_scenario(conn)[3];verdict(conn,a,tier1)
    case=escalate(conn,a);case=conclude(conn,case,command(expert,category,case.revision)).case
    assert review.unsafe_suppression_count(conn)==unsafe
    assert not conn.execute('SELECT 1 FROM conclusion_memory_contributions').fetchone()
    case=conclude(conn,case,command('suspicious',None,case.revision)).case
    assert review.unsafe_suppression_count(conn)==1
    conclude(conn,case,command('expected_activity',None,case.revision))
    assert review.unsafe_suppression_count(conn)==0


@pytest.mark.parametrize('delta',[-1,0,1])
def test_strict_later_time_boundary(conn,monkeypatch,delta):
    a=review_scenario(conn)[3]
    stamp=review.read_review(conn,a.operational_alert_ref).last_decision.created_at
    from datetime import datetime
    when=datetime.fromisoformat(stamp.replace('Z','+00:00'))+timedelta(microseconds=delta)
    # Simulate historical ordering/clock boundary; all decisions still use real commands.
    monkeypatch.setattr(m,'utc_now',lambda:when)
    verdict(conn,a,'confirmed_malicious')
    assert review.unsafe_suppression_count(conn)==int(delta>0)
    assert defer(conn,a).disposition=='must_review'


def test_absent_verdict_preserves_previous_input_hash(conn):
    a=review_scenario(conn)[3];s=review.read_review(conn,a.operational_alert_ref).policy_evaluation
    old=review._hash(dict(inputs=s.inputs.model_dump(mode='json',exclude={'canonical_verdict'}),
        policy=s.policy_config_snapshot.model_dump(mode='json'),result=s.result.model_dump(mode='json'),
        provenance=s.context_provenance.model_dump(mode='json',exclude={'evaluated_at'})))
    assert old==s.input_version
    historical=s.model_dump(by_alias=True);historical['inputs'].pop('canonicalVerdict')
    assert review.ReviewSnapshot.model_validate(historical).inputs.canonical_verdict is None
