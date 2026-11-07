-- Migration 23 (B7; review S1-03, S1-11): database guards for rows the schema already calls immutable.
--
-- alerts: detection_score is the anchor that guardrails and family learning read, and
-- feedback_events.original_score must keep agreeing with it. alert_ref, evidence_class, dataset_id and
-- run_id are identity or detection facts. Feedback moves combined_score / severity / queue_* only.
-- A no-op write (the same value) is allowed, so whole-row writers keep working.
CREATE TRIGGER trg_alerts_detection_immutable
BEFORE UPDATE OF detection_score, alert_ref, evidence_class, dataset_id, run_id ON alerts
WHEN OLD.detection_score IS NOT NEW.detection_score
  OR OLD.alert_ref IS NOT NEW.alert_ref
  OR OLD.evidence_class IS NOT NEW.evidence_class
  OR OLD.dataset_id IS NOT NEW.dataset_id
  OR OLD.run_id IS NOT NEW.run_id
BEGIN SELECT RAISE(ABORT, 'alerts detection fields are immutable'); END;

-- operational_triage_state_v2: every V2 alert has exactly one state row; without it every V2 read fails.
CREATE TRIGGER trg_triage_v2_no_delete BEFORE DELETE ON operational_triage_state_v2
BEGIN SELECT RAISE(ABORT, 'V2 triage state cannot be deleted'); END;
