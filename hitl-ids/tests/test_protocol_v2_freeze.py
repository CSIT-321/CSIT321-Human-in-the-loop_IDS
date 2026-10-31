"""Freeze checks use temporary config copies or isolated service fixtures only."""
from contextlib import closing
from datetime import timedelta
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from scripts import check_protocol_v2_freeze as f
from packages.contracts import db
from packages.detection import prospective_collection as c
from test_api import client, database
from test_selective_review import alerts
from test_prospective_collection import collection

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def frozen(tmp_path):
    (tmp_path/'config').mkdir()
    for name in f.CONFIGS | {Path(f.PROTOCOL).name, Path(f.MANIFEST).name}:
        shutil.copyfile(ROOT/'config'/name, tmp_path/'config'/name)
    return tmp_path


def test_valid_protocol_and_reproducible_hashes(frozen):
    p = f.validate_artifacts(frozen, frozen)
    assert p['minimumEligibleAlerts'] == 100 and p['minimumOutcomeCompleteness'] == .95
    assert f.digest(p) == f.digest(json.loads(json.dumps(p, indent=4))) == f.PROTOCOL_SHA
    assert f.stamp(p['registeredAt']) < f.stamp(p['holdoutStart'])
    assert p['participantClass'] == 'proxy_student_analyst'
    assert p['evaluationMode'] == 'prospective_recorded'
    assert set(p['metrics']) == f.METRICS
    assert p['collectionOpened'] is False
    assert f.digest(f.read(frozen/'config/prospective-context-protocol-v1.json')) == (
        '931e91df5ec4bc723b8332e1f7c2324c7d83497d1fd17af0bdcff5e63c8356de')


@pytest.mark.parametrize('name', sorted(f.CONFIGS))
def test_any_configuration_change_rejected(frozen, name):
    path = frozen/'config'/name
    value = f.read(path)
    value['unexpectedConfigurationChange'] = True
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='hash mismatch'):
        f.validate_artifacts(frozen, frozen)


@pytest.mark.parametrize('field,value', [
    ('reviewedCodeSha','0'*40), ('evaluationMode','temporal_replay'),
    ('holdoutStart','2020-01-01T00:00:00Z'), ('holdoutEnd','2030-01-01T00:00:00Z'),
    ('participantClass','professional_analyst'), ('collectionOpened',True),
    ('minimumEligibleAlerts',1), ('metrics',{}),
])
def test_immutable_protocol_cannot_be_redefined(frozen, field, value):
    path = frozen/f.PROTOCOL
    p = f.read(path)
    p[field] = value
    path.write_text(json.dumps(p))
    with pytest.raises(ValueError, match='protocol hash mismatch'):
        f.validate_artifacts(frozen, frozen)


def test_manifest_omission_rejected(frozen):
    path = frozen/f.MANIFEST
    m = f.read(path)
    m['configs'].pop()
    path.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='inventory'):
        f.validate_artifacts(frozen, frozen)


@pytest.mark.parametrize('head,dirty,valid', [(f.SOURCE_SHA,'',True),('0'*40,'',False),
                                           (f.SOURCE_SHA,' M config/selective-review-v1.json',False)])
def test_runtime_must_be_exact_clean_reviewed_source(monkeypatch, head, dirty, valid):
    def git(source, *args):
        if args == ('rev-parse','--show-toplevel'): return ROOT.parent.as_posix()
        if args == ('rev-parse','HEAD'): return head
        if args[0] == 'status': return dirty
        raise AssertionError(args)
    monkeypatch.setattr(f, 'git', git)
    if valid: f.validate_source(ROOT)
    else:
        with pytest.raises(ValueError): f.validate_source(ROOT)


def test_new_run_stays_draft_until_explicit_open(collection):
    path, items, admin, old, clock = collection
    request = old.protocol.registration.model_copy(update={
        'request_id':uuid4(), 'protocol_version':'isolated-freeze-gate-test',
        'holdout_start':clock[0]+timedelta(days=1),
        'holdout_end':clock[0]+timedelta(days=2),
        'outcome_cutoff':clock[0]+timedelta(days=3)})
    with closing(db.connect(path)) as conn:
        run = c.create_run(conn, admin, request)
        assert run.status == 'draft' and run.opened_at is None and run.decision_count == 0
        assert not conn.execute(
            'SELECT 1 FROM prospective_run_events e JOIN prospective_runs r ON r.id=e.run_id WHERE r.run_ref=?',
            (str(run.run_ref),)).fetchall()
