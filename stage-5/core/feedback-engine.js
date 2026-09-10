const fs = require('fs');

const {
  resolveEffectiveFeedbackEvents,
  aggregateHistoricalFeedback,
  buildGeneratedHistoricalMemory,
} = require('./feedback-aggregation-engine');

function loadJsonFile(filePath, fallback = null) {
  if (!fs.existsSync(filePath)) {
    if (fallback !== null) {
      return fallback;
    }
    throw new Error(`JSON file not found: ${filePath}`);
  }
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function clampScore(score) {
  const numericScore = Number(score);
  if (Number.isNaN(numericScore)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(numericScore)));
}

function indexById(records = []) {
  const index = new Map();
  for (const record of records) {
    if (record && record.id !== undefined && record.id !== null) {
      index.set(String(record.id), record);
    }
  }
  return index;
}

function findDirectFeedback(alert, effectiveByAlert = new Map()) {
  return effectiveByAlert.get(String(alert.id)) || null;
}

function matchesException(alert, exception) {
  if (!exception || !exception.enabled || !exception.matchFields) {
    return false;
  }

  return Object.entries(exception.matchFields).every(([field, expectedValue]) => {
    if (!(field in alert)) {
      return false;
    }
    return alert[field] === expectedValue;
  });
}

function findMatchingException(alert, exceptionMemory = []) {
  return exceptionMemory.find((exception) => matchesException(alert, exception)) || null;
}

function applyGuardrails(alert, proposedAdjustment, guardrailConfig = {}) {
  const detectionScore = clampScore(alert.detectionScore ?? alert.fusionRiskScore);
  const guardrailsApplied = [];
  const guardrailInterventions = [];
  let requiresReviewDueToGuardrail = false;
  let cappedAdjustment = Number(proposedAdjustment || 0);
  const maximumNegativeAdjustment = Number(guardrailConfig.maximumNegativeAdjustment ?? -30);
  const maximumPositiveAdjustment = Number(guardrailConfig.maximumPositiveAdjustment ?? 20);

  if (!Number.isFinite(cappedAdjustment)) {
    guardrailsApplied.push('non_finite_adjustment_rejected');
    guardrailInterventions.push({
      code: 'non_finite_adjustment_rejected',
      configuredValue: 0,
      originalValue: proposedAdjustment,
    });
    cappedAdjustment = 0;
  }

  if (cappedAdjustment < maximumNegativeAdjustment) {
    const originalValue = cappedAdjustment;
    cappedAdjustment = maximumNegativeAdjustment;
    guardrailsApplied.push('maximum_negative_adjustment_capped');
    guardrailInterventions.push({
      code: 'maximum_negative_adjustment_capped',
      configuredValue: maximumNegativeAdjustment,
      originalValue,
      appliedValue: cappedAdjustment,
    });
    requiresReviewDueToGuardrail = true;
  }

  if (cappedAdjustment > maximumPositiveAdjustment) {
    const originalValue = cappedAdjustment;
    cappedAdjustment = maximumPositiveAdjustment;
    guardrailsApplied.push('maximum_increase_capped');
    guardrailInterventions.push({
      code: 'maximum_increase_capped',
      configuredValue: maximumPositiveAdjustment,
      originalValue,
      appliedValue: cappedAdjustment,
    });
  }

  let operationalPriorityScore = clampScore(detectionScore + cappedAdjustment);

  if (
    cappedAdjustment < 0
    && (alert.fusionConfidenceLevel === 'Critical' || alert.signatureSeverity === 'Critical')
    && operationalPriorityScore < Number(guardrailConfig.criticalFloor ?? 70)
  ) {
    const configuredFloor = Number(guardrailConfig.criticalFloor ?? 70);
    operationalPriorityScore = configuredFloor;
    guardrailsApplied.push('critical_alert_floor');
    guardrailInterventions.push({
      code: 'critical_alert_floor',
      configuredValue: configuredFloor,
      originalValue: clampScore(detectionScore + cappedAdjustment),
      appliedValue: operationalPriorityScore,
    });
    requiresReviewDueToGuardrail = true;
  }

  if (
    cappedAdjustment < 0
    && alert.fusionAttackType === 'Infiltration'
    && operationalPriorityScore < Number(guardrailConfig.infiltrationFloor ?? 75)
  ) {
    const configuredFloor = Number(guardrailConfig.infiltrationFloor ?? 75);
    operationalPriorityScore = configuredFloor;
    guardrailsApplied.push('infiltration_alert_floor');
    guardrailInterventions.push({
      code: 'infiltration_alert_floor',
      configuredValue: configuredFloor,
      originalValue: clampScore(detectionScore + cappedAdjustment),
      appliedValue: operationalPriorityScore,
    });
    requiresReviewDueToGuardrail = true;
  }

  if (alert.fusionDecision === 'SIGNATURE_ML_DISAGREE') {
    guardrailsApplied.push('signature_ml_disagreement_review_preserved');
    guardrailInterventions.push({
      code: 'signature_ml_disagreement_review_preserved',
      configuredValue: true,
    });
    requiresReviewDueToGuardrail = true;
  }

  return {
    detectionScore,
    operationalPriorityScore,
    currentRiskScore: operationalPriorityScore,
    proposedAdjustment: Number(proposedAdjustment || 0),
    cappedAdjustment,
    feedbackAdjustment: operationalPriorityScore - detectionScore,
    feedbackGuardrailsApplied: [...new Set(guardrailsApplied)],
    guardrailInterventions,
    requiresReviewDueToGuardrail,
  };
}

