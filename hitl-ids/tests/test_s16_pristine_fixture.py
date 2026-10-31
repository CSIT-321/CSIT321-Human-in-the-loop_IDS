"""The legacy narrative needs a pristine gate, not a reset of legitimate demo history."""
from contextlib import closing
import sqlite3

import pytest
from scripts.serve_s16_rehearsal import build_pristine_fixture
from packages.contracts import db
from packages.contracts import models as m
from packages.detection.pipeline.store import detector_for_alert, flow_for_alert


def test_pristine_fixture_deterministic_without_source_access(tmp_path,monkeypatch):
    original=sqlite3.connect
    def isolated(path,*args,**kwargs):
        assert 'demo.db' not in str(path)
        assert str(tmp_path) in str(path)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',isolated)
    first=build_pristine_fixture(tmp_path/'first.db')
    second=build_pristine_fixture(tmp_path/'second.db')
    with closing(db.connect(first)) as a,closing(db.connect(second)) as b:
        for table in ('alerts','flow_data','datasets','detection_runs'):
            assert list(map(tuple,a.execute(f'SELECT * FROM {table} ORDER BY id')))==list(map(tuple,b.execute(f'SELECT * FROM {table} ORDER BY id')))
        assert a.execute('SELECT count(*) FROM alerts').fetchone()[0]==5000
        assert a.execute('SELECT count(*) FROM alerts WHERE family_key IS NOT NULL').fetchone()[0]==5
        for table in ('feedback_events','audit_log','alert_families','prospective_runs'):
            assert a.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0
        assert a.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        for number in (478,3086,1696,3873,3153,3044,4526):
            alert=db.get(a,m.Alert,number)
            assert detector_for_alert(a,alert,flow_for_alert(a,number)) is not None
    with pytest.raises(FileExistsError): build_pristine_fixture(first)
