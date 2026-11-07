#!/usr/bin/env bash
# B6 red check: each planted defect must fail at least one test in test_tier1_eligibility.py.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
cd "$H"
run() { .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$LOCALAPPDATA/Temp/hitl-review/pt-red-b6" tests/test_tier1_eligibility.py 2>&1 | grep -E "passed|failed|error" | tail -1; }
mutate() { cp "$1" "$1.orig"; .venv/Scripts/python.exe - "$1" "$2" "$3" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p, encoding="utf-8").read()
assert old in s, old; open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
EOF
}
restore() { mv "$1.orig" "$1"; }

E=packages/detection/tier1_eligibility.py
echo "1. rule ignores the routing row (historical counted as current):"
mutate $E 'return "current" if has_system_route(conn, alert_id) else "historical"' 'return "current"'; run; restore $E

echo "2. selective review accepts current only (historical loses review):"
mutate packages/detection/selective_review.py "tier1_status(conn,aid,snapshot.inputs.triage)!='none'" "tier1_status(conn,aid,snapshot.inputs.triage)=='current'"; run; restore packages/detection/selective_review.py

echo "3. routing actions for current only (historical loses its actions):"
mutate packages/detection/routing.py "if status in ('current', 'historical'):" "if status == 'current':"; run; restore packages/detection/routing.py

echo "4. queue SQL drops the routing-row condition:"
mutate $E 'CURRENT_TIER1_SQL = ("s.operational_alert_id IS NOT NULL AND t.handling_route' 'CURRENT_TIER1_SQL = ("1=1 AND t.handling_route'; run; restore $E

echo "5. a module restates the rule inline again:"
mutate packages/detection/analyst_work.py "    return tier1_status(conn,alert_id)=='current'" "    state=read_triage(conn,alert_id)
    return (state.handling_route,state.workflow_stage)==('tier1_review','triage') and tier1_status(conn,alert_id)=='current'"; run; restore packages/detection/analyst_work.py

echo "restored:"; run
git status -s packages apps | grep -v -E "^( M|\?\?) (packages/detection/(analyst_verdict|analyst_work|routing|selective_review|tier1_eligibility)|apps/api/(operational_queue|routing_routes))\.py$" || true
