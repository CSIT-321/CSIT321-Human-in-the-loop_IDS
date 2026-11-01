"""Real Verdict → evidence commands, dynamic supersession and active guidance safety."""
import json
import sqlite3
from uuid import uuid4
import pytest
from test_pre_freeze_review_fixes import conn,api
from pre_freeze_fixture import event,stage,admit_all,review_scenario
from packages.contracts import db,models as m
from packages.detection import triage_memory as memory
from packages.detection.analyst_verdict import read_verdict,record_verdict,VerdictCommand,verdict_history
from packages.detection.selective_review import read_review

def alerts(conn,n=4):
    stage(conn,[event(100+i,'SYNTHETIC memory SSH scan',severity=1) for i in range(n)])
    return admit_all(conn)

def verdict(conn,a,outcome='expected_activity'):
    v=read_verdict(conn,a.operational_alert_ref,1)
    return record_verdict(conn,a.operational_alert_ref,actor_id=1,request=VerdictCommand(request_id=uuid4(),
        expected_revision=v.revision,expected_state_version=v.source_state_version,outcome=outcome,reason='Canonical reason: '+outcome)).verdict

def request(conn,a,v,scope='exact'):
    return memory.VerdictMemoryRequest(request_id=uuid4(),verdict_ref=v.verdict_ref,scope=scope,
        expected_state_version=read_verdict(conn,a.operational_alert_ref,1).source_state_version)

def contribute(conn,a,v,scope='exact',actor=1):
    return memory.contribute_verdict(conn,a.operational_alert_ref,actor_id=actor,request=request(conn,a,v,scope))

