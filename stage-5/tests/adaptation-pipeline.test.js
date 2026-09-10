const test = require('node:test');
const assert = require('node:assert/strict');

const adaptationConfig = require('../config/adaptation-config.json');
const { calculateSimilarity } = require('../core/similarity-engine');
const {
  resolveEffectiveFeedbackEvents,
  aggregateHistoricalFeedback,
  chooseDominantFeedback,
} = require('../core/feedback-aggregation-engine');
const {
  applyGuardrails,
  adjustAlertsWithFeedback,
  buildEvaluatorRecords,
  stripGroundTruthFields,
} = require('../core/feedback-engine');
const {
  buildFrozenCalibrationHeldOutEvaluation,
} = require('../scripts/run-feedback-demo');

function alert(id, overrides = {}) {
  return {
    id,
    fusionRiskScore: 80,
    fusionAttackType: 'Web Attack',
    fusionDecision: 'ML_ONLY_HIGH_CONFIDENCE',
    fusionConfidenceLevel: 'High',
    signatureSeverity: null,
    signatureId: null,
    requiresAnalystReview: true,
    flowFeatureSummary: {
      protocol: 'TCP',
      destinationPort: 80,
    },
    ...overrides,
  };
}

function feedback(feedbackId, alertId, feedbackType, overrides = {}) {
  const feedbackIdText = feedbackId === undefined || feedbackId === null ? '' : String(feedbackId);
  return {
    feedbackId,
    alertId,
    eventType: 'feedback_submitted',
    feedbackType,
    analystId: 'analyst-test',
    timestamp: `2026-07-04T10:${String(Number(feedbackIdText.replace(/\D/g, '')) || 0).padStart(2, '0')}:00Z`,
    reason: 'test feedback',
    appliesToFutureSimilarAlerts: true,
    ...overrides,
  };
}

test('optional similarity fields missing on either side are excluded from the denominator', () => {
  const current = alert('AL-CURRENT', { signatureId: undefined });
  const historical = alert('AL-HISTORICAL', { signatureId: undefined });
  const result = calculateSimilarity(current, historical, adaptationConfig.similarity);

  assert.equal(result.passed, true);
  assert.equal(result.unavailableFields.includes('signatureId'), true);
  assert.equal(result.totalAvailableWeight, 0.85);
  assert.equal(result.evidenceCoverage, 0.85);
  assert.equal(result.score, 1);
});

test('low similarity evidence coverage rejects attack-type-only matches', () => {
  const current = {
    id: 'AL-CURRENT',
    fusionAttackType: 'Web Attack',
  };
  const historical = {
    id: 'AL-HISTORICAL',
    fusionAttackType: 'Web Attack',
  };
  const result = calculateSimilarity(current, historical, adaptationConfig.similarity);

  assert.equal(result.score, 1);
  assert.equal(result.evidenceCoverage < adaptationConfig.similarity.minimumEvidenceCoverage, true);
  assert.equal(result.passed, false);
  assert.equal(result.failureReason, 'below_evidence_coverage_threshold');
});

test('numeric and protocol canonicalisation prevents primitive representation mismatch', () => {
  const current = alert('AL-CURRENT', {
    flowFeatureSummary: {
      protocol: 6,
      destinationPort: '80',
    },
  });
  const historical = alert('AL-HISTORICAL', {
    flowFeatureSummary: {
      protocol: 'TCP',
      destinationPort: 80,
    },
  });
  const result = calculateSimilarity(current, historical, adaptationConfig.similarity);

  assert.equal(result.passed, true);
  assert.equal(result.matchedFields.includes('protocol'), true);
  assert.equal(result.matchedFields.includes('destinationPort'), true);
});

test('missing required similarity fields fail similarity', () => {
  const current = alert('AL-CURRENT', { fusionAttackType: undefined });
  const historical = alert('AL-HISTORICAL');
  const result = calculateSimilarity(current, historical, adaptationConfig.similarity);

  assert.equal(result.passed, false);
  assert.equal(result.failureReason, 'missing_required_field');
});

