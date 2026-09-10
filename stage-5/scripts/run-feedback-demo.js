const fs = require('fs');
const path = require('path');

const {
  loadJsonFile,
  adjustAlertsWithFeedback,
  buildEvaluatorRecords,
  stripGroundTruthFields,
  summariseFeedbackResults,
} = require('../core/feedback-engine');
const {
  resolveEffectiveFeedbackEvents,
} = require('../core/feedback-aggregation-engine');

const repoRoot = path.resolve(__dirname, '..', '..');
const fusedAlertsPath = path.join(repoRoot, 'stage-4', 'outputs', 'fusion-alerts.sample.json');
const analystFeedbackPath = path.join(repoRoot, 'stage-5', 'data', 'analyst-feedback.sample.json');
const exceptionMemoryPath = path.join(repoRoot, 'stage-5', 'data', 'exception-memory.sample.json');
const adaptationConfigPath = path.join(repoRoot, 'stage-5', 'config', 'adaptation-config.json');
const groundTruthPath = path.join(repoRoot, 'stage-1', 'data', 'processed', 'ground-truth.json');
const outputDir = path.join(repoRoot, 'stage-5', 'outputs');
const evaluationDir = path.join(repoRoot, 'stage-5', 'evaluation');
const adjustedAlertsPath = path.join(outputDir, 'feedback-adjusted-alerts.sample.json');
const generatedHistoricalMemoryPath = path.join(outputDir, 'historical-feedback-memory.generated.json');
const evaluatorRecordsPath = path.join(evaluationDir, 'feedback-evaluation-records.json');
const evaluationJsonPath = path.join(evaluationDir, 'feedback-evaluation-summary.json');
const evaluationMarkdownPath = path.join(evaluationDir, 'feedback-evaluation-summary.md');

function renderCounter(counter) {
  const entries = Object.entries(counter || {}).sort((a, b) => b[1] - a[1]);
  if (!entries.length) {
    return '- none';
  }
  return entries.map(([key, value]) => `- ${key}: ${value}`).join('\n');
}

