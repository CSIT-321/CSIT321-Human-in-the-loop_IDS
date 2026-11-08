#!/usr/bin/env bash
# C3 red check: each planted defect must fail at least one test. Run only when no other test run is active.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
B="$LOCALAPPDATA/Temp/hitl-review/red-c3"; mkdir -p "$B"
PY="$H/.venv/Scripts/python.exe"
PYT="tests/test_tier2_recommendation_panel.py tests/test_routing_workflow.py tests/test_external_operational_admission.py"
WEBT="src/features/alert/Tier2Recommendation.test.tsx src/pages/analyst/V2RoutingPage.test.tsx"

plant() {  # n, file, python-replace-expression-on-text, kind(py|web)
  local n="$1" f="$H/$2" expr="$3" kind="$4"
  cp "$f" "$B/orig"
  "$PY" -c "import sys;p=sys.argv[1];t=open(p,encoding='utf-8',newline='').read();n=$expr;assert n!=t,'NO CHANGE';open(p,'w',encoding='utf-8',newline='').write(n)" "$f" || { echo "$n PLANT FAILED"; cp "$B/orig" "$f"; return; }
  if [ "$kind" = py ]; then (cd "$H" && "$PY" -m pytest -q -x -p no:cacheprovider --basetemp="$B/pt" $PYT > "$B/out.txt" 2>&1)
  else (cd "$H/apps/web" && timeout 300 npx vitest run $WEBT > "$B/out.txt" 2>&1); fi
  local rc=$?
  cp "$B/orig" "$f"
  [ $rc -ne 0 ] && echo "$n caught" || echo "$n MISSED"
}

R=packages/detection/routing.py; RR=apps/api/routing_routes.py
P=apps/web/src/features/alert/Tier2Recommendation.tsx; V=apps/web/src/pages/analyst/V2RoutingPage.tsx
S=apps/web/src/features/alert/SystemRouting.tsx
plant 1 $R "t.replace(\"state.decision_source != 'analyst'\", 'True')" py                       # reject does not close it
plant 2 $R "t.replace(\"return state.tier2_recommended and status == 'historical'\", 'return state.tier2_recommended')" py  # open when not in Tier 1
plant 3 $RR "t.replace(\"actions=[a for a in actions if a!='reject_tier2']\", 'pass')" py              # view offers reject server refuses
plant 4 $RR "t.replace(\"tier2_recommendation_open=status=='current' and recommendation_open(state, status)\", 'tier2_recommendation_open=state.tier2_recommended')" py
plant 5 $P "t.replace('if (!view.tier2RecommendationOpen) return null;', '')" web
plant 6 $P "t.replace('disabled={busy || !text || !can(\"reject_tier2\")}', 'disabled={busy || !text}')" web
plant 7 $P "t.replace('body: { ...pending.current!.body, action } }', 'body: { ...pending.current!.body, action: \"manual_escalate\" } }')" web
plant 8 $P "t.replace('pending.current = null; setReason(\"\");', '').replace('if (!previous || previous.action !== action || previous.body.reason !== text)', 'if (true)')" web
plant 9 $V "t.replace(' && !(compact && view.tier2RecommendationOpen)', '')" web
plant 10 $S "t.replace('!(panelShown && view.tier2RecommendationOpen)', '!view.tier2RecommendationOpen')" web
plant 11 $P "t.replace('reason: text }', 'reason }')" web
