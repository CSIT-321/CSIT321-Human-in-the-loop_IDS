"""Disposable real API for the focused V3 boundary browser journey."""
import runpy
from pathlib import Path
import sys
import tempfile

base=runpy.run_path(str(Path(__file__).with_name('pre-freeze-fixture.py')))
from pre_freeze_fixture import event,stage,admit_all
from packages.contracts import db
from apps.api.main import create_app
import uvicorn

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='hitl-f2-boundary-') as directory:
        path=Path(directory)/'boundary.db';base['build_fixture'](path)
        with db.connect(path) as conn:
            actor=conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
            pairs=[('ET POLICY Possible ransomware communication','Misc activity'),
                   ('ET POLICY Credential harvesting detected','Potential Corporate Privacy Violation'),
                   ('ET POLICY Unauthorized remote access detected','Misc activity'),
                   ('ET POLICY Opaque channel rendezvous','Misc activity'),
                   ('ET POLICY SQL injection','Misc activity')]
            stage(conn,[event(20000+i,*pair,severity=4) for i,pair in enumerate(pairs)],scope='f2-browser')
            admit_all(conn,actor)
            assert conn.execute('SELECT count(*) FROM prospective_runs').fetchone()[0]==0
        uvicorn.run(create_app(path),host='127.0.0.1',port=8016,log_level='warning')