function renderSummaryMarkdown(summary) {
  const lines = [
    '# Stage 5 Feedback Evaluation Summary',
    '',
    'Stage 5 applies append-only analyst feedback events to Stage 4 fused alerts through deterministic similarity matching, historical aggregation, eligibility gates, and guardrails.',
    '',
    'The current evaluation uses a frozen calibration / held-out split. It does not claim chronological temporal evaluation because the current sample is not ordered by reliable operational time.',
    '',
    'Ground truth is joined only after detection, fusion, feedback aggregation, and priority adaptation for evaluator-only records. It is not written to the analyst-facing alert artifact and is not used as adaptation input.',
    '',
    'This is a prototype workload and priority evaluation, not production IDS performance.',
    '',
    '## Overall Counts',
    '',
    `- Total alerts: ${summary.totalAlerts}`,
    `- Evaluation split: ${summary.evaluationSplit}`,
    `- Calibration alert ids: ${summary.calibrationAlertCount}`,
    `- Held-out alerts ranked: ${summary.heldOutAlertCount}`,
    `- Held-out feedback ignored during ranking: ${summary.ignoredHeldOutFeedbackCount}`,
    `- Manual exception memory enabled: ${summary.manualExceptionMemoryEnabled}`,
    `- Alerts adjusted: ${summary.alertsAdjusted}`,
    `- Alerts unchanged: ${summary.alertsUnchanged}`,
    `- Direct feedback applied count: ${summary.directFeedbackAppliedCount}`,
    `- Unmatched direct feedback count: ${summary.unmatchedDirectFeedbackCount}`,
    `- Historical feedback adaptation count: ${summary.historicalFeedbackAdaptationCount}`,
    `- Exception memory applied count: ${summary.exceptionMemoryAppliedCount}`,
    `- Ignored exception count: ${summary.ignoredExceptionCount}`,
    `- Guardrail applied count: ${summary.guardrailAppliedCount}`,
    `- Score adjustment guardrail count: ${summary.scoreAdjustmentGuardrailCount}`,
    `- Exception rejected by trust gate count: ${summary.exceptionRejectedByTrustGateCount}`,
    `- Low confidence exception ignored count: ${summary.lowConfidenceExceptionIgnoredCount}`,
    `- Insufficient feedback exception ignored count: ${summary.insufficientFeedbackExceptionIgnoredCount}`,
    '',
    '## Guardrail Metric Clarification',
    '',
    '`guardrailAppliedCount` is a broad combined count. It includes both score-limiting guardrails and exception trust-gate rejections.',
    '',
    '`scoreAdjustmentGuardrailCount` counts cases where a risk score adjustment was actually limited by a safety rule, such as maximum reduction, Critical alert floor, or Infiltration floor.',
    '',
    '`exceptionRejectedByTrustGateCount` counts exception memory matches that were ignored because they did not meet trust requirements. This includes low confidence exceptions and exceptions with insufficient feedback evidence.',
    '',
    'Trust-gate rejections do not change the risk score. For report writing, use the split metrics when describing whether feedback changed priority or whether an exception was rejected before adjustment.',
    '',
    '## Adaptation Coverage',
    '',
    `- Similarity match count: ${summary.similarityMatchCount}`,
    `- Similarity match coverage: ${summary.similarityMatchCoverage}`,
    `- Adaptation eligible count: ${summary.adaptationEligibleCount}`,
    `- Adaptation eligibility coverage: ${summary.adaptationEligibilityCoverage}`,
    `- Actual adaptation count: ${summary.actualAdaptationCount}`,
    `- Actual adaptation coverage: ${summary.actualAdaptationCoverage}`,
    `- Generated historical memory count: ${summary.generatedHistoricalMemoryCount}`,
    `- Low evidence coverage rejection count: ${summary.lowEvidenceCoverageRejectionCount}`,
    `- Low similarity rejection count: ${summary.lowSimilarityRejectionCount}`,
    '',
    '## Risk Before And After Feedback',
    '',
    `- Average risk before feedback: ${summary.averageRiskBeforeFeedback}`,
    `- Average risk after feedback: ${summary.averageRiskAfterFeedback}`,
    `- Average risk change: ${summary.averageRiskChange}`,
    `- High-risk threshold: ${summary.highRiskThreshold}`,
    `- High-risk alerts before: ${summary.highRiskAlertsBefore}`,
    `- High-risk alerts after: ${summary.highRiskAlertsAfter}`,
    '',
    '## Review Queue Before And After Feedback',
    '',
    `- Review queue before: ${summary.reviewQueueBefore}`,
    `- Review queue after: ${summary.reviewQueueAfter}`,
    `- Reviewed benign before: ${summary.reviewedBenignBefore}`,
    `- Reviewed benign after: ${summary.reviewedBenignAfter}`,
    `- Reviewed malicious before: ${summary.reviewedMaliciousBefore}`,
    `- Reviewed malicious after: ${summary.reviewedMaliciousAfter}`,
    '',
    '## Ground Truth Evaluation',
    '',
    `- Evaluated with ground truth count: ${summary.evaluatedWithGroundTruthCount || 0}`,
    `- Benign high-risk before: ${summary.benignHighRiskBefore}`,
    `- Benign high-risk after: ${summary.benignHighRiskAfter}`,
    `- Malicious high-risk before: ${summary.maliciousHighRiskBefore}`,
    `- Malicious high-risk after: ${summary.maliciousHighRiskAfter}`,
    `- True positive suppression count: ${summary.truePositiveSuppressionCount}`,
    `- Infiltration adjusted count: ${summary.infiltrationAdjustedCount}`,
    `- Infiltration guardrail count: ${summary.infiltrationGuardrailCount}`,
    '',
    '## Count By Analyst Feedback Status',
    '',
    renderCounter(summary.countByAnalystFeedbackStatus),
    '',
    '## Count By Adaptation Source',
    '',
    renderCounter(summary.countByAdaptationSource),
    '',
    '## Count By Feedback Recorded',
    '',
    renderCounter(summary.countByFeedbackRecorded),
    '',
    '## Notes',
    '',
    ...summary.notes.map((note) => `- ${note}`),
  ];

  return `${lines.join('\n')}\n`;
}