test('high similarity with low agreement produces no historical adaptation', () => {
  const alerts = [
    alert('AL-TARGET'),
    alert('AL-H1'),
    alert('AL-H2'),
    alert('AL-H3'),
  ];
  const events = [
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    feedback('FB-2', 'AL-H2', 'confirm_true_positive'),
    feedback('FB-3', 'AL-H3', 'confirm_true_positive'),
  ];

  const { adjustedAlerts } = adjustAlertsWithFeedback(alerts, [], [], adaptationConfig, {
    historicalFeedbackEvents: events,
  });
  const target = adjustedAlerts.find((item) => item.id === 'AL-TARGET');

  assert.equal(target.similarityMatched, true);
  assert.equal(target.adaptationEligible, false);
  assert.equal(target.operationalPriorityScore, target.detectionScore);
});

test('low similarity with high agreement produces no historical adaptation', () => {
  const alerts = [
    alert('AL-TARGET', { fusionAttackType: 'DoS' }),
    alert('AL-H1'),
    alert('AL-H2'),
    alert('AL-H3'),
  ];
  const events = [
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    feedback('FB-2', 'AL-H2', 'mark_false_positive'),
    feedback('FB-3', 'AL-H3', 'mark_false_positive'),
  ];

  const { adjustedAlerts } = adjustAlertsWithFeedback(alerts, [], [], adaptationConfig, {
    historicalFeedbackEvents: events,
  });
  const target = adjustedAlerts.find((item) => item.id === 'AL-TARGET');

  assert.equal(target.similarityMatched, false);
  assert.equal(target.adaptationEligible, false);
  assert.equal(target.operationalPriorityScore, target.detectionScore);
});

test('reverted feedback is excluded from active aggregation', () => {
  const events = [
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    {
      feedbackId: 'FB-2',
      eventType: 'feedback_reverted',
      revertsFeedbackId: 'FB-1',
      alertId: 'AL-H1',
      analystId: 'analyst-test',
      timestamp: '2026-07-04T10:05:00Z',
    },
  ];
  const resolved = resolveEffectiveFeedbackEvents(events);

  assert.equal(resolved.effectiveEvents.length, 0);
  assert.deepEqual(resolved.revertedFeedbackIds, ['FB-1']);
});

test('FP amended to TP then amendment reverted restores the previous FP disposition', () => {
  const events = [
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    feedback('FB-2', 'AL-H1', 'confirm_true_positive', {
      supersedesFeedbackId: 'FB-1',
    }),
    {
      feedbackId: 'FB-3',
      eventType: 'feedback_reverted',
      revertsFeedbackId: 'FB-2',
      alertId: 'AL-H1',
      analystId: 'analyst-test',
      timestamp: '2026-07-04T10:05:00Z',
    },
  ];
  const resolved = resolveEffectiveFeedbackEvents(events);

  assert.equal(resolved.integrityErrors.length, 0);
  assert.equal(resolved.effectiveEvents.length, 1);
  assert.equal(resolved.effectiveEvents[0].feedbackId, 'FB-1');
  assert.equal(resolved.effectiveEvents[0].feedbackType, 'mark_false_positive');
});

test('cross-alert revert or supersede references are invalid', () => {
  const resolved = resolveEffectiveFeedbackEvents([
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    feedback('FB-2', 'AL-H2', 'confirm_true_positive', {
      supersedesFeedbackId: 'FB-1',
    }),
    {
      feedbackId: 'FB-3',
      eventType: 'feedback_reverted',
      revertsFeedbackId: 'FB-1',
      alertId: 'AL-H2',
      analystId: 'analyst-test',
      timestamp: '2026-07-04T10:05:00Z',
    },
  ]);

  assert.equal(resolved.integrityErrors.some((error) => error.code === 'cross_alert_supersedesFeedbackId'), true);
  assert.equal(resolved.integrityErrors.some((error) => error.code === 'cross_alert_revertsFeedbackId'), true);
});

