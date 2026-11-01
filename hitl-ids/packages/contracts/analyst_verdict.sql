CREATE TABLE analyst_verdict_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 verdict_ref TEXT NOT NULL UNIQUE,
 operational_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 revision INTEGER NOT NULL CHECK(revision>0),
 supersedes_ref TEXT REFERENCES analyst_verdict_events(verdict_ref),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
 UNIQUE(operational_alert_id,revision)
);
CREATE TRIGGER verdict_no_update BEFORE UPDATE ON analyst_verdict_events
BEGIN SELECT RAISE(ABORT,'analyst verdict history is immutable'); END;
CREATE TRIGGER verdict_no_delete BEFORE DELETE ON analyst_verdict_events
BEGIN SELECT RAISE(ABORT,'analyst verdict history is immutable'); END;
CREATE TRIGGER verdict_no_replace BEFORE INSERT ON analyst_verdict_events
WHEN EXISTS(SELECT 1 FROM analyst_verdict_events WHERE id=NEW.id OR verdict_ref=NEW.verdict_ref OR request_id=NEW.request_id OR (operational_alert_id=NEW.operational_alert_id AND revision=NEW.revision))
BEGIN SELECT RAISE(ABORT,'analyst verdict history is immutable'); END;
