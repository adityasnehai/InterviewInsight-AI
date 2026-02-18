import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.services.ai_interviewer import generate_followup_question

try:
    from app.models.session import SessionStartRequest
    from app.services.session_store import session_store

    DEPENDENCIES_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - env dependent
    DEPENDENCIES_AVAILABLE = False
    SessionStartRequest = None
    session_store = None


class LiveInterviewerUtilsTests(unittest.TestCase):
    def test_generate_followup_question_starts_with_greeting_when_no_turns(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            question = generate_followup_question(
                job_role="Backend Engineer",
                domain="FinTech",
                turns=[],
            )
        self.assertIn("great to meet you", question.lower())

    def test_generate_followup_question_returns_text(self) -> None:
        question = generate_followup_question(
            job_role="Backend Engineer",
            domain="FinTech",
            turns=[
                {"role": "assistant", "text": "Tell me about your backend experience."},
                {"role": "user", "text": "I designed APIs and improved latency."},
            ],
        )
        self.assertTrue(isinstance(question, str))
        self.assertTrue(question.strip())

    def test_generate_followup_question_supports_datetime_turn_fields(self) -> None:
        question = generate_followup_question(
            job_role="Backend Engineer",
            domain="FinTech",
            turns=[
                {
                    "role": "assistant",
                    "text": "Walk me through your latest backend migration.",
                    "timestamp": datetime.now(timezone.utc),
                },
                {
                    "role": "user",
                    "text": "I migrated services from monolith to async APIs.",
                    "timestamp": datetime.now(timezone.utc),
                },
            ],
        )
        self.assertTrue(isinstance(question, str))
        self.assertTrue(question.strip())


@unittest.skipUnless(DEPENDENCIES_AVAILABLE, "pydantic dependencies are not installed")
class LiveInterviewerStateTests(unittest.TestCase):
    def test_session_store_live_state_flow(self) -> None:
        session = session_store.create_session(
            SessionStartRequest(userId="live-user", jobRole="ML Engineer", domain="Healthcare")
        )
        session_id = session["sessionId"]
        self.assertEqual(len(session["questions"]), 5)
        self.assertIn("great to meet you", str(session["questions"][0]["questionText"]).lower())
        live_state = session_store.initialize_live_interview(session_id)
        self.assertIsNotNone(live_state)
        self.assertEqual(live_state["questionIndex"], 0)
        self.assertIn("great to meet you", str(live_state["currentQuestionText"]).lower())

        saved_answer = session_store.record_live_answer(session_id=session_id, answer_text="I built model APIs.")
        self.assertIsNotNone(saved_answer)

        next_state = session_store.set_live_next_question(
            session_id=session_id,
            question_id="q2",
            question_text="How did you evaluate model quality?",
            question_index=1,
        )
        self.assertIsNotNone(next_state)
        self.assertEqual(next_state["questionIndex"], 1)

        completed = session_store.mark_live_complete(session_id)
        self.assertTrue(completed["complete"])


if __name__ == "__main__":
    unittest.main()
