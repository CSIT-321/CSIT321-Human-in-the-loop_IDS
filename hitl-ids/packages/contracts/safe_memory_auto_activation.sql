-- Forward migration 20: preserve historical human rows; represent system learning honestly.
CREATE TABLE triage_memory_lessons_new (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 lesson_ref TEXT NOT NULL UNIQUE,
 context_key TEXT NOT NULL,
 detector_source TEXT NOT NULL,
 source_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 source_case_id INTEGER REFERENCES tier2_cases(id),
 actor_id INTEGER REFERENCES users(id),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
 created_at TEXT NOT NULL,
 decision_source TEXT NOT NULL DEFAULT 'analyst' CHECK(decision_source IN ('analyst','system_policy')),
 policy_version TEXT,
 CHECK((decision_source='analyst' AND actor_id IS NOT NULL) OR (decision_source='system_policy' AND actor_id IS NULL AND policy_version IS NOT NULL))
);
INSERT INTO triage_memory_lessons_new (id,lesson_ref,context_key,detector_source,source_alert_id,source_case_id,actor_id,snapshot,created_at) SELECT id,lesson_ref,context_key,detector_source,source_alert_id,source_case_id,actor_id,snapshot,created_at FROM triage_memory_lessons;
DROP TABLE triage_memory_lessons;
ALTER TABLE triage_memory_lessons_new RENAME TO triage_memory_lessons;
CREATE INDEX idx_memory_context ON triage_memory_lessons(context_key,id);
CREATE INDEX idx_memory_detector ON triage_memory_lessons(detector_source,id);
CREATE TRIGGER memory_lesson_update BEFORE UPDATE ON triage_memory_lessons BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_lesson_delete BEFORE DELETE ON triage_memory_lessons BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_lesson_replace BEFORE INSERT ON triage_memory_lessons WHEN EXISTS(SELECT 1 FROM triage_memory_lessons WHERE id=NEW.id OR lesson_ref=NEW.lesson_ref) BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TABLE triage_memory_decisions_new (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 lesson_id INTEGER NOT NULL UNIQUE REFERENCES triage_memory_lessons(id),
 actor_id INTEGER REFERENCES users(id),
 action TEXT NOT NULL CHECK(action IN ('activate','reject')),
 reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 4000),
 lesson_snapshot TEXT NOT NULL CHECK(json_valid(lesson_snapshot)),
 valid_from TEXT,
 expires_at TEXT,
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 created_at TEXT NOT NULL,
 decision_source TEXT NOT NULL DEFAULT 'analyst' CHECK(decision_source IN ('analyst','system_policy')),
 policy_version TEXT,
 CHECK((decision_source='analyst' AND actor_id IS NOT NULL) OR (decision_source='system_policy' AND actor_id IS NULL AND policy_version IS NOT NULL))
);
INSERT INTO triage_memory_decisions_new (id,lesson_id,actor_id,action,reason,lesson_snapshot,valid_from,expires_at,request_id,request_payload,created_at) SELECT id,lesson_id,actor_id,action,reason,lesson_snapshot,valid_from,expires_at,request_id,request_payload,created_at FROM triage_memory_decisions;
DROP TABLE triage_memory_decisions;
ALTER TABLE triage_memory_decisions_new RENAME TO triage_memory_decisions;
CREATE TRIGGER memory_decision_update BEFORE UPDATE ON triage_memory_decisions BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_decision_delete BEFORE DELETE ON triage_memory_decisions BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_decision_replace BEFORE INSERT ON triage_memory_decisions WHEN EXISTS(SELECT 1 FROM triage_memory_decisions WHERE id=NEW.id OR lesson_id=NEW.lesson_id OR request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TABLE triage_memory_audit_new (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 lesson_id INTEGER NOT NULL REFERENCES triage_memory_lessons(id),
 actor_id INTEGER REFERENCES users(id),
 event_type TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)),
 created_at TEXT NOT NULL,
 decision_source TEXT NOT NULL DEFAULT 'analyst' CHECK(decision_source IN ('analyst','system_policy')),
 policy_version TEXT,
 CHECK((decision_source='analyst' AND actor_id IS NOT NULL) OR (decision_source='system_policy' AND actor_id IS NULL AND policy_version IS NOT NULL))
);
INSERT INTO triage_memory_audit_new (id,lesson_id,actor_id,event_type,payload,created_at) SELECT id,lesson_id,actor_id,event_type,payload,created_at FROM triage_memory_audit;
DROP TABLE triage_memory_audit;
ALTER TABLE triage_memory_audit_new RENAME TO triage_memory_audit;
CREATE INDEX idx_memory_audit ON triage_memory_audit(lesson_id,id);
CREATE TRIGGER memory_audit_update BEFORE UPDATE ON triage_memory_audit BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_audit_delete BEFORE DELETE ON triage_memory_audit BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TRIGGER memory_audit_replace BEFORE INSERT ON triage_memory_audit WHEN EXISTS(SELECT 1 FROM triage_memory_audit WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT,'memory is append-only'); END;
CREATE TABLE verdict_memory_contributions_new (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 source_verdict_ref TEXT NOT NULL REFERENCES analyst_verdict_events(verdict_ref),
 actor_id INTEGER REFERENCES users(id),
 scope TEXT NOT NULL CHECK(scope IN ('exact','narrow')),
 primary_lesson_id INTEGER NOT NULL REFERENCES triage_memory_lessons(id),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 decision_source TEXT NOT NULL DEFAULT 'analyst' CHECK(decision_source IN ('analyst','system_policy')),
 policy_version TEXT,
 CHECK((decision_source='analyst' AND actor_id IS NOT NULL) OR (decision_source='system_policy' AND actor_id IS NULL AND policy_version IS NOT NULL)),
 UNIQUE(source_verdict_ref,scope)
);
INSERT INTO verdict_memory_contributions_new (id,source_alert_id,source_verdict_ref,actor_id,scope,primary_lesson_id,request_id,request_payload) SELECT id,source_alert_id,source_verdict_ref,actor_id,scope,primary_lesson_id,request_id,request_payload FROM verdict_memory_contributions;
DROP TABLE verdict_memory_contributions;
ALTER TABLE verdict_memory_contributions_new RENAME TO verdict_memory_contributions;
CREATE INDEX verdict_memory_source ON verdict_memory_contributions(source_alert_id,id);
CREATE TRIGGER vm_contribution_update BEFORE UPDATE ON verdict_memory_contributions BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER vm_contribution_delete BEFORE DELETE ON verdict_memory_contributions BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER vm_contribution_replace BEFORE INSERT ON verdict_memory_contributions WHEN EXISTS(SELECT 1 FROM verdict_memory_contributions WHERE id=NEW.id OR (source_verdict_ref=NEW.source_verdict_ref AND scope=NEW.scope) OR request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TABLE conclusion_memory_contributions_new (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 source_case_id INTEGER NOT NULL REFERENCES tier2_cases(id),
 conclusion_event_id INTEGER NOT NULL REFERENCES tier2_case_events(id),
 actor_id INTEGER REFERENCES users(id),
 scope TEXT NOT NULL CHECK(scope IN ('exact','narrow')),
 primary_lesson_id INTEGER NOT NULL REFERENCES triage_memory_lessons(id),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 decision_source TEXT NOT NULL DEFAULT 'analyst' CHECK(decision_source IN ('analyst','system_policy')),
 policy_version TEXT,
 CHECK((decision_source='analyst' AND actor_id IS NOT NULL) OR (decision_source='system_policy' AND actor_id IS NULL AND policy_version IS NOT NULL)),
 UNIQUE(conclusion_event_id,scope)
);
INSERT INTO conclusion_memory_contributions_new (id,source_alert_id,source_case_id,conclusion_event_id,actor_id,scope,primary_lesson_id,request_id,request_payload) SELECT id,source_alert_id,source_case_id,conclusion_event_id,actor_id,scope,primary_lesson_id,request_id,request_payload FROM conclusion_memory_contributions;
DROP TABLE conclusion_memory_contributions;
ALTER TABLE conclusion_memory_contributions_new RENAME TO conclusion_memory_contributions;
CREATE INDEX conclusion_memory_source ON conclusion_memory_contributions(source_alert_id,id);
CREATE TRIGGER cm_contribution_update BEFORE UPDATE ON conclusion_memory_contributions BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER cm_contribution_delete BEFORE DELETE ON conclusion_memory_contributions BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER cm_contribution_replace BEFORE INSERT ON conclusion_memory_contributions WHEN EXISTS(SELECT 1 FROM conclusion_memory_contributions WHERE id=NEW.id OR (conclusion_event_id=NEW.conclusion_event_id AND scope=NEW.scope) OR request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
