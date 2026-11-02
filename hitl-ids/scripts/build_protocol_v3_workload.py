"""Deterministic construction only. Never calls admission, review, learning or an experiment."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_v3.common import BUNDLE, SENSOR, SCOPE, canonical, write
from packages.detection.adapters.suricata_bundle import build_bundle, parse_record

GENERATOR_VERSION = 'protocol-v3-generator-1'

def construct():
    rows, structure, outcomes, contexts = [], [], {}, {}
    start = datetime(2026, 11, 3, tzinfo=timezone.utc)  # logical scenario clock, not registration time
    def add(phase, stratum, pattern, outcome, *, unknown=False, risk=None, drift_audit=False):
        i = len(rows) + 1
        record = {'timestamp': (start + timedelta(minutes=i)).isoformat(), 'flow_id': 330000 + i,
            'event_type': 'alert', 'src_ip': f'192.0.2.{pattern}', 'dest_ip': f'198.51.100.{pattern}',
            'src_port': 51234, 'dest_port': 22, 'proto': 'TCP',
            'alert': {'signature_id': 3300000 + pattern, 'rev': 1, 'severity': 3, 'action': 'allowed',
                'signature': f'CONTROLLED V3 pattern {pattern:03d} ' + ('opaque anomaly' if unknown else 'SSH brute force'),
                'category': f'Controlled sensor category {pattern:03d}'}}
        alert = build_bundle([parse_record(record, SENSOR, SCOPE)])
        ref = str(alert.canonical_alert_id)
        rows.append(record)
        structure.append({'index': i, 'alertRef': ref, 'phase': phase, 'stratum': stratum,
            'pattern': f'p{pattern:03d}', 'plannedRoute': 'tier2_case' if unknown else 'tier1_review',
            'driftAudit': drift_audit, 'analyst': f'v3-analyst-{(i-1)%3+1}'})
        outcomes[ref] = outcome
        contexts[ref] = dict(assetCriticality='low', repeatedCampaign=False, correlatedAlertCount=1,
            responseRequired=False, knownMaliciousIndicator=risk=='indicator', analystEscalated=False,
            unresolvedByTier1=False, evidenceConflict=risk=='conflict', confirmedMalicious=False)
    for pattern in range(1, 9):
        for _ in range(3): add('learning', 'stable_learning', pattern, 'expected_activity' if pattern<=4 else 'false_positive')
    for pattern in (9, 10):
        for _ in range(3): add('learning', 'drift_learning', pattern, 'expected_activity')
    for n in range(10): add('learning', 'negative_learning', 11+n, 'confirmed_malicious' if n<5 else 'suspicious', risk='indicator' if n<5 else 'conflict')
    for pattern in range(1, 9):
        for _ in range(10): add('holdout', 'stable_matching_benign', pattern, 'expected_activity' if pattern<=4 else 'false_positive')
    for n in range(20): add('holdout', 'unseen_benign', 21+n, 'expected_activity' if n<10 else 'false_positive')
    for n in range(20): add('holdout', 'malicious', 41+n, 'confirmed_malicious', risk='indicator')
    for n in range(20): add('holdout', 'suspicious', 61+n, 'suspicious', risk='conflict')
    for n in range(10): add('holdout', 'unknown_tier2', 81+n, 'confirmed_malicious' if n<5 else 'suspicious', unknown=True)
    for pattern in (9, 10):
        for n in range(5): add('holdout', 'drift_conflict', pattern, 'confirmed_malicious' if pattern==9 else 'suspicious', drift_audit=n==0)
    return rows, structure, contexts, outcomes

def build(output):
    if (output/'manifest.json').exists(): raise ValueError('Frozen bundle cannot be overwritten; generate into a separate directory')
    rows, structure, contexts, outcomes = construct()
    (output/'workload').mkdir(parents=True, exist_ok=True)
    (output/'workload/operational-workload.jsonl').write_bytes(b'\n'.join(canonical(row) for row in rows)+b'\n')
    write(output/'workload/trusted-context.json', contexts)
    write(output/'oracle/external-outcomes.json', outcomes)
    write(output/'expected/workload-structure.json', structure)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--out',type=Path,default=BUNDLE)
    build(parser.parse_args().out)