test('duplicate feedback IDs are rejected by integrity validation', () => {
  const resolved = resolveEffectiveFeedbackEvents([
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    feedback('FB-1', 'AL-H2', 'confirm_true_positive'),
  ]);

  assert.deepEqual(resolved.duplicateFeedbackIds, ['FB-1']);
  assert.equal(resolved.integrityErrors.some((error) => error.code === 'duplicate_feedback_id'), true);
});

test('formal feedback events without stable IDs are invalid unless legacy generation is explicitly allowed', () => {
  const resolved = resolveEffectiveFeedbackEvents([
    feedback(undefined, 'AL-H1', 'mark_false_positive'),
  ]);
  const legacyResolved = resolveEffectiveFeedbackEvents([
    feedback(undefined, 'AL-H1', 'mark_false_positive'),
  ], { allowGeneratedIds: true });

  assert.equal(resolved.integrityErrors.some((error) => error.code === 'missing_feedback_id'), true);
  assert.equal(legacyResolved.effectiveEvents[0].feedbackId, 'FB-GENERATED-1');
});

test('formal feedback events require eventType unless legacy compatibility inference is explicitly enabled', () => {
  const resolved = resolveEffectiveFeedbackEvents([
    feedback('FB-1', 'AL-H1', 'mark_false_positive', { eventType: undefined }),
  ]);
  const legacyResolved = resolveEffectiveFeedbackEvents([
    feedback('FB-2', 'AL-H1', 'mark_false_positive', { eventType: undefined }),
  ], { inferMissingSubmittedEventType: true });

  assert.equal(resolved.integrityErrors.some((error) => error.code === 'invalid_event_type'), true);
  assert.equal(resolved.effectiveEvents.length, 0);
  assert.equal(legacyResolved.integrityErrors.length, 0);
  assert.equal(legacyResolved.effectiveEvents[0].eventType, 'feedback_submitted');
});

test('feedback event validation rejects missing required fields and invalid enums', () => {
  const resolved = resolveEffectiveFeedbackEvents([
    {
      feedbackId: 'FB-BAD',
      alertId: '',
      analystId: '',
      timestamp: 'not-a-date',
      eventType: 'bad_event',
      feedbackType: 'bad_feedback',
    },
  ]);
  const codes = resolved.integrityErrors.map((error) => error.code);

  assert.equal(codes.includes('missing_alert_id'), true);
  assert.equal(codes.includes('missing_analyst_id'), true);
  assert.equal(codes.includes('invalid_timestamp'), true);
  assert.equal(codes.includes('invalid_event_type'), true);
  assert.equal(resolved.effectiveEvents.length, 0);
});

test('submitted feedback events require a valid feedbackType', () => {
  const missingType = resolveEffectiveFeedbackEvents([
    feedback('FB-1', 'AL-H1', undefined),
  ]);
  const invalidType = resolveEffectiveFeedbackEvents([
    feedback('FB-2', 'AL-H1', 'not_a_valid_type'),
  ]);

  assert.equal(missingType.integrityErrors.some((error) => error.code === 'missing_feedback_type'), true);
  assert.equal(invalidType.integrityErrors.some((error) => error.code === 'invalid_feedback_type'), true);
  assert.equal(missingType.effectiveEvents.length, 0);
  assert.equal(invalidType.effectiveEvents.length, 0);
});

test('revert and supersede references must point to earlier events', () => {
  const resolved = resolveEffectiveFeedbackEvents([
    feedback('FB-1', 'AL-H1', 'mark_false_positive', {
      timestamp: '2026-07-04T10:10:00Z',
    }),
    feedback('FB-2', 'AL-H1', 'confirm_true_positive', {
      supersedesFeedbackId: 'FB-1',
      timestamp: '2026-07-04T10:00:00Z',
    }),
    {
      feedbackId: 'FB-3',
      alertId: 'AL-H1',
      analystId: 'analyst-test',
      eventType: 'feedback_reverted',
      revertsFeedbackId: 'FB-1',
      timestamp: '2026-07-04T10:00:00Z',
    },
  ]);

  assert.equal(resolved.integrityErrors.some((error) => error.code === 'invalid_order_supersedesFeedbackId'), true);
  assert.equal(resolved.integrityErrors.some((error) => error.code === 'invalid_order_revertsFeedbackId'), true);
});

