"""Real canonical commands exercise automatic evidence, fixed validity and safety withdrawal."""
from datetime import timedelta
from uuid import uuid4
import sqlite3
import pytest
from packages.contracts import db,models as m
from packages.detection import triage_memory as memory
from packages.detection import selective_review as review
from packages.detection.analyst_verdict import record_verdict,read_verdict,VerdictCommand
from pre_freeze_fixture import stage,event,admit_all,safe_context,defer
from packages.detection.context_store import seed_synthetic_facts
from test_investigation_assistance import escalate
from test_tier2_human_reclassification import conclude,command
from test_verdict_memory import contribute

@pytest.fixture
def conn():
    c=db.connect(':memory:');db.create_schema(c)
    db.insert(c,m.User(username='reviewer',display_name='Reviewer',password_hash='x',email='r@example.test',role='security_analyst'));c.commit()
    yield c
    c.close()

def sources(c,n=6):
    stage(c,[event(300+i,'SYNTHETIC automatic SSH scan',severity=1) for i in range(n)])
    alerts=admit_all(c)
    for a in alerts:seed_synthetic_facts(c,a,safe_context(),m.utc_now())
    return alerts

def verdict(c,a,outcome='expected_activity'):
    view=read_verdict(c,a.operational_alert_ref,1)
    req=VerdictCommand(request_id=uuid4(),expected_revision=view.revision,expected_state_version=view.source_state_version,outcome=outcome,reason='SYNTHETIC canonical '+outcome)
    return record_verdict(c,a.operational_alert_ref,actor_id=1,request=req),req

def lesson(c,a):return memory.verdict_memory_state(c,a.operational_alert_ref).memory

@pytest.mark.parametrize('outcome',['expected_activity','false_positive'])
def test_three_independent_sources_auto_activate_with_real_attribution(conn,outcome):
    aa=sources(conn)
    for i,a in enumerate(aa[:3],1):
        result,req=verdict(conn,a,outcome);view=lesson(conn,a)
        assert view.support_count==i and view.status==('active' if i==3 else 'candidate')
        assert record_verdict(conn,a.operational_alert_ref,actor_id=1,request=req).replayed
        assert contribute(conn,a,result.verdict).replayed
        assert lesson(conn,a).support_count==i
    assert view.decision.actor_id is None and view.decision.decision_source=='system_policy'
    assert view.expires_at-view.valid_from==timedelta(days=30)
    audit=memory.memory_history(conn,view.lesson.lesson_ref,200,0)[0]
    e=next(e.evidence for e in audit if e.evidence)
    assert e.actor_id is None and e.decision_source=='system_policy'
    assert e.verdict_author_id==1 and e.verdict_author_name=='Reviewer'
    before='\n'.join(conn.iterdump());conn.execute('PRAGMA query_only=ON')
    memory.list_memory(conn,200,0);review.read_review(conn,aa[3].operational_alert_ref)
    assert '\n'.join(conn.iterdump())==before
    conn.execute('PRAGMA query_only=OFF')
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()

@pytest.mark.parametrize('outcome',['confirmed_malicious','suspicious'])
def test_unsafe_evidence_never_auto_activates(conn,outcome):
    aa=sources(conn)
    for a in aa[:3]:verdict(conn,a,outcome)
    view=lesson(conn,aa[0]);assert view.support_count==3 and view.decision is None
    assert not memory.explain_match(view,memory.context_for(aa[3])).guidance_active
    assert defer(conn,aa[3]).disposition=='must_review'

@pytest.mark.parametrize('expert',['confirmed_malicious','inconclusive'])
def test_expert_authority_replaces_tier1_and_withdraws(conn,expert):
    aa=sources(conn)
    for a in aa[:3]:verdict(conn,a)
    original=lesson(conn,aa[0]);case=escalate(conn,aa[0])
    case=conclude(conn,case,command(expert,'web_attack' if expert=='confirmed_malicious' else None,case.revision)).case
    old=memory.read_memory(conn,original.lesson.lesson_ref)
    assert old.support_count==2 and old.status!='active'
    current=memory.conclusion_memory_state(conn,case.case_ref)
    if expert=='inconclusive':assert not current.eligible and current.contribution_status=='not_contributed'
    else:
        assert current.contribution_status=='contributed' and current.decision_source=='system_policy'
        assert old.conflict_count==1
    assert defer(conn,aa[3]).disposition=='must_review'


def test_correction_conflict_and_exact_narrow_dedup(conn):
    aa=sources(conn)
    for a in aa[:3]:verdict(conn,a)
    original=lesson(conn,aa[0]);v,_=verdict(conn,aa[0],'confirmed_malicious')
    current=lesson(conn,aa[0]);assert current.support_count==2 and current.conflict_count==1
    assert current.status=='conflict_review' and current.decision==original.decision
    contribute(conn,aa[0],v.verdict,'narrow')
    assert memory.read_memory(conn,original.lesson.lesson_ref).conflict_count==1
    assert defer(conn,aa[3]).disposition=='must_review'


