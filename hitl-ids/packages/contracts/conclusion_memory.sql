CREATE TABLE conclusion_memory_contributions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 source_case_id INTEGER NOT NULL REFERENCES tier2_cases(id),
 conclusion_event_id INTEGER NOT NULL UNIQUE REFERENCES tier2_case_events(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 scope TEXT NOT NULL CHECK(scope IN ('exact','narrow')),
 primary_lesson_id INTEGER NOT NULL REFERENCES triage_memory_lessons(id),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload))
);
CREATE TABLE conclusion_memory_evidence (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 contribution_id INTEGER NOT NULL REFERENCES conclusion_memory_contributions(id),
 lesson_id INTEGER NOT NULL REFERENCES triage_memory_lessons(id),
 evidence_snapshot TEXT NOT NULL CHECK(json_valid(evidence_snapshot)),
 UNIQUE(contribution_id,lesson_id)
);
CREATE INDEX conclusion_memory_source ON conclusion_memory_contributions(source_alert_id,id);
CREATE INDEX conclusion_memory_lesson ON conclusion_memory_evidence(lesson_id,id);
CREATE TRIGGER cm_contribution_update BEFORE UPDATE ON conclusion_memory_contributions BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER cm_contribution_delete BEFORE DELETE ON conclusion_memory_contributions BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER cm_contribution_replace BEFORE INSERT ON conclusion_memory_contributions WHEN EXISTS(SELECT 1 FROM conclusion_memory_contributions WHERE id=NEW.id OR conclusion_event_id=NEW.conclusion_event_id OR request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER cm_evidence_update BEFORE UPDATE ON conclusion_memory_evidence BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER cm_evidence_delete BEFORE DELETE ON conclusion_memory_evidence BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER cm_evidence_replace BEFORE INSERT ON conclusion_memory_evidence WHEN EXISTS(SELECT 1 FROM conclusion_memory_evidence WHERE id=NEW.id OR (contribution_id=NEW.contribution_id AND lesson_id=NEW.lesson_id)) BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