test('ties in historical feedback set conflictDetected and no dominant feedback', () => {
  const result = chooseDominantFeedback({
    mark_false_positive: 2,
    confirm_true_positive: 2,
  });

  assert.equal(result.conflictDetected, true);
  assert.equal(result.dominantFeedback, null);
});

test('workflow feedback does not contribute to future learning aggregation', () => {
  const alerts = new Map([
    ['AL-H1', alert('AL-H1')],
    ['AL-H2', alert('AL-H2')],
  ]);
  const aggregation = aggregateHistoricalFeedback(
    alert('AL-TARGET'),
    alerts,
    [
      feedback('FB-1', 'AL-H1', 'escalate'),
      feedback('FB-2', 'AL-H2', 'needs_investigation'),
    ],
    {
      ...adaptationConfig.aggregation,
      similarity: adaptationConfig.similarity,
    }
  );

  assert.equal(aggregation.learningFeedbackEventCount, 0);
  assert.equal(aggregation.matchedFeedbackCount, 0);
});

test('Expected Activity does not propagate without the stricter context gate', () => {
  const alerts = [
    alert('AL-TARGET'),
    alert('AL-H1'),
    alert('AL-H2'),
    alert('AL-H3'),
    alert('AL-H4'),
    alert('AL-H5'),
  ];
  const events = [
    feedback('FB-1', 'AL-H1', 'mark_expected_activity'),
    feedback('FB-2', 'AL-H2', 'mark_expected_activity'),
    feedback('FB-3', 'AL-H3', 'mark_expected_activity'),
    feedback('FB-4', 'AL-H4', 'mark_expected_activity'),
    feedback('FB-5', 'AL-H5', 'mark_expected_activity'),
  ];

  const { adjustedAlerts } = adjustAlertsWithFeedback(alerts, [], [], adaptationConfig, {
    historicalFeedbackEvents: events,
  });
  const target = adjustedAlerts.find((item) => item.id === 'AL-TARGET');

  assert.equal(target.dominantHistoricalFeedback, 'mark_expected_activity');
  assert.equal(target.adaptationEligible, false);
  assert.equal(target.operationalPriorityScore, target.detectionScore);
});

test('formal adaptive evaluation runs with manual exception memory disabled', () => {
  const alerts = [alert('AL-TARGET')];
  const exceptionMemory = [{
    exceptionId: 'EX-1',
    enabled: true,
    matchFields: {
      fusionAttackType: 'Web Attack',
      fusionDecision: 'ML_ONLY_HIGH_CONFIDENCE',
    },
    feedbackCount: 10,
    confidence: 1,
    riskAdjustment: -30,
  }];

  const { adjustedAlerts, useManualExceptionMemory } = adjustAlertsWithFeedback(
    alerts,
    [],
    exceptionMemory,
    adaptationConfig,
    { useManualExceptionMemory: false }
  );

  assert.equal(useManualExceptionMemory, false);
  assert.equal(adjustedAlerts[0].matchedExceptionId, null);
  assert.equal(adjustedAlerts[0].operationalPriorityScore, adjustedAlerts[0].detectionScore);
});

