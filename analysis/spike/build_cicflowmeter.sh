#!/usr/bin/env bash
# Build the GintsEngelen CICFlowMeter fork's command-line tool (cic.cs.unb.ca.ifm.Cmd) with plain javac.
# Gradle 4.2 (the fork's wrapper) cannot run on Java 21, so the jars come straight from Maven Central.
set -euo pipefail
T="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids/.tools"
C="$T/cicflowmeter"
L="$T/cicflowmeter-lib"
mkdir -p "$L"
M=https://repo1.maven.org/maven2
for j in \
  org/apache/logging/log4j/log4j-core/2.17.2/log4j-core-2.17.2.jar \
  org/apache/logging/log4j/log4j-api/2.17.2/log4j-api-2.17.2.jar \
  org/apache/logging/log4j/log4j-slf4j-impl/2.17.2/log4j-slf4j-impl-2.17.2.jar \
  org/slf4j/slf4j-api/1.7.25/slf4j-api-1.7.25.jar \
  org/apache/commons/commons-lang3/3.6/commons-lang3-3.6.jar \
  org/apache/commons/commons-math3/3.5/commons-math3-3.5.jar \
  commons-io/commons-io/2.5/commons-io-2.5.jar \
  com/google/guava/guava/23.6-jre/guava-23.6-jre.jar \
  org/apache/tika/tika-core/1.17/tika-core-1.17.jar ; do
  f="$L/$(basename "$j")"
  [ -s "$f" ] || curl -s -f -L -o "$f" "$M/$j"
done
# jnetpcap is not on Maven Central; the fork ships the jar beside its native DLLs.
JN="$C/jnetpcap/win/jnetpcap-1.4.r1425/jnetpcap.jar"
echo "jnetpcap jar: $JN"
CP=""
for f in "$L"/*.jar "$JN"; do CP="$CP$(cygpath -w "$f");"; done
SRC=$(cd "$C/src/main/java" && find . -name "*.java" | grep -v -E "/ui/|/ifm/App.java|/ifm/ui|/weka/|FlowMonitor|chart" )
rm -rf "$L/classes" && mkdir -p "$L/classes"
(cd "$C/src/main/java" && javac -nowarn -encoding UTF-8 -cp "$CP" -d "$(cygpath -w "$L/classes")" $SRC 2>&1 | grep -E "error|^[0-9]+ error" | head -20)
ls "$L/classes/cic/cs/unb/ca/ifm/Cmd.class"