@pytest.mark.parametrize('outcome',['suspicious','expected_activity','false_positive','confirmed_malicious'])
def test_canonical_mapping_provenance_no_source_side_effects(conn,outcome):
    a=alerts(conn,1)[0];v=verdict(conn,a,outcome)
    uid=db.insert(conn,m.User(username='contributor',password_hash='x',display_name='Contributor',email='c@example.test',role='security_analyst'));conn.commit()
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'triage_memory_%' AND name NOT LIKE 'verdict_memory_%'")]
    before={t:[tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in tables}
    result=contribute(conn,a,v,actor=uid).memory
    assert result.support_count==1 and result.status=='candidate' and result.decision is None
    e=memory.memory_history(conn,result.lesson.lesson_ref,50,0)[0][0].evidence
    assert e.outcome==v.outcome and e.human_reason==v.reason and e.source_verdict_ref==v.verdict_ref
    assert e.source_verdict_revision==v.revision and e.verdict_author_id==1 and e.actor_id==uid
    assert e.source_state_version==v.source_state_version and e.detector_snapshot.operational_alert_ref==a.operational_alert_ref
    assert {t:[tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in tables}==before

def test_support_distinct_alerts_retry_and_conflicts_across_scopes(conn):
    aa=alerts(conn);last=None
    for index,a in enumerate(aa[:3],1):
        v=verdict(conn,a);req=request(conn,a,v)
        last=memory.contribute_verdict(conn,a.operational_alert_ref,actor_id=1,request=req).memory
        assert last.support_count==index
        assert memory.contribute_verdict(conn,a.operational_alert_ref,actor_id=1,request=req).replayed
        with pytest.raises(memory.MemoryConflict):contribute(conn,a,v)
        with pytest.raises(memory.MemoryConflict):contribute(conn,a,v,'narrow')
        with pytest.raises(memory.MemoryConflict):memory.contribute_verdict(conn,a.operational_alert_ref,actor_id=1,request=req.model_copy(update={'scope':'narrow'}))
    assert last.status=='eligible_for_activation'
    active=memory.decide_memory(conn,last.lesson.lesson_ref,actor_id=1,action='activate',request=memory.MemoryDecisionRequest(request_id=uuid4(),expected_revision=last.revision,reason='Review three distinct human conclusions')).memory
    assert active.status=='active'
    contribute(conn,aa[3],verdict(conn,aa[3],'confirmed_malicious'),'narrow')
    conflict=memory.read_memory(conn,active.lesson.lesson_ref)
    assert conflict.conflict_count==1 and conflict.status=='conflict_review'
    assert not memory.explain_match(conflict,memory.context_for(aa[3])).guidance_active

def test_correction_invalidates_active_guidance_and_future_deferral_without_writes(conn):
    aa=review_scenario(conn);target=aa[0]
    before=memory.verdict_memory_state(conn,target.operational_alert_ref)
    lesson=memory.read_memory(conn,before.lesson_ref);old_revision=lesson.revision
    assert lesson.status=='active' and lesson.support_count==3
    assert read_review(conn,aa[3].operational_alert_ref).disposition=='no_immediate_review'
    v=verdict(conn,target,'confirmed_malicious')
    original_dump='\n'.join(conn.iterdump());conn.execute('PRAGMA query_only=ON')
    projected=memory.read_memory(conn,lesson.lesson.lesson_ref)
    assert projected.support_count==2 and projected.conflict_count==0 and projected.status=='candidate'
    assert projected.revision>old_revision
    assert memory.verdict_memory_state(conn,target.operational_alert_ref).contribution_status=='superseded'
    assert read_review(conn,aa[3].operational_alert_ref).disposition=='must_review'
    assert '\n'.join(conn.iterdump())==original_dump;conn.execute('PRAGMA query_only=OFF')
    replacement=contribute(conn,target,v).memory
    assert replacement.support_count==2 and replacement.conflict_count==1 and replacement.status=='conflict_review'
    assert verdict_history(conn,target.operational_alert_ref).total==2
    history=memory.memory_history(conn,replacement.lesson.lesson_ref,200,0)[0]
    old=[x for x in history if x.evidence and x.evidence.source_operational_alert_ref==target.operational_alert_ref and x.evidence.source_verdict_revision==1]
    new=[x for x in history if x.evidence and x.evidence.source_verdict_ref==v.verdict_ref]
    assert old and all(x.evidence_current is False for x in old)
    assert new and all(x.evidence_current is True for x in new)
    assert memory.verdict_memory_state(conn,target.operational_alert_ref).contribution_status=='contributed'

def test_http_no_verdict_tampering_roles_state_readonly_and_legacy_block(conn,api):
    a=alerts(conn,1)[0];ref=str(a.operational_alert_ref);url=f'/api/v2/alerts/{ref}/triage-memory/from-verdict'
    req={'requestId':str(uuid4()),'verdictRef':str(uuid4()),'expectedStateVersion':read_verdict(conn,a.operational_alert_ref,1).source_state_version,'scope':'exact'}
    assert api.post(url,json=req).status_code==409
    v=verdict(conn,a);req['verdictRef']=str(v.verdict_ref)
    for extra in [{'outcome':'confirmed_malicious'},{'reason':'alternate human reason'},{'actorId':999}]:
        assert api.post(url,json={**req,**extra}).status_code==400
    legacy={'requestId':str(uuid4()),'expectedStateVersion':req['expectedStateVersion'],'outcome':'confirmed_malicious','reason':'competing legacy conclusion','scope':'exact'}
    assert api.post(f'/api/v2/alerts/{ref}/triage-memory/candidate',json=legacy).status_code==409
    assert api.post(url,json=req).status_code==200
    assert api.post(url,json=req).json()['replayed']
    before='\n'.join(conn.iterdump());state=api.get(f'/api/v2/alerts/{ref}/triage-memory/verdict-state')
    assert state.json()['contributionStatus']=='contributed' and '\n'.join(conn.iterdump())==before
    from apps.api import auth
    uid=db.insert(conn,m.User(username='evaluator',password_hash='x',display_name='Evaluator',email='e@example.test',role='evaluator'));conn.commit()
    api.headers['Authorization']='Bearer '+auth.encode_token(db.get(conn,m.User,uid))
    assert api.get(f'/api/v2/alerts/{ref}/triage-memory/verdict-state').status_code==200
    assert api.post(url,json=req).status_code==403

def test_stale_verdict_and_tier2_no_fake_human_requirement(conn):
    aa=alerts(conn,1);a=aa[0];v=verdict(conn,a);old=request(conn,a,v)
    verdict(conn,a,'false_positive')
    with pytest.raises(memory.MemoryConflict):memory.contribute_verdict(conn,a.operational_alert_ref,actor_id=1,request=old)
    stage(conn,[event(999,'Opaque unresolved signal')]);unknown=admit_all(conn)[0]
    assert conn.execute('SELECT 1 FROM tier2_cases WHERE primary_operational_alert_id=?',(unknown.id,)).fetchone()
    assert memory.verdict_memory_state(conn,unknown.operational_alert_ref).latest_verdict_ref is None

def test_exact_positive_evidence_does_not_broaden_to_narrow_scope(conn):
    aa=alerts(conn)
    narrow=contribute(conn,aa[0],verdict(conn,aa[0]),'narrow').memory
    for a in aa[1:3]:contribute(conn,a,verdict(conn,a),'exact')
    assert memory.read_memory(conn,narrow.lesson.lesson_ref).support_count==1
    contribute(conn,aa[3],verdict(conn,aa[3],'confirmed_malicious'),'exact')
    assert memory.read_memory(conn,narrow.lesson.lesson_ref).conflict_count==1

def test_evidence_immutability_and_atomic_failure(conn):
    a=alerts(conn,1)[0];v=verdict(conn,a)
    before='\n'.join(conn.iterdump())
    conn.execute("CREATE TRIGGER fail_linked_evidence BEFORE INSERT ON verdict_memory_evidence BEGIN SELECT RAISE(ABORT,'injected'); END");conn.commit()
    failed='\n'.join(conn.iterdump())
    with pytest.raises(sqlite3.IntegrityError):contribute(conn,a,v)
    assert '\n'.join(conn.iterdump())==failed
    conn.execute('DROP TRIGGER fail_linked_evidence');conn.commit()
    assert '\n'.join(conn.iterdump())==before
    contribute(conn,a,v)
    for table in ['verdict_memory_evidence','verdict_memory_contributions']:
        for statement in [f'DELETE FROM {table}',f'UPDATE {table} SET id=id',f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}']:
            with pytest.raises(sqlite3.IntegrityError):conn.execute(statement)
            conn.rollback()

def test_migration_seventeen_preserves_verdicts_and_rolls_back(tmp_path,monkeypatch):
    migrations=db.MIGRATIONS
    c=db.connect(tmp_path/'migration.db')
    try:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:16]);db.create_schema(c)
        db.insert(c,m.User(username='reviewer',password_hash='x',display_name='Reviewer',email='r@example.test',role='security_analyst'));c.commit()
        a=alerts(c,1)[0];verdict(c,a)
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in tables};dump='\n'.join(c.iterdump())
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:16]+((17,'injected',migrations[16][2]+'\nSELECT * FROM missing_contribution_table;\n'),))
        with pytest.raises(sqlite3.OperationalError):db.migrate(c)
        assert '\n'.join(c.iterdump())==dump
        monkeypatch.setattr(db,'MIGRATIONS',migrations)
        assert db.migrate(c)==[17,18,19] and db.migrate(c)==[]
        assert {t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in tables}==before
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
    finally:c.close()
