CREATE TABLE selective_review_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 event_ref TEXT NOT NULL UNIQUE,
 operational_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 action TEXT NOT NULL CHECK(action IN ('apply','require_review')),
 reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 4000),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 decision_snapshot TEXT NOT NULL CHECK(json_valid(decision_snapshot)),
 event_type TEXT NOT NULL CHECK(event_type IN ('V2_SELECTIVE_REVIEW_DECIDED','V2_HUMAN_REVIEW_REQUIRED')),
 created_at TEXT NOT NULL
);
CREATE INDEX idx_selective_alert ON selective_review_events(operational_alert_id,id);
CREATE TRIGGER selective_update BEFORE UPDATE ON selective_review_events BEGIN SELECT RAISE(ABORT,'selective review is append-only'); END;
CREATE TRIGGER selective_delete BEFORE DELETE ON selective_review_events BEGIN SELECT RAISE(ABORT,'selective review is append-only'); END;
CREATE TRIGGER selective_replace BEFORE INSERT ON selective_review_events
WHEN EXISTS(SELECT 1 FROM selective_review_events WHERE id=NEW.id OR event_ref=NEW.event_ref OR request_id=NEW.request_id)
BEGIN SELECT RAISE(ABORT,'selective review is append-only'); END;
