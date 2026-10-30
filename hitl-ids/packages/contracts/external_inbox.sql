CREATE TABLE external_alert_inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_alert_id TEXT NOT NULL UNIQUE CHECK (length(canonical_alert_id) = 36),
    detector_source TEXT NOT NULL CHECK (detector_source = 'suricata'),
    sensor_id TEXT NOT NULL CHECK (length(sensor_id) > 0),
    raw_reference TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    occurred_at_timezone_offset TEXT,
    native_severity INTEGER NOT NULL CHECK (native_severity >= 0),
    confidence NUMERIC CHECK (confidence IS NULL),
    detection_title TEXT NOT NULL,
    detection_category TEXT NOT NULL,
    source_ip TEXT NOT NULL,
    destination_ip TEXT NOT NULL,
    source_port INTEGER CHECK (source_port BETWEEN 0 AND 65535),
    destination_port INTEGER CHECK (destination_port BETWEEN 0 AND 65535),
    protocol TEXT NOT NULL,
    canonical_snapshot TEXT NOT NULL CHECK (json_valid(canonical_snapshot)),
    admission_policy_version TEXT NOT NULL,
    admission_decision TEXT NOT NULL CHECK (admission_decision = 'hold_for_review'),
    admission_reason TEXT NOT NULL,
    review_required INTEGER NOT NULL CHECK (review_required = 1),
    learning_eligible INTEGER NOT NULL CHECK (learning_eligible = 0),
    evaluation_eligible INTEGER NOT NULL CHECK (evaluation_eligible = 0),
    proposed_operational_priority NUMERIC NOT NULL CHECK (proposed_operational_priority BETWEEN 0 AND 100),
    proposed_evidence_class TEXT NOT NULL CHECK (proposed_evidence_class = 'external_rule'),
    policy_snapshot TEXT NOT NULL CHECK (json_valid(policy_snapshot)),
    import_status TEXT NOT NULL CHECK (import_status = 'staged'),
    imported_at TEXT NOT NULL
);
CREATE TRIGGER trg_external_inbox_no_update BEFORE UPDATE ON external_alert_inbox
BEGIN SELECT RAISE(ABORT, 'external inbox evidence is immutable'); END;
CREATE TRIGGER trg_external_inbox_no_delete BEFORE DELETE ON external_alert_inbox
BEGIN SELECT RAISE(ABORT, 'external inbox evidence is immutable'); END;
CREATE TRIGGER trg_external_inbox_no_replace BEFORE INSERT ON external_alert_inbox
WHEN EXISTS (SELECT 1 FROM external_alert_inbox
             WHERE id = NEW.id OR canonical_alert_id = NEW.canonical_alert_id)
BEGIN SELECT RAISE(ABORT, 'external inbox evidence is immutable'); END;
