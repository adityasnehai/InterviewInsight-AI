import unittest

try:
    from app.models.reports import InterviewReportRequest
    from app.services.reports_utils import build_interview_report_payload

    PYDANTIC_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - environment-dependent guard
    PYDANTIC_AVAILABLE = False
    InterviewReportRequest = None
    build_interview_report_payload = None


@unittest.skipUnless(PYDANTIC_AVAILABLE, "pydantic/fastapi dependencies are not installed")
class ReportsUtilsTests(unittest.TestCase):
    def test_build_report_payload_shape(self) -> None:
        payload = build_interview_report_payload(
            session_id="session-42",
            session_data={
                "userId": "user-1",
                "jobRole": "Backend Engineer",
                "domain": "FinTech",
                "startedAt": "2026-02-16T09:00:00Z",
            },
            analysis_result={
                "sessionMeta": {
                    "sessionId": "session-42",
                    "jobRole": "Backend Engineer",
                    "domain": "FinTech",
                    "dateTime": "2026-02-16T09:00:00Z",
                },
                "summaryScores": {"engagementScore": 83.0, "overallPerformanceScore": 81.0},
                "detailedScores": {"engagement": {"score": 83.0, "components": {"eyeContactScore": 81.0}}},
                "segmentLabels": [
                    {
                        "segmentId": "segment_1",
                        "label": "Question Segment 1",
                        "startTime": 0.0,
                        "endTime": 25.0,
                        "engagementScore": 82.0,
                        "speechFluency": 79.0,
                        "textRelevanceScore": 86.0,
                        "dominantEmotion": "neutral",
                    }
                ],
                "feedbackSummary": {
                    "strengths": ["Consistent pacing."],
                    "improvements": ["Stronger closing statements."],
                },
                "feedbackMessages": ["Use more quantified achievements."],
            },
            scoring_result={
                "summaryScores": {"engagementScore": 84.0, "overallPerformanceScore": 82.0},
                "detailedScores": {"engagement": {"score": 84.0, "components": {"eyeContactScore": 82.0}}},
                "feedbackMessages": ["Good confidence in technical explanations."],
            },
            request_payload=InterviewReportRequest(
                includeChartSnapshots=True,
                chartSnapshots={
                    "engagementTimeline": "data:image/png;base64,ZmFrZQ==",
                    "invalid": "bad",
                },
            ),
        )

        self.assertEqual(payload["title"], "InterviewInsight AI Report")
        self.assertEqual(payload["sessionMetadata"]["sessionId"], "session-42")
        self.assertEqual(payload["overallScores"]["engagementScore"], 84.0)
        self.assertEqual(payload["feedbackMessages"][0], "Good confidence in technical explanations.")
        self.assertEqual(len(payload["segmentSummaries"]), 1)
        self.assertIn("engagementTimeline", payload["chartSnapshots"])
        self.assertNotIn("invalid", payload["chartSnapshots"])


if __name__ == "__main__":
    unittest.main()
