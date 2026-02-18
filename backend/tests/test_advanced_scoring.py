import unittest

from app.scoring.advanced_scoring import compute_advanced_multimodal_scores, generate_score_explanations
from app.scoring.fairness import analyze_score_fairness
from app.scoring.llm_judge import build_llm_judge_prompt, evaluate_llm_judge


class AdvancedScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engagement_metrics = {
            "overallEngagement": 0.82,
            "eyeContactRatio": 0.78,
            "avgHeadStability": 0.85,
        }
        self.speech_quality_metrics = {
            "averagePauseDuration": 0.32,
            "speakingRateWpm": 132.0,
            "prosodyScore": 0.71,
        }
        self.segment_labels = [
            {"segmentId": "segment_1", "textRelevanceScore": 88.0},
            {"segmentId": "segment_2", "textRelevanceScore": 82.0},
        ]
        self.fused_feature_vectors = [
            {
                "gazeDirection": "center",
                "headPose": {"yaw": 2.0, "pitch": 1.0, "roll": 0.8},
                "speechFeatures": {"pitch": 145.0},
                "textScores": {"semantic_relevance": 0.86, "answer_coherence": 0.81, "sentiment_score": 0.15},
                "fusedVector": [0.4, 0.5, 0.1, 132.0, 145.0, 0.32, 0.86, 0.15, 0.81, 0.78],
            },
            {
                "gazeDirection": "center",
                "headPose": {"yaw": 1.8, "pitch": 1.1, "roll": 0.7},
                "speechFeatures": {"pitch": 147.0},
                "textScores": {"semantic_relevance": 0.84, "answer_coherence": 0.79, "sentiment_score": 0.2},
                "fusedVector": [0.42, 0.48, 0.1, 129.0, 147.0, 0.29, 0.84, 0.2, 0.79, 0.8],
            },
        ]
        self.transcript = (
            "I designed scalable backend APIs, improved performance by 35 percent, "
            "and added automated testing and observability for production reliability."
        )

    def test_advanced_scores_are_normalized(self) -> None:
        scores = compute_advanced_multimodal_scores(
            engagement_metrics=self.engagement_metrics,
            speech_quality_metrics=self.speech_quality_metrics,
            segment_labels=self.segment_labels,
            fused_feature_vectors=self.fused_feature_vectors,
        )
        for key in ["engagement", "communicationClarity", "interviewComprehension", "overallPerformance"]:
            self.assertIn(key, scores)
            self.assertGreaterEqual(float(scores[key]), 0.0)
            self.assertLessEqual(float(scores[key]), 100.0)

    def test_explanations_are_non_empty(self) -> None:
        scores = compute_advanced_multimodal_scores(
            engagement_metrics=self.engagement_metrics,
            speech_quality_metrics=self.speech_quality_metrics,
            segment_labels=self.segment_labels,
            fused_feature_vectors=self.fused_feature_vectors,
        )
        llm_scores = evaluate_llm_judge(
            transcript_text=self.transcript,
            job_role="Backend Engineer",
            domain="FinTech",
        )
        explanations = generate_score_explanations(
            numeric_scores=scores,
            engagement_metrics=self.engagement_metrics,
            speech_quality_metrics=self.speech_quality_metrics,
            segment_labels=self.segment_labels,
            llm_scores=llm_scores,
        )
        self.assertEqual(len(explanations), 4)
        for explanation in explanations:
            self.assertTrue(explanation["explanation"].strip())
            self.assertIn("scoreKey", explanation)
            self.assertIn("drivers", explanation)

    def test_llm_judge_prompt_and_scores(self) -> None:
        prompt = build_llm_judge_prompt(
            transcript_text=self.transcript,
            job_role="Backend Engineer",
            domain="FinTech",
        )
        self.assertIn("Backend Engineer", prompt)
        self.assertIn("FinTech", prompt)

        llm_scores = evaluate_llm_judge(
            transcript_text=self.transcript,
            job_role="Backend Engineer",
            domain="FinTech",
        )
        self.assertIn("rationale", llm_scores)
        self.assertIn("answerDepth", llm_scores)
        self.assertGreaterEqual(float(llm_scores["overallLLMJudgeScore"]), 0.0)
        self.assertLessEqual(float(llm_scores["overallLLMJudgeScore"]), 100.0)

    def test_fairness_report_has_summary(self) -> None:
        scores = compute_advanced_multimodal_scores(
            engagement_metrics=self.engagement_metrics,
            speech_quality_metrics=self.speech_quality_metrics,
            segment_labels=self.segment_labels,
            fused_feature_vectors=self.fused_feature_vectors,
        )
        fairness = analyze_score_fairness(
            session_id="session-advanced",
            core_scores=scores,
            engagement_metrics=self.engagement_metrics,
            speech_quality_metrics=self.speech_quality_metrics,
            segment_labels=self.segment_labels,
        )
        self.assertIn("sampleCount", fairness)
        self.assertIn("groupVariance", fairness)
        self.assertIn("neutralMetricsUsed", fairness)


if __name__ == "__main__":
    unittest.main()
