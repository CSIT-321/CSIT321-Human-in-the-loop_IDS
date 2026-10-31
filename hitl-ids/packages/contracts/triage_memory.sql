CREATE TABLE triage_memory_lessons (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 lesson_ref TEXT NOT NULL UNIQUE,
 context_key TEXT NOT NULL,
 detector_source TEXT NOT NULL,
 source_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 source_case_id INTEGER REFERENCES tier2_cases(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
 created_at TEXT NOT NULL
);
CREATE INDEX idx_memory_context ON triage_memory_lessons(context_key,id);
CREATE INDEX idx_memory_detector ON triage_memory_lessons(detector_source,id);
CREATE TABLE triage_memory_support_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 lesson_id INTEGER NOT NULL REFERENCES triage_memory_lessons(id),
 source_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 source_case_id INTEGER REFERENCES tier2_cases(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 outcome TEXT NOT NULL CHECK(outcome IN ('expected_activity','false_positive','confirmed_malicious','suspicious')),
 relation TEXT NOT NULL CHECK(relation IN ('support','conflict')),
 reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 4000),
 evidence_snapshot TEXT NOT NULL CHECK(json_valid(evidence_snapshot)),
 is_primary INTEGER NOT NULL CHECK(is_primary IN (0,1)),
 request_id TEXT NOT NULL,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 created_at TEXT NOT NULL,
 UNIQUE(lesson_id,source_alert_id),
 UNIQUE(lesson_id,request_id)
);
CREATE INDEX idx_memory_support ON triage_memory_support_events(lesson_id,id);
CREATE UNIQUE INDEX idx_memory_review_alert ON triage_memory_support_events(source_alert_id) WHERE is_primary=1;
CREATE UNIQUE INDEX idx_memory_review_request ON triage_memory_support_events(request_id) WHERE is_primary=1;
CREATE TABLE triage_memory_decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 lesson_id INTEGER NOT NULL UNIQUE REFERENCES triage_memory_lessons(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 action TEXT NOT NULL CHECK(action IN ('activate','reject')),
 reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 4000),
 lesson_snapshot TEXT NOT NULL CHECK(json_valid(lesson_snapshot)),
 valid_from TEXT,
 expires_at TEXT,
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 created_at TEXT NOT NULL
);
CREATE TABLE triage_memory_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 lesson_id INTEGER NOT NULL REFERENCES triage_memory_lessons(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 event_type TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)),
 created_at TEXT NOT NULL
);
CREATE INDEX idx_memory_audit ON triage_memory_audit(lesson_id,id);
CREATE TRIGGER memory_lesson_update BEFORE UPDATE ON triage_memory_lessons BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_lesson_delete BEFORE DELETE ON triage_memory_lessons BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_lesson_replace BEFORE INSERT ON triage_memory_lessons WHEN EXISTS(SELECT 1 FROM triage_memory_lessons WHERE id=NEW.id OR lesson_ref=NEW.lesson_ref) BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_support_update BEFORE UPDATE ON triage_memory_support_events BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_support_delete BEFORE DELETE ON triage_memory_support_events BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_support_replace BEFORE INSERT ON triage_memory_support_events WHEN EXISTS(SELECT 1 FROM triage_memory_support_events WHERE id=NEW.id OR (lesson_id=NEW.lesson_id AND (source_alert_id=NEW.source_alert_id OR request_id=NEW.request_id)) OR (is_primary=1 AND NEW.is_primary=1 AND (source_alert_id=NEW.source_alert_id OR request_id=NEW.request_id))) BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_decision_update BEFORE UPDATE ON triage_memory_decisions BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_decision_delete BEFORE DELETE ON triage_memory_decisions BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_decision_replace BEFORE INSERT ON triage_memory_decisions WHEN EXISTS(SELECT 1 FROM triage_memory_decisions WHERE id=NEW.id OR lesson_id=NEW.lesson_id OR request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_audit_update BEFORE UPDATE ON triage_memory_audit BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_audit_delete BEFORE DELETE ON triage_memory_audit BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_audit_replace BEFORE INSERT ON triage_memory_audit WHEN EXISTS(SELECT 1 FROM triage_memory_audit WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
