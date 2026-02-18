import unittest

from app.scoring.rubric import map_scores_to_rubric, score_to_level


class RubricMappingTests(unittest.TestCase):
    def test_score_to_level_thresholds(self) -> None:
        levels = [
            type("Level", (), {"min_score": 85.0, "label": "Excellent"}),
            type("Level", (), {"min_score": 70.0, "label": "Good"}),
            type("Level", (), {"min_score": 0.0, "label": "Needs Improvement"}),
        ]
        self.assertEqual(score_to_level(91.0, levels).label, "Excellent")
        self.assertEqual(score_to_level(74.0, levels).label, "Good")
        self.assertEqual(score_to_level(45.0, levels).label, "Needs Improvement")

    def test_map_scores_to_rubric_returns_descriptors(self) -> None:
        rubric = map_scores_to_rubric(
            summary_scores={
                "engagementScore": 82.0,
                "communicationEffectiveness": 77.0,
                "contentRelevanceScore": 89.0,
                "overallPerformanceScore": 80.0,
            },
            advanced_scores={
                "communicationClarity": 79.0,
                "interviewComprehension": 88.0,
                "overallPerformance": 81.0,
            },
        )
        self.assertIn("communication", rubric)
        self.assertIn("technical_clarity", rubric)
        self.assertIn("behavioral_response", rubric)
        self.assertIn("engagement", rubric)

        for _, entry in rubric.items():
            self.assertIn(entry["level"], {"Excellent", "Good", "Needs Improvement"})
            self.assertTrue(str(entry["descriptor"]).strip())


if __name__ == "__main__":
    unittest.main()
