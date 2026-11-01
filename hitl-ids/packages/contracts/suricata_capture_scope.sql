-- Historical raw rows retain their IDs, bytes and legacy NULL scope. New captures
-- use an explicit scope; no canonical inbox/operational snapshot is rewritten.
CREATE TABLE suricata_eve_records_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT NOT NULL,
    capture_scope TEXT CHECK(capture_scope IS NULL OR (length(trim(capture_scope)) BETWEEN 1 AND 200 AND capture_scope=trim(capture_scope))),
    source_record_ref TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('alert','flow','http','dns','tls','ssh','fileinfo','anomaly')),
    flow_id TEXT,
    tx_id TEXT,
    timestamp TEXT NOT NULL,
    raw_snapshot TEXT NOT NULL CHECK(json_valid(raw_snapshot)),
    imported_at TEXT NOT NULL
);
INSERT INTO suricata_eve_records_new (id,sensor_id,source_record_ref,event_type,flow_id,tx_id,timestamp,raw_snapshot,imported_at)
SELECT id,sensor_id,source_record_ref,event_type,flow_id,tx_id,timestamp,raw_snapshot,imported_at FROM suricata_eve_records;
DROP TABLE suricata_eve_records;
ALTER TABLE suricata_eve_records_new RENAME TO suricata_eve_records;
CREATE UNIQUE INDEX idx_eve_record_scope ON suricata_eve_records(sensor_id,coalesce(capture_scope,''),source_record_ref);
CREATE INDEX idx_eve_flow ON suricata_eve_records(sensor_id,capture_scope,flow_id);
CREATE TRIGGER trg_suricata_eve_records_no_update BEFORE UPDATE ON suricata_eve_records
BEGIN SELECT RAISE(ABORT, 'suricata_eve_records is immutable'); END;
CREATE TRIGGER trg_suricata_eve_records_no_delete BEFORE DELETE ON suricata_eve_records
BEGIN SELECT RAISE(ABORT, 'suricata_eve_records is immutable'); END;
CREATE TRIGGER trg_suricata_eve_records_no_replace BEFORE INSERT ON suricata_eve_records
WHEN EXISTS (SELECT 1 FROM suricata_eve_records WHERE id=NEW.id OR
    (sensor_id=NEW.sensor_id AND capture_scope IS NEW.capture_scope AND source_record_ref=NEW.source_record_ref))
BEGIN SELECT RAISE(ABORT, 'suricata_eve_records is immutable'); END;
