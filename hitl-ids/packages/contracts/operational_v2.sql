CREATE TABLE operational_alerts_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operational_alert_ref TEXT NOT NULL UNIQUE CHECK (length(operational_alert_ref) = 36),
    canonical_alert_id TEXT NOT NULL UNIQUE CHECK (canonical_alert_id = operational_alert_ref),
    source_kind TEXT NOT NULL CHECK (source_kind IN ('legacy_flow_alert', 'external_nids_alert')),
    detector_source TEXT NOT NULL,
    detector_name TEXT NOT NULL,
    detector_version TEXT,
    legacy_alert_id INTEGER UNIQUE REFERENCES alerts(id),
    external_inbox_id INTEGER UNIQUE REFERENCES external_alert_inbox(id),
    detection_title TEXT NOT NULL,
    detection_category TEXT,
    native_severity TEXT NOT NULL CHECK (json_valid(native_severity) AND json_type(native_severity) IN ('text', 'integer')),
    detector_confidence NUMERIC CHECK (detector_confidence BETWEEN 0 AND 1),
    detector_evidence TEXT NOT NULL CHECK (json_valid(detector_evidence) AND json_type(detector_evidence) = 'object'),
    source_provenance TEXT NOT NULL CHECK (json_valid(source_provenance) AND json_type(source_provenance) = 'object'),
    occurred_at TEXT NOT NULL,
    occurred_at_timezone_offset TEXT,
    source_ip TEXT NOT NULL,
    destination_ip TEXT NOT NULL,
    source_port INTEGER CHECK (source_port BETWEEN 0 AND 65535),
    destination_port INTEGER CHECK (destination_port BETWEEN 0 AND 65535),
    protocol TEXT NOT NULL,
    CHECK ((source_kind = 'legacy_flow_alert' AND legacy_alert_id IS NOT NULL AND external_inbox_id IS NULL)
        OR (source_kind = 'external_nids_alert' AND legacy_alert_id IS NULL AND external_inbox_id IS NOT NULL)),
    CHECK ((source_kind = 'legacy_flow_alert' AND detector_source = 'current_flow')
        OR (source_kind = 'external_nids_alert' AND detector_source <> 'current_flow')),
    CHECK (detector_source <> 'suricata' OR detector_confidence IS NULL),
    CHECK (json_extract(detector_evidence, '$.canonical_alert_id') IS canonical_alert_id),
    CHECK (json_extract(detector_evidence, '$.detector_source') IS detector_source),
    CHECK (json_extract(detector_evidence, '$.confidence') IS detector_confidence),
    CHECK (json_extract(detector_evidence, '$.detector_severity') IS json_extract(native_severity, '$')),
    CHECK (json_extract(source_provenance, '$.source_kind') IS source_kind)
);
CREATE TRIGGER trg_operational_v2_no_update BEFORE UPDATE ON operational_alerts_v2
BEGIN SELECT RAISE(ABORT, 'V2 detector and source evidence is immutable'); END;
CREATE TRIGGER trg_operational_v2_no_delete BEFORE DELETE ON operational_alerts_v2
BEGIN SELECT RAISE(ABORT, 'V2 detector and source evidence is immutable'); END;
CREATE TRIGGER trg_operational_v2_no_replace BEFORE INSERT ON operational_alerts_v2
WHEN EXISTS (SELECT 1 FROM operational_alerts_v2 WHERE id = NEW.id
    OR operational_alert_ref = NEW.operational_alert_ref OR canonical_alert_id = NEW.canonical_alert_id
    OR legacy_alert_id = NEW.legacy_alert_id OR external_inbox_id = NEW.external_inbox_id)
BEGIN SELECT RAISE(ABORT, 'V2 detector and source evidence is immutable'); END;
CREATE TABLE operational_triage_state_v2 (
    operational_alert_id INTEGER PRIMARY KEY REFERENCES operational_alerts_v2(id),
    operational_priority NUMERIC CHECK (operational_priority BETWEEN 0 AND 100),
    priority_band TEXT CHECK (priority_band IN ('critical', 'high', 'medium', 'low', 'informational')),
    handling_route TEXT NOT NULL DEFAULT 'unassigned' CHECK (handling_route IN
        ('unassigned', 'tier1_review', 'tier2_candidate', 'tier2_case', 'no_immediate_review')),
    workflow_stage TEXT NOT NULL DEFAULT 'staged' CHECK (workflow_stage IN
        ('staged', 'triage', 'assessment', 'investigation', 'incident', 'resolved')),
    review_required INTEGER NOT NULL DEFAULT 1 CHECK (review_required IN (0, 1)),
    review_reason TEXT NOT NULL,
    tier2_recommended INTEGER NOT NULL DEFAULT 0 CHECK (tier2_recommended IN (0, 1)),
    tier2_recommendation_reasons TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(tier2_recommendation_reasons) AND json_type(tier2_recommendation_reasons) = 'array'),
    decision_source TEXT NOT NULL CHECK (decision_source IN
        ('system_policy', 'analyst', 'historical_memory', 'legacy_projection')),
    triage_policy_version TEXT,
    updated_at TEXT NOT NULL,
    CHECK ((operational_priority IS NULL) = (priority_band IS NULL)),
    CHECK (tier2_recommended = (json_array_length(tier2_recommendation_reasons) > 0))
);
CREATE TRIGGER trg_triage_v2_identity BEFORE UPDATE OF operational_alert_id ON operational_triage_state_v2
WHEN OLD.operational_alert_id IS NOT NEW.operational_alert_id
BEGIN SELECT RAISE(ABORT, 'V2 triage identity cannot change'); END;
