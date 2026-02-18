import test from "node:test";
import assert from "node:assert/strict";

import { buildReportContentStructure } from "../src/utils/reportContent.js";

test("buildReportContentStructure returns expected report sections", () => {
  const structure = buildReportContentStructure({
    title: "InterviewInsight AI Report",
    generatedAt: "2026-02-16T11:00:00Z",
    sessionMetadata: {
      sessionId: "session-123",
      jobRole: "Backend Engineer",
      interviewDateTime: "2026-02-15T08:30:00Z",
    },
    overallScores: {
      engagementScore: 84.5,
      communicationEffectiveness: 79.2,
    },
    segmentSummaries: [
      {
        segmentId: "segment_1",
        label: "Question Segment 1",
        startTime: 0,
        endTime: 30,
        dominantEmotion: "neutral",
        scores: {
          speechFluency: 77.1,
          textRelevance: 88.6,
        },
      },
    ],
    feedbackMessages: ["Keep answers concise and outcome-oriented."],
    strengths: ["Strong eye contact."],
    improvements: ["Reduce filler words."],
    chartSnapshots: {
      emotionTimeline: "data:image/png;base64,ZmFrZQ==",
    },
  });

  assert.equal(structure.title, "InterviewInsight AI Report");
  assert.equal(structure.metadata.sessionId, "session-123");
  assert.equal(structure.overallScores.length, 2);
  assert.equal(structure.overallScores[0].label, "Engagement Score");
  assert.equal(structure.segmentSummaries.length, 1);
  assert.equal(structure.segmentSummaries[0].timeRange, "0.0s - 30.0s");
  assert.equal(structure.feedbackMessages[0], "Keep answers concise and outcome-oriented.");
  assert.ok(structure.chartSnapshots.emotionTimeline.startsWith("data:image/"));
});
