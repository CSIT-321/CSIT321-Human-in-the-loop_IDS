"""Disposable real API; only prerequisites are seeded, never claims or Verdicts."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import os
import sys
import sqlite3
import tempfile
from threading import Barrier,Lock

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import uvicorn
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db,models as m
from pre_freeze_fixture import stage,event,admit_all
from packages.detection import analyst_work

def serve(path):
    with closing(db.connect(path)) as c:
        db.create_schema(c)
        for name,role in [('alice','security_analyst'),('bob','security_analyst'),('carol','security_analyst'),('observer','evaluator')]:
            db.insert(c,m.User(username=name,display_name=name.title(),password_hash=auth.hash_password('work-demo'),email=name+'@example.test',role=role))
        c.commit();auth.ensure_demo_accounts(c)
        stage(c,[event(i,'SYNTHETIC shared SSH brute force') for i in range(1,6)]+[event(100,'SYNTHETIC opaque unknown anomaly')])
        alerts=admit_all(c)
        manifest={str(i+1):str(a.operational_alert_ref) for i,a in enumerate(alerts)}
    app=create_app(path)
    # Deterministic scheduling only: both real HTTP handlers enter registration
    # together, then both real committed intents precede finalization. No outcome,
    # ownership, clock, policy or database write is mocked by this harness.
    entering=Barrier(2);registered=Barrier(2);lock=Lock();participants=0
    original_register=analyst_work.register
    def synchronized_register(conn,ref,actor_id,request):
        nonlocal participants
        with lock:
            contend=str(ref)==manifest['2'] and participants<2
            if contend:participants+=1
        if contend:entering.wait(timeout=10)
        result=original_register(conn,ref,actor_id,request)
        if contend:registered.wait(timeout=10)
        return result
    analyst_work.register=synchronized_register
    @app.get('/__work/manifest')
    def read_manifest():return manifest
    @app.get('/__work/proof')
    def proof():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
            c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
            return {'digest':sha256('\n'.join(c.iterdump()).encode()).hexdigest(),
                'work':[dict(r) for r in c.execute('SELECT * FROM analyst_work')],
                'rounds':[dict(r) for r in c.execute('SELECT * FROM analyst_claim_rounds')],
                'intents':[dict(r) for r in c.execute('SELECT actor_id,round_ref FROM analyst_claim_intents')],
                'events':[dict(r) for r in c.execute('SELECT * FROM analyst_work_events')],
                'verdicts':c.execute('SELECT count(*) FROM analyst_verdict_events').fetchone()[0],
                'memoryEvidence':c.execute('SELECT count(*) FROM verdict_memory_contributions').fetchone()[0],
                'cases':c.execute('SELECT count(*) FROM tier2_cases').fetchone()[0],
                'collectionRuns':c.execute('SELECT count(*) FROM prospective_runs').fetchone()[0],
                'foreignKeys':len(c.execute('PRAGMA foreign_key_check').fetchall())}
    uvicorn.run(app,host='127.0.0.1',port=int(os.environ.get("HITL_WORK_API_PORT", "8032")),log_level='warning')

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='hitl-shared-work-') as directory:
        serve(Path(directory)/'shared.db')
