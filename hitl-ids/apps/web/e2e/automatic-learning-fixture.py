"""Disposable real API for automatic learning; no demo DB or collection."""
import argparse
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import uvicorn
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db,models as m
from packages.detection.adapters.suricata_bundle import build_bundle,parse_record
from packages.detection.context_store import seed_synthetic_facts
from pre_freeze_fixture import stage,event,admit_all,safe_context
from packages.detection.analyst_verdict import read_verdict,record_verdict,VerdictCommand

def build(path):
    with closing(db.connect(path)) as c:
        db.create_schema(c);auth.ensure_demo_accounts(c)
        actor=c.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        rows=[];flow=950000
        while len(rows)<6:
            raw=event(flow,'SYNTHETIC automatic learning SSH scan',severity=1);flow+=1
            ref=build_bundle([parse_record(raw,'review-sensor','auto-learning')]).canonical_alert_id
            if int(sha256(str(ref).encode()).hexdigest()[:8],16)%100<10:continue
            rows.append(raw)
        stage(c,rows,'auto-learning')
        for alert in admit_all(c,actor):seed_synthetic_facts(c,alert,safe_context(),m.utc_now())
        assert c.execute('SELECT count(*) FROM triage_memory_lessons').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM prospective_runs').fetchone()[0]==0
        # Historical clock fixture, through real commands: active at T, expired at T+31.
        stage(c,[event(960000+i,'SYNTHETIC expired learning SSH scan',severity=1) for i in range(4)],'expired-learning')
        expired=admit_all(c,actor);now=m.utc_now()
        with patch.object(m,'utc_now',return_value=now-timedelta(days=31)):
            for alert in expired[:3]:
                view=read_verdict(c,alert.operational_alert_ref,actor)
                record_verdict(c,alert.operational_alert_ref,actor_id=actor,request=VerdictCommand(
                    request_id=uuid4(),expected_revision=0,expected_state_version=view.source_state_version,
                    outcome='expected_activity',reason='SYNTHETIC historical authorized activity'))
        for alert in expired:seed_synthetic_facts(c,alert,safe_context(),now)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8025);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hitl-auto-learning-') as directory:
        path=Path(directory)/'learning.db';build(path)
        uvicorn.run(create_app(path),host='127.0.0.1',port=args.port,log_level='warning')
