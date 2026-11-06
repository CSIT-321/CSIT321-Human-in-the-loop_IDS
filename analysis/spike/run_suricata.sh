#!/usr/bin/env bash
# Spike B: run Suricata 8.0.7 offline on one capture. Config = the shipped YAML with only three local paths
# changed (same rule LCK used in docs/real-suricata-pcap-validation.md). No network capture, no service.
#   bash run_suricata.sh <pcap> <output-dir>
set -euo pipefail
T="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids/.tools"
S="$T/suricata/PFiles/Suricata"
CONF="$T/suricata-spike.yaml"
RULES="$T/et-compatible.rules"
if [ ! -f "$CONF" ]; then
  sed -e "s#^default-rule-path: .*#default-rule-path: $T/et/rules/#" \
      -e "s#^classification-file: .*#classification-file: $T/et/rules/classification.config#" \
      -e "s#^reference-config-file: .*#reference-config-file: $S/reference.config#" \
      "$S/suricata.yaml" > "$CONF"
fi
if [ ! -f "$RULES" ]; then
  # All ET Open rules; disable only the file.magic rules this Windows build cannot load (no libmagic).
  cat "$T"/et/rules/*.rules | sed -E '/file\.magic/ s/^alert /# libmagic-unavailable alert /' > "$RULES"
fi
mkdir -p "$2"
"$S/suricata.exe" -T -c "$CONF" -S "$RULES" -l "$2" > "$2/config-test.log" 2>&1 || { tail -5 "$2/config-test.log"; exit 1; }
"$S/suricata.exe" -c "$CONF" -S "$RULES" -r "$1" -l "$2" --runmode single -k none > "$2/run.log" 2>&1
grep -c '"event_type":"alert"' "$2/eve.json" || true
