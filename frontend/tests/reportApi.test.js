import test from "node:test";
import assert from "node:assert/strict";

import {
  buildReportFilename,
  buildReportRequestPayload,
  fetchReportTemplate,
} from "../src/utils/reportApi.js";

test("buildReportFilename sanitizes session IDs", () => {
  const filename = buildReportFilename("session:abc/123");
  assert.equal(filename, "interview_report_session_abc_123.pdf");
});

test("buildReportRequestPayload includes chart snapshot flags", () => {
  const payload = buildReportRequestPayload({
    userName: "Ada",
    chartSnapshots: {
      engagementTimeline: "data:image/png;base64,ZmFrZQ==",
    },
  });

  assert.equal(payload.includeChartSnapshots, true);
  assert.equal(payload.userName, "Ada");
  assert.equal(payload.format, "pdf");
  assert.ok(payload.chartSnapshots.engagementTimeline.startsWith("data:image/"));
});

test("fetchReportTemplate posts JSON payload and returns response body", async () => {
  const calls = [];
  const fetchMock = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      async json() {
        return {
          title: "InterviewInsight AI Report",
          overallScores: {
            engagementScore: 88,
          },
        };
      },
    };
  };

  const data = await fetchReportTemplate({
    apiBaseUrl: "http://localhost:8000",
    sessionId: "session-001",
    userName: "Ada",
    chartSnapshots: {},
    fetchImpl: fetchMock,
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://localhost:8000/reports/session-001/generate");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.equal(data.title, "InterviewInsight AI Report");
});