function applyDirectFeedback(alert, feedback, guardrailConfig = {}) {
  const feedbackMap = {
    confirm_true_positive: {
      adjustment: 10,
      status: 'confirmed_true_positive',
      reason: 'Analyst confirmed this alert as a true positive.',
      forceReview: true,
    },
    mark_false_positive: {
      adjustment: -30,
      status: 'marked_false_positive',
      reason: 'Analyst marked this alert as a false positive.',
      forceReview: false,
    },
    mark_expected_activity: {
      adjustment: -15,
      status: 'marked_expected_activity',
      reason: 'Analyst marked this alert as expected activity.',
      forceReview: false,
    },
    needs_investigation: {
      adjustment: 0,
      status: 'needs_investigation',
      reason: 'Analyst requested continued investigation.',
      forceReview: true,
    },
    escalate: {
      adjustment: 15,
      status: 'escalated',
      reason: 'Analyst escalated this alert for higher priority review.',
      forceReview: true,
    },
    duplicate: {
      adjustment: 0,
      status: 'duplicate',
      reason: 'Analyst marked this alert as a duplicate workflow item.',
      forceReview: false,
    },
    uncertain: {
      adjustment: 0,
      status: 'uncertain',
      reason: 'Analyst marked this alert as uncertain.',
      forceReview: true,
    },
  };
  const feedbackEffect = feedbackMap[feedback.feedbackType];

  if (!feedbackEffect) {
    return null;
  }

  const guarded = applyGuardrails(alert, feedbackEffect.adjustment, guardrailConfig);
  const guardrailLimited = guarded.feedbackGuardrailsApplied.some((code) => (
    code === 'maximum_negative_adjustment_capped'
    || code === 'critical_alert_floor'
    || code === 'infiltration_alert_floor'
  ));

  return {
    ...guarded,
    feedbackRecorded: true,
    priorityAdjusted: guarded.feedbackAdjustment !== 0,
    feedbackApplied: guarded.feedbackAdjustment !== 0,
    proposedFeedbackAdjustment: guarded.proposedAdjustment,
    cappedFeedbackAdjustment: guarded.cappedAdjustment,
    matchedFeedbackId: feedback.feedbackId,
    feedbackReason: `${feedbackEffect.reason} ${feedback.reason || ''}`.trim(),
    analystFeedbackStatus: guardrailLimited ? 'guardrail_limited_adjustment' : feedbackEffect.status,
    forceReview: feedbackEffect.forceReview || guarded.requiresReviewDueToGuardrail,
    adaptationSource: 'direct_feedback',
    adaptationExplanation: 'Direct analyst feedback takes priority for the current alert and remains an append-only event for future aggregation.',
  };
}

function applyExceptionMemory(alert, exception, guardrailConfig = {}) {
  if (!exception) {
    return null;
  }

  const detectionScore = clampScore(alert.detectionScore ?? alert.fusionRiskScore);
  if (Number(exception.confidence || 0) < 0.6) {
    return {
      detectionScore,
      operationalPriorityScore: detectionScore,
      currentRiskScore: detectionScore,
      feedbackApplied: false,
      feedbackRecorded: false,
      priorityAdjusted: false,
      feedbackAdjustment: 0,
      proposedFeedbackAdjustment: 0,
      cappedFeedbackAdjustment: 0,
      matchedExceptionId: exception.exceptionId,
      matchedExceptionType: exception.patternType,
      feedbackReason: 'Matching manual exception memory was ignored because confidence is below 0.6.',
      feedbackGuardrailsApplied: ['low_confidence_exception_ignored'],
      analystFeedbackStatus: 'ignored_low_confidence_exception',
      forceReview: false,
      ignoredException: true,
      adaptationSource: 'manual_exception_memory',
    };
  }

  if (Number(exception.feedbackCount || 0) < 3) {
    return {
      detectionScore,
      operationalPriorityScore: detectionScore,
      currentRiskScore: detectionScore,
      feedbackApplied: false,
      feedbackRecorded: false,
      priorityAdjusted: false,
      feedbackAdjustment: 0,
      proposedFeedbackAdjustment: 0,
      cappedFeedbackAdjustment: 0,
      matchedExceptionId: exception.exceptionId,
      matchedExceptionType: exception.patternType,
      feedbackReason: 'Matching manual exception memory was ignored because feedbackCount is below 3.',
      feedbackGuardrailsApplied: ['insufficient_feedback_exception_ignored'],
      analystFeedbackStatus: 'ignored_insufficient_feedback',
      forceReview: false,
      ignoredException: true,
      adaptationSource: 'manual_exception_memory',
    };
  }

  const guarded = applyGuardrails(alert, exception.riskAdjustment, guardrailConfig);
  const guardrailLimited = guarded.feedbackGuardrailsApplied.length > 0;
  const scoreChanged = guarded.feedbackAdjustment !== 0;

  return {
    ...guarded,
    feedbackRecorded: false,
    priorityAdjusted: scoreChanged,
    feedbackApplied: scoreChanged,
    proposedFeedbackAdjustment: guarded.proposedAdjustment,
    cappedFeedbackAdjustment: guarded.cappedAdjustment,
    matchedExceptionId: exception.exceptionId,
    matchedExceptionType: exception.patternType,
    feedbackReason: scoreChanged
      ? exception.reason || 'Manual exception memory matched this alert.'
      : 'Manual exception memory matched, but the priority did not change after clamping.',
    analystFeedbackStatus: scoreChanged
      ? (guardrailLimited ? 'guardrail_limited_adjustment' : 'adjusted_by_exception_memory')
      : 'unchanged',
    forceReview: guarded.requiresReviewDueToGuardrail,
    ignoredException: false,
    adaptationSource: 'manual_exception_memory',
  };
}

