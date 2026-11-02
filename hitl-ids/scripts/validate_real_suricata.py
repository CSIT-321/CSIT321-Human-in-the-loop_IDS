"""Validate actual external EVE through existing product code in a fresh disposable DB.

Never generates EVE, changes detection policies, or opens a baseline database.
The input directory must contain actual Suricata outputs and source PCAPs.
"""
import argparse
from collections import Counter
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apps.api import auth
from packages.contracts import db
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.suricata_bundle import SUPPORTED, canonical_json
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.external_admission import review_eligibility, admit_external, EligibilityRequest, AdmissionRequest

SENSOR = 'suricata-offline-validation-01'
CAPTURES = [
    ('slammer', 'slammer.pcap', 'https://wiki.wireshark.org/uploads/__moin_import__/attachments/SampleCaptures/slammer.pcap'),
    ('http', 'http.cap', 'https://wiki.wireshark.org/uploads/27707187aeb30df68e70c8fb9d614981/http.cap'),
    ('attack', 'attack-pcap/2024-11-26-traffic-analysis-exercise.pcap', 'https://www.malware-traffic-analysis.net/2024/11/26/index.html'),
]

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def counts(c):
    return {t: c.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in
            ('suricata_eve_records', 'external_alert_inbox', 'operational_alerts_v2', 'tier2_cases', 'prospective_runs')}

def raw_digest(c):
    return sha256(canonical_json([tuple(r) for r in c.execute(
        'SELECT sensor_id,capture_scope,source_record_ref,raw_snapshot FROM suricata_eve_records ORDER BY id')]).encode()).hexdigest()

