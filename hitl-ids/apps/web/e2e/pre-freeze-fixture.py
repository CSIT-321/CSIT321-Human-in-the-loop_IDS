"""Real API with disposable synthetic remediation scenarios; never uses demo.db."""
import argparse
from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

HITL=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(HITL),str(HITL/'tests')]
import uvicorn
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection.context_store import collect_fact, FactRequest
from pre_freeze_fixture import event, stage, admit_all, review_scenario


def build_fixture(path):
    with closing(db.connect(path)) as conn:
        db.create_schema(conn);auth.ensure_demo_accounts(conn)
        actor=conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        review_scenario(conn,actor)
        now=m.utc_now()
        collect_fact(conn,actor_id=actor,request=FactRequest(request_id=uuid4(),expected_revision=conn.execute('SELECT max(id) FROM trusted_context_facts').fetchone()[0],
            subject_type='ip',subject_value='198.51.100.99',context_key='assetCriticality',value='critical',
            observed_at=now-timedelta(seconds=1),valid_from=now-timedelta(minutes=1),expires_at=now+timedelta(hours=12),
            reason='SYNTHETIC critical asset',source_reference='synthetic:critical-asset'))
        events=[event(9001,'SYNTHETIC Known routine brute force',severity=1)]
        events += [event(9100+i,'Informational notice: software version','Misc activity',4) for i in range(53)]
        events += [event(9200+i,f'SYNTHETIC Unresolved suspicious network activity {i}','Misc activity',4) for i in range(3)]
        events += [event(9300,'SYNTHETIC DDoS detected','Attempted Denial of Service',1),event(9301,'SYNTHETIC DDoS conflicting evidence','Web Application Attack',2)]
        critical=event(9400,'SYNTHETIC critical SQL injection',severity=1);critical['dest_ip']='198.51.100.99';events.append(critical)
        stage(conn,events,scope='browser-signals');admit_all(conn,actor)
        for scope in ('capture-one','capture-two'):
            stage(conn,[event(7777,'SYNTHETIC Capture-isolated port scan')],scope=scope);admit_all(conn,actor)
        assert conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0]==68
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0]==5
        assert conn.execute('SELECT count(*) FROM prospective_runs').fetchone()[0]==0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8014);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hitl-pre-freeze-') as directory:
        path=Path(directory)/'review.db';build_fixture(path)
        print(f'Disposable synthetic remediation database: {path}',flush=True)
        uvicorn.run(create_app(path),host='127.0.0.1',port=args.port,log_level='warning')