function expectedActivityEligible(aggregation, config = {}) {
  const expectedConfig = config.expectedActivity || {};
  if (expectedConfig.enabledForFutureAdaptation === false) {
    return {
      passed: false,
      reason: 'Expected Activity is disabled for future adaptation.',
    };
  }

  const minimumFeedbackCount = Number(expectedConfig.minimumFeedbackCount ?? 5);
  const minimumAgreementRatio = Number(expectedConfig.minimumAgreementRatio ?? 0.9);
  if (aggregation.matchedFeedbackCount < minimumFeedbackCount) {
    return {
      passed: false,
      reason: `Expected Activity requires at least ${minimumFeedbackCount} specific matching feedback records.`,
    };
  }
  if (aggregation.agreementRatio < minimumAgreementRatio) {
    return {
      passed: false,
      reason: `Expected Activity requires agreement ratio >= ${minimumAgreementRatio}.`,
    };
  }

  const exactMatches = aggregation.matchedFeedback.filter((item) => item.exactExpectedActivityContext.passed);
  if (exactMatches.length < minimumFeedbackCount) {
    return {
      passed: false,
      reason: 'Expected Activity was not propagated because the stricter organisational-context gate did not pass.',
    };
  }

  return {
    passed: true,
    reason: 'Expected Activity passed the stricter exact/context gate.',
  };
}

function checkAdaptationEligibility(aggregation, config = {}) {
  const minimumFeedbackCount = Number(config.minimumFeedbackCount ?? 3);
  const minimumAgreementRatio = Number(config.minimumAgreementRatio ?? 0.67);

  if (!aggregation || aggregation.matchedFeedbackCount === 0) {
    return {
      eligible: false,
      reason: 'Cold start: no sufficiently similar historical feedback was found.',
    };
  }
  if (aggregation.matchedFeedbackCount < minimumFeedbackCount) {
    return {
      eligible: false,
      reason: `Not enough similar learning feedback. Required ${minimumFeedbackCount}, found ${aggregation.matchedFeedbackCount}.`,
    };
  }
  if (aggregation.conflictDetected || !aggregation.dominantFeedback) {
    return {
      eligible: false,
      reason: 'Historical feedback conflict detected; no dominant feedback type was trusted.',
    };
  }
  if (aggregation.agreementRatio < minimumAgreementRatio) {
    return {
      eligible: false,
      reason: `Historical feedback agreement ratio ${aggregation.agreementRatio} is below ${minimumAgreementRatio}.`,
    };
  }
  if (aggregation.dominantFeedback === 'mark_expected_activity') {
    const expected = expectedActivityEligible(aggregation, config);
    if (!expected.passed) {
      return {
        eligible: false,
        reason: expected.reason,
      };
    }
  }

  return {
    eligible: true,
    reason: 'Similarity and historical-feedback agreement gates passed.',
  };
}

