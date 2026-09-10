const {
  calculateSimilarity,
  canonicalize,
  getValueByPath,
  isAvailable,
} = require('./similarity-engine');

const DEFAULT_LEARNING_TYPES = [
  'mark_false_positive',
  'confirm_true_positive',
  'mark_expected_activity',
];

const WORKFLOW_TYPES = [
  'escalate',
  'needs_investigation',
  'duplicate',
  'uncertain',
];
const ALLOWED_EVENT_TYPES = [
  'feedback_submitted',
  'feedback_reverted',
];
const ALLOWED_FEEDBACK_TYPES = [
  ...DEFAULT_LEARNING_TYPES,
  ...WORKFLOW_TYPES,
];

function normalizeFeedbackEvent(event, index = 0, options = {}) {
  const allowGeneratedIds = options.allowGeneratedIds === true;
  const inferMissingSubmittedEventType = options.inferMissingSubmittedEventType === true;
  return {
    ...event,
    feedbackId: event.feedbackId || (allowGeneratedIds ? `FB-GENERATED-${index + 1}` : null),
    eventType: event.eventType || (inferMissingSubmittedEventType ? 'feedback_submitted' : null),
    appliesToFutureSimilarAlerts: event.appliesToFutureSimilarAlerts !== false,
  };
}

function timestampValue(event) {
  const value = Date.parse(event.timestamp || '');
  return Number.isNaN(value) ? 0 : value;
}

