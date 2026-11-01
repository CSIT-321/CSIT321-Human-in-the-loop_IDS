"""Authenticated human conclusions: corrections, retries, guards and isolation."""
from uuid import uuid4
import json
import sqlite3
import pytest
from pydantic import ValidationError
from test_pre_freeze_review_fixes import conn,api
from pre_freeze_fixture import event,stage,admit_all,review_scenario
from packages.contracts import db,models as m
from packages.detection.analyst_verdict import *
from packages.detection.selective_review import read_review

def alert(conn,signature='SSH brute force',category='Misc activity'):
    stage(conn,[event(signature=signature,category=category)])
    return admit_all(conn)[0]

def command(conn,a,outcome='suspicious',**changes):
    view=read_verdict(conn,a.operational_alert_ref,1)
    return VerdictCommand(request_id=uuid4(),expected_revision=view.revision,expected_state_version=view.source_state_version,
        outcome=outcome,reason='Independent analyst conclusion',**changes)

def unchanged(conn):
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='analyst_verdict_events' AND name NOT LIKE 'triage_memory_%' AND name NOT LIKE 'verdict_memory_%'")]
    return {t:[tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in tables}

@pytest.mark.parametrize('outcome',['confirmed_malicious','suspicious','expected_activity','false_positive'])
def test_outcomes_no_operational_side_effects(conn,outcome):
    a=alert(conn);before=unchanged(conn);review=read_review(conn,a.operational_alert_ref)
    result=record_verdict(conn,a.operational_alert_ref,actor_id=1,request=command(conn,a,outcome))
    assert result.verdict.outcome==outcome and result.verdict.actor_id==1
    assert result.verdict.evidence_snapshot['classification']['attackCategory']=='brute_force'
    assert result.verdict.source_state_version and result.verdict.created_at
    assert unchanged(conn)==before
    current=read_review(conn,a.operational_alert_ref)
    assert current.version!=review.version and current.disposition=="must_review"
    assert current.policy_evaluation.inputs.human_verdict_present
    assert current.policy_evaluation.inputs.canonical_verdict.verdict_ref==result.verdict.verdict_ref

def test_correction_retry_stale_conflicts_and_append_only(conn):
    a=alert(conn);ref=a.operational_alert_ref;first=command(conn,a)
    one=record_verdict(conn,ref,actor_id=1,request=first)
    two=record_verdict(conn,ref,actor_id=1,request=command(conn,a,'false_positive'))
    assert two.verdict.supersedes_ref==one.verdict.verdict_ref
    assert read_verdict(conn,ref,1).latest==two.verdict
    assert [v.outcome for v in verdict_history(conn,ref).items]==['false_positive','suspicious']
    assert record_verdict(conn,ref,actor_id=1,request=first).replayed
    assert verdict_history(conn,ref).total==2
    with pytest.raises(VerdictConflict):record_verdict(conn,ref,actor_id=1,request=first.model_copy(update={'reason':'different'}))
    with pytest.raises(VerdictConflict):record_verdict(conn,ref,actor_id=1,request=first.model_copy(update={'request_id':uuid4()}))
    for sql in ['UPDATE analyst_verdict_events SET revision=revision','DELETE FROM analyst_verdict_events','INSERT OR REPLACE INTO analyst_verdict_events SELECT * FROM analyst_verdict_events']:
        with pytest.raises(sqlite3.IntegrityError):conn.execute(sql)
        conn.rollback()

@pytest.mark.parametrize('reason',['',' ','\n'])
def test_nonblank_reason(conn,reason):
    a=alert(conn)
    with pytest.raises(ValidationError):VerdictCommand.model_validate({**command(conn,a).model_dump(),'reason':reason})

def test_informational_no_review_and_auto_tier2(conn):
    a=alert(conn,'Policy notice')
    assert record_verdict(conn,a.operational_alert_ref,actor_id=1,request=command(conn,a,'expected_activity')).verdict.outcome=='expected_activity'
    stage(conn,[event(2,'Unresolved opaque protocol','Misc activity')]);unknown=admit_all(conn)[0]
    assert conn.execute('SELECT 1 FROM tier2_cases WHERE primary_operational_alert_id=?',(unknown.id,)).fetchone()
    assert not read_verdict(conn,unknown.operational_alert_ref,1).can_record
    with pytest.raises(VerdictConflict):record_verdict(conn,unknown.operational_alert_ref,actor_id=1,request=command(conn,unknown))

def test_deferred_alert_verdict_recalls_attention_without_memory(conn):
    alerts=review_scenario(conn);a=alerts[3];before=read_review(conn,a.operational_alert_ref)
    assert before.disposition=='no_immediate_review'
    record_verdict(conn,a.operational_alert_ref,actor_id=1,request=command(conn,a,'expected_activity'))
    current=read_review(conn,a.operational_alert_ref)
    assert current.version!=before.version and current.disposition=="must_review" and current.recalled
    assert current.policy_evaluation.inputs.human_verdict_present

def test_http_roles_payload_identity_readonly_and_manual_escalation(conn,api):
    a=alert(conn);ref=str(a.operational_alert_ref);url=f'/api/v2/alerts/{ref}/verdict'
    body=command(conn,a).model_dump(mode='json',by_alias=True)
    before='\n'.join(conn.iterdump());assert api.get(url).json()['latest'] is None
    assert api.get(f'/api/v2/alerts/{ref}/verdict-history').json()['total']==0
    assert '\n'.join(conn.iterdump())==before
    for extra in [{'actorId':999},{'decisionSource':'system_policy'}]:
        assert api.post(url,json={**body,**extra}).status_code==400
    saved=api.post(url,json=body);assert saved.status_code==200,saved.text
    assert api.post(url,json=body).json()['replayed']
    for role,allowed in [('evaluator',False),('system_admin',True),('security_analyst',True)]:
        uid=db.insert(conn,m.User(username=role,password_hash='x',display_name=role,email=role+'@example.test',role=role));conn.commit()
        from apps.api import auth
        api.headers['Authorization']='Bearer '+auth.encode_token(db.get(conn,m.User,uid))
        assert api.get(url).status_code==200
        assert api.get(url).json()['canRecord'] is allowed
        # Same key cannot be borrowed by another authorized actor either.
        assert api.post(url,json=body).status_code==(409 if allowed else 403)
        if allowed:
            authorized=api.post(url,json=command(conn,a).model_dump(mode='json',by_alias=True))
            assert authorized.status_code==200 and authorized.json()['verdict']['actorId']==uid
    api.headers['Authorization']='Bearer '+auth.encode_token(db.get(conn,m.User,1))
    state=api.get(f'/api/v2/alerts/{ref}/triage-state').json()
    result=api.post(f'/api/v2/alerts/{ref}/tier2/escalate-case',json={'requestId':str(uuid4()),'expectedStateVersion':state['stateVersion'],'reason':'Explicit manual escalation'})
    assert result.status_code==200 and result.json()['view']['state']['handlingRoute']=='tier2_case'
    assert api.get(url).json()['latest']['outcome']=='suspicious' and not api.get(url).json()['canRecord']
    assert api.post(url,json=command(conn,a).model_dump(mode='json',by_alias=True)).status_code==409
    api.headers.pop('Authorization');assert api.post(url,json=body).status_code==401

def test_invalid_actor_stale_workflow_missing_and_inactive(conn):
    a=alert(conn);req=command(conn,a)
    for actor in [None,999]:
        with pytest.raises(PermissionError):record_verdict(conn,a.operational_alert_ref,actor_id=actor,request=req)
    with pytest.raises(VerdictConflict):record_verdict(conn,a.operational_alert_ref,actor_id=1,request=req.model_copy(update={'expected_state_version':'0'*64}))
    with pytest.raises(LookupError):record_verdict(conn,uuid4(),actor_id=1,request=req)
    conn.execute("UPDATE users SET status='inactive' WHERE id=1");conn.commit()
    with pytest.raises(PermissionError):record_verdict(conn,a.operational_alert_ref,actor_id=1,request=req)

def test_migration_sixteen_preserves_previous_data_and_rolls_back(tmp_path,monkeypatch):
    migrations=db.MIGRATIONS[:16]
    c=db.connect(tmp_path/'migration.db')
    try:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:15]);db.create_schema(c)
        db.insert(c,m.User(username='reviewer',password_hash='x',display_name='Reviewer',email='r@example.test',role='security_analyst'));c.commit()
        alert(c);before='\n'.join(c.iterdump());rows=unchanged(c)
        broken=migrations[:15]+((16,'injected',migrations[15][2]+'\nSELECT * FROM missing_verdict_migration;\n'),)
        monkeypatch.setattr(db,'MIGRATIONS',broken)
        with pytest.raises(sqlite3.OperationalError):db.migrate(c)
        assert '\n'.join(c.iterdump())==before
        monkeypatch.setattr(db,'MIGRATIONS',migrations)
        assert db.migrate(c)==[16] and db.migrate(c)==[]
        assert unchanged(c)==rows and not c.execute('PRAGMA foreign_key_check').fetchall()
    finally:c.close()
