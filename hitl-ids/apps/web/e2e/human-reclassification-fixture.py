"""Disposable real API with an additional independent known-category correction case."""
from pathlib import Path
import runpy
import tempfile
base=runpy.run_path(str(Path(__file__).with_name('pre-freeze-fixture.py')))
from pre_freeze_fixture import event,stage,admit_all
from packages.contracts import db
from apps.api.main import create_app
import uvicorn

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='hitl-human-classification-') as directory:
        path=Path(directory)/'conclusions.db';base['build_fixture'](path)
        with db.connect(path) as conn:
            actor=conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
            stage(conn,[event(44000,'SYNTHETIC reclassification known brute force',severity=1)],scope='human-classification-browser')
            admit_all(conn,actor)
            assert conn.execute('SELECT count(*) FROM prospective_runs').fetchone()[0]==0
        uvicorn.run(create_app(path),host='127.0.0.1',port=8020,log_level='warning')
