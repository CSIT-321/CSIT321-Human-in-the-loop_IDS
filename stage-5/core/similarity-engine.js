function getValueByPath(source, fieldPath) {
  return String(fieldPath || '').split('.').reduce((value, key) => {
    if (value === null || value === undefined || typeof value !== 'object') {
      return undefined;
    }
    return value[key];
  }, source);
}

function isAvailable(value) {
  return value !== undefined && value !== null && value !== '';
}

function normalizeValue(value) {
  if (value === undefined || value === null) {
    return null;
  }
  return String(value).trim().toLowerCase();
}

function canonicalizeProtocol(value) {
  const normalized = normalizeValue(value);
  const protocolNumbers = {
    0: 'hopopt',
    1: 'icmp',
    6: 'tcp',
    17: 'udp',
  };
  return protocolNumbers[normalized] || normalized;
}

function canonicalizeNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const numeric = Number(value.trim());
    if (Number.isFinite(numeric)) {
      return String(numeric);
    }
  }
  return null;
}

function canonicalize(value, canonicalType = 'string') {
  if (!isAvailable(value)) {
    return null;
  }
  if (canonicalType === 'number') {
    return canonicalizeNumber(value);
  }
  if (canonicalType === 'protocol') {
    return canonicalizeProtocol(value);
  }
  return normalizeValue(value);
}

function valuesEqual(left, right, canonicalType) {
  const canonicalLeft = canonicalize(left, canonicalType);
  const canonicalRight = canonicalize(right, canonicalType);
  if (canonicalLeft === null || canonicalRight === null) {
    return false;
  }
  return canonicalLeft === canonicalRight;
}

function calculateSimilarity(currentAlert, historicalAlert, config) {
  const fields = (config && config.fields) || [];
  const threshold = Number((config && config.threshold) || 0);
  const minimumEvidenceCoverage = Number((config && config.minimumEvidenceCoverage) || 0);
  const reasons = [];
  const unavailableFields = [];
  const matchedFields = [];
  const differedFields = [];
  const totalConfiguredWeight = fields.reduce((sum, field) => sum + Number(field.weight || 0), 0);
  let totalAvailableWeight = 0;
  let matchedWeight = 0;

  for (const field of fields) {
    const path = field.path || field.name;
    const currentValue = getValueByPath(currentAlert, path);
    const historicalValue = getValueByPath(historicalAlert, path);
    const currentAvailable = isAvailable(currentValue);
    const historicalAvailable = isAvailable(historicalValue);

    if (!currentAvailable || !historicalAvailable) {
      unavailableFields.push(field.name || path);
      reasons.push(`${field.name || path} unavailable and excluded from similarity denominator.`);
      if (field.required) {
        return {
          score: 0,
          passed: false,
          threshold,
          matchedWeight: 0,
          totalAvailableWeight,
          matchedFields,
          differedFields,
          unavailableFields,
          reasons: [
            ...reasons,
            `${field.name || path} is required, so similarity failed.`,
          ],
          failureReason: 'missing_required_field',
        };
      }
      continue;
    }

    totalAvailableWeight += Number(field.weight || 0);
    if (valuesEqual(currentValue, historicalValue, field.canonicalType || 'string')) {
      matchedWeight += Number(field.weight || 0);
      matchedFields.push(field.name || path);
      reasons.push(`${field.name || path} matched.`);
    } else {
      differedFields.push(field.name || path);
      reasons.push(`${field.name || path} differed.`);
    }
  }

  const score = totalAvailableWeight === 0
    ? 0
    : Number((matchedWeight / totalAvailableWeight).toFixed(4));
  const evidenceCoverage = totalConfiguredWeight === 0
    ? 0
    : Number((totalAvailableWeight / totalConfiguredWeight).toFixed(4));
  const similarityPassed = score >= threshold;
  const evidenceCoveragePassed = evidenceCoverage >= minimumEvidenceCoverage;
  let failureReason = null;
  if (!evidenceCoveragePassed) {
    failureReason = 'below_evidence_coverage_threshold';
  } else if (!similarityPassed) {
    failureReason = 'below_similarity_threshold';
  }

  return {
    score,
    passed: similarityPassed && evidenceCoveragePassed,
    threshold,
    evidenceCoverage,
    minimumEvidenceCoverage,
    evidenceCoveragePassed,
    similarityPassed,
    matchedWeight: Number(matchedWeight.toFixed(4)),
    totalAvailableWeight: Number(totalAvailableWeight.toFixed(4)),
    totalConfiguredWeight: Number(totalConfiguredWeight.toFixed(4)),
    matchedFields,
    differedFields,
    unavailableFields,
    reasons,
    failureReason,
  };
}

module.exports = {
  getValueByPath,
  isAvailable,
  canonicalize,
  calculateSimilarity,
};
