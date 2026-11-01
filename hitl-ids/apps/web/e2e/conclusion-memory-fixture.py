"""Real disposable expert learning + existing active-memory safety scenarios."""
from pathlib import Path
import runpy
import tempfile
base=runpy.run_path(str(Path(__file__).with_name('pre-freeze-fixture.py')))
from pre_freeze_fixture import event,stage,admit_all
from packages.contracts import db
from apps.api.main import create_app
import uvicorn

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='hitl-expert-memory-') as directory:
        path=Path(directory)/'expert.db';base['build_fixture'](path)
        with db.connect(path) as conn:
            actor=conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
            stage(conn,[event(55000+i,'SYNTHETIC expert learning brute force',severity=1) for i in range(3)],scope='expert-learning-browser')
            admit_all(conn,actor)
            assert conn.execute('SELECT count(*) FROM prospective_runs').fetchone()[0]==0
        uvicorn.run(create_app(path),host='127.0.0.1',port=8022,log_level='warning')