test('held-out evaluation uses frozen calibration feedback and excludes held-out feedback from adaptation', () => {
  const calibrationAlerts = [
    alert('AL-H1'),
    alert('AL-H2'),
    alert('AL-H3'),
  ];
  const futureAlerts = [
    alert('AL-TARGET'),
    alert('AL-FUTURE-FEEDBACK'),
  ];
  const calibrationFeedback = [
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    feedback('FB-2', 'AL-H2', 'mark_false_positive'),
    feedback('FB-3', 'AL-H3', 'mark_false_positive'),
  ];
  const futureFeedback = [
    feedback('FB-4', 'AL-FUTURE-FEEDBACK', 'confirm_true_positive'),
    feedback('FB-5', 'AL-FUTURE-FEEDBACK', 'confirm_true_positive'),
    feedback('FB-6', 'AL-FUTURE-FEEDBACK', 'confirm_true_positive'),
  ];

  const evaluation = buildFrozenCalibrationHeldOutEvaluation({
    fusedAlerts: [...calibrationAlerts, ...futureAlerts],
    calibrationFeedback,
    heldOutFeedback: futureFeedback,
    analystFeedback: [...calibrationFeedback, ...futureFeedback],
    exceptionMemory: [],
    adaptationConfig,
  });
  const target = evaluation.adjustedAlerts.find((item) => item.id === 'AL-TARGET');

  assert.equal(evaluation.evaluationSplit, 'frozen_calibration_held_out');
  assert.equal(evaluation.ignoredHeldOutFeedbackCount, 3);
  assert.equal(target.dominantHistoricalFeedback, 'mark_false_positive');
  assert.equal(target.operationalPriorityScore, 55);
});

test('invalid calibration feedback does not remove its alert from the held-out evaluation set', () => {
  const fusedAlerts = [
    alert('AL-X'),
    alert('AL-H1'),
    alert('AL-H2'),
    alert('AL-H3'),
  ];
  const calibrationFeedback = [
    feedback('FB-BAD', 'AL-X', 'mark_false_positive', { eventType: undefined }),
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    feedback('FB-2', 'AL-H2', 'mark_false_positive'),
    feedback('FB-3', 'AL-H3', 'mark_false_positive'),
  ];

  const evaluation = buildFrozenCalibrationHeldOutEvaluation({
    fusedAlerts,
    calibrationFeedback,
    exceptionMemory: [],
    adaptationConfig,
  });

  assert.equal(evaluation.calibrationAlertIds.includes('AL-X'), false);
  assert.equal(evaluation.heldOutAlerts.some((item) => item.id === 'AL-X'), true);
  assert.equal(
    evaluation.calibrationFeedbackResolution.integrityErrors.some((error) => error.feedbackId === 'FB-BAD'),
    true
  );
});

test('analyst-facing output contains no ground-truth fields while evaluator records may contain them', () => {
  const adjusted = [{
    ...alert('AL-TARGET'),
    detectionScore: 80,
    operationalPriorityScore: 55,
    groundTruth: 'malicious',
    trueAttackType: 'Web Attack',
    mappedAttackType: 'Web Attack',
    rawLabel: 'SQL Injection',
  }];
  const analystOutput = stripGroundTruthFields(adjusted);
  const evaluatorOutput = buildEvaluatorRecords(analystOutput, {
    'AL-TARGET': {
      groundTruth: 'malicious',
      mappedAttackType: 'Web Attack',
      rawLabel: 'SQL Injection',
    },
  });

  assert.equal('groundTruth' in analystOutput[0], false);
  assert.equal('rawLabel' in analystOutput[0], false);
  assert.equal('trueAttackType' in analystOutput[0], false);
  assert.equal(evaluatorOutput[0].groundTruth, 'malicious');
});

test('successful historical FP future adaptation reduces operational priority', () => {
  const alerts = [
    alert('AL-TARGET'),
    alert('AL-H1'),
    alert('AL-H2'),
    alert('AL-H3'),
  ];
  const events = [
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    feedback('FB-2', 'AL-H2', 'mark_false_positive'),
    feedback('FB-3', 'AL-H3', 'mark_false_positive'),
  ];

  const { adjustedAlerts } = adjustAlertsWithFeedback([alerts[0]], [], [], adaptationConfig, {
    historicalFeedbackEvents: events,
    similarityReferenceAlerts: alerts,
  });
  const target = adjustedAlerts[0];

  assert.equal(target.adaptationSource, 'historical_feedback');
  assert.equal(target.detectionScore, 80);
  assert.equal(target.operationalPriorityScore, 55);
});