function proposeHistoricalAdjustment(aggregation, config = {}) {
  if (!aggregation || !aggregation.dominantFeedback) {
    return {
      proposedAdjustment: 0,
      adjustmentBand: 'none',
      reason: 'No dominant historical feedback was available.',
    };
  }

  const bands = (config.adjustments && config.adjustments[aggregation.dominantFeedback]) || {};
  const strongAgreementRatio = Number(config.strongAgreementRatio ?? 0.8);
  const strong = aggregation.agreementRatio >= strongAgreementRatio;

  if (aggregation.dominantFeedback === 'mark_expected_activity') {
    return {
      proposedAdjustment: Number(bands.strong ?? -15),
      adjustmentBand: 'conservative_expected_activity',
      reason: 'Expected Activity passed the stricter context gate, so only a conservative reduction is proposed.',
    };
  }
  if (aggregation.dominantFeedback === 'mark_false_positive') {
    return {
      proposedAdjustment: Number(strong ? bands.strong ?? -25 : bands.moderate ?? -10),
      adjustmentBand: strong ? 'strong_negative' : 'moderate_negative',
      reason: strong
        ? 'Similar historical feedback strongly indicates repeated false positives.'
        : 'Similar historical feedback moderately indicates repeated false positives.',
    };
  }
  if (aggregation.dominantFeedback === 'confirm_true_positive') {
    return {
      proposedAdjustment: Number(strong ? bands.strong ?? 15 : bands.moderate ?? 8),
      adjustmentBand: strong ? 'strong_positive' : 'moderate_positive',
      reason: strong
        ? 'Similar historical feedback strongly confirms threat priority.'
        : 'Similar historical feedback moderately confirms threat priority.',
    };
  }

  return {
    proposedAdjustment: 0,
    adjustmentBand: 'workflow_or_unsupported',
    reason: 'Dominant feedback is not a learning feedback type used for priority adaptation.',
  };
}

function setReviewFlag(alert, operationalPriorityScore, forceReview) {
  if (forceReview) {
    return true;
  }
  return operationalPriorityScore >= Number(alert.reviewThreshold ?? 70);
}

function buildDefaultResult(alert, reason = 'No direct feedback or trusted historical feedback matched this alert.') {
  const detectionScore = clampScore(alert.fusionRiskScore);
  return {
    detectionScore,
    operationalPriorityScore: detectionScore,
    currentRiskScore: detectionScore,
    feedbackApplied: false,
    feedbackRecorded: false,
    priorityAdjusted: false,
    feedbackAdjustment: 0,
    proposedFeedbackAdjustment: 0,
    cappedFeedbackAdjustment: 0,
    matchedExceptionId: null,
    matchedExceptionType: null,
    matchedFeedbackId: null,
    feedbackReason: reason,
    feedbackGuardrailsApplied: [],
    guardrailInterventions: [],
    analystFeedbackStatus: 'unchanged',
    forceReview: false,
    ignoredException: false,
    adaptationSource: 'none',
    adaptationEligible: false,
    adaptationEligibilityReason: reason,
    similarityMatched: false,
    similarityReason: reason,
    matchedHistoricalFeedbackCount: 0,
    matchedHistoricalFeedbackIds: [],
    dominantHistoricalFeedback: null,
    historicalAgreementRatio: 0,
    conflictDetected: false,
    adaptationExplanation: reason,
  };
}

