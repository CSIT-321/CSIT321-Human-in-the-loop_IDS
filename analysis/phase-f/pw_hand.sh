#!/usr/bin/env bash
# Run the 3 hand-setup Playwright configs (workspaces, presentation, persistent-workstation).
# Each run: a FRESH schema-created disposable database (never data/demo.db), its own API (uvicorn) and Vite,
# then stop both. Recipe: docs/operational-workspaces-and-v3-1-replay.md "Browser verification".
# real-suricata is NOT run here: it needs HITL_REAL_SURICATA_DIR built from PCAPs.
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
PY="$H/.venv/Scripts/python.exe"
OUT="${PW_OUT:-$LOCALAPPDATA/Temp/hitl-review/pw-hand}"; mkdir -p "$OUT"
export HITL_PYTHON="$PY"
API_PORT=8121
for c in ${*:-workspaces presentation persistent-workstation}; do
  WEB_PORT=5221; [ "$c" = persistent-workstation ] && WEB_PORT=5332
  if netstat -ano | grep -E -q "127\.0\.0\.1:($API_PORT|$WEB_PORT)\s+.*LISTENING"; then echo "$c NOT RUN: port $API_PORT or $WEB_PORT busy"; continue; fi
  # Own folder per run: the API keeps control.db and v3-1-replay.db in <db dir>/workspaces/ (apps/api/main.py:112,
  # workspaces.py:40). A shared folder leaked replay state between configs.
  RUN="$LOCALAPPDATA/Temp/hitl-review/hand-$c"; rm -rf "$RUN"; mkdir -p "$RUN"
  DB="$(cygpath -m "$RUN/operational.db")"
  (cd "$H" && "$PY" -c "import sys;from contextlib import closing;from packages.contracts import db;from apps.api import auth
with closing(db.connect(sys.argv[1])) as c: db.create_schema(c);auth.ensure_demo_accounts(c)" "$DB") || { echo "$c schema FAILED"; continue; }
  (cd "$H" && HITL_IDS_DB="$DB" "$PY" -m uvicorn apps.api.main:app --host 127.0.0.1 --port $API_PORT > "$OUT/$c-api.log" 2>&1) &
  API=$!
  (cd "$H/apps/web" && HITL_API_TARGET="http://127.0.0.1:$API_PORT" node node_modules/vite/bin/vite.js --host 127.0.0.1 --port $WEB_PORT --strictPort > "$OUT/$c-vite.log" 2>&1) &
  VITE=$!
  for i in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:$API_PORT/api/health" && curl -s -o /dev/null "http://127.0.0.1:$WEB_PORT" && break; sleep 1; done
  (cd "$H/apps/web" && HITL_WORKSPACES_DB="$DB" HITL_WORKSPACES_WEB_PORT=$WEB_PORT timeout 560 npx playwright test -c "playwright.$c.config.ts" > "$OUT/$c.txt" 2>&1)
  code=$?
  echo "$c exit=$code $(grep -E '^ +[0-9]+ (passed|failed|skipped|flaky)' "$OUT/$c.txt" | tr -s ' ' | tr '\n' ' ')"
  kill $API $VITE 2>/dev/null
  # kill the real children too (Windows: the bash subshell pid is not the python/node pid)
  for p in $API_PORT $WEB_PORT; do
    pid=$(netstat -ano | grep -E "127\.0\.0\.1:$p .*LISTENING" | awk '{print $NF}' | head -1)
    [ -n "$pid" ] && taskkill /PID "$pid" /F /T > /dev/null 2>&1   # MSYS path conversion is off: single slash
  done
  sleep 2
done