function buildFrozenCalibrationHeldOutEvaluation({
  fusedAlerts,
  analystFeedback,
  calibrationFeedback,
  heldOutFeedback,
  exceptionMemory,
  adaptationConfig,
}) {
  const frozenCalibrationFeedback = calibrationFeedback || analystFeedback || [];
  const ignoredHeldOutFeedback = heldOutFeedback || [];
  const fusedAlertIds = new Set(fusedAlerts.map((alert) => String(alert.id)));
  const calibrationFeedbackResolution = resolveEffectiveFeedbackEvents(frozenCalibrationFeedback);
  const calibrationAlertIds = new Set(
    calibrationFeedbackResolution.effectiveEvents
      .filter((feedback) => feedback.alertId && fusedAlertIds.has(String(feedback.alertId)))
      .map((feedback) => String(feedback.alertId))
  );
  const heldOutAlerts = fusedAlerts.filter((alert) => !calibrationAlertIds.has(String(alert.id)));
  const {
    adjustedAlerts,
    unmatchedFeedback,
    generatedHistoricalMemory,
    feedbackResolution,
    useManualExceptionMemory,
  } = adjustAlertsWithFeedback(
    heldOutAlerts,
    [],
    exceptionMemory,
    adaptationConfig,
    {
      historicalFeedbackEvents: frozenCalibrationFeedback,
      similarityReferenceAlerts: fusedAlerts,
      useManualExceptionMemory: false,
    }
  );

  return {
    adjustedAlerts,
    unmatchedFeedback,
    generatedHistoricalMemory,
    feedbackResolution,
    useManualExceptionMemory,
    calibrationFeedbackResolution,
    calibrationAlertIds: [...calibrationAlertIds].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
    heldOutAlerts,
    ignoredHeldOutFeedbackCount: ignoredHeldOutFeedback.length,
    evaluationSplit: 'frozen_calibration_held_out',
  };
}