def test_fixed_expiry_no_renewal_or_reactivation(conn,monkeypatch):
    aa=sources(conn);clock=m.utc_now();monkeypatch.setattr(m,'utc_now',lambda:clock)
    for a in aa[:3]:verdict(conn,a)
    first=lesson(conn,aa[0]);assert first.valid_from==clock
    clock+=timedelta(days=15);verdict(conn,aa[3]);assert lesson(conn,aa[0]).expires_at==first.expires_at
    clock+=timedelta(days=15)
    expired=lesson(conn,aa[0]);assert expired.status=='expired'
    verdict(conn,aa[4]);again=lesson(conn,aa[4]);assert again.lesson.lesson_ref==first.lesson.lesson_ref
    assert again.status=='expired' and again.expires_at==first.expires_at
    assert not memory.explain_match(again,memory.context_for(aa[5])).guidance_active
    assert defer(conn,aa[5]).disposition=='must_review'


def test_human_rejection_never_reconsidered(conn):
    aa=sources(conn);verdict(conn,aa[0]);view=lesson(conn,aa[0])
    memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=1,action='reject',request=memory.MemoryDecisionRequest(request_id=uuid4(),expected_revision=view.revision,reason='Do not trust this context'))
    for a in aa[1:4]:verdict(conn,a)
    current=lesson(conn,aa[3]);assert current.lesson.lesson_ref==view.lesson.lesson_ref
    assert current.status=='rejected' and current.decision.actor_id==1


def test_atomic_failure_rolls_back_verdict_and_learning(conn):
    a=sources(conn)[0]
    conn.execute("CREATE TRIGGER fail_auto BEFORE INSERT ON verdict_memory_evidence BEGIN SELECT RAISE(ABORT,'injected'); END");conn.commit()
    before='\n'.join(conn.iterdump())
    with pytest.raises(sqlite3.IntegrityError):verdict(conn,a)
    assert '\n'.join(conn.iterdump())==before

def test_auto_active_memory_still_requires_independent_selective_gate(conn,monkeypatch):
    aa=sources(conn,12)
    for a in aa[:3]:verdict(conn,a)
    # Existing 10% audit sampling remains authoritative; choose a non-sampled future source.
    future=next(a for a in aa[3:] if review.read_review(conn,a.operational_alert_ref).policy_evaluation.result.disposition=='no_immediate_review')
    assert defer(conn,future).disposition=='no_immediate_review'
    current=lesson(conn,aa[0]);clock=current.expires_at
    monkeypatch.setattr(m,'utc_now',lambda:clock)
    seed_synthetic_facts(conn,future,safe_context(),clock)
    assert memory.read_memory(conn,current.lesson.lesson_ref).status=='expired'
    assert defer(conn,future).disposition=='must_review'


def test_expert_failure_rolls_back_canonical_conclusion_and_supersession(conn):
    a=sources(conn)[0];verdict(conn,a);case=escalate(conn,a)
    conn.execute("CREATE TRIGGER fail_auto_expert BEFORE INSERT ON conclusion_memory_evidence BEGIN SELECT RAISE(ABORT,'injected'); END");conn.commit()
    before='\n'.join(conn.iterdump())
    with pytest.raises(sqlite3.IntegrityError):conclude(conn,case,command('confirmed_malicious','web_attack',case.revision))
    assert '\n'.join(conn.iterdump())==before
    assert memory.verdict_memory_state(conn,a.operational_alert_ref).contribution_status=='contributed'


def test_activation_failure_rolls_back_third_verdict_and_support(conn):
    aa=sources(conn)
    for a in aa[:2]:verdict(conn,a)
    conn.execute("CREATE TRIGGER fail_activation BEFORE INSERT ON triage_memory_decisions BEGIN SELECT RAISE(ABORT,'injected'); END");conn.commit()
    before='\n'.join(conn.iterdump())
    with pytest.raises(sqlite3.IntegrityError):verdict(conn,aa[2])
    assert '\n'.join(conn.iterdump())==before
    assert lesson(conn,aa[0]).support_count==2

@pytest.mark.parametrize('outcome',['expected_activity','suspicious','confirmed_malicious'])
def test_three_expert_judgments_automatically_learn_but_only_benign_activates(conn,outcome):
    aa=sources(conn)
    for i,a in enumerate(aa[:3],1):
        case=escalate(conn,a)
        result=conclude(conn,case,command(outcome,'web_attack' if outcome=='confirmed_malicious' else None,case.revision)).case
        state=memory.conclusion_memory_state(conn,result.case_ref)
        assert state.memory.support_count==i and state.decision_source=='system_policy'
        assert bool(state.memory.decision)==(outcome=='expected_activity' and i==3)
    evidence=next(e.evidence for e in memory.memory_history(conn,state.lesson_ref,200,0)[0] if e.evidence)
    assert evidence.actor_id is None and evidence.source_conclusion.actor_id==1
    assert evidence.conclusion_author_name=='Reviewer'


def test_eligible_historical_candidate_is_not_activated_by_read(conn,monkeypatch):
    aa=sources(conn)
    with monkeypatch.context() as patch:
        patch.setattr(memory,'automatic_evidence',lambda *a,**k:None)
        for a in aa[:3]:
            v,_=verdict(conn,a);contribute(conn,a,v.verdict)
    current=lesson(conn,aa[0]);assert current.status=='eligible_for_activation'
    snapshot='\n'.join(conn.iterdump());conn.execute('PRAGMA query_only=ON')
    memory.list_memory(conn,50,0);memory.lookup_memory(conn,aa[3].operational_alert_ref,50,0)
    memory.memory_history(conn,current.lesson.lesson_ref,200,0);review.read_review(conn,aa[3].operational_alert_ref)
    assert '\n'.join(conn.iterdump())==snapshot
    conn.execute('PRAGMA query_only=OFF')
    verdict(conn,aa[3]);assert lesson(conn,aa[0]).status=='active'
