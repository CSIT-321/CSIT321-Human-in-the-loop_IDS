CREATE TABLE analyst_work (
 operational_alert_id INTEGER PRIMARY KEY REFERENCES operational_alerts_v2(id),
 status TEXT NOT NULL CHECK(status IN ('available','in_review','completed','escalated')),
 revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
 owner_actor_id INTEGER REFERENCES users(id),
 owner_name TEXT,
 claimed_at TEXT,
 round_ref TEXT REFERENCES analyst_claim_rounds(round_ref),
 finished_at TEXT,
 finished_by_actor_id INTEGER REFERENCES users(id),
 finished_by_name TEXT,
 verdict_ref TEXT REFERENCES analyst_verdict_events(verdict_ref),
 CHECK((status='in_review' AND owner_actor_id IS NOT NULL AND owner_name IS NOT NULL AND claimed_at IS NOT NULL AND round_ref IS NOT NULL)
    OR (status!='in_review' AND owner_actor_id IS NULL)),
 CHECK(status NOT IN ('completed','escalated') OR finished_at IS NOT NULL)
);
CREATE TABLE analyst_claim_rounds (
 round_ref TEXT PRIMARY KEY,
 operational_alert_id INTEGER NOT NULL REFERENCES analyst_work(operational_alert_id),
 work_revision INTEGER NOT NULL,
 policy_version TEXT NOT NULL,
 window_ms INTEGER NOT NULL CHECK(window_ms>0),
 started_at TEXT NOT NULL,
 closes_at TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','claimed','contended','ineligible')),
 finalized_at TEXT,
 owner_actor_id INTEGER REFERENCES users(id),
 CHECK((status='claimed' AND owner_actor_id IS NOT NULL) OR (status!='claimed' AND owner_actor_id IS NULL)),
 CHECK((status='pending' AND finalized_at IS NULL) OR (status!='pending' AND finalized_at IS NOT NULL))
);
CREATE UNIQUE INDEX one_pending_claim_round ON analyst_claim_rounds(operational_alert_id) WHERE status='pending';
CREATE TABLE analyst_claim_intents (
 request_id TEXT PRIMARY KEY,
 round_ref TEXT NOT NULL REFERENCES analyst_claim_rounds(round_ref),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 actor_name TEXT NOT NULL,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 created_at TEXT NOT NULL
);
CREATE TABLE analyst_work_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 operational_alert_id INTEGER NOT NULL REFERENCES analyst_work(operational_alert_id),
 event_type TEXT NOT NULL,
 actor_id INTEGER REFERENCES users(id),
 decision_source TEXT NOT NULL CHECK(decision_source IN ('analyst','system_policy','historical_migration')),
 round_ref TEXT REFERENCES analyst_claim_rounds(round_ref),
 created_at TEXT NOT NULL,
 detail TEXT NOT NULL CHECK(json_valid(detail))
);
CREATE TRIGGER work_no_delete BEFORE DELETE ON analyst_work
BEGIN SELECT RAISE(ABORT,'human work history cannot be deleted'); END;
CREATE TRIGGER work_no_replace BEFORE INSERT ON analyst_work WHEN EXISTS(SELECT 1 FROM analyst_work WHERE operational_alert_id=NEW.operational_alert_id)
BEGIN SELECT RAISE(ABORT,'human work cannot be replaced'); END;
CREATE TRIGGER work_revision BEFORE UPDATE ON analyst_work
WHEN NEW.operational_alert_id!=OLD.operational_alert_id OR NEW.revision!=OLD.revision+1 OR OLD.status IN ('completed','escalated')
 OR (OLD.status='in_review' AND NEW.status NOT IN ('completed','escalated'))
 OR (OLD.status='available' AND NEW.status NOT IN ('available','in_review'))
BEGIN SELECT RAISE(ABORT,'invalid human work revision or terminal transition'); END;
CREATE TRIGGER work_owner_round BEFORE UPDATE ON analyst_work
WHEN NEW.status='in_review' AND NOT EXISTS(SELECT 1 FROM analyst_claim_rounds r
 WHERE r.round_ref=NEW.round_ref AND r.operational_alert_id=NEW.operational_alert_id
 AND r.status='claimed' AND r.owner_actor_id=NEW.owner_actor_id)
