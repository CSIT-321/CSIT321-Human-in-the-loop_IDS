CREATE TABLE prospective_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_ref TEXT NOT NULL UNIQUE,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
 created_at TEXT NOT NULL
);
CREATE TABLE prospective_run_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_id INTEGER NOT NULL REFERENCES prospective_runs(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 action TEXT NOT NULL CHECK(action IN ('open','close','evaluated')),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
 created_at TEXT NOT NULL,
 UNIQUE(run_id, action)
);
CREATE TABLE prospective_decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_id INTEGER NOT NULL REFERENCES prospective_runs(id),
 review_event_id INTEGER NOT NULL UNIQUE REFERENCES selective_review_events(id),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot))
);
CREATE TABLE prospective_observations (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_id INTEGER NOT NULL REFERENCES prospective_runs(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
 created_at TEXT NOT NULL
);
CREATE TRIGGER prospective_runs_update BEFORE UPDATE ON prospective_runs BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_runs_delete BEFORE DELETE ON prospective_runs BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_runs_replace BEFORE INSERT ON prospective_runs WHEN EXISTS(SELECT 1 FROM prospective_runs WHERE id=NEW.id OR run_ref=NEW.run_ref OR request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_run_events_update BEFORE UPDATE ON prospective_run_events BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_run_events_delete BEFORE DELETE ON prospective_run_events BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_run_events_replace BEFORE INSERT ON prospective_run_events WHEN EXISTS(SELECT 1 FROM prospective_run_events WHERE id=NEW.id OR request_id=NEW.request_id OR (run_id=NEW.run_id AND action=NEW.action)) BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_decisions_update BEFORE UPDATE ON prospective_decisions BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_decisions_delete BEFORE DELETE ON prospective_decisions BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_decisions_replace BEFORE INSERT ON prospective_decisions WHEN EXISTS(SELECT 1 FROM prospective_decisions WHERE id=NEW.id OR review_event_id=NEW.review_event_id) BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_observations_update BEFORE UPDATE ON prospective_observations BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_observations_delete BEFORE DELETE ON prospective_observations BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
CREATE TRIGGER prospective_observations_replace BEFORE INSERT ON prospective_observations WHEN EXISTS(SELECT 1 FROM prospective_observations WHERE id=NEW.id OR request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'collection history is append-only'); END;
