#!/usr/bin/env bash
# Red-capability check for the grouping and D4 tests: deliberate defects, each must fail tests.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
M="$H/scripts/materialize_flow_queue.py"
cd "$H"
cp "$M" "$M.orig"
run() { .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$LOCALAPPDATA/Temp/hitl-review/pt-red" tests/test_flow_queue.py tests/test_flow_routing.py 2>&1 | grep -E "passed|failed" | tail -1; }
mutate() { .venv/Scripts/python.exe - "$M" "$1" "$2" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p, encoding="utf-8").read()
assert old in s, old; open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
EOF
}
echo "1. window ignored (all alerts of one IP merge forever):"
mutate "when - previous[0] > gap" "when - previous[0] > timedelta(days=365)"
run
cp "$M.orig" "$M"
echo "2. unflagged alerts join groups:"
mutate "WHERE a.evidence_class != 'none'" "WHERE a.evidence_class IS NOT NULL"
run
cp "$M.orig" "$M"
echo "3. limit ignored (every E1 group escalates):"
mutate "escalated_groups_this_minute=minute_escalations.get(minute, 0)" "escalated_groups_this_minute=0"
run
cp "$M.orig" "$M"
echo "4. D4 dropped (unflagged flows not projected):"
mutate "WHERE a.evidence_class = 'none' AND o.id IS NULL" "WHERE 0 AND o.id IS NULL"
run
cp "$M.orig" "$M"
echo "5. D4 unflagged projected but never routed (not claimable):"
mutate "for row in conn.execute(UNFLAGGED_UNROUTED).fetchall():" "for row in []:"
run
cp "$M.orig" "$M"
echo "6. D4 unflagged grouped by source (projected twice: group + single):"
mutate "WHERE a.evidence_class != 'none' ORDER BY a.id" "ORDER BY a.id"
run
cp "$M.orig" "$M" && rm "$M.orig"
echo "restored:"; run
