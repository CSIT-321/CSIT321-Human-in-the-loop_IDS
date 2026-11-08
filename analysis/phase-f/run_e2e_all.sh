#!/usr/bin/env bash
# Run every self-contained Playwright config in turn. Each config starts its own API on a temporary
# database (fixture scripts use TemporaryDirectory) and its own Vite; data/demo.db is never opened.
# Excluded (need hand-started servers or real capture data): workspaces, presentation,
# persistent-workstation, real-suricata.
cd "${E2E_WEB:-/c/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids/apps/web}" || exit 2
export HITL_PYTHON="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids/.venv/Scripts/python.exe"
OUT="${E2E_OUT:-$LOCALAPPDATA/Temp/hitl-review/e2e}"
mkdir -p "$OUT"; : > "$OUT/summary.txt"
CONFIGS="${E2E_CONFIGS:-playwright.config.ts playwright.routing.config.ts playwright.refinement.config.ts playwright.direct.config.ts
playwright.unified.config.ts playwright.suricata.config.ts playwright.operational-queue.config.ts playwright.prospective.config.ts
playwright.pre-freeze.config.ts playwright.verdict.config.ts playwright.verdict-safety.config.ts playwright.assistance.config.ts
playwright.reclassification.config.ts playwright.conclusion-memory.config.ts playwright.resolution.config.ts
playwright.automatic-learning.config.ts playwright.verdict-memory.config.ts playwright.f2-boundary.config.ts
playwright.shared-work.config.ts playwright.current-surface.config.ts playwright.final-golden-path.config.ts}"
for c in $CONFIGS; do
  name="${c#playwright.}"; name="${name%.ts}"; name="${name%.config}"; [ "$name" = "config" ] && name="default"
  start=$(date +%s)
  timeout 900 npx playwright test -c "$c" > "$OUT/$name.log" 2>&1; code=$?
  line=$(grep -E "^\s+[0-9]+ (passed|failed|flaky|skipped|did not run)" "$OUT/$name.log" | tr -s ' ' | tr '\n' ' ')
  printf '%-22s exit=%-3s %4ss  %s\n' "$name" "$code" "$(( $(date +%s) - start ))" "$line" | tee -a "$OUT/summary.txt"
done
echo DONE | tee -a "$OUT/summary.txt"
