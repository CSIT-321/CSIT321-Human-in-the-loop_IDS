"""Real DB-backed arbitration, owner enforcement and independent human work status."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db,models as m
from packages.detection import analyst_work as work
from packages.detection.analyst_verdict import VerdictCommand,record_verdict,read_verdict,VerdictConflict
from packages.detection.routing import state_version,RoutingConflict
from packages.detection.adapters.operational_v2 import read_triage
from packages.detection.tier2_escalation import escalate_case,EscalateCaseRequest
from packages.detection.selective_review import review_metrics
from pre_freeze_fixture import event,stage,admit_all
from work_claim_fixture import claim_work

@pytest.fixture
def setup(tmp_path):
    path=tmp_path/'claims.db'
    with closing(db.connect(path)) as c:
        db.create_schema(c)
        for index,role in enumerate(('security_analyst','security_analyst','security_analyst','evaluator','system_admin'),1):
            db.insert(c,m.User(username=f'user{index}',password_hash='test',display_name=f'Analyst {index}',email=f'u{index}@example.test',role=role))
        c.commit()
        stage(c,[event(i,'SSH brute force') for i in range(1,5)])
        alerts=admit_all(c)
    return path,alerts

def command(c,a,outcome='expected_activity'):
    v=read_verdict(c,a.operational_alert_ref,1)
    return VerdictCommand(request_id=uuid4(),expected_revision=v.revision,expected_state_version=v.source_state_version,outcome=outcome,reason='Test canonical judgment')

def headers(path,actor):
    with closing(db.connect(path)) as c:
        return {'Authorization':'Bearer '+auth.encode_token(db.get(c,m.User,actor))}

def test_real_concurrent_http_distinct_actors_both_conflict_then_retry(setup,monkeypatch):
    path,alerts=setup;a=alerts[0];app=create_app(path)
    start=Barrier(2);registered=Barrier(2);original=work.register
    def register(*args,**kwargs):
        result=original(*args,**kwargs)
        registered.wait(timeout=5)  # both actual HTTP workers committed intents before either can finalize
        return result
    def send(actor):
        with TestClient(app) as client:
            start.wait(timeout=5)
            return client.post(f'/api/v2/alerts/{a.operational_alert_ref}/work/claim',headers=headers(path,actor),json={'requestId':str(uuid4()),'expectedRevision':0})
    with patch.object(work,'register',register),ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(send,actor) for actor in (1,2)]
        results=[f.result(timeout=10) for f in futures]
    assert [r.status_code for r in results]==[409,409]
    assert all(r.json()['error']['code']=='CLAIM_CONTENTION' for r in results)
    assert len({r.json()['error']['detail']['roundRef'] for r in results})==1
    with closing(db.connect(path)) as c:
        view=work.read_work(c,a.id,1)
        assert view.status=='available' and view.owner_actor_id is None and view.revision==1
        assert c.execute('SELECT count(*) FROM analyst_claim_rounds').fetchone()[0]==1
        assert c.execute('SELECT count(DISTINCT actor_id) FROM analyst_claim_intents').fetchone()[0]==2
        assert claim_work(c,a).owner_actor_id==1
        with pytest.raises(work.WorkConflict,match='Analyst 1'):
            work.claim(c,a.operational_alert_ref,actor_id=2,request=work.ClaimCommand(request_id=uuid4(),expected_revision=2))
        assert work.read_work(c,a.id,2).owner_actor_id==1
        assert not c.execute('PRAGMA foreign_key_check').fetchall()

@pytest.mark.parametrize('same_request',[True,False])
def test_same_actor_concurrent_retries_are_one_contender(setup,same_request):
    path,alerts=setup;a=alerts[0];barrier=Barrier(2);req=work.ClaimCommand(request_id=uuid4(),expected_revision=0)
    def attempt(index):
        with closing(db.connect(path)) as c:
            barrier.wait(timeout=5)
            return work.claim(c,a.operational_alert_ref,actor_id=1,request=req if same_request or index==0 else req.model_copy(update={'request_id':uuid4()}))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,(0,1)))
    assert all(r.outcome=='claimed' for r in results)
    assert len({r.round_ref for r in results})==1
    with closing(db.connect(path)) as c:
        events=c.execute("SELECT count(*) FROM analyst_work_events WHERE event_type='CLAIM_FINALIZED'").fetchone()[0]
        assert events==1
        assert work.claim(c,a.operational_alert_ref,actor_id=1,request=req).replayed
        with pytest.raises(work.WorkConflict):work.claim(c,a.operational_alert_ref,actor_id=2,request=req)
        with pytest.raises(work.WorkConflict):work.claim(c,alerts[1].operational_alert_ref,actor_id=1,request=req)
        with pytest.raises(work.WorkConflict):work.claim(c,a.operational_alert_ref,actor_id=1,request=req.model_copy(update={'expected_revision':1}))

def test_owner_only_verdict_atomic_completion_correction_and_unchanged_evidence(setup):
    path,alerts=setup;a=alerts[0]
    with closing(db.connect(path)) as c:
        request=command(c,a)
        with pytest.raises(VerdictConflict):record_verdict(c,a.operational_alert_ref,actor_id=1,request=request)
        claim_work(c,a)
        with pytest.raises(VerdictConflict):record_verdict(c,a.operational_alert_ref,actor_id=2,request=request)
        before=read_triage(c,a.id)
        result=record_verdict(c,a.operational_alert_ref,actor_id=1,request=request)
        assert read_triage(c,a.id)==before
        v=work.read_work(c,a.id,2)
        assert v.status=='completed' and v.owner_actor_id is None and v.finished_by_actor_id==1
        assert v.verdict_ref==str(result.verdict.verdict_ref)
        assert c.execute('SELECT count(*) FROM verdict_memory_contributions').fetchone()[0]==1
        events=c.execute('SELECT count(*) FROM analyst_work_events').fetchone()[0]
        assert record_verdict(c,a.operational_alert_ref,actor_id=1,request=request).replayed
        corrected=record_verdict(c,a.operational_alert_ref,actor_id=2,request=command(c,a,'confirmed_malicious'))
        assert corrected.verdict.revision==2 and corrected.verdict.supersedes_ref==result.verdict.verdict_ref
        assert work.read_work(c,a.id,2).status=='completed'
        assert c.execute('SELECT count(*) FROM analyst_work_events').fetchone()[0]==events
        assert review_metrics(c).unsafe_suppression_count==0  # no deferral in this independent scenario
        assert c.execute("SELECT count(*) FROM triage_memory_decisions WHERE action='activate'").fetchone()[0]==0
        with pytest.raises(work.WorkConflict):work.claim(c,a.operational_alert_ref,actor_id=1,request=work.ClaimCommand(request_id=uuid4(),expected_revision=2))
    with TestClient(create_app(path)) as client:
        h=headers(path,1)
        assert len(client.get('/api/v2/alerts?workScope=active',headers=h).json()['items'])==3
        completed=client.get('/api/v2/alerts?workScope=completed',headers=h).json()['items']
        assert len(completed)==1 and completed[0]['work']['status']=='completed'
        summary=client.get('/api/v2/alerts/summary',headers=h).json()
        assert summary['activeAlerts']==3 and summary['totalAlerts']==4 and summary['completedWork']==1 and summary['tier1Review']==3

def test_escalation_owner_only_and_atomic_terminal_work(setup):
    path,alerts=setup;a=alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c,a)
        request=EscalateCaseRequest(request_id=uuid4(),expected_state_version=state_version(read_triage(c,a.id)),reason='Explicit human handoff')
        with pytest.raises(RoutingConflict):escalate_case(c,a.operational_alert_ref,actor_id=2,request=request)
        result=escalate_case(c,a.operational_alert_ref,actor_id=1,request=request)
        assert work.read_work(c,a.id,1).status=='escalated'
        assert read_triage(c,a.id).handling_route=='tier2_case'
        assert result.case.created_by_actor_id==1
        assert escalate_case(c,a.operational_alert_ref,actor_id=1,request=request).replayed
        assert c.execute("SELECT count(*) FROM analyst_work_events WHERE event_type='WORK_ESCALATED'").fetchone()[0]==1

def test_get_never_claims_evaluator_forbidden_and_no_lease(setup,monkeypatch):
    path,alerts=setup;a=alerts[0]
    with closing(db.connect(path)) as c,TestClient(create_app(path)) as client:
        before='\n'.join(c.iterdump());h=headers(path,1)
        for url in ('/api/v2/alerts','/api/v2/alerts/summary',f'/api/v2/alerts/{a.operational_alert_ref}/work',f'/api/v2/alerts/{a.operational_alert_ref}/work/events',f'/api/v2/alerts/{a.operational_alert_ref}/evidence'):
            assert client.get(url,headers=h).status_code==200
        assert '\n'.join(c.iterdump())==before
        assert client.post(f'/api/v2/alerts/{a.operational_alert_ref}/work/claim',headers=headers(path,4),json={'requestId':str(uuid4()),'expectedRevision':0}).status_code==403
        assert '\n'.join(c.iterdump())==before
        claim_work(c,a)
        future=work.now()+work.timedelta(days=365)
        monkeypatch.setattr(work,'now',lambda:future)
        assert work.read_work(c,a.id,1).is_owner
        assert work.read_work(c,a.id,2).owner_actor_id==1
        with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM analyst_work_events')
        c.rollback()
        with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE analyst_work SET status='available',revision=revision+1 WHERE operational_alert_id=?",(a.id,))
        c.rollback()

@pytest.mark.parametrize('terminal',['verdict','escalation'])
def test_terminal_audit_failure_rolls_back_entire_command(setup,terminal):
    path,alerts=setup;a=alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c,a)
        c.execute("CREATE TRIGGER fail_work_finish BEFORE INSERT ON analyst_work_events WHEN NEW.event_type IN ('WORK_COMPLETED','WORK_ESCALATED') BEGIN SELECT RAISE(ABORT,'injected terminal audit failure'); END")
        c.commit();before='\n'.join(c.iterdump())
        with pytest.raises(sqlite3.IntegrityError,match='injected'):
            if terminal=='verdict':record_verdict(c,a.operational_alert_ref,actor_id=1,request=command(c,a))
            else:escalate_case(c,a.operational_alert_ref,actor_id=1,request=EscalateCaseRequest(request_id=uuid4(),expected_state_version=state_version(read_triage(c,a.id)),reason='Atomic handoff'))
        assert '\n'.join(c.iterdump())==before
        assert work.read_work(c,a.id,1).is_owner

def test_crashed_pending_round_only_post_recovers_and_late_actor_cannot_join(setup,monkeypatch):
    path,alerts=setup;a=alerts[0]
    with closing(db.connect(path)) as c:
        req=work.ClaimCommand(request_id=uuid4(),expected_revision=0)
        ref,_=work.register(c,a.operational_alert_ref,1,req)
        future=work.now()+work.timedelta(seconds=2);monkeypatch.setattr(work,'now',lambda:future)
        assert work.read_work(c,a.id,2).owner_actor_id is None
        assert c.execute('SELECT status FROM analyst_claim_rounds').fetchone()[0]=='pending'
        with pytest.raises(work.WorkConflict):work.register(c,a.operational_alert_ref,2,req.model_copy(update={'request_id':uuid4()}))
        assert work.read_work(c,a.id,2).owner_actor_id==1
        assert work.claim(c,a.operational_alert_ref,actor_id=1,request=req).replayed
        events=work.history(c,a.id)
        assert len([e for e in events if e.event_type=='CLAIM_FINALIZED'])==1
        assert next(e for e in events if e.event_type=='CLAIM_FINALIZED').actor_id is None
        assert next(e for e in events if e.event_type=='CLAIM_INTENT').actor_id==1

def test_unknown_bypasses_claim_and_nonowner_cannot_change_review(setup):
    from packages.detection import selective_review as review
    path,alerts=setup;a=alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c,a)
        current=review.read_review(c,a.operational_alert_ref)
        with pytest.raises(review.ReviewConflict):review.decide_review(c,a.operational_alert_ref,actor_id=2,action='require_review',request=review.ReviewCommand(request_id=uuid4(),expected_version=current.version,reason='Other actor blocked'))
        stage(c,[event(100,'Opaque unrecognized anomaly')]);unknown=admit_all(c)[0]
        assert read_triage(c,unknown.id).handling_route=='tier2_case'
        assert work.read_work(c,unknown.id,1).status is None
        with pytest.raises(work.WorkConflict):work.claim(c,unknown.operational_alert_ref,actor_id=1,request=work.ClaimCommand(request_id=uuid4(),expected_revision=0))

def test_owner_guard_covers_context_and_manual_memory_and_admin_policy(setup):
    from packages.detection.context_store import FactRequest,FactConflict,collect_fact,revision
    from packages.detection import triage_memory as memory
    from pre_freeze_fixture import review_request
    path,alerts=setup;a=alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c,a);stamp=m.utc_now()
        before='\n'.join(c.iterdump())
        with pytest.raises(FactConflict):collect_fact(c,actor_id=2,request=FactRequest(request_id=uuid4(),expected_revision=revision(c),subject_type='operational_alert',subject_value=str(a.operational_alert_ref),context_key='responseRequired',value=True,observed_at=stamp,valid_from=stamp,expires_at=stamp+work.timedelta(hours=1),reason='Other actor blocked',source_reference='synthetic:claim'))
        with pytest.raises(memory.MemoryConflict):memory.record_review(c,a.operational_alert_ref,actor_id=2,request=review_request(c,a))
        assert '\n'.join(c.iterdump())==before
        assert claim_work(c,alerts[1],5).owner_actor_id==5  # existing operational admin policy
        c.execute("UPDATE users SET status='inactive' WHERE id=3");c.commit()
        with pytest.raises(PermissionError):work.claim(c,alerts[2].operational_alert_ref,actor_id=3,request=work.ClaimCommand(request_id=uuid4(),expected_revision=0))

def test_migration_21_preserves_populated_schema20_and_atomic_failure(tmp_path,monkeypatch):
    from packages.detection import triage_memory as memory
    path=tmp_path/'upgrade.db';migrations=db.MIGRATIONS
    with closing(db.connect(path)) as c:
        with monkeypatch.context() as old:
            old.setattr(db,'MIGRATIONS',migrations[:20]);db.create_schema(c)
            db.insert(c,m.User(username='alice',display_name='Alice',password_hash='x',email='a@example.test',role='security_analyst'));c.commit()
            stage(c,[event(i,'SSH brute force') for i in range(1,4)]);aa=admit_all(c)
            # Fixture construction reproduces version-20 command semantics only.
            old.setattr(work,'read_work',lambda *a,**k:work.WorkView(status=None,revision=0,can_mutate=True,explanation='pre-claim history'))
            old.setattr(work,'complete',lambda *a,**k:None)
            old.setattr(work,'row',lambda *a,**k:None)
            old.setattr(work,'require_owner',lambda *a,**k:None)
            record_verdict(c,aa[0].operational_alert_ref,actor_id=1,request=command(c,aa[0]))
            escalate_case(c,aa[1].operational_alert_ref,actor_id=1,request=EscalateCaseRequest(request_id=uuid4(),expected_state_version=state_version(read_triage(c,aa[1].id)),reason='Historical handoff'))
            assert memory.verdict_memory_state(c,aa[0].operational_alert_ref).memory is not None
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in tables};dump='\n'.join(c.iterdump())
        with monkeypatch.context() as broken:
            broken.setattr(db,'MIGRATIONS',migrations[:20]+((21,'broken',migrations[20][2]+'\nSELECT * FROM deliberately_missing;'),))
            with pytest.raises(sqlite3.OperationalError):db.migrate(c)
        assert '\n'.join(c.iterdump())==dump
        assert db.migrate(c)==[21] and db.migrate(c)==[]
        assert {t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in tables}==before
        assert work.read_work(c,aa[0].id,1).status=='completed'
        assert work.read_work(c,aa[1].id,1).status=='escalated'
        assert work.read_work(c,aa[2].id,1).status=='available'
        assert c.execute('SELECT count(*) FROM analyst_claim_rounds').fetchone()[0]==0
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

def test_no_immediate_review_requires_explicit_override_before_claim(setup):
    from hashlib import sha256
    from packages.detection.adapters.suricata_bundle import build_bundle,parse_record
    from packages.detection.context_store import seed_synthetic_facts
    from packages.detection import selective_review as review
    from pre_freeze_fixture import safe_context,defer
    path,alerts=setup
    with closing(db.connect(path)) as c:
        # Three real canonical benign judgments activate the existing exact lesson.
        for a in alerts[:3]:
            seed_synthetic_facts(c,a,safe_context(),m.utc_now());claim_work(c,a)
            record_verdict(c,a.operational_alert_ref,actor_id=1,request=command(c,a))
        flow=200
        while True:
            raw=event(flow,'SSH brute force');flow+=1
            ref=build_bundle([parse_record(raw,'review-sensor','review-fixture')]).canonical_alert_id
            if int(sha256(str(ref).encode()).hexdigest()[:8],16)%100>=10:break
        stage(c,[raw]);a=admit_all(c)[0];seed_synthetic_facts(c,a,safe_context(),m.utc_now())
        assert defer(c,a).disposition=='no_immediate_review'
        before='\n'.join(c.iterdump())
        assert not work.read_work(c,a.id,1).can_claim
        with pytest.raises(work.WorkConflict,match='Require Human Review'):
            work.claim(c,a.operational_alert_ref,actor_id=1,request=work.ClaimCommand(request_id=uuid4(),expected_revision=0))
        assert '\n'.join(c.iterdump())==before
        current=review.read_review(c,a.operational_alert_ref)
        review.decide_review(c,a.operational_alert_ref,actor_id=1,action='require_review',request=review.ReviewCommand(request_id=uuid4(),expected_version=current.version,reason='Explicit human work required'))
        assert claim_work(c,a).owner_actor_id==1