function main() {
  if (!fs.existsSync(fusedAlertsPath)) {
    throw new Error('Stage 4 fused alerts were not found. Run `node stage-4/scripts/run-fusion-demo.js` before Stage 5.');
  }

  const fusedAlerts = loadJsonFile(fusedAlertsPath);
  const analystFeedback = loadJsonFile(analystFeedbackPath);
  const exceptionMemory = loadJsonFile(exceptionMemoryPath);
  const adaptationConfig = loadJsonFile(adaptationConfigPath);
  const evaluationResult = buildFrozenCalibrationHeldOutEvaluation({
    fusedAlerts,
    analystFeedback,
    exceptionMemory,
    adaptationConfig,
  });

  const {
    adjustedAlerts,
    unmatchedFeedback,
    generatedHistoricalMemory,
    feedbackResolution,
    useManualExceptionMemory,
    calibrationAlertIds,
    heldOutAlerts,
    ignoredHeldOutFeedbackCount,
  } = evaluationResult;

  // Ground truth is loaded only after baseline/adaptive ranking is complete.
  const groundTruth = loadJsonFile(groundTruthPath, null);
  const analystFacingAdjustedAlerts = stripGroundTruthFields(adjustedAlerts);
  const evaluatorRecords = buildEvaluatorRecords(adjustedAlerts, groundTruth);
  const evaluationSummary = summariseFeedbackResults(evaluatorRecords, unmatchedFeedback, groundTruth, {
    feedbackResolution,
    generatedHistoricalMemoryCount: generatedHistoricalMemory.length,
    useManualExceptionMemory,
    config: adaptationConfig,
    evaluationSplit: evaluationResult.evaluationSplit,
    calibrationAlertCount: calibrationAlertIds.length,
    heldOutAlertCount: heldOutAlerts.length,
    ignoredHeldOutFeedbackCount,
  });

  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(evaluationDir, { recursive: true });
  fs.writeFileSync(adjustedAlertsPath, `${JSON.stringify(analystFacingAdjustedAlerts, null, 2)}\n`, 'utf8');
  fs.writeFileSync(generatedHistoricalMemoryPath, `${JSON.stringify(generatedHistoricalMemory, null, 2)}\n`, 'utf8');
  if (process.env.WRITE_FULL_EVALUATOR_RECORDS === '1') {
    fs.writeFileSync(evaluatorRecordsPath, `${JSON.stringify(evaluatorRecords, null, 2)}\n`, 'utf8');
  }
  fs.writeFileSync(evaluationJsonPath, `${JSON.stringify(evaluationSummary, null, 2)}\n`, 'utf8');
  fs.writeFileSync(evaluationMarkdownPath, renderSummaryMarkdown(evaluationSummary), 'utf8');

  console.log(`Fused alerts loaded: ${fusedAlerts.length}`);
  console.log(`Analyst feedback records loaded: ${analystFeedback.length}`);
  console.log(`Evaluation split: ${evaluationResult.evaluationSplit}`);
  console.log(`Calibration alert ids: ${calibrationAlertIds.length}`);
  console.log(`Held-out alerts ranked: ${heldOutAlerts.length}`);
  console.log(`Held-out feedback ignored during ranking: ${ignoredHeldOutFeedbackCount}`);
  console.log(`Exception memory records loaded: ${exceptionMemory.length}`);
  console.log(`Manual exception memory enabled: ${useManualExceptionMemory}`);
  console.log(`Analyst-facing adjusted alerts written: ${analystFacingAdjustedAlerts.length}`);
  console.log(`Generated historical memory records written: ${generatedHistoricalMemory.length}`);
  console.log(`Alerts adjusted: ${evaluationSummary.alertsAdjusted}`);
  console.log(`Direct feedback applied: ${evaluationSummary.directFeedbackAppliedCount}`);
  console.log(`Historical feedback adaptations: ${evaluationSummary.historicalFeedbackAdaptationCount}`);
  console.log(`Unmatched direct feedback: ${evaluationSummary.unmatchedDirectFeedbackCount}`);
  console.log(`Exception memory applied: ${evaluationSummary.exceptionMemoryAppliedCount}`);
  console.log(`Guardrails applied: ${evaluationSummary.guardrailAppliedCount}`);
  console.log(`Similarity match coverage: ${evaluationSummary.similarityMatchCoverage}`);
  console.log(`Adaptation eligibility coverage: ${evaluationSummary.adaptationEligibilityCoverage}`);
  console.log(`Actual adaptation coverage: ${evaluationSummary.actualAdaptationCoverage}`);
  console.log(`Review queue before: ${evaluationSummary.reviewQueueBefore}`);
  console.log(`Review queue after: ${evaluationSummary.reviewQueueAfter}`);
  console.log(`Feedback output: ${adjustedAlertsPath}`);
  console.log(`Evaluator-only records: ${process.env.WRITE_FULL_EVALUATOR_RECORDS === '1' ? evaluatorRecordsPath : 'not written; set WRITE_FULL_EVALUATOR_RECORDS=1 to regenerate locally'}`);
  console.log(`Generated historical memory: ${generatedHistoricalMemoryPath}`);
  console.log(`Evaluation summary: ${evaluationMarkdownPath}`);
}

if (require.main === module) {
  main();
}

module.exports = {
  buildFrozenCalibrationHeldOutEvaluation,
  renderSummaryMarkdown,
};
