"""Test-only real API, staged EVE prerequisites and deterministic clock; never demo.db.

The /__golden helpers exist only in this disposable harness. They cannot create
Verdicts, Memory, routing, Cases, responses or resolutions. All those use product UI/API.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import uvicorn
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db,models as m
from packages.detection.adapters.suricata_bundle import build_bundle,parse_record
from packages.detection.adapters.operational_v2 import read_projection
from packages.detection.context_store import seed_synthetic_facts
from packages.detection import triage_memory as memory
from pre_freeze_fixture import stage,safe_context

def build(path):
    manifest={};flow=970000
    template=json.loads((ROOT/'tests/fixtures/suricata-correlated.json').read_text())[:3]
    with closing(db.connect(path)) as c:
        db.create_schema(c);auth.ensure_demo_accounts(c)
        for group,names,title in [
            ('routine',list('ABCDEF'),'SYNTHETIC Golden routine SSH brute force'),
            ('authority',['I1','I2','I3'],'SYNTHETIC Golden authority SSH brute force'),
            ('aging',['T1','T2','T3','T4','T5'],'SYNTHETIC Golden aging SSH brute force'),
            ('unknown',['U'],'SYNTHETIC Golden opaque anomalous activity')]:
            for name in names:
                while True:
                    flow+=1;records=deepcopy(template if group!='unknown' else template[:2])
                    for r in records:
                        r['flow_id']=flow;r['timestamp']=datetime.now(timezone.utc).isoformat()
                        r['src_ip']='192.0.2.'+str({'routine':10,'authority':11,'aging':12,'unknown':13}[group])
                        r['dest_ip']='198.51.100.'+str({'routine':20,'authority':21,'aging':22,'unknown':23}[group])
                    records[0]['alert'].update(signature=title,severity=1,signature_id=970001)
                    if group=='aging':records[0]['alert']['category']='SYNTHETIC authorized scanner audit'
                    if group!='unknown':
                        extra=deepcopy(records[0]);extra['alert']['signature_id']=970002;records.append(extra)
                    bundle=build_bundle([parse_record(r,'golden-sensor','golden-'+group) for r in records])
                    if int(sha256(str(bundle.canonical_alert_id).encode()).hexdigest()[:8],16)%100>=10:break
                stage(c,records,'golden-'+group,'golden-sensor')
                inbox=c.execute('SELECT id FROM external_alert_inbox WHERE canonical_alert_id=?',(str(bundle.canonical_alert_id),)).fetchone()[0]
                manifest[name]={'inboxId':inbox,'canonicalAlertId':str(bundle.canonical_alert_id),'flowId':flow,'captureScope':'golden-'+group,'recordCount':len(records)}
        for table in ('operational_alerts_v2','tier2_cases','analyst_verdict_events','triage_memory_lessons'):
            assert c.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM prospective_runs').fetchone()[0]==0
    return manifest

def serve(path,manifest):
    app=create_app(path);offset=timedelta()
    m.utc_now=lambda:datetime.now(timezone.utc)+offset
    @app.get('/__golden/manifest')
    def read_manifest():return manifest
    @app.post('/__golden/clock')
    def clock(body:dict):
        nonlocal offset
        target=datetime.fromisoformat(body['at'].replace('Z','+00:00'))
        assert target>=m.utc_now()
        offset=target-datetime.now(timezone.utc)
        return {'now':m.utc_now().isoformat()}
    @app.post('/__golden/context/{ref}')
    def context(ref:str,body:dict):
        with closing(db.connect(path)) as c:
            row=c.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?',(ref,)).fetchone()
            alert=read_projection(c,row[0]);assert alert.detection_title.startswith('SYNTHETIC Golden')
            values=safe_context().model_copy(update=body.get('changes',{}))
            seed_synthetic_facts(c,alert,values,m.utc_now()-timedelta(hours=5) if body.get('stale') else m.utc_now())
        return {'syntheticPrerequisite':True}
    @app.get('/__golden/proof')
    def proof():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
            c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
            votes={r['lesson_ref']:[{'alertRef':str(e.source_operational_alert_ref),'sourceKind':e.source_kind,'outcome':e.outcome,'actorId':e.actor_id,'authorId':e.source_conclusion.actor_id if e.source_conclusion else e.verdict_author_id} for e in memory.effective_evidence(c,r['id'])[0]] for r in c.execute('SELECT id,lesson_ref FROM triage_memory_lessons')}
            return {'digest':sha256('\n'.join(c.iterdump()).encode()).hexdigest(),'votes':votes,
                'collectionRuns':c.execute('SELECT count(*) FROM prospective_runs').fetchone()[0],
                'foreignKeys':len(c.execute('PRAGMA foreign_key_check').fetchall())}
    uvicorn.run(app,host='127.0.0.1',port=8030,log_level='warning')

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='hitl-final-golden-') as directory:
        path=Path(directory)/'golden.db';serve(path,build(path))