BEGIN SELECT RAISE(ABORT,'owner must match the finalized claim round'); END;
CREATE TRIGGER claim_round_no_delete BEFORE DELETE ON analyst_claim_rounds
BEGIN SELECT RAISE(ABORT,'claim rounds are retained'); END;
CREATE TRIGGER claim_round_no_replace BEFORE INSERT ON analyst_claim_rounds WHEN EXISTS(SELECT 1 FROM analyst_claim_rounds WHERE round_ref=NEW.round_ref)
BEGIN SELECT RAISE(ABORT,'claim rounds cannot be replaced'); END;
CREATE TRIGGER claim_round_finalize_once BEFORE UPDATE ON analyst_claim_rounds
WHEN OLD.status!='pending' OR NEW.status='pending' OR NEW.round_ref!=OLD.round_ref
 OR NEW.operational_alert_id!=OLD.operational_alert_id OR NEW.work_revision!=OLD.work_revision
 OR NEW.started_at!=OLD.started_at OR NEW.closes_at!=OLD.closes_at OR NEW.policy_version!=OLD.policy_version OR NEW.window_ms!=OLD.window_ms
BEGIN SELECT RAISE(ABORT,'claim round can only be finalized once'); END;
CREATE TRIGGER claim_intent_no_update BEFORE UPDATE ON analyst_claim_intents
BEGIN SELECT RAISE(ABORT,'claim intents are immutable'); END;
CREATE TRIGGER claim_intent_no_delete BEFORE DELETE ON analyst_claim_intents
BEGIN SELECT RAISE(ABORT,'claim intents are immutable'); END;
CREATE TRIGGER claim_intent_no_replace BEFORE INSERT ON analyst_claim_intents WHEN EXISTS(SELECT 1 FROM analyst_claim_intents WHERE request_id=NEW.request_id)
BEGIN SELECT RAISE(ABORT,'claim intents are immutable'); END;
CREATE TRIGGER work_event_no_update BEFORE UPDATE ON analyst_work_events
BEGIN SELECT RAISE(ABORT,'work events are immutable'); END;
CREATE TRIGGER work_event_no_delete BEFORE DELETE ON analyst_work_events
BEGIN SELECT RAISE(ABORT,'work events are immutable'); END;
CREATE TRIGGER work_event_no_replace BEFORE INSERT ON analyst_work_events WHEN EXISTS(SELECT 1 FROM analyst_work_events WHERE id=NEW.id)
BEGIN SELECT RAISE(ABORT,'work events are immutable'); END;

-- Existing canonical judgments are completed history, never invented claims.
INSERT INTO analyst_work(operational_alert_id,status,revision,finished_at,finished_by_actor_id,finished_by_name,verdict_ref)
SELECT v.operational_alert_id,'completed',1,json_extract(v.snapshot,'$.createdAt'),v.actor_id,
 json_extract(v.snapshot,'$.actorName'),v.verdict_ref
FROM analyst_verdict_events v WHERE v.revision=(SELECT max(v2.revision) FROM analyst_verdict_events v2 WHERE v2.operational_alert_id=v.operational_alert_id);
-- Historical manual handoffs without a Verdict are no longer active Tier 1 work.
INSERT INTO analyst_work(operational_alert_id,status,revision,finished_at,finished_by_actor_id,finished_by_name)
SELECT c.primary_operational_alert_id,'escalated',1,c.created_at,c.created_by_actor_id,u.display_name
FROM tier2_cases c JOIN users u ON u.id=c.created_by_actor_id
WHERE c.decision_source='analyst' AND NOT EXISTS(SELECT 1 FROM analyst_work w WHERE w.operational_alert_id=c.primary_operational_alert_id);
INSERT INTO analyst_work_events(operational_alert_id,event_type,actor_id,decision_source,created_at,detail)
SELECT operational_alert_id,'WORK_HISTORY_MIGRATED',NULL,'historical_migration',finished_at,
 json_object('status',status,'historicalActorId',finished_by_actor_id,'verdictRef',verdict_ref)
FROM analyst_work;
