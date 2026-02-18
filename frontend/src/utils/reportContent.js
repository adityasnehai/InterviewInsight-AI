export function toDisplayLabel(key) {
  return String(key || "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function buildReportContentStructure(reportPayload) {
  const payload = reportPayload || {};

  return {
    title: payload.title || "InterviewInsight AI Report",
    generatedAt: payload.generatedAt || "",
    metadata: payload.sessionMetadata || {},
    overallScores: Object.entries(payload.overallScores || {}).map(([key, value]) => ({
      key,
      label: toDisplayLabel(key),
      value: Number(value || 0),
    })),
    segmentSummaries: (payload.segmentSummaries || []).map((segment) => ({
      segmentId: segment.segmentId,
      label: segment.label,
      timeRange: `${Number(segment.startTime || 0).toFixed(1)}s - ${Number(segment.endTime || 0).toFixed(1)}s`,
      dominantEmotion: segment.dominantEmotion || "neutral",
      scores: Object.entries(segment.scores || {}).map(([key, value]) => ({
        key,
        label: toDisplayLabel(key),
        value: Number(value || 0),
      })),
    })),
    feedbackMessages: payload.feedbackMessages || [],
    strengths: payload.strengths || [],
    improvements: payload.improvements || [],
    chartSnapshots: payload.chartSnapshots || {},
  };
}
