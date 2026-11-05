#!/usr/bin/env bash
# Progress of the review workers: log size, output lines, start errors.
B="C:/Users/Glenn Ang/fyp-review-wt"
for n in 1 2 3 4 5 6 7 8 9; do
  f="$B/slice-$n/analysis/codebase-review/slice-$n.md"
  lines=none
  [ -f "$f" ] && lines=$(wc -l < "$f")
  size=$(stat -c %s "$B/slice-$n.log" 2>/dev/null || echo 0)
  errs=$(grep -c -i 'UnknownError' "$B/slice-$n.log" 2>/dev/null || echo 0)
  tailline=$(tail -n 1 "$B/slice-$n.log" 2>/dev/null | cut -c1-80)
  echo "slice $n: log=${size}B out=${lines} errors=${errs} last=[${tailline}]"
done
