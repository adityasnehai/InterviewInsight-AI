export function buildPerformanceTrend(sessionHistory = []) {
  const rows = Array.isArray(sessionHistory) ? sessionHistory : [];
  return rows
    .map((entry, index) => {
      const summary = entry.summaryScores || {};
      return {
        sessionId: entry.sessionId || `session_${index + 1}`,
        order: index + 1,
        timestamp: entry.timestamp || null,
        engagementScore: Number(summary.engagementScore || 0),
        confidenceScore: Number(summary.confidenceScore || 0),
        speechFluency: Number(summary.speechFluency || 0),
        emotionalStability: Number(summary.emotionalStability || 0),
        overallPerformanceScore: Number(summary.overallPerformanceScore || 0),
      };
    })
    .sort((a, b) => {
      if (!a.timestamp && !b.timestamp) {
        return a.order - b.order;
      }
      if (!a.timestamp) {
        return -1;
      }
      if (!b.timestamp) {
        return 1;
      }
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });
}


export function summarizeTrendDirection(trendRows = []) {
  if (!Array.isArray(trendRows) || trendRows.length < 2) {
    return "insufficient_data";
  }
  const first = trendRows[0].overallPerformanceScore || 0;
  const last = trendRows[trendRows.length - 1].overallPerformanceScore || 0;
  if (last - first >= 2) {
    return "improving";
  }
  if (first - last >= 2) {
    return "declining";
  }
  return "stable";
}
