import unittest

try:
    from app.models.reports import InterviewReportRequest
    from app.models.session import SessionStartRequest
    from app.services.session_store import session_store
    from fastapi import HTTPException
    from app.api.reports import generate_interview_report

    DEPENDENCIES_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - environment-dependent guard
    DEPENDENCIES_AVAILABLE = False
    HTTPException = Exception
    InterviewReportRequest = None
    SessionStartRequest = None
    session_store = None
    generate_interview_report = None


@unittest.skipUnless(DEPENDENCIES_AVAILABLE, "pydantic/fastapi dependencies are not installed")
class ReportsGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        session = session_store.create_session(
            SessionStartRequest(userId="report-user", jobRole="Data Scientist", domain="HealthTech")
        )
        self.session_id = session["sessionId"]

        session_store.set_analysis_result(
            self.session_id,
            {
                "sessionId": self.session_id,
                "sessionMeta": {
                    "sessionId": self.session_id,
                    "jobRole": "Data Scientist",
                    "domain": "HealthTech",
                    "dateTime": "2026-02-16T10:00:00Z",
                },
                "summaryScores": {
                    "engagementScore": 82.0,
                    "confidenceScore": 78.0,
                    "speechFluency": 80.0,
                    "emotionalStability": 76.0,
                    "contentRelevanceScore": 85.0,
                    "overallPerformanceScore": 80.0,
                    "communicationEffectiveness": 79.0,
                    "interviewReadiness": 81.0,
                },
                "detailedScores": {
                    "engagement": {"score": 82.0, "components": {"eyeContactScore": 80.0}},
                    "speechClarity": {"score": 80.0, "components": {"pauseScore": 78.0}},
                },
                "segmentLabels": [
                    {
                        "segmentId": "segment_1",
                        "label": "Question Segment 1",
                        "startTime": 0.0,
                        "endTime": 30.0,
                        "engagementScore": 81.0,
                        "speechFluency": 79.0,
                        "textRelevanceScore": 84.0,
                        "dominantEmotion": "neutral",
                    }
                ],
                "feedbackSummary": {
                    "strengths": ["Good pacing and concise delivery."],
                    "improvements": ["Add more outcome-driven examples."],
                },
                "feedbackMessages": ["Maintain steady eye contact in key moments."],
            },
        )
        session_store.set_scoring_result(
            self.session_id,
            {
                "summaryScores": {
                    "engagementScore": 82.0,
                    "confidenceScore": 78.0,
                    "speechFluency": 80.0,
                    "emotionalStability": 76.0,
                    "contentRelevanceScore": 85.0,
                    "overallPerformanceScore": 80.0,
                    "communicationEffectiveness": 79.0,
                    "interviewReadiness": 81.0,
                },
                "detailedScores": {
                    "engagement": {"score": 82.0, "components": {"eyeContactScore": 80.0}},
                },
                "feedbackMessages": ["Great composure under follow-up questions."],
            },
        )

    def test_generate_report_returns_structured_payload(self) -> None:
        result = generate_interview_report(
            self.session_id,
            InterviewReportRequest(
                includeChartSnapshots=True,
                chartSnapshots={
                    "emotionTimeline": "data:image/png;base64,ZmFrZQ==",
                    "invalid": "not-an-image",
                },
                userName="Ada Lovelace",
            ),
        )

        self.assertEqual(result.title, "InterviewInsight AI Report")
        self.assertEqual(result.sessionMetadata["sessionId"], self.session_id)
        self.assertEqual(result.sessionMetadata["jobRole"], "Data Scientist")
        self.assertEqual(result.sessionMetadata["userName"], "Ada Lovelace")
        self.assertIn("overallPerformanceScore", result.overallScores)
        self.assertEqual(len(result.segmentSummaries), 1)
        self.assertEqual(result.segmentSummaries[0].segmentId, "segment_1")
        self.assertEqual(result.feedbackMessages[0], "Great composure under follow-up questions.")
        self.assertIn("emotionTimeline", result.chartSnapshots or {})
        self.assertNotIn("invalid", result.chartSnapshots or {})
        self.assertIsNotNone(session_store.get_report_result(self.session_id))

    def test_generate_report_requires_analysis(self) -> None:
        no_analysis_session = session_store.create_session(
            SessionStartRequest(userId="new-user", jobRole="Engineer", domain="General")
        )

        with self.assertRaises(HTTPException) as context:
            generate_interview_report(no_analysis_session["sessionId"], InterviewReportRequest())

        self.assertEqual(context.exception.status_code, 404)
        self.assertIn("Analysis result not found", str(context.exception.detail))


if __name__ == "__main__":
    unittest.main()
