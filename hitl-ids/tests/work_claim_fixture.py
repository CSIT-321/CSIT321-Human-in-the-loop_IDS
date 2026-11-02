"""Explicit ownership prerequisite for existing operational judgment scenarios."""
from unittest.mock import patch
from uuid import uuid4
from packages.detection import analyst_work as work

def claim_work(conn,alert,actor_id=1):
    view=work.read_work(conn,alert.id,actor_id)
    if view.is_owner or view.status in ('completed','escalated') or view.status is None:
        return view
    # Tests that already deferred an unowned item must explicitly recall it first.
    if not view.can_claim:
        from packages.detection.selective_review import read_review,decide_review,ReviewCommand
        current=read_review(conn,alert.operational_alert_ref)
        decide_review(conn,alert.operational_alert_ref,actor_id=actor_id,action='require_review',request=ReviewCommand(
            request_id=uuid4(),expected_version=current.version,reason='Test analyst explicitly requires active review'))
    with patch.object(work,'policy',return_value={'version':'analyst-work-claim-v1','claimArbitrationWindowMs':1}):
        result=work.claim(conn,alert.operational_alert_ref,actor_id=actor_id,request=work.ClaimCommand(request_id=uuid4(),expected_revision=view.revision))
    assert result.outcome=='claimed'
    return result.work
