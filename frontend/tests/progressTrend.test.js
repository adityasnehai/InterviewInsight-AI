import test from "node:test";
import assert from "node:assert/strict";

import { buildPerformanceTrend, summarizeTrendDirection } from "../src/utils/progressTrend.js";

test("buildPerformanceTrend sorts and maps rows for chart rendering", () => {
  const rows = buildPerformanceTrend([
    {
      sessionId: "s2",
      timestamp: "2026-02-16T12:00:00Z",
      summaryScores: { overallPerformanceScore: 72, engagementScore: 70 },
    },
    {
      sessionId: "s1",
      timestamp: "2026-02-15T12:00:00Z",
      summaryScores: { overallPerformanceScore: 65, engagementScore: 62 },
    },
  ]);

  assert.equal(rows.length, 2);
  assert.equal(rows[0].sessionId, "s1");
  assert.equal(rows[1].sessionId, "s2");
  assert.equal(rows[0].overallPerformanceScore, 65);
});

test("summarizeTrendDirection reports improving trend", () => {
  const direction = summarizeTrendDirection([
    { overallPerformanceScore: 55 },
    { overallPerformanceScore: 61 },
    { overallPerformanceScore: 69 },
  ]);
  assert.equal(direction, "improving");
});

test("summarizeTrendDirection reports stable when changes are small", () => {
  const direction = summarizeTrendDirection([
    { overallPerformanceScore: 70 },
    { overallPerformanceScore: 71 },
  ]);
  assert.equal(direction, "stable");
});