function adjustAlertWithFeedback(alert, context = {}) {
  const {
    effectiveByAlert = new Map(),
    effectiveFeedbackEvents = [],
    alertsById = new Map(),
    exceptionMemory = [],
    config = {},
    useManualExceptionMemory = false,
  } = context;
  const detectionScore = clampScore(alert.fusionRiskScore);
  const alertWithDetectionScore = {
    ...alert,
    detectionScore,
  };
  const directFeedback = findDirectFeedback(alertWithDetectionScore, effectiveByAlert);
  const matchingException = useManualExceptionMemory
    ? findMatchingException(alertWithDetectionScore, exceptionMemory)
    : null;
  let result = buildDefaultResult(alertWithDetectionScore);

  if (directFeedback) {
    const directResult = applyDirectFeedback(alertWithDetectionScore, directFeedback, config.guardrails || {});
    if (directResult) {
      result = {
        ...result,
        ...directResult,
        matchedExceptionId: matchingException ? matchingException.exceptionId : null,
        matchedExceptionType: matchingException ? matchingException.patternType : null,
        adaptationEligible: false,
        adaptationEligibilityReason: 'Direct analyst feedback applies to the current alert, so historical adaptation eligibility is not evaluated for this alert.',
      };
      if (matchingException) {
        result.feedbackReason = `${result.feedbackReason} Manual exception ${matchingException.exceptionId} was recorded but not applied because direct analyst feedback takes priority.`;
      }
    }
  } else {
    const aggregation = aggregateHistoricalFeedback(
      alertWithDetectionScore,
      alertsById,
      effectiveFeedbackEvents,
      {
        ...(config.aggregation || {}),
        similarity: config.similarity || {},
      }
    );
    const eligibility = checkAdaptationEligibility(aggregation, {
      ...(config.aggregation || {}),
      adjustments: config.adjustments || {},
    });

    result = {
      ...result,
      matchedHistoricalFeedbackCount: aggregation.matchedFeedbackCount,
      matchedHistoricalFeedbackIds: aggregation.sourceFeedbackIds,
      dominantHistoricalFeedback: aggregation.dominantFeedback,
      historicalAgreementRatio: aggregation.agreementRatio,
      conflictDetected: aggregation.conflictDetected,
      similarityMatched: aggregation.matchedFeedbackCount > 0,
      similarityReason: aggregation.matchedFeedbackCount > 0
        ? `Matched ${aggregation.matchedFeedbackCount} similar effective historical feedback event(s).`
        : aggregation.lowEvidenceCoverageCount > 0
          ? 'Historical feedback was found, but similarity evidence coverage was too low.'
          : 'No sufficiently similar historical learning feedback passed the similarity gate.',
      lowEvidenceCoverageCount: aggregation.lowEvidenceCoverageCount,
      lowSimilarityCount: aggregation.lowSimilarityCount,
      adaptationEligible: eligibility.eligible,
      adaptationEligibilityReason: eligibility.reason,
    };

    if (eligibility.eligible) {
      const proposal = proposeHistoricalAdjustment(aggregation, {
        ...(config.aggregation || {}),
        adjustments: config.adjustments || {},
      });
      const guarded = applyGuardrails(alertWithDetectionScore, proposal.proposedAdjustment, config.guardrails || {});
      result = {
        ...result,
        ...guarded,
        feedbackRecorded: false,
        priorityAdjusted: guarded.feedbackAdjustment !== 0,
        feedbackApplied: guarded.feedbackAdjustment !== 0,
        proposedFeedbackAdjustment: proposal.proposedAdjustment,
        cappedFeedbackAdjustment: guarded.cappedAdjustment,
        feedbackReason: `${proposal.reason} ${eligibility.reason}`,
        analystFeedbackStatus: guarded.feedbackAdjustment === 0 ? 'unchanged' : 'adjusted_by_historical_feedback',
        forceReview: guarded.requiresReviewDueToGuardrail,
        adaptationSource: 'historical_feedback',
        adaptationExplanation: `Detection score ${detectionScore} became operational priority ${guarded.operationalPriorityScore}. ${proposal.reason}`,
      };
    } else if (matchingException) {
      const exceptionResult = applyExceptionMemory(alertWithDetectionScore, matchingException, config.guardrails || {});
      if (exceptionResult) {
        result = {
          ...result,
          ...exceptionResult,
          adaptationEligibilityReason: `${eligibility.reason} Manual exception memory was used only because backwards-compatible demo mode is enabled.`,
          adaptationExplanation: `${eligibility.reason} Manual exception memory was used only because backwards-compatible demo mode is enabled.`,
        };
      }
    }
  }

  const requiresAnalystReviewBeforeFeedback = Boolean(alert.requiresAnalystReview);
  const updatedReviewFlag = setReviewFlag(
    { ...alertWithDetectionScore, reviewThreshold: config.guardrails?.reviewThreshold },
    result.operationalPriorityScore,
    result.forceReview
  );

  return {
    ...alert,
    detectionScore,
    requiresAnalystReviewBeforeFeedback,
    requiresAnalystReview: updatedReviewFlag,
    operationalPriorityScore: result.operationalPriorityScore,
    currentRiskScore: result.currentRiskScore,
    feedbackApplied: result.feedbackApplied,
    feedbackRecorded: result.feedbackRecorded,
    priorityAdjusted: result.priorityAdjusted,
    feedbackAdjustment: result.feedbackAdjustment,
    proposedFeedbackAdjustment: result.proposedFeedbackAdjustment ?? result.proposedAdjustment ?? 0,
    cappedFeedbackAdjustment: result.cappedFeedbackAdjustment ?? result.cappedAdjustment ?? 0,
    matchedExceptionId: result.matchedExceptionId || null,
    matchedExceptionType: result.matchedExceptionType || null,
    matchedFeedbackId: result.matchedFeedbackId || null,
    feedbackReason: result.feedbackReason,
    feedbackGuardrailsApplied: result.feedbackGuardrailsApplied || [],
    guardrailInterventions: result.guardrailInterventions || [],
    analystFeedbackStatus: result.analystFeedbackStatus,
    adaptationSource: result.adaptationSource,
    adaptationEligible: result.adaptationEligible,
    adaptationEligibilityReason: result.adaptationEligibilityReason,
    adaptationExplanation: result.adaptationExplanation,
    similarityMatched: result.similarityMatched,
    similarityReason: result.similarityReason,
    matchedHistoricalFeedbackCount: result.matchedHistoricalFeedbackCount,
    matchedHistoricalFeedbackIds: result.matchedHistoricalFeedbackIds || [],
    dominantHistoricalFeedback: result.dominantHistoricalFeedback,
    historicalAgreementRatio: result.historicalAgreementRatio,
    conflictDetected: result.conflictDetected,
    lowEvidenceCoverageCount: result.lowEvidenceCoverageCount || 0,
    lowSimilarityCount: result.lowSimilarityCount || 0,
  };
}