def build(folder):
    path = folder / 'real-validation.db'
    if path.exists():
        raise ValueError('Refusing to overwrite a database; use a fresh validation directory')
    result = {'sensorId': SENSOR, 'captures': [], 'sourceBoundary': 'actual Suricata offline output; external scenario labels never imported'}
    with closing(db.connect(path)) as c:
        db.create_schema(c)
        auth.ensure_demo_accounts(c)
        actor = c.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        result['initialCounts'] = counts(c)
        assert not any(result['initialCounts'].values())
        for name, filename, url in CAPTURES:
            pcap, eve = folder / filename, folder / (name + '-output') / 'eve.json'
            rows = [json.loads(line) for line in eve.read_text(encoding='utf-8').splitlines() if line.strip()]
            scope = 'pcap-sha256:' + digest(pcap)
            report = stage_file(c, eve, SENSOR, capture_scope=scope).as_dict()
            assert report['invalid'] == report['rejected_by_policy'] == 0, report
            expected = {canonical_json(r) for r in rows if r['event_type'] in SUPPORTED}
            saved = {r[0] for r in c.execute('SELECT raw_snapshot FROM suricata_eve_records WHERE capture_scope=?', (scope,))}
            assert saved == expected, 'raw evidence lost or invented'
            bundles = []
            for row in c.execute('SELECT id,canonical_snapshot FROM external_alert_inbox ORDER BY id').fetchall():
                canonical = json.loads(row['canonical_snapshot'])
                if canonical['provenance']['captureScope'] != scope:
                    continue
                bundle = canonical['structuredEvidence']['suricataBundle']
                original = [r for r in rows if 'flow_id' in r and str(r['flow_id']) == bundle['flowId'] and r['event_type'] in SUPPORTED]
                assert {canonical_json(r['raw']) for r in bundle['records']} == {canonical_json(r) for r in original}
                assert len(bundle['relatedSignatures']) == sum(r['event_type'] == 'alert' for r in original)
                assert canonical['confidence'] is None
                review = review_eligibility(c, row['id'], actor_id=actor, request=EligibilityRequest(
                    request_id=uuid4(), expected_review_id=None, decision='accepted', reason='Disposable integration validation: actual EVE provenance and correlation verified'))
                admit_external(c, row['id'], actor_id=actor, request=AdmissionRequest(
                    request_id=uuid4(), expected_review_id=review['id'], reason='Offline real-PCAP integration validation; no dataset label supplied'))
                bundles.append({'inboxId': row['id'], 'alertRef': canonical['canonicalAlertId'], 'flowId': bundle['flowId'],
                    'signatureIds': [s['signatureId'] for s in bundle['relatedSignatures']],
                    'signatures': bundle['relatedSignatures'], 'recordCount': len(bundle['records']),
                    'evidenceTypes': bundle['evidenceTypes'], 'transactionCount': len(bundle['transactionRecords']),
                    'primaryRecordRef': bundle['primaryRecordRef'], 'timestamp': canonical['occurredAt'],
                    'sourceIp': canonical['sourceIp'], 'destinationIp': canonical['destinationIp'],
                    'sourcePort': canonical['sourcePort'], 'destinationPort': canonical['destinationPort'],
                    'protocol': canonical['protocol'], 'nativeCategory': canonical['detectionCategory'],
                    'nativeSeverity': canonical['detectorSeverity']})
            before = counts(c)
            repeat = stage_file(c, eve, SENSOR, capture_scope=scope).as_dict()
            after = counts(c)
            assert before == after and repeat['staged'] == repeat['preserved'] == 0
            result['captures'].append({'name': name, 'filename': filename, 'sourceReference': url,
                'pcapBytes': pcap.stat().st_size, 'pcapSha256': digest(pcap), 'eveSha256': digest(eve),
                'captureScope': scope, 'inputEvents': len(rows), 'eventTypes': dict(Counter(r['event_type'] for r in rows)),
                'uniqueFlowIds': len({r['flow_id'] for r in rows if 'flow_id' in r}),
                'uniqueSignatures': sorted({r['alert']['signature_id'] for r in rows if r['event_type'] == 'alert'}),
                'missingFlowIdByType': dict(Counter(r['event_type'] for r in rows if 'flow_id' not in r)),
                'missingTxIdByType': dict(Counter(r['event_type'] for r in rows if 'tx_id' not in r)),
                'import': report, 'bundles': bundles, 'reimport': repeat,
                'beforeReimport': before, 'afterReimport': after,
                'rawEquality': True, 'allSignaturesPreserved': True})
        result['operational'] = []
        for row in c.execute('SELECT id FROM operational_alerts_v2 ORDER BY id').fetchall():
            result['operational'].append({'projection': read_projection(c,row[0]).model_dump(mode='json',by_alias=True),
                                          'triage': read_triage(c,row[0]).model_dump(mode='json',by_alias=True)})
        result['caseRows'] = [dict(r) for r in c.execute('SELECT * FROM tier2_cases')]
        # Replay under a different capture identity, then a different sensor. This is
        # identity testing, NOT another detector run or independent traffic sample.
        attack = result['captures'][-1]
        eve = folder / 'attack-output/eve.json'
        before = counts(c)
        isolated = stage_file(c,eve,SENSOR,capture_scope=attack['captureScope']+'-identity-test').as_dict()
        sensor = stage_file(c,eve,SENSOR+'-identity-test',capture_scope=attack['captureScope']).as_dict()
        assert isolated['staged'] == sensor['staged'] == len(attack['bundles'])
        after = counts(c)
        assert before['operational_alerts_v2'] == after['operational_alerts_v2']
        result['identityIsolation'] = {'capture': isolated, 'sensor': sensor, 'before': before, 'after': after,
                                       'note': 'staged only, never admitted; not independent detector runs'}
        result['rawDigestBeforeUI'] = raw_digest(c)
        result['finalCountsBeforeUI'] = counts(c)
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
    (folder/'import-evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k: v for k,v in result.items() if k in ('initialCounts','finalCountsBeforeUI')},indent=2))
    for capture in result['captures']:
        print(capture['name'], capture['eventTypes'], capture['import'], 'bundles',len(capture['bundles']))

def serve(folder, port):
    import uvicorn
    from apps.api.main import create_app
    path = folder/'real-validation.db'
    if not path.is_file():
        raise ValueError('Build the disposable real-data validation database first')
    app = create_app(path)
    # Read-only test evidence endpoint; no new product write path.
    @app.get('/__real/proof')
    def proof():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
            c.execute('PRAGMA query_only=ON')
            return {'rawDigest': raw_digest(c), 'databaseDigest': sha256('\n'.join(c.iterdump()).encode()).hexdigest(),
                    'counts': counts(c), 'foreignKeyViolations': len(c.execute('PRAGMA foreign_key_check').fetchall())}
    uvicorn.run(app, host='127.0.0.1',port=port,log_level='warning')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['build','serve'])
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8031)
    args=parser.parse_args()
    folder=args.directory.resolve()
    build(folder) if args.action=='build' else serve(folder,args.port)
