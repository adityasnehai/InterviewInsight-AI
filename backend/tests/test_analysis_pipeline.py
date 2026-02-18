import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from app.api.analysis import get_analysis_results, get_analysis_scores
    from app.models.analysis import VideoAnalysisRequest
    from app.models.session import SessionStartRequest
    from app.services.analysis_pipeline import execute_video_analysis
    from app.services.session_store import session_store

    DEPENDENCIES_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - env dependent
    DEPENDENCIES_AVAILABLE = False


@unittest.skipUnless(DEPENDENCIES_AVAILABLE, "analysis dependencies are not installed")
class AnalysisPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        session = session_store.create_session(
            SessionStartRequest(userId="test-user", jobRole="ML Engineer", domain="Healthcare")
        )
        self.session_id = session["sessionId"]
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(b"fake-video-content")
        tmp.close()
        self.video_path = Path(tmp.name)

    def tearDown(self) -> None:
        self.video_path.unlink(missing_ok=True)

    @patch("app.services.analysis_pipeline.fuse_multimodal_features")
    @patch("app.services.analysis_pipeline.compute_session_scores")
    @patch("app.services.analysis_pipeline.generate_feedback_payload")
    @patch("app.services.analysis_pipeline.audit_scoring_bias")
    @patch("app.services.analysis_pipeline.process_transcript")
    @patch("app.services.analysis_pipeline.process_audio")
    @patch("app.services.analysis_pipeline.process_video")
    @patch("app.services.analysis_pipeline.compute_advanced_multimodal_scores")
    @patch("app.services.analysis_pipeline.evaluate_llm_judge")
    @patch("app.services.analysis_pipeline.analyze_score_fairness")
    @patch("app.services.analysis_pipeline.generate_score_explanations")
    def test_video_analysis_and_result_fetch(
        self,
        explanations_mock,
        fairness_mock,
        llm_judge_mock,
        advanced_scores_mock,
        process_video_mock,
        process_audio_mock,
        process_transcript_mock,
        audit_scoring_bias_mock,
        generate_feedback_payload_mock,
        compute_session_scores_mock,
        fuse_mock,
    ) -> None:
        process_video_mock.return_value = [
            {
                "timestamp": 0.0,
                "facial_emotion_scores": {"neutral": 0.8, "happy": 0.2},
                "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
                "gaze_direction": "center",
                "eye_contact": 1.0,
            }
        ]
        process_audio_mock.return_value = {
            "audio_file_path": "/tmp/sample.wav",
            "transcript_text": "I built scalable APIs.",
            "transcript_segments": [{"start": 0.0, "end": 2.0, "text": "I built scalable APIs."}],
            "speech_features": {},
            "segment_features": [
                {
                    "start": 0.0,
                    "end": 2.0,
                    "pitch": 140.0,
                    "pause_duration": 0.2,
                    "speaking_rate": 120.0,
                    "prosody": {"log_mel_std": 0.7},
                }
            ],
        }
        process_transcript_mock.return_value = {
            "transcript_text": "I built scalable APIs.",
            "segment_scores": [
                {
                    "start": 0.0,
                    "end": 2.0,
                    "text": "I built scalable APIs.",
                    "semantic_relevance": 0.9,
                    "sentiment_score": 0.3,
                    "answer_coherence": 0.95,
                }
            ],
            "overall": {},
        }
        fuse_mock.return_value = {
            "engagement_metrics": {
                "overallEngagement": 0.86,
                "eyeContactRatio": 1.0,
                "avgHeadStability": 0.95,
                "avgSpeakingRateWpm": 120.0,
            },
            "emotion_trajectory": [
                {"timestamp": 0.0, "dominantEmotion": "neutral", "emotionScores": {"neutral": 0.8, "happy": 0.2}}
            ],
            "speech_quality_metrics": {
                "averagePitch": 140.0,
                "averagePauseDuration": 0.2,
                "speakingRateWpm": 120.0,
                "prosodyScore": 0.7,
            },
            "fused_feature_vectors": [
                {
                    "startTime": 0.0,
                    "endTime": 2.0,
                    "facialEmotionScores": {"neutral": 0.8, "happy": 0.2},
                    "headPose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
                    "gazeDirection": "center",
                    "speechFeatures": {
                        "pitch": 140.0,
                        "pause_duration": 0.2,
                        "speaking_rate": 120.0,
                        "prosody_score": 0.7,
                    },
                    "textScores": {"semantic_relevance": 0.9, "sentiment_score": 0.3, "answer_coherence": 0.95},
                    "fusedVector": [0.8, 120.0, 0.9],
                }
            ],
            "segment_labels": [
                {
                    "segmentId": "segment_1",
                    "label": "Question Segment 1",
                    "startTime": 0.0,
                    "endTime": 2.0,
                    "engagementScore": 86.0,
                    "speechFluency": 78.0,
                    "textRelevanceScore": 90.0,
                    "dominantEmotion": "neutral",
                    "emotionAverages": {"neutral": 0.8, "happy": 0.2},
                    "speechQualityMetrics": {"pitch": 140.0, "speaking_rate": 120.0},
                }
            ],
            "timeline_arrays": {
                "emotionTimeline": [
                    {"timestamp": 0.0, "dominantEmotion": "neutral", "emotionScores": {"neutral": 0.8, "happy": 0.2}}
                ],
                "engagementTimeline": [{"timestamp": 1.0, "engagement": 86.0, "confidence": 84.0}],
                "speechTimeline": [{"timestamp": 1.0, "speakingRate": 120.0, "pitch": 140.0, "pauseDuration": 0.2, "fluency": 78.0}],
                "gazeHeadPoseTimeline": [{"timestamp": 0.0, "headYaw": 0.0, "headPitch": 0.0, "headRoll": 0.0, "eyeContact": 100.0, "gazeDirection": "center"}],
            },
            "feedback_summary": {
                "strengths": ["Strong engagement maintained across most of the interview."],
                "improvements": ["Work on pacing and reducing long pauses between key points."],
                "suggestedFeedbackText": "Top strengths: Strong engagement maintained across most of the interview. Primary improvements: Work on pacing and reducing long pauses between key points.",
            },
        }

        compute_session_scores_mock.return_value = {
            "summaryScores": {
                "engagementScore": 86.0,
                "confidenceScore": 84.0,
                "speechFluency": 78.0,
                "emotionalStability": 82.0,
                "contentRelevanceScore": 90.0,
                "overallPerformanceScore": 84.0,
                "communicationEffectiveness": 83.0,
                "interviewReadiness": 82.0,
            },
            "detailedScores": {
                "engagement": {"score": 86.0, "components": {"eyeContactScore": 100.0}},
                "emotionalRegulation": {"score": 82.0, "components": {"dominantEmotionVariance": 0.01}},
                "speechClarity": {"score": 78.0, "components": {"pauseScore": 85.0}},
                "contentRelevance": {"score": 90.0, "components": {"avgSegmentRelevance": 90.0}},
                "modelPredictions": {
                    "confidence": 84.0,
                    "communicationEffectiveness": 83.0,
                    "interviewReadiness": 82.0,
                },
                "weights": {
                    "engagement": 0.3,
                    "emotionalRegulation": 0.2,
                    "speechClarity": 0.25,
                    "contentRelevance": 0.25,
                },
                "biasAudit": {},
            },
        }
        audit_scoring_bias_mock.return_value = {
            "checkedSensitiveAttributes": [],
            "checkedIrrelevantAttributes": [],
            "warnings": [],
            "historySampleCount": 0,
        }
        generate_feedback_payload_mock.return_value = {
            "feedbackMessages": ["Engagement is strong."],
            "strengths": ["Strong engagement maintained across most of the interview."],
            "improvements": ["Work on pacing and reducing long pauses between key points."],
            "rationale": {},
            "suggestedFeedbackText": "Top strengths: Strong engagement maintained across most of the interview.",
        }
        advanced_scores_mock.return_value = {
            "engagement": 85.0,
            "communicationClarity": 83.0,
            "interviewComprehension": 82.0,
            "overallPerformance": 84.0,
        }
        llm_judge_mock.return_value = {
            "answerDepth": 80.0,
            "technicalCorrectness": 82.0,
            "relevanceToRole": 84.0,
            "rationale": "Looks good.",
        }
        fairness_mock.return_value = {"sampleCount": 1, "warnings": []}
        explanations_mock.return_value = [
            {"scoreKey": "engagement", "explanation": "Engagement was high."}
        ]

        result = execute_video_analysis(
            VideoAnalysisRequest(
                sessionId=self.session_id,
                videoFilePath=str(self.video_path),
                frameFps=3,
                windowSizeSeconds=2.0,
            )
        )
        stored_result = get_analysis_results(self.session_id)
        stored_scores = get_analysis_scores(self.session_id)

        self.assertEqual(result.sessionId, self.session_id)
        self.assertEqual(result.engagementMetrics.overallEngagement, 0.86)
        self.assertEqual(result.summaryScores.engagementScore, 86.0)
        self.assertEqual(result.summaryScores.overallPerformanceScore, 84.0)
        self.assertEqual(stored_result.sessionId, self.session_id)
        self.assertEqual(len(stored_result.fusedFeatureVectors), 1)
        self.assertEqual(len(stored_result.segmentLabels), 1)
        self.assertEqual(stored_scores.summaryScores.overallPerformanceScore, 84.0)
        self.assertEqual(stored_scores.feedbackMessages[0], "Engagement is strong.")


if __name__ == "__main__":
    unittest.main()
