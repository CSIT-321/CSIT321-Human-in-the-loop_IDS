CREATE TABLE tier2_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_ref TEXT NOT NULL UNIQUE,
    primary_operational_alert_id INTEGER NOT NULL UNIQUE REFERENCES operational_alerts_v2(id),
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
    owner_actor_id INTEGER NOT NULL REFERENCES users(id),
    created_by_actor_id INTEGER NOT NULL REFERENCES users(id),
    snapshot TEXT NOT NULL CHECK (json_valid(snapshot)),
    created_at TEXT NOT NULL
);
CREATE TABLE tier2_case_state (
    case_id INTEGER PRIMARY KEY REFERENCES tier2_cases(id),
    status TEXT NOT NULL CHECK (status IN ('open','investigating')),
    revision INTEGER NOT NULL CHECK (revision>=1),
    updated_at TEXT NOT NULL
);
CREATE TABLE tier2_case_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES tier2_cases(id),
    actor_id INTEGER NOT NULL REFERENCES users(id),
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
    CHECK ((action='link' AND linked_alert_id IS NOT NULL) OR (action!='link' AND linked_alert_id IS NULL)),
    CHECK ((action='finding' AND finding IS NOT NULL) OR (action!='finding' AND finding IS NULL))
);
CREATE UNIQUE INDEX idx_case_link_unique ON tier2_case_events(case_id,linked_alert_id) WHERE action='link';
CREATE INDEX idx_case_events ON tier2_case_events(case_id,id);
CREATE TRIGGER trg_case_no_update BEFORE UPDATE ON tier2_cases
BEGIN SELECT RAISE(ABORT, 'case creation snapshot is immutable'); END;
CREATE TRIGGER trg_case_no_delete BEFORE DELETE ON tier2_cases
BEGIN SELECT RAISE(ABORT, 'case creation snapshot is immutable'); END;
CREATE TRIGGER trg_case_no_replace BEFORE INSERT ON tier2_cases
WHEN EXISTS (SELECT 1 FROM tier2_cases WHERE id=NEW.id OR case_ref=NEW.case_ref
             OR primary_operational_alert_id=NEW.primary_operational_alert_id)
BEGIN SELECT RAISE(ABORT, 'case creation snapshot is immutable'); END;
CREATE TRIGGER trg_case_state_identity BEFORE UPDATE OF case_id ON tier2_case_state
BEGIN SELECT RAISE(ABORT, 'case state identity is immutable'); END;
CREATE TRIGGER trg_case_event_no_update BEFORE UPDATE ON tier2_case_events
BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
CREATE TRIGGER trg_case_event_no_delete BEFORE DELETE ON tier2_case_events
BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
CREATE TRIGGER trg_case_event_no_replace BEFORE INSERT ON tier2_case_events
WHEN EXISTS (SELECT 1 FROM tier2_case_events WHERE id=NEW.id OR request_id=NEW.request_id
             OR (case_id=NEW.case_id AND linked_alert_id=NEW.linked_alert_id))
BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
