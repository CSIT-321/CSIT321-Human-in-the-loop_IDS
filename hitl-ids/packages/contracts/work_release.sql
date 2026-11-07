-- Migration 24 (C7, decision D5): a claimed Tier 1 item can be released back to `available`.
--
-- Before: `work_revision` refused every in_review -> available move, so a claim could only end in a verdict or an
-- escalation, and an absent analyst locked the alert for good. The release itself is written by
-- `analyst_work.release` (owner, or administrator with a reason). The database still refuses a release that leaves
-- no audit trace: in_review -> available needs a WORK_RELEASED event for this alert, at the new revision, inserted
-- first in the same transaction.
DROP TRIGGER work_revision;
CREATE TRIGGER work_revision BEFORE UPDATE ON analyst_work
WHEN NEW.operational_alert_id!=OLD.operational_alert_id OR NEW.revision!=OLD.revision+1 OR OLD.status IN ('completed','escalated')
 OR (OLD.status='in_review' AND NEW.status NOT IN ('completed','escalated','available'))
 OR (OLD.status='available' AND NEW.status NOT IN ('available','in_review'))
BEGIN SELECT RAISE(ABORT,'invalid human work revision or terminal transition'); END;
CREATE TRIGGER work_release_audited BEFORE UPDATE ON analyst_work
WHEN OLD.status='in_review' AND NEW.status='available' AND NOT EXISTS(
 SELECT 1 FROM analyst_work_events e WHERE e.operational_alert_id=NEW.operational_alert_id
  AND e.event_type='WORK_RELEASED' AND json_extract(e.detail,'$.revision')=NEW.revision
  AND json_extract(e.detail,'$.previousOwnerActorId')=OLD.owner_actor_id)
BEGIN SELECT RAISE(ABORT,'a release needs its WORK_RELEASED audit event first'); END;
