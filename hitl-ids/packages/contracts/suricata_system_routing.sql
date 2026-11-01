-- Migration 14: retain historical rows and IDs; nullable actors represent system policy.
-- Executed with foreign_keys disabled outside the transaction and checked before commit.

CREATE TABLE IF NOT EXISTS operational_routing_audit_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operational_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
    actor_id INTEGER REFERENCES users(id),
    request_id TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL CHECK (action IN ('admit_tier1','approve_tier2','reject_tier2','manual_escalate','system_route')),
    event_type TEXT NOT NULL,
    expected_state_version TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 2000),
    before_state TEXT NOT NULL CHECK (json_valid(before_state)),
    after_state TEXT NOT NULL CHECK (json_valid(after_state)),
    created_at TEXT NOT NULL,
    decision_source TEXT NOT NULL DEFAULT 'analyst' CHECK (decision_source IN ('analyst','system_policy')),
    CHECK ((decision_source='system_policy' AND actor_id IS NULL AND action='system_route') OR (decision_source='analyst' AND actor_id IS NOT NULL AND action!='system_route'))
);
INSERT INTO operational_routing_audit_new (id,operational_alert_id,actor_id,request_id,action,event_type,expected_state_version,reason,before_state,after_state,created_at) SELECT id,operational_alert_id,actor_id,request_id,action,event_type,expected_state_version,reason,before_state,after_state,created_at FROM operational_routing_audit;
DROP TABLE operational_routing_audit;
ALTER TABLE operational_routing_audit_new RENAME TO operational_routing_audit;
CREATE INDEX IF NOT EXISTS idx_routing_alert ON operational_routing_audit(operational_alert_id,id);
CREATE TRIGGER IF NOT EXISTS trg_routing_no_update BEFORE UPDATE ON operational_routing_audit
BEGIN SELECT RAISE(ABORT, 'routing audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_routing_no_delete BEFORE DELETE ON operational_routing_audit
BEGIN SELECT RAISE(ABORT, 'routing audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_routing_no_replace BEFORE INSERT ON operational_routing_audit
WHEN EXISTS (SELECT 1 FROM operational_routing_audit WHERE id=NEW.id OR request_id=NEW.request_id)
BEGIN SELECT RAISE(ABORT, 'routing audit is append-only'); END;
CREATE TABLE tier2_cases_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_ref TEXT NOT NULL UNIQUE,
    primary_operational_alert_id INTEGER NOT NULL UNIQUE REFERENCES operational_alerts_v2(id),
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
    owner_actor_id INTEGER REFERENCES users(id),
    created_by_actor_id INTEGER REFERENCES users(id),
    snapshot TEXT NOT NULL CHECK (json_valid(snapshot)),
    created_at TEXT NOT NULL,
    decision_source TEXT NOT NULL DEFAULT 'analyst' CHECK (decision_source IN ('analyst','system_policy')),
    CHECK ((decision_source='system_policy' AND created_by_actor_id IS NULL AND owner_actor_id IS NULL) OR (decision_source='analyst' AND created_by_actor_id IS NOT NULL AND owner_actor_id IS NOT NULL))
);
INSERT INTO tier2_cases_new (id,case_ref,primary_operational_alert_id,title,owner_actor_id,created_by_actor_id,snapshot,created_at) SELECT id,case_ref,primary_operational_alert_id,title,owner_actor_id,created_by_actor_id,snapshot,created_at FROM tier2_cases;
DROP TABLE tier2_cases;
ALTER TABLE tier2_cases_new RENAME TO tier2_cases;
CREATE TRIGGER trg_case_no_update BEFORE UPDATE ON tier2_cases
BEGIN SELECT RAISE(ABORT, 'case creation snapshot is immutable'); END;
CREATE TRIGGER trg_case_no_delete BEFORE DELETE ON tier2_cases
BEGIN SELECT RAISE(ABORT, 'case creation snapshot is immutable'); END;
CREATE TRIGGER trg_case_no_replace BEFORE INSERT ON tier2_cases
WHEN EXISTS (SELECT 1 FROM tier2_cases WHERE id=NEW.id OR case_ref=NEW.case_ref
             OR primary_operational_alert_id=NEW.primary_operational_alert_id)
BEGIN SELECT RAISE(ABORT, 'case creation snapshot is immutable'); END;
CREATE TABLE tier2_case_events_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES tier2_cases(id),
    actor_id INTEGER REFERENCES users(id),
    request_id TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL CHECK (action IN ('create','link','note','finding','start')),
    event_type TEXT NOT NULL,
    request_payload TEXT NOT NULL CHECK (json_valid(request_payload)),
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 4000),
    finding TEXT CHECK (finding IN ('confirmed_malicious','suspicious','inconclusive','expected_activity')),
    linked_alert_id INTEGER REFERENCES operational_alerts_v2(id),
    before_state TEXT NOT NULL CHECK (json_valid(before_state)),
    after_state TEXT NOT NULL CHECK (json_valid(after_state)),
    created_at TEXT NOT NULL,
    decision_source TEXT NOT NULL DEFAULT 'analyst' CHECK (decision_source IN ('analyst','system_policy')),
    CHECK ((action='link' AND linked_alert_id IS NOT NULL) OR (action!='link' AND linked_alert_id IS NULL)),
    CHECK ((action='finding' AND finding IS NOT NULL) OR (action!='finding' AND finding IS NULL)),
    CHECK ((decision_source='system_policy' AND actor_id IS NULL AND action='create') OR (decision_source='analyst' AND actor_id IS NOT NULL))
);
INSERT INTO tier2_case_events_new (id,case_id,actor_id,request_id,action,event_type,request_payload,reason,finding,linked_alert_id,before_state,after_state,created_at) SELECT id,case_id,actor_id,request_id,action,event_type,request_payload,reason,finding,linked_alert_id,before_state,after_state,created_at FROM tier2_case_events;
DROP TABLE tier2_case_events;
ALTER TABLE tier2_case_events_new RENAME TO tier2_case_events;
CREATE UNIQUE INDEX idx_case_link_unique ON tier2_case_events(case_id,linked_alert_id) WHERE action='link';
CREATE INDEX idx_case_events ON tier2_case_events(case_id,id);
CREATE TRIGGER trg_case_event_no_update BEFORE UPDATE ON tier2_case_events
BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
CREATE TRIGGER trg_case_event_no_delete BEFORE DELETE ON tier2_case_events
BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
CREATE TRIGGER trg_case_event_no_replace BEFORE INSERT ON tier2_case_events
WHEN EXISTS (SELECT 1 FROM tier2_case_events WHERE id=NEW.id OR request_id=NEW.request_id
             OR (case_id=NEW.case_id AND linked_alert_id=NEW.linked_alert_id))
BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
CREATE TABLE operational_triage_policy_audit_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operational_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
    actor_id INTEGER REFERENCES users(id),
    policy_version TEXT NOT NULL,
    policy_snapshot TEXT NOT NULL CHECK (json_valid(policy_snapshot)),
    context_snapshot TEXT NOT NULL CHECK (json_valid(context_snapshot)),
    result_snapshot TEXT NOT NULL CHECK (json_valid(result_snapshot)),
    before_state TEXT NOT NULL CHECK (json_valid(before_state)),
    after_state TEXT NOT NULL CHECK (json_valid(after_state)),
    created_at TEXT NOT NULL,
    decision_source TEXT NOT NULL DEFAULT 'analyst' CHECK (decision_source IN ('analyst','system_policy')),
    CHECK ((decision_source='system_policy' AND actor_id IS NULL) OR (decision_source='analyst' AND actor_id IS NOT NULL))
);
INSERT INTO operational_triage_policy_audit_new (id,operational_alert_id,actor_id,policy_version,policy_snapshot,context_snapshot,result_snapshot,before_state,after_state,created_at) SELECT id,operational_alert_id,actor_id,policy_version,policy_snapshot,context_snapshot,result_snapshot,before_state,after_state,created_at FROM operational_triage_policy_audit;
DROP TABLE operational_triage_policy_audit;
ALTER TABLE operational_triage_policy_audit_new RENAME TO operational_triage_policy_audit;
CREATE INDEX idx_triage_policy_audit_alert ON operational_triage_policy_audit (operational_alert_id, id);
CREATE TRIGGER trg_triage_policy_audit_no_update BEFORE UPDATE ON operational_triage_policy_audit
BEGIN SELECT RAISE(ABORT, 'V2 policy audit is append-only'); END;
CREATE TRIGGER trg_triage_policy_audit_no_delete BEFORE DELETE ON operational_triage_policy_audit
BEGIN SELECT RAISE(ABORT, 'V2 policy audit is append-only'); END;
CREATE TRIGGER trg_triage_policy_audit_no_replace BEFORE INSERT ON operational_triage_policy_audit
WHEN EXISTS (SELECT 1 FROM operational_triage_policy_audit WHERE id=NEW.id)
BEGIN SELECT RAISE(ABORT, 'V2 policy audit is append-only'); END;
CREATE TABLE suricata_eve_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT NOT NULL,
    source_record_ref TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('alert','flow','http','dns','tls','ssh','fileinfo','anomaly')),
    flow_id TEXT,
    tx_id TEXT,
    timestamp TEXT NOT NULL,
    raw_snapshot TEXT NOT NULL CHECK(json_valid(raw_snapshot)),
    imported_at TEXT NOT NULL,
    UNIQUE(sensor_id,source_record_ref)
);
CREATE INDEX idx_eve_flow ON suricata_eve_records(sensor_id,flow_id);
CREATE TABLE operational_system_routing (
    operational_alert_id INTEGER PRIMARY KEY REFERENCES operational_alerts_v2(id),
    classification TEXT NOT NULL CHECK(json_valid(classification)),
    classification_policy TEXT NOT NULL CHECK(json_valid(classification_policy)),
    routing_decision TEXT NOT NULL CHECK(json_valid(routing_decision)),
    routing_policy TEXT NOT NULL CHECK(json_valid(routing_policy)),
    context_provenance TEXT NOT NULL CHECK(json_valid(context_provenance)),
    routing_audit_id INTEGER NOT NULL UNIQUE REFERENCES operational_routing_audit(id),
    policy_audit_id INTEGER NOT NULL UNIQUE REFERENCES operational_triage_policy_audit(id),
    case_ref TEXT REFERENCES tier2_cases(case_ref),
    created_at TEXT NOT NULL
);
CREATE TRIGGER trg_suricata_eve_records_no_update BEFORE UPDATE ON suricata_eve_records
BEGIN SELECT RAISE(ABORT, 'suricata_eve_records is immutable'); END;
CREATE TRIGGER trg_suricata_eve_records_no_delete BEFORE DELETE ON suricata_eve_records
BEGIN SELECT RAISE(ABORT, 'suricata_eve_records is immutable'); END;
CREATE TRIGGER trg_suricata_eve_records_no_replace BEFORE INSERT ON suricata_eve_records
WHEN EXISTS (SELECT 1 FROM suricata_eve_records WHERE id=NEW.id OR (sensor_id=NEW.sensor_id AND source_record_ref=NEW.source_record_ref))
BEGIN SELECT RAISE(ABORT, 'suricata_eve_records is immutable'); END;
CREATE TRIGGER trg_operational_system_routing_no_update BEFORE UPDATE ON operational_system_routing
BEGIN SELECT RAISE(ABORT, 'operational_system_routing is immutable'); END;
CREATE TRIGGER trg_operational_system_routing_no_delete BEFORE DELETE ON operational_system_routing
BEGIN SELECT RAISE(ABORT, 'operational_system_routing is immutable'); END;
CREATE TRIGGER trg_operational_system_routing_no_replace BEFORE INSERT ON operational_system_routing
WHEN EXISTS (SELECT 1 FROM operational_system_routing WHERE operational_alert_id=NEW.operational_alert_id)
BEGIN SELECT RAISE(ABORT, 'operational_system_routing is immutable'); END;