test('successful historical TP future adaptation increases operational priority', () => {
  const alerts = [
    alert('AL-TARGET'),
    alert('AL-H1'),
    alert('AL-H2'),
    alert('AL-H3'),
  ];
  const events = [
    feedback('FB-1', 'AL-H1', 'confirm_true_positive'),
    feedback('FB-2', 'AL-H2', 'confirm_true_positive'),
    feedback('FB-3', 'AL-H3', 'confirm_true_positive'),
  ];

  const { adjustedAlerts } = adjustAlertsWithFeedback([alerts[0]], [], [], adaptationConfig, {
    historicalFeedbackEvents: events,
    similarityReferenceAlerts: alerts,
  });
  const target = adjustedAlerts[0];

  assert.equal(target.adaptationSource, 'historical_feedback');
  assert.equal(target.detectionScore, 80);
  assert.equal(target.operationalPriorityScore, 95);
});

test('Detection Score remains immutable after repeated adaptation', () => {
  const alerts = [
    alert('AL-TARGET'),
    alert('AL-H1'),
    alert('AL-H2'),
    alert('AL-H3'),
  ];
  const events = [
    feedback('FB-1', 'AL-H1', 'mark_false_positive'),
    feedback('FB-2', 'AL-H2', 'mark_false_positive'),
    feedback('FB-3', 'AL-H3', 'mark_false_positive'),
  ];

  const first = adjustAlertsWithFeedback(alerts, [], [], adaptationConfig, {
    historicalFeedbackEvents: events,
  }).adjustedAlerts;
  const second = adjustAlertsWithFeedback(first, [], [], adaptationConfig, {
    historicalFeedbackEvents: events,
  }).adjustedAlerts;
  const target = second.find((item) => item.id === 'AL-TARGET');

  assert.equal(target.detectionScore, 80);
  assert.equal(target.fusionRiskScore, 80);
  assert.equal(target.operationalPriorityScore, 55);
});

test('guardrail caps adjustment before adding it to Detection Score and preserves Critical protection', () => {
  const result = applyGuardrails(
    alert('AL-TARGET', {
      fusionRiskScore: 95,
      signatureSeverity: 'Critical',
      fusionConfidenceLevel: 'High',
    }),
    -90,
    adaptationConfig.guardrails
  );

  assert.equal(result.cappedAdjustment, -30);
  assert.equal(result.operationalPriorityScore, 70);
  assert.equal(result.feedbackGuardrailsApplied.includes('critical_alert_floor'), true);
  assert.equal(result.guardrailInterventions.some((item) => (
    item.code === 'critical_alert_floor' && item.configuredValue === 70
  )), true);
});

test('invalid or non-finite adjustment is rejected safely', () => {
  const result = applyGuardrails(alert('AL-TARGET'), Number.POSITIVE_INFINITY, adaptationConfig.guardrails);

  assert.equal(result.cappedAdjustment, 0);
  assert.equal(result.operationalPriorityScore, result.detectionScore);
  assert.equal(result.feedbackGuardrailsApplied.includes('non_finite_adjustment_rejected'), true);
});

test('config-driven guardrail values are reflected in structured metadata', () => {
  const result = applyGuardrails(
    alert('AL-TARGET', {
      fusionRiskScore: 92,
      fusionConfidenceLevel: 'Critical',
    }),
    -50,
    {
      maximumNegativeAdjustment: -20,
      maximumPositiveAdjustment: 12,
      criticalFloor: 85,
      infiltrationFloor: 90,
    }
  );

  assert.equal(result.cappedAdjustment, -20);
  assert.equal(result.operationalPriorityScore, 85);
  assert.equal(result.guardrailInterventions.some((item) => (
    item.code === 'maximum_negative_adjustment_capped' && item.configuredValue === -20
  )), true);
  assert.equal(result.guardrailInterventions.some((item) => (
    item.code === 'critical_alert_floor' && item.configuredValue === 85
  )), true);
});
