#!/usr/bin/env bash
# C1 verdict bridge red check: each planted defect must fail at least one test.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
cd "$H"
V=packages/detection/analyst_verdict.py
E=packages/detection/tier2_escalation.py
B=packages/detection/verdict_bridge.py
S=packages/detection/feedback/service.py
Q=apps/api/operational_queue.py
T="tests/test_verdict_bridge.py"
run() { .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$LOCALAPPDATA/Temp/hitl-review/pt-red-c1" $T 2>&1 | grep -E "passed|failed|error" | tail -1; }
mutate() { cp "$1" "$1.orig"; .venv/Scripts/python.exe - "$1" "$2" "$3" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p, encoding="utf-8", newline="").read()
assert s.count(old) == 1, old; open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
EOF
}
restore() { mv "$1.orig" "$1"; }

echo "1. verdict not bridged:"
mutate $V 'bridge_verdict(conn,alert,actor_id=actor_id,outcome=verdict.outcome,note=verdict.reason)' 'pass'; run; restore $V
echo "2. escalation not bridged:"
mutate $E 'bridge_escalation(conn, alert, actor_id=actor_id, note=request.reason)' 'pass'; run; restore $E
echo "3. wrong mapping (suspicious -> confirm_true_positive):"
mutate $B '"suspicious": "needs_investigation"' '"suspicious": "confirm_true_positive"'; run; restore $B
echo "4. approved write commits early (submit_feedback instead of apply_feedback):"
mutate $B 'return apply_feedback(conn,' 'from packages.detection.feedback.service import submit_feedback
    return submit_feedback(conn,'; run; restore $B
echo "5. bridge runs after the commit:"
mutate $V '        bridge_verdict(conn,alert,actor_id=actor_id,outcome=verdict.outcome,note=verdict.reason)' '        pass'
cp $V $V.mid; .venv/Scripts/python.exe - $V <<'EOF'
import sys; p = sys.argv[1]; s = open(p, encoding="utf-8", newline="").read()
old = "        conn.commit();return VerdictMutation(verdict=verdict,replayed=False)"
assert s.count(old) == 1
s = s.replace(old, old.replace("return VerdictMutation", "bridge_verdict(conn,alert,actor_id=actor_id,outcome=verdict.outcome,note=verdict.reason);conn.commit();return VerdictMutation"), 1)
open(p, "w", encoding="utf-8", newline="").write(s)
EOF
rm -f $V.mid; run; restore $V
echo "6. queue ignores the verdict delta:"
mutate $Q 'QUEUE_SCORE = f"max(0, min(100, ({ROUTING_PRIORITY}) + {VERDICT_DELTA}))"' 'QUEUE_SCORE = f"({ROUTING_PRIORITY})"'; run; restore $Q
echo "7. queue uses combined_score alone (drops routing priority and context):"
mutate $Q 'QUEUE_SCORE = f"max(0, min(100, ({ROUTING_PRIORITY}) + {VERDICT_DELTA}))"' 'QUEUE_SCORE = "COALESCE((SELECT d.combined_score FROM alerts d WHERE d.id = a.legacy_alert_id), 0)"'; run; restore $Q
echo "8. every group member gets a verdict:"
mutate $B '    return apply_feedback(conn, alert_id=alert.legacy_alert_id, user_id=actor_id, category=category, note=note)' '    result = None
    for (member,) in conn.execute("SELECT m.legacy_alert_id FROM alert_group_members m JOIN alert_groups g ON g.id = m.group_id WHERE g.representative_operational_alert_id = ?", (alert.id,)).fetchall() or [(alert.legacy_alert_id,)]:
        result = apply_feedback(conn, alert_id=member, user_id=actor_id, category=category, note=note)
    return result'; run; restore $B
echo "9. submit_feedback no longer commits (old API callers):"
mutate $S '    with conn:  # one transaction: commits on success, rolls back on any exception
        return apply_feedback(' '    if True:
        return apply_feedback('; T="tests/test_verdict_bridge.py tests/test_guardrail.py tests/test_learning.py"; run; restore $S
T="tests/test_verdict_bridge.py"
echo "restored:"; run
