#!/usr/bin/env bash
# C4 red check: each planted defect must fail at least one test in OperationalEvidenceFlow.test.tsx.
set -u
W="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids/apps/web"
cd "$W" || exit 2
F=src/features/alert/OperationalEvidence.tsx
P=src/features/alert/DetectorProvenance.tsx
cp "$F" "$LOCALAPPDATA/Temp/hitl-review/c4-oe.bak"; cp "$P" "$LOCALAPPDATA/Temp/hitl-review/c4-dp.bak"
restore() { cp "$LOCALAPPDATA/Temp/hitl-review/c4-oe.bak" "$F"; cp "$LOCALAPPDATA/Temp/hitl-review/c4-dp.bak" "$P"; }
trap restore EXIT
run() { echo "$1:"; timeout 200 npx vitest run src/features/alert/OperationalEvidenceFlow.test.tsx 2>&1 | grep -E "Tests " ; restore; }

sed -i 's/return typeof fusion === "number" ? fusion : alert.detectorEvidence.confidence;/return alert.detectorEvidence.confidence;/' "$F"
run "1. confidence ignores the legacy fusion confidence"
sed -i 's/const shown = confidence === undefined ? detector.confidence : confidence;/const shown = detector.confidence;/' "$P"
run "2. provenance ignores the confidence override"
sed -i 's/const conditions = fields.matched_conditions ?? fields.matchedConditions;/const conditions = fields.matchedConditions;/' "$F"
run "3. rule table reads only camelCase conditions"
sed -i 's/{legacy \&\& typeof explanation === "string"/{false \&\& typeof explanation === "string"/' "$F"
run "4. combined explanation not shown"
sed -i 's/agreement={legacy ? AGREEMENT\[detector.evidenceClass\] ?? null : null}/agreement={null}/' "$F"
run "5. agreement line not shown"
sed -i 's/signature_override: "Rule overrides the model",/signature_override: "Rule and model agree",/' "$F"
run "6. override labelled as agreement"
sed -i 's#return isFlow(alert) \&\& typeof ref === "string" \&\& /^AL-\\d+$/.test(ref) ? ref : null;#return typeof ref === "string" ? ref : null;#' "$F"
run "7. short name shown for every source"
echo "restored:"; timeout 200 npx vitest run src/features/alert/OperationalEvidenceFlow.test.tsx 2>&1 | grep -E "Tests "
