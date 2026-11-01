-- Migration 19: preserve state/event rows, IDs, provenance and all dependent foreign keys.
CREATE TABLE tier2_case_state_new (
 case_id INTEGER PRIMARY KEY REFERENCES tier2_cases(id),
 status TEXT NOT NULL CHECK(status IN ('open','investigating','resolved')),
 revision INTEGER NOT NULL CHECK(revision>=1),
 updated_at TEXT NOT NULL
);
INSERT INTO tier2_case_state_new SELECT * FROM tier2_case_state;
DROP TABLE tier2_case_state;
ALTER TABLE tier2_case_state_new RENAME TO tier2_case_state;
CREATE TRIGGER trg_case_state_identity BEFORE UPDATE OF case_id ON tier2_case_state
BEGIN SELECT RAISE(ABORT,'case state identity is immutable'); END;
CREATE TRIGGER trg_case_state_resolved BEFORE UPDATE ON tier2_case_state WHEN OLD.status='resolved'
BEGIN SELECT RAISE(ABORT,'resolved Case is closed; no reopen in V1'); END;
CREATE TABLE tier2_case_events_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES tier2_cases(id),
    actor_id INTEGER REFERENCES users(id),
    request_id TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL CHECK (action IN ('create','link','note','finding','start','resolve')),
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
INSERT INTO tier2_case_events_new (id,case_id,actor_id,request_id,action,event_type,request_payload,reason,finding,linked_alert_id,before_state,after_state,created_at,decision_source) SELECT id,case_id,actor_id,request_id,action,event_type,request_payload,reason,finding,linked_alert_id,before_state,after_state,created_at,decision_source FROM tier2_case_events;
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
CREATE UNIQUE INDEX idx_case_resolution_unique ON tier2_case_events(case_id) WHERE action='resolve';
CREATE TRIGGER trg_case_closed_event BEFORE INSERT ON tier2_case_events
WHEN NEW.action!='resolve' AND EXISTS(SELECT 1 FROM tier2_case_state WHERE case_id=NEW.case_id AND status='resolved')
BEGIN SELECT RAISE(ABORT,'resolved Case does not accept new investigation events'); END;
