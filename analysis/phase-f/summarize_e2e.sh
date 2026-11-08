#!/usr/bin/env bash
# Summarise every failing browser test in a batch-run log folder: test name + first error lines.
# Usage: bash summarize_e2e.sh <log-dir> [config ...]
D="$1"; shift
CONFIGS="${*:-$(ls "$D" | sed -n 's/\.log$//p')}"
for c in $CONFIGS; do
  f="$D/$c.log"; [ -f "$f" ] || continue
  echo "=== $c: $(grep -E '^\s+[0-9]+ (passed|failed|did not run|flaky)' "$f" | tr -s ' ' | tr '\n' ' ')"
  awk '/^  [0-9]+\) \[chromium\]/{t=$0; sub(/ ─+$/,"",t); sub(/^ +[0-9]+\) \[chromium\] › /,"",t); n=0; print "  T: " substr(t,1,140)}
       /Error:|Locator:|> *[0-9]+ \|/{ if (n<3) {print "     " substr($0,1,200); n++} }' "$f" | head -40
  grep -m2 -E "Traceback|TypeError:|exited early|Process from config.webServer" "$f" | cut -c1-200
done
