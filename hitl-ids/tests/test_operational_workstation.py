"""The workstation evidence projection is authenticated, immutable and source-neutral."""
from contextlib import closing
from uuid import uuid4

from packages.contracts import db
from packages.detection.adapters.operational_v2 import materialize_source, read_projection
from test_routing_workflow import client, database, staged


def test_evidence_read_is_immutable_and_matches_materialized_source(client, database, staged):
    ref = staged[0].operational_alert_ref
    with closing(db.connect(database)) as conn:
        expected = read_projection(conn, staged[0].id).model_dump(mode='json', by_alias=True)
        before = '\n'.join(conn.iterdump())
    for account in ('g.ang', 'admin', 'evaluator'):
        response = client.get(f'/api/v2/alerts/{ref}/evidence',
            headers={'Authorization': f'Bearer {client.tokens[account]}'})
        assert response.status_code == 200, response.text
        assert response.json() == expected
    assert client.get('/api/v2/alerts').json()['items'][0]['detectorSource'] == 'suricata'
    with closing(db.connect(database)) as conn:
        assert '\n'.join(conn.iterdump()) == before


def test_legacy_canonical_evidence_does_not_require_legacy_alert_api(client, database):
    with closing(db.connect(database)) as conn:
        alert = materialize_source(conn, 'legacy_flow_alert', 1)
    result = client.get(f'/api/v2/alerts/{alert.operational_alert_ref}/evidence')
    assert result.status_code == 200
    assert result.json()['detectorEvidence']['detectorSource'] == 'current_flow'
    assert result.json()['sourceKind'] == 'legacy_flow_alert'


def test_evidence_authentication_and_missing_alert(client, staged):
    path = f'/api/v2/alerts/{staged[0].operational_alert_ref}/evidence'
    assert client.get(path, headers={'Authorization': ''}).status_code == 401
    assert client.get(f'/api/v2/alerts/{uuid4()}/evidence').status_code == 404