function validateFeedbackEvents(events = []) {
  const errors = [];
  const byId = new Map();
  const duplicateIds = new Set();

  for (const event of events) {
    if (!event.feedbackId) {
      errors.push({
        code: 'missing_feedback_id',
        message: 'Formal feedback events must include a stable feedbackId.',
        event,
      });
      continue;
    }
    if (!event.alertId) {
      errors.push({
        code: 'missing_alert_id',
        feedbackId: event.feedbackId,
        message: 'Formal feedback events must include alertId.',
      });
    }
    if (!event.analystId) {
      errors.push({
        code: 'missing_analyst_id',
        feedbackId: event.feedbackId,
        message: 'Formal feedback events must include analystId.',
      });
    }
    if (!event.timestamp || Number.isNaN(Date.parse(event.timestamp))) {
      errors.push({
        code: 'invalid_timestamp',
        feedbackId: event.feedbackId,
        message: 'Formal feedback events must include a valid timestamp.',
      });
    }
    if (!event.eventType || !ALLOWED_EVENT_TYPES.includes(event.eventType)) {
      errors.push({
        code: 'invalid_event_type',
        feedbackId: event.feedbackId,
        eventType: event.eventType || null,
        message: `Invalid eventType: ${event.eventType || 'missing'}.`,
      });
    }
    if (event.eventType === 'feedback_submitted') {
      if (!event.feedbackType) {
        errors.push({
          code: 'missing_feedback_type',
          feedbackId: event.feedbackId,
          message: 'Submitted feedback events must include feedbackType.',
        });
      } else if (!ALLOWED_FEEDBACK_TYPES.includes(event.feedbackType)) {
        errors.push({
          code: 'invalid_feedback_type',
          feedbackId: event.feedbackId,
          feedbackType: event.feedbackType,
          message: `Invalid feedbackType: ${event.feedbackType}.`,
        });
      }
    }
    const id = String(event.feedbackId);
    if (byId.has(id)) {
      duplicateIds.add(id);
      errors.push({
        code: 'duplicate_feedback_id',
        feedbackId: id,
        message: `Duplicate feedbackId detected: ${id}.`,
      });
    } else {
      byId.set(id, event);
    }
  }

  for (const event of events) {
    const references = [
      ['supersedesFeedbackId', event.supersedesFeedbackId],
      ['revertsFeedbackId', event.revertsFeedbackId],
    ].filter(([, value]) => value);

    for (const [field, value] of references) {
      const referenced = byId.get(String(value));
      if (!referenced) {
        errors.push({
          code: `invalid_${field}`,
          feedbackId: event.feedbackId || null,
          referencedFeedbackId: String(value),
          message: `${field} references a missing feedback event.`,
        });
        continue;
      }
      if (referenced.alertId && event.alertId && String(referenced.alertId) !== String(event.alertId)) {
        errors.push({
          code: `cross_alert_${field}`,
          feedbackId: event.feedbackId || null,
          referencedFeedbackId: String(value),
          message: `${field} must reference a feedback event for the same alert.`,
        });
      }
      if (
        event.timestamp
        && referenced.timestamp
        && !Number.isNaN(Date.parse(event.timestamp))
        && !Number.isNaN(Date.parse(referenced.timestamp))
        && Date.parse(referenced.timestamp) >= Date.parse(event.timestamp)
      ) {
        errors.push({
          code: `invalid_order_${field}`,
          feedbackId: event.feedbackId || null,
          referencedFeedbackId: String(value),
          message: `${field} must reference an earlier feedback event.`,
        });
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    duplicateIds: [...duplicateIds],
  };
}

function activeEventForAlert(event, eventById, revertedIds) {
  if (!event || revertedIds.has(String(event.feedbackId))) {
    return null;
  }
  return event;
}

function resolveEffectiveFeedbackEvents(events = [], options = {}) {
  const normalizedEvents = events.map((event, index) => normalizeFeedbackEvent(event, index, options));
  const integrity = validateFeedbackEvents(normalizedEvents);
  const invalidFeedbackIds = new Set(integrity.errors.map((error) => String(error.feedbackId)).filter((id) => id !== 'null'));
  const eventById = new Map(
    normalizedEvents
      .filter((event) => event.feedbackId && !invalidFeedbackIds.has(String(event.feedbackId)))
      .map((event) => [String(event.feedbackId), event])
  );
  const reverted = new Set();
  const superseded = new Set();
  const currentByAlert = new Map();

  const sortedEvents = normalizedEvents
    .filter((event) => event.feedbackId && !invalidFeedbackIds.has(String(event.feedbackId)))
    .sort((a, b) => timestampValue(a) - timestampValue(b));

  for (const event of sortedEvents) {
    if (!event.alertId) {
      continue;
    }
    const alertKey = String(event.alertId);
    if (event.eventType === 'feedback_reverted') {
      const target = eventById.get(String(event.revertsFeedbackId || ''));
      if (!target) {
        continue;
      }
      reverted.add(String(target.feedbackId));
      if (currentByAlert.get(alertKey)?.feedbackId === target.feedbackId) {
        const previous = target.supersedesFeedbackId
          ? eventById.get(String(target.supersedesFeedbackId))
          : null;
        const restored = activeEventForAlert(previous, eventById, reverted);
        if (restored) {
          currentByAlert.set(alertKey, restored);
        } else {
          currentByAlert.delete(alertKey);
        }
      }
      continue;
    }

    if (event.eventType !== 'feedback_submitted') {
      continue;
    }

    if (event.supersedesFeedbackId) {
      superseded.add(String(event.supersedesFeedbackId));
    }
    currentByAlert.set(alertKey, event);
  }

  return {
    allEvents: normalizedEvents,
    effectiveEvents: [...currentByAlert.values()],
    effectiveByAlert: currentByAlert,
    revertedFeedbackIds: [...reverted],
    supersededFeedbackIds: [...superseded],
    integrityErrors: integrity.errors,
    duplicateFeedbackIds: integrity.duplicateIds,
    auditEventCount: normalizedEvents.length,
  };
}

function isLearningFeedback(event, config = {}) {
  const learningTypes = config.learningFeedbackTypes || DEFAULT_LEARNING_TYPES;
  if (WORKFLOW_TYPES.includes(event.feedbackType)) {
    return false;
  }
  return learningTypes.includes(event.feedbackType);
}

function hasExactContext(currentAlert, historicalAlert, fields = []) {
  const unavailable = [];
  const differed = [];

  for (const field of fields) {
    const currentValue = getValueByPath(currentAlert, field);
    const historicalValue = getValueByPath(historicalAlert, field);
    if (!isAvailable(currentValue) || !isAvailable(historicalValue)) {
      unavailable.push(field);
      continue;
    }
    if (canonicalize(currentValue) !== canonicalize(historicalValue)) {
      differed.push(field);
    }
  }

  return {
    passed: unavailable.length === 0 && differed.length === 0,
    unavailable,
    differed,
  };
}

function chooseDominantFeedback(counts) {
  const entries = Object.entries(counts).filter(([, count]) => count > 0);
  if (!entries.length) {
    return {
      dominantFeedback: null,
      dominantCount: 0,
      agreementRatio: 0,
      conflictDetected: false,
    };
  }

  const highestCount = Math.max(...entries.map(([, count]) => count));
  const winners = entries.filter(([, count]) => count === highestCount);
  if (winners.length > 1) {
    return {
      dominantFeedback: null,
      dominantCount: highestCount,
      agreementRatio: Number((highestCount / entries.reduce((sum, [, count]) => sum + count, 0)).toFixed(4)),
      conflictDetected: true,
    };
  }

  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  return {
    dominantFeedback: winners[0][0],
    dominantCount: highestCount,
    agreementRatio: Number((highestCount / total).toFixed(4)),
    conflictDetected: false,
  };
}

function aggregateHistoricalFeedback(currentAlert, alertsById, effectiveEvents = [], config = {}) {
  const counts = {
    mark_false_positive: 0,
    confirm_true_positive: 0,
    mark_expected_activity: 0,
  };
  const matchedFeedback = [];
  const similarityAttempts = [];
  const learningEvents = effectiveEvents.filter((event) => (
    event.appliesToFutureSimilarAlerts !== false && isLearningFeedback(event, config)
  ));

  for (const event of learningEvents) {
    if (!event.alertId || String(event.alertId) === String(currentAlert.id)) {
      continue;
    }

    const historicalAlert = alertsById.get(String(event.alertId));
    if (!historicalAlert) {
      similarityAttempts.push({
        feedbackId: event.feedbackId,
        passed: false,
        reason: 'historical_alert_not_found',
      });
      continue;
    }

    const similarity = calculateSimilarity(currentAlert, historicalAlert, config.similarity || {});
    similarityAttempts.push({
      feedbackId: event.feedbackId,
      alertId: event.alertId,
      feedbackType: event.feedbackType,
      similarity,
    });

    if (!similarity.passed) {
      continue;
    }

    counts[event.feedbackType] = (counts[event.feedbackType] || 0) + 1;
    matchedFeedback.push({
      feedbackId: event.feedbackId,
      alertId: event.alertId,
      feedbackType: event.feedbackType,
      similarityScore: similarity.score,
      similarityReasons: similarity.reasons,
      exactExpectedActivityContext: hasExactContext(
        currentAlert,
        historicalAlert,
        (config.expectedActivity && config.expectedActivity.requiredExactContextFields) || []
      ),
    });
  }

  const dominant = chooseDominantFeedback(counts);
  const matchedFeedbackCount = matchedFeedback.length;
  const averageSimilarity = matchedFeedbackCount
    ? Number((matchedFeedback.reduce((sum, item) => sum + item.similarityScore, 0) / matchedFeedbackCount).toFixed(4))
    : 0;
  const lowEvidenceCoverageCount = similarityAttempts.filter((attempt) => (
    attempt.similarity && attempt.similarity.failureReason === 'below_evidence_coverage_threshold'
  )).length;
  const lowSimilarityCount = similarityAttempts.filter((attempt) => (
    attempt.similarity && attempt.similarity.failureReason === 'below_similarity_threshold'
  )).length;

  return {
    matchedFeedbackCount,
    counts,
    falsePositiveCount: counts.mark_false_positive || 0,
    confirmedThreatCount: counts.confirm_true_positive || 0,
    expectedActivityCount: counts.mark_expected_activity || 0,
    dominantFeedback: dominant.dominantFeedback,
    dominantFeedbackCount: dominant.dominantCount,
    agreementRatio: dominant.agreementRatio,
    conflictDetected: dominant.conflictDetected,
    averageSimilarity,
    lowEvidenceCoverageCount,
    lowSimilarityCount,
    matchedFeedback,
    sourceFeedbackIds: matchedFeedback.map((item) => item.feedbackId),
    similarityAttempts,
    learningFeedbackEventCount: learningEvents.length,
  };
}

function buildGeneratedHistoricalMemory(alertsById, effectiveEvents = [], config = {}) {
  const grouped = new Map();
  const events = effectiveEvents.filter((event) => (
    event.appliesToFutureSimilarAlerts !== false && isLearningFeedback(event, config)
  ));

  for (const event of events) {
    const alert = alertsById.get(String(event.alertId));
    if (!alert) {
      continue;
    }

    const profile = {
      fusionAttackType: alert.fusionAttackType || null,
      fusionDecision: alert.fusionDecision || null,
      protocol: getValueByPath(alert, 'flowFeatureSummary.protocol') || null,
      destinationPort: getValueByPath(alert, 'flowFeatureSummary.destinationPort') || null,
      signatureId: alert.signatureId || null,
    };
    const key = JSON.stringify(profile);
    if (!grouped.has(key)) {
      grouped.set(key, {
        profile,
        counts: {},
        sourceFeedbackIds: [],
        sourceAlertIds: [],
        reasons: [],
      });
    }
    const group = grouped.get(key);
    group.counts[event.feedbackType] = (group.counts[event.feedbackType] || 0) + 1;
    group.sourceFeedbackIds.push(event.feedbackId);
    group.sourceAlertIds.push(event.alertId);
    if (event.reason) {
      group.reasons.push(event.reason);
    }
  }

  return [...grouped.values()].map((group, index) => {
    const dominant = chooseDominantFeedback(group.counts);
    return {
      memoryId: `HM-${String(index + 1).padStart(4, '0')}`,
      profile: group.profile,
      effectiveFeedbackCount: group.sourceFeedbackIds.length,
      falsePositiveCount: group.counts.mark_false_positive || 0,
      confirmedThreatCount: group.counts.confirm_true_positive || 0,
      expectedActivityCount: group.counts.mark_expected_activity || 0,
      dominantFeedback: dominant.dominantFeedback,
      agreementRatio: dominant.agreementRatio,
      conflictDetected: dominant.conflictDetected,
      sourceFeedbackIds: group.sourceFeedbackIds,
      sourceAlertIds: [...new Set(group.sourceAlertIds)],
      exampleReasons: group.reasons.slice(0, 3),
      derivedFrom: 'analyst-feedback events',
    };
  });
}

module.exports = {
  normalizeFeedbackEvent,
  resolveEffectiveFeedbackEvents,
  isLearningFeedback,
  hasExactContext,
  chooseDominantFeedback,
  aggregateHistoricalFeedback,
  buildGeneratedHistoricalMemory,
};
