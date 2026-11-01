"""Seed pre-bundle immutable snapshots for historical workflow/migration regression.

This is test data construction, never the current importer. Keeping the original adapter
version exercises historical admission, recommendation, manual routing and Selective Review
without falsely reclassifying historical records as newly correlated detections.
"""
import hashlib
from packages.detection.adapters.admission_policy import load_admission_policy
from packages.detection.adapters.staging import ImportReport, records, inbox_row
from packages.detection.adapters.suricata import SuricataEveAdapter, SuricataOutput
from packages.detection.adapters.suricata_bundle import canonical_json


def stage_file(conn, path, sensor_id):
    report = ImportReport()
    with conn:
        for _, raw, error in records(path):
            assert error is None and raw['event_type'] == 'alert'
            report.parsed += 1
            reference = 'eve-sha256:' + hashlib.sha256(canonical_json(raw).encode()).hexdigest()
            alert = SuricataEveAdapter().adapt(SuricataOutput(raw, reference, sensor_id=sensor_id))
            if conn.execute('SELECT 1 FROM external_alert_inbox WHERE canonical_alert_id=?',
                            (str(alert.canonical_alert_id),)).fetchone():
                report.duplicate += 1
                continue
            row = inbox_row(alert, load_admission_policy().decide(alert), sensor_id)
            conn.execute(f"INSERT INTO external_alert_inbox ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", list(row.values()))
            report.staged += 1
    return report


def import_file(path, sensor_id, database):
    from contextlib import closing
    from packages.contracts import db
    with closing(db.connect(database)) as conn:
        db.migrate(conn)
        return stage_file(conn, path, sensor_id)