function adjustAlertsWithFeedback(alerts, analystFeedback = [], exceptionMemory = [], config = {}, options = {}) {
  const alertsById = indexById(options.similarityReferenceAlerts || alerts || []);
  const feedbackResolution = resolveEffectiveFeedbackEvents(analystFeedback || []);
  const historicalFeedbackResolution = resolveEffectiveFeedbackEvents(
    options.historicalFeedbackEvents || analystFeedback || []
  );
  const alertIds = new Set((alerts || []).map((alert) => String(alert.id)));
  const unmatchedFeedback = feedbackResolution.effectiveEvents.filter((feedback) => !alertIds.has(String(feedback.alertId)));
  const useManualExceptionMemory = Boolean(
    options.useManualExceptionMemory ?? config.formalEvaluation?.useManualExceptionMemory
  );
  const generatedHistoricalMemory = buildGeneratedHistoricalMemory(
    alertsById,
    historicalFeedbackResolution.effectiveEvents,
    config.aggregation || {}
  );
  const adjustedAlerts = (alerts || [])
    .map((alert) => adjustAlertWithFeedback(alert, {
      effectiveByAlert: feedbackResolution.effectiveByAlert,
      effectiveFeedbackEvents: historicalFeedbackResolution.effectiveEvents,
      alertsById,
      exceptionMemory,
      config,
      useManualExceptionMemory,
    }))
    .sort((a, b) => {
      if (b.operationalPriorityScore !== a.operationalPriorityScore) {
        return b.operationalPriorityScore - a.operationalPriorityScore;
      }
      if (a.requiresAnalystReview !== b.requiresAnalystReview) {
        return a.requiresAnalystReview ? -1 : 1;
      }
      return String(a.id).localeCompare(String(b.id), undefined, { numeric: true });
    });

  return {
    adjustedAlerts,
    unmatchedFeedback,
    generatedHistoricalMemory,
    feedbackResolution: {
      auditEventCount: feedbackResolution.auditEventCount,
      effectiveFeedbackCount: feedbackResolution.effectiveEvents.length,
      revertedFeedbackIds: feedbackResolution.revertedFeedbackIds,
      supersededFeedbackIds: feedbackResolution.supersededFeedbackIds,
      integrityErrors: feedbackResolution.integrityErrors,
      duplicateFeedbackIds: feedbackResolution.duplicateFeedbackIds,
      historicalSnapshotEffectiveFeedbackCount: historicalFeedbackResolution.effectiveEvents.length,
      historicalSnapshotIntegrityErrors: historicalFeedbackResolution.integrityErrors,
    },
    useManualExceptionMemory,
  };
}

function stripGroundTruthFields(alerts = []) {
  return alerts.map((alert) => {
    const {
      groundTruth,
      trueAttackType,
      mappedAttackType,
      rawLabel,
      groundTruthLabel,
      ...analystSafeAlert
    } = alert;
    return analystSafeAlert;
  });
}

function buildEvaluatorRecords(adjustedAlerts, groundTruth = null) {
  if (!groundTruth) {
    return adjustedAlerts.map((alert) => ({ ...alert }));
  }
  return adjustedAlerts.map((alert) => {
    const truth = groundTruth[String(alert.id)] || {};
    return {
      ...alert,
      groundTruth: truth.groundTruth || null,
      trueAttackType: truth.mappedAttackType || null,
      mappedAttackType: truth.mappedAttackType || null,
      rawLabel: truth.rawLabel || null,
    };
  });
}

function attachGroundTruthFields(adjustedAlerts, groundTruth = null) {
  if (!groundTruth) {
    return adjustedAlerts;
  }

  return adjustedAlerts.map((alert) => {
    const truth = groundTruth[String(alert.id)];
    if (!truth) {
      return alert;
    }

    // Ground truth is joined only after detection, fusion, feedback aggregation,
    // and priority adaptation. It is not used as adaptation input.
    return {
      ...alert,
      groundTruth: truth.groundTruth,
      trueAttackType: truth.mappedAttackType,
      mappedAttackType: truth.mappedAttackType,
      rawLabel: truth.rawLabel,
    };
  });
}

function incrementCounter(counter, key) {
  const safeKey = key || 'Unknown';
  counter[safeKey] = (counter[safeKey] || 0) + 1;
}

function averageScore(alerts, field) {
  if (!alerts.length) {
    return 0;
  }
  const total = alerts.reduce((sum, alert) => sum + Number(alert[field] || 0), 0);
  return Number((total / alerts.length).toFixed(2));
}

