import unittest

try:
    from app.models.session import SessionStartRequest
    from app.scoring.llm_feedback import generate_reflective_coaching
    from app.services.session_store import session_store

    DEPENDENCIES_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    DEPENDENCIES_AVAILABLE = False
    SessionStartRequest = None
    session_store = None
    generate_reflective_coaching = None


@unittest.skipUnless(DEPENDENCIES_AVAILABLE, "pydantic/fastapi dependencies are not installed")
class ReflectiveWorkflowTests(unittest.TestCase):
    def test_reflection_storage_and_summary(self) -> None:
        session = session_store.create_session(
            SessionStartRequest(userId="reflect-user", jobRole="ML Engineer", domain="Healthcare")
        )
        session_id = session["sessionId"]
        session_store.set_scoring_result(
            session_id,
            {
                "summaryScores": {
                    "engagementScore": 68.0,
                    "communicationEffectiveness": 64.0,
                    "contentRelevanceScore": 71.0,
                    "overallPerformanceScore": 66.0,
                },
                "feedbackMessages": ["Use clearer structure and stronger quantified examples."],
                "rubricEvaluation": {},
            },
        )

        coaching = generate_reflective_coaching(
            session_id=session_id,
            reflection_text="I felt I lost structure in technical answers.",
            summary_scores=session_store.get_scoring_result(session_id)["summaryScores"],
            feedback_messages=session_store.get_scoring_result(session_id)["feedbackMessages"],
        )
        entry = session_store.add_reflection(
            session_id=session_id,
            reflection_text="I need better structure and confidence.",
            coaching_feedback=coaching,
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["sessionId"], session_id)
        self.assertTrue(str(entry["coachingFeedback"]["coachingResponse"]).strip())

        summary = session_store.summarize_user_reflections("reflect-user")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["userId"], "reflect-user")
        self.assertGreaterEqual(summary["totalReflections"], 1)
        self.assertTrue(len(summary["aggregatedInsights"]) >= 1)


if __name__ == "__main__":
    unittest.main()
