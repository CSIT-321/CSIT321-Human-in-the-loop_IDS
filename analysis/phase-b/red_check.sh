#!/usr/bin/env bash
# Red-capability check for tests/test_flow_routing.py: three deliberate defects, each must fail tests.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
F="$H/packages/detection/flow_routing.py"
cd "$H"
cp "$F" "$F.orig"
run() { .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$LOCALAPPDATA/Temp/hitl-review/pt-b" tests/test_flow_routing.py 2>&1 | grep -E "passed|failed" | tail -1; }
mutate() { .venv/Scripts/python.exe - "$F" "$1" "$2" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p, encoding="utf-8").read()
assert old in s, old; open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
EOF
}
echo "1. candidate flag hard-coded False (LCK's system_routing.py:101 defect):"
.venv/Scripts/python.exe - "$F" <<'EOF'
import sys; p=sys.argv[1]; s=open(p,encoding="utf-8").read()
s=s.replace("tier2_recommended=bool(route.tier2_reasons),","tier2_recommended=False,",1)
s=s.replace("tier2_recommendation_reasons=route.tier2_reasons, decision_source","tier2_recommendation_reasons=(), decision_source",1)
s=s.replace("tier2_recommendation_reasons=json.dumps(list(route.tier2_reasons))","tier2_recommendation_reasons='[]'",1)
open(p,"w",encoding="utf-8").write(s)
EOF
run
cp "$F.orig" "$F"
echo "2. fail-safe removed (errors propagate):"
mutate "    except Exception as error:  # fail-safe" "    except ZeroDivisionError as error:  # fail-safe"
run
cp "$F.orig" "$F"
echo "3. Admin switch ignored:"
mutate "enabled = [reason for reason, on in e1 if on]" "enabled = [reason for reason, on in e1]"
run
cp "$F.orig" "$F" && rm "$F.orig"
echo "restored:"; run