function summariseFeedbackResults(adjustedAlerts, unmatchedFeedback = [], groundTruth = null, metadata = {}) {
  const scoreAdjustmentGuardrailCount = adjustedAlerts.filter((alert) => (
    (alert.guardrailInterventions || []).some((intervention) => [
      'maximum_negative_adjustment_capped',
      'maximum_increase_capped',
      'critical_alert_floor',
      'infiltration_alert_floor',
      'non_finite_adjustment_rejected',
    ].includes(intervention.code))
  )).length;
  const lowConfidenceExceptionIgnoredCount = adjustedAlerts.filter(
    (alert) => alert.analystFeedbackStatus === 'ignored_low_confidence_exception'
  ).length;
  const insufficientFeedbackExceptionIgnoredCount = adjustedAlerts.filter(
    (alert) => alert.analystFeedbackStatus === 'ignored_insufficient_feedback'
  ).length;
  const exceptionRejectedByTrustGateCount =
    lowConfidenceExceptionIgnoredCount + insufficientFeedbackExceptionIgnoredCount;
  const similarityMatchCount = adjustedAlerts.filter((alert) => alert.similarityMatched).length;
  const adaptationEligibleCount = adjustedAlerts.filter((alert) => alert.adaptationEligible).length;
  const actualAdaptationCount = adjustedAlerts.filter((alert) => (
    alert.adaptationSource === 'historical_feedback' && alert.feedbackAdjustment !== 0
  )).length;

  const summary = {
    totalAlerts: adjustedAlerts.length,
    evaluationSplit: metadata.evaluationSplit || 'frozen_calibration_held_out',
    calibrationAlertCount: metadata.calibrationAlertCount || 0,
    heldOutAlertCount: metadata.heldOutAlertCount || adjustedAlerts.length,
    ignoredHeldOutFeedbackCount: metadata.ignoredHeldOutFeedbackCount || 0,
    detectionScoreField: 'detectionScore',
    operationalPriorityScoreField: 'operationalPriorityScore',
    manualExceptionMemoryEnabled: Boolean(metadata.useManualExceptionMemory),
    alertsAdjusted: adjustedAlerts.filter((alert) => alert.feedbackAdjustment !== 0).length,
    alertsUnchanged: adjustedAlerts.filter((alert) => alert.feedbackAdjustment === 0).length,
    directFeedbackAppliedCount: adjustedAlerts.filter((alert) => alert.matchedFeedbackId).length,
    unmatchedDirectFeedbackCount: unmatchedFeedback.length,
    historicalFeedbackAdaptationCount: actualAdaptationCount,
    exceptionMemoryAppliedCount: adjustedAlerts.filter((alert) => (
      alert.adaptationSource === 'manual_exception_memory'
      && alert.matchedExceptionId
      && !alert.matchedFeedbackId
      && alert.feedbackApplied
      && ![
        'ignored_low_confidence_exception',
        'ignored_insufficient_feedback',
      ].includes(alert.analystFeedbackStatus)
    )).length,
    ignoredExceptionCount: adjustedAlerts.filter((alert) => (
      alert.analystFeedbackStatus === 'ignored_low_confidence_exception'
      || alert.analystFeedbackStatus === 'ignored_insufficient_feedback'
    )).length,
    guardrailAppliedCount: scoreAdjustmentGuardrailCount + exceptionRejectedByTrustGateCount,
    scoreAdjustmentGuardrailCount,
    exceptionRejectedByTrustGateCount,
    lowConfidenceExceptionIgnoredCount,
    insufficientFeedbackExceptionIgnoredCount,
    averageRiskBeforeFeedback: averageScore(adjustedAlerts, 'detectionScore'),
    averageRiskAfterFeedback: averageScore(adjustedAlerts, 'operationalPriorityScore'),
    averageRiskChange: 0,
    averageDetectionScore: averageScore(adjustedAlerts, 'detectionScore'),
    averageOperationalPriorityScore: averageScore(adjustedAlerts, 'operationalPriorityScore'),
    highRiskThreshold: Number(metadata.config?.guardrails?.highRiskThreshold ?? 70),
    highRiskAlertsBefore: adjustedAlerts.filter((alert) => (
      alert.detectionScore >= Number(metadata.config?.guardrails?.highRiskThreshold ?? 70)
    )).length,
    highRiskAlertsAfter: adjustedAlerts.filter((alert) => (
      alert.operationalPriorityScore >= Number(metadata.config?.guardrails?.highRiskThreshold ?? 70)
    )).length,
    reviewQueueBefore: adjustedAlerts.filter((alert) => alert.requiresAnalystReviewBeforeFeedback).length,
    reviewQueueAfter: adjustedAlerts.filter((alert) => alert.requiresAnalystReview).length,
    similarityMatchCount,
    similarityMatchCoverage: adjustedAlerts.length ? Number((similarityMatchCount / adjustedAlerts.length).toFixed(4)) : 0,
    adaptationEligibleCount,
    adaptationEligibilityCoverage: adjustedAlerts.length ? Number((adaptationEligibleCount / adjustedAlerts.length).toFixed(4)) : 0,
    actualAdaptationCount,
    actualAdaptationCoverage: adjustedAlerts.length ? Number((actualAdaptationCount / adjustedAlerts.length).toFixed(4)) : 0,
    feedbackResolution: metadata.feedbackResolution || null,
    generatedHistoricalMemoryCount: metadata.generatedHistoricalMemoryCount || 0,
    lowEvidenceCoverageRejectionCount: adjustedAlerts.filter((alert) => alert.lowEvidenceCoverageCount > 0).length,
    lowSimilarityRejectionCount: adjustedAlerts.filter((alert) => alert.lowSimilarityCount > 0).length,
    benignHighRiskBefore: null,
    benignHighRiskAfter: null,
    maliciousHighRiskBefore: null,
    maliciousHighRiskAfter: null,
    reviewedBenignBefore: null,
    reviewedBenignAfter: null,
    reviewedMaliciousBefore: null,
    reviewedMaliciousAfter: null,
    truePositiveSuppressionCount: null,
    infiltrationAdjustedCount: adjustedAlerts.filter(
      (alert) => alert.fusionAttackType === 'Infiltration' && alert.feedbackAdjustment !== 0
    ).length,
    infiltrationGuardrailCount: adjustedAlerts.filter(
      (alert) => alert.feedbackGuardrailsApplied.includes('infiltration_floor_75')
    ).length,
    countByAnalystFeedbackStatus: {},
    countByAdaptationSource: {},
    countByFeedbackRecorded: {},
    notes: [
      'Analyst feedback events are the source of truth. Generated historical feedback memory is derived data and should not be manually authored.',
      'This evaluation uses a frozen calibration / held-out split. It should not be described as temporal evaluation until reliable chronological ordering metadata is used.',
      'Ground truth is joined only after detection, fusion, feedback aggregation, and priority adaptation for evaluator-only records. It is not written to the analyst-facing alert artifact and is not used as adaptation input.',
      'Full evaluator-only records are reproducible from the runner and are not required as the primary committed evidence.',
      'Detection score is preserved as detectionScore/fusionRiskScore. Historical feedback affects operationalPriorityScore for ranking.',
      'Manual exception memory is disabled for formal adaptive evaluation so improvements can be attributed to analyst feedback events.',
      'This is a prototype feedback evaluation, not production IDS performance.',
    ],
  };

  summary.averageRiskChange = Number((summary.averageRiskAfterFeedback - summary.averageRiskBeforeFeedback).toFixed(2));

  for (const alert of adjustedAlerts) {
    incrementCounter(summary.countByAnalystFeedbackStatus, alert.analystFeedbackStatus);
    incrementCounter(summary.countByAdaptationSource, alert.adaptationSource);
    incrementCounter(summary.countByFeedbackRecorded, alert.feedbackRecorded ? 'recorded' : 'not_recorded');
  }

  if (groundTruth) {
    const evaluatedAlerts = adjustedAlerts
      .map((alert) => {
        const truth = groundTruth[String(alert.id)];
        if (!truth) {
          return null;
        }
        const label = truth.groundTruth || (truth.mappedAttackType === 'Benign' ? 'benign' : 'malicious');
        return {
          ...alert,
          groundTruthLabel: label,
        };
      })
      .filter(Boolean);

    const benignAlerts = evaluatedAlerts.filter((alert) => alert.groundTruthLabel === 'benign');
    const maliciousAlerts = evaluatedAlerts.filter((alert) => alert.groundTruthLabel === 'malicious');

    summary.evaluatedWithGroundTruthCount = evaluatedAlerts.length;
    summary.benignHighRiskBefore = benignAlerts.filter((alert) => alert.detectionScore >= summary.highRiskThreshold).length;
    summary.benignHighRiskAfter = benignAlerts.filter((alert) => alert.operationalPriorityScore >= summary.highRiskThreshold).length;
    summary.maliciousHighRiskBefore = maliciousAlerts.filter((alert) => alert.detectionScore >= summary.highRiskThreshold).length;
    summary.maliciousHighRiskAfter = maliciousAlerts.filter((alert) => alert.operationalPriorityScore >= summary.highRiskThreshold).length;
    summary.reviewedBenignBefore = benignAlerts.filter((alert) => alert.requiresAnalystReviewBeforeFeedback).length;
    summary.reviewedBenignAfter = benignAlerts.filter((alert) => alert.requiresAnalystReview).length;
    summary.reviewedMaliciousBefore = maliciousAlerts.filter((alert) => alert.requiresAnalystReviewBeforeFeedback).length;
    summary.reviewedMaliciousAfter = maliciousAlerts.filter((alert) => alert.requiresAnalystReview).length;
    summary.truePositiveSuppressionCount = maliciousAlerts.filter((alert) => (
      alert.detectionScore >= 40
      && alert.operationalPriorityScore < 40
      && alert.feedbackAdjustment < 0
    )).length;
  }

  return summary;
}

module.exports = {
  loadJsonFile,
  clampScore,
  indexById,
  findDirectFeedback,
  matchesException,
  findMatchingException,
  applyGuardrails,
  applyDirectFeedback,
  applyExceptionMemory,
  expectedActivityEligible,
  checkAdaptationEligibility,
  proposeHistoricalAdjustment,
  adjustAlertWithFeedback,
  adjustAlertsWithFeedback,
  attachGroundTruthFields,
  stripGroundTruthFields,
  buildEvaluatorRecords,
  summariseFeedbackResults,
};
