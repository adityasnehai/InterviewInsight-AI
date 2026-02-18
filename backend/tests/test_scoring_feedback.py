import unittest

from app.scoring.feedback_generator import generate_feedback_payload
from app.scoring.score_calculator import audit_scoring_bias, compute_session_scores


class ScoringFeedbackTests(unittest.TestCase):
    def test_compute_session_scores_range_and_shape(self) -> None:
        score_payload = compute_session_scores(
            engagement_metrics={
                "overallEngagement": 0.74,
                "eyeContactRatio": 0.7,
                "avgHeadStability": 0.82,
                "avgSpeakingRateWpm": 128.0,
            },
            emotion_trajectory=[
                {
                    "timestamp": 0.0,
                    "dominantEmotion": "neutral",
                    "emotionScores": {"neutral": 0.8, "happy": 0.2},
                },
                {
                    "timestamp": 2.0,
                    "dominantEmotion": "neutral",
                    "emotionScores": {"neutral": 0.75, "happy": 0.25},
                },
            ],
            speech_quality_metrics={
                "averagePitch": 148.0,
                "averagePauseDuration": 0.35,
                "speakingRateWpm": 132.0,
                "prosodyScore": 0.74,
            },
            segment_labels=[
                {
                    "segmentId": "segment_1",
                    "textRelevanceScore": 88.0,
                },
                {
                    "segmentId": "segment_2",
                    "textRelevanceScore": 82.0,
                },
            ],
            fused_feature_vectors=[
                {
                    "gazeDirection": "center",
                    "headPose": {"yaw": 2.0, "pitch": 1.5, "roll": 1.0},
                    "textScores": {"semantic_relevance": 0.86, "sentiment_score": 0.2, "answer_coherence": 0.8},
                    "fusedVector": [0.3, 0.6, 0.1, 132.0, 148.0, 0.35, 0.86, 0.2, 0.8, 1.0],
                },
                {
                    "gazeDirection": "center",
                    "headPose": {"yaw": 2.5, "pitch": 1.8, "roll": 1.1},
                    "textScores": {"semantic_relevance": 0.84, "sentiment_score": 0.1, "answer_coherence": 0.79},
                    "fusedVector": [0.28, 0.62, 0.1, 130.0, 146.0, 0.3, 0.84, 0.1, 0.79, 1.0],
                },
            ],
            timeline_arrays={
                "speechTimeline": [
                    {"timestamp": 1.0, "pitch": 148.0},
                    {"timestamp": 2.0, "pitch": 146.0},
                ]
            },
        )

        summary = score_payload["summaryScores"]
        self.assertIn("overallPerformanceScore", summary)
        for key, value in summary.items():
            self.assertGreaterEqual(float(value), 0.0, key)
            self.assertLessEqual(float(value), 100.0, key)

        detailed = score_payload["detailedScores"]
        self.assertIn("engagement", detailed)
        self.assertIn("speechClarity", detailed)
        self.assertIn("modelPredictions", detailed)

    def test_feedback_rules_trigger_for_low_scores(self) -> None:
        feedback_payload = generate_feedback_payload(
            summary_scores={
                "engagementScore": 45.0,
                "confidenceScore": 52.0,
                "speechFluency": 41.0,
                "emotionalStability": 46.0,
                "contentRelevanceScore": 58.0,
                "overallPerformanceScore": 49.0,
                "communicationEffectiveness": 50.0,
                "interviewReadiness": 48.0,
            },
            detailed_scores={
                "engagement": {"score": 45.0, "components": {"eyeContactScore": 42.0}},
                "emotionalRegulation": {"score": 46.0, "components": {"dominantEmotionVariance": 0.2}},
                "speechClarity": {"score": 41.0, "components": {"pauseScore": 35.0}},
                "contentRelevance": {"score": 58.0, "components": {"avgSegmentRelevance": 58.0}},
            },
        )

        messages = " ".join(feedback_payload["feedbackMessages"]).lower()
        self.assertIn("engagement", messages)
        self.assertIn("speech", messages)
        self.assertIn("overall performance", messages)
        self.assertGreaterEqual(len(feedback_payload["improvements"]), 1)

    def test_bias_audit_flags_irrelevant_fields(self) -> None:
        audit = audit_scoring_bias(
            session_context={
                "userId": "abc",
                "jobRole": "Engineer",
                "camera_brand": "BrandX",
            },
            summary_scores={
                "overallPerformanceScore": 71.0,
            },
        )

        self.assertIn("camera_brand", audit["checkedIrrelevantAttributes"])


if __name__ == "__main__":
    unittest.main()
