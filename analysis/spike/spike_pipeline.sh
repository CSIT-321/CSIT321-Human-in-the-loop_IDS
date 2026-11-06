#!/usr/bin/env bash
# Spike B: repair -> Suricata -> CICFlowMeter for each downloaded host capture of one day.
#   bash spike_pipeline.sh <day> [host-ip ...]
set -euo pipefail
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
A="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/analysis/spike"
T="$H/.tools"; L="$T/cicflowmeter-lib"; JNDIR="$T/cicflowmeter/jnetpcap/win/jnetpcap-1.4.r1425"
DAY="$1"; shift
OUT="$H/data/spike/$DAY"; mkdir -p "$OUT/repaired" "$OUT/flows"
CP="$(cygpath -w "$L/classes");"; for f in "$L"/*.jar "$JNDIR/jnetpcap.jar"; do CP="$CP$(cygpath -w "$f");"; done
for ip in "$@"; do
  src=$(ls "$H/data/raw/pcap/$DAY/pcap/"*"$ip" | head -1)
  rep="$OUT/repaired/$ip.pcap"
  [ -s "$rep" ] || "$H/.venv/Scripts/python.exe" "$H/scripts/repair_pcap.py" "$src" "$rep"
  [ -s "$OUT/suricata-$ip/eve.json" ] || { rm -rf "$OUT/suricata-$ip"; echo "suricata $ip alerts: $(bash "$A/run_suricata.sh" "$rep" "$OUT/suricata-$ip")"; }
  if [ ! -s "$OUT/flows/$ip.pcap_Flow.csv" ]; then
    (cd "$OUT" && java -Djava.library.path="$(cygpath -w "$JNDIR")" -cp "$CP" cic.cs.unb.ca.ifm.Cmd \
      "$(cygpath -w "$rep")" "$(cygpath -w "$OUT/flows")" 2>&1 | tr '\r' '\n' | grep -E "done|Packet stats")
  fi
done
