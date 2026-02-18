import logging
import statistics
from collections import defaultdict

from app.scoring.rubric import map_scores_to_rubric
from app.scoring.scoring_models import InterviewReadinessModel

LOGGER = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "gender",
    "race",
    "ethnicity",
    "age",
    "accent",
    "nationality",
    "religion",
    "disability",
}
IRRELEVANT_KEYS = {"camera_brand", "device_model", "network_quality", "lighting_condition"}


class BiasAuditor:
    """Tracks score distributions and warns on potential demographic leakage."""

    def __init__(self) -> None:
        self._history: list[dict] = []
        self._max_samples = 500

    def audit(self, session_context: dict, summary_scores: dict) -> dict:
        flagged_sensitive = {k: v for k, v in session_context.items() if k in SENSITIVE_KEYS and v is not None}
        flagged_irrelevant = {k: v for k, v in session_context.items() if k in IRRELEVANT_KEYS and v is not None}

        warnings: list[str] = []
        if flagged_irrelevant:
            warnings.append(
                "Irrelevant context fields detected; they are excluded from scoring inputs."
            )

        if flagged_sensitive:
            self._history.append(
                {
                    "overall": float(summary_scores.get("overallPerformanceScore", 0.0)),
                    "sensitive": flagged_sensitive,
                }
            )
            self._history = self._history[-self._max_samples :]

            for key in flagged_sensitive:
                group_scores: dict[str, list[float]] = defaultdict(list)
                for sample in self._history:
                    if key not in sample["sensitive"]:
                        continue
                    group_scores[str(sample["sensitive"][key])].append(float(sample["overall"]))

                if len(group_scores) < 2:
                    continue
                means = [statistics.mean(values) for values in group_scores.values() if values]
                if not means:
                    continue
                spread = max(means) - min(means)
                if spread > 15.0 and len(self._history) >= 20:
                    warnings.append(
                        f"Potential score disparity detected across '{key}' groups (mean spread {spread:.2f})."
                    )

        if warnings:
            LOGGER.warning("Scoring fairness audit warnings: %s", warnings)
        else:
            LOGGER.info("Scoring fairness audit passed with no detected disparities in available context.")

        return {
            "checkedSensitiveAttributes": sorted(flagged_sensitive.keys()),
            "checkedIrrelevantAttributes": sorted(flagged_irrelevant.keys()),
            "warnings": warnings,
            "historySampleCount": len(self._history),
        }


BIAS_AUDITOR = BiasAuditor()


def compute_session_scores(
    engagement_metrics: dict,
    emotion_trajectory: list[dict],
    speech_quality_metrics: dict,
    segment_labels: list[dict],
    fused_feature_vectors: list[dict],
    timeline_arrays: dict | None = None,
) -> dict:
    """Compute normalized 0-100 composite scores for interview performance."""
    timeline_arrays = timeline_arrays or {}

    engagement_score, engagement_details = compute_engagement_score(
        engagement_metrics=engagement_metrics,
        fused_feature_vectors=fused_feature_vectors,
    )
    emotional_regulation_score, emotional_details = compute_emotional_regulation_score(
        emotion_trajectory=emotion_trajectory,
    )
    speech_clarity_score, speech_details = compute_speech_clarity_score(
        speech_quality_metrics=speech_quality_metrics,
        speech_timeline=timeline_arrays.get("speechTimeline", []),
    )
    content_relevance_score, content_details = compute_content_relevance_score(
        segment_labels=segment_labels,
        fused_feature_vectors=fused_feature_vectors,
    )

    overall_score = compute_overall_performance_score(
        engagement_score=engagement_score,
        emotional_regulation_score=emotional_regulation_score,
        speech_clarity_score=speech_clarity_score,
        content_relevance_score=content_relevance_score,
    )

    readiness_model = InterviewReadinessModel()
    model_predictions = readiness_model.predict(fused_feature_vectors)

    summary_scores = {
        "engagementScore": round(engagement_score, 2),
        "confidenceScore": round(model_predictions["confidence"], 2),
        "speechFluency": round(speech_clarity_score, 2),
        "emotionalStability": round(emotional_regulation_score, 2),
        "contentRelevanceScore": round(content_relevance_score, 2),
        "overallPerformanceScore": round(overall_score, 2),
        "communicationEffectiveness": round(model_predictions["communicationEffectiveness"], 2),
        "interviewReadiness": round(model_predictions["interviewReadiness"], 2),
    }

    detailed_scores = {
        "engagement": {
            "score": round(engagement_score, 2),
            "components": engagement_details,
        },
        "emotionalRegulation": {
            "score": round(emotional_regulation_score, 2),
            "components": emotional_details,
        },
        "speechClarity": {
            "score": round(speech_clarity_score, 2),
            "components": speech_details,
        },
        "contentRelevance": {
            "score": round(content_relevance_score, 2),
            "components": content_details,
        },
        "modelPredictions": model_predictions,
        "weights": {
            "engagement": 0.3,
            "emotionalRegulation": 0.2,
            "speechClarity": 0.25,
            "contentRelevance": 0.25,
        },
    }
    rubric_evaluation = map_scores_to_rubric(summary_scores=summary_scores)

    return {
        "summaryScores": summary_scores,
        "detailedScores": detailed_scores,
        "rubricEvaluation": rubric_evaluation,
    }


def compute_engagement_score(engagement_metrics: dict, fused_feature_vectors: list[dict]) -> tuple[float, dict]:
    eye_contact_ratio = float(engagement_metrics.get("eyeContactRatio", 0.0))
    eye_contact_score = _normalize_percent(eye_contact_ratio)

    gazes = [str(item.get("gazeDirection", "unknown")).lower() for item in fused_feature_vectors]
    if gazes:
        counts: dict[str, int] = defaultdict(int)
        for gaze in gazes:
            counts[gaze] += 1
        dominant_ratio = max(counts.values()) / len(gazes)
        center_ratio = counts.get("center", 0) / len(gazes)
        gaze_stability = ((dominant_ratio * 0.5) + (center_ratio * 0.5)) * 100.0
    else:
        gaze_stability = 40.0

    head_motion_values = []
    for item in fused_feature_vectors:
        head_pose = item.get("headPose", {})
        motion = (
            abs(float(head_pose.get("yaw", 0.0)))
            + abs(float(head_pose.get("pitch", 0.0)))
            + abs(float(head_pose.get("roll", 0.0)))
        )
        head_motion_values.append(motion)

    avg_head_motion = statistics.mean(head_motion_values) if head_motion_values else 20.0
    head_motion_score = _clamp(100.0 - (avg_head_motion * 1.5), 0.0, 100.0)

    score = (eye_contact_score * 0.4) + (gaze_stability * 0.35) + (head_motion_score * 0.25)
    return _clamp(score, 0.0, 100.0), {
        "eyeContactScore": round(eye_contact_score, 2),
        "gazeStabilityScore": round(gaze_stability, 2),
        "headMotionScore": round(head_motion_score, 2),
    }


def compute_emotional_regulation_score(emotion_trajectory: list[dict]) -> tuple[float, dict]:
    if not emotion_trajectory:
        return 50.0, {"dominantEmotionVariance": 0.0, "averageEmotionVariance": 0.0}

    dominant_scores = []
    per_label_series: dict[str, list[float]] = defaultdict(list)

    for point in emotion_trajectory:
        emotion_scores = point.get("emotionScores", {})
        if not emotion_scores:
            continue
        dominant_scores.append(max(float(value) for value in emotion_scores.values()))
        for label, value in emotion_scores.items():
            per_label_series[label].append(float(value))

    dominant_var = statistics.pvariance(dominant_scores) if len(dominant_scores) > 1 else 0.0
    label_vars = [statistics.pvariance(series) for series in per_label_series.values() if len(series) > 1]
    avg_label_var = statistics.mean(label_vars) if label_vars else 0.0

    variance_penalty = min(100.0, (dominant_var * 280.0) + (avg_label_var * 220.0))
    score = _clamp(100.0 - variance_penalty, 0.0, 100.0)
    return score, {
        "dominantEmotionVariance": round(dominant_var, 6),
        "averageEmotionVariance": round(avg_label_var, 6),
    }


def compute_speech_clarity_score(speech_quality_metrics: dict, speech_timeline: list[dict]) -> tuple[float, dict]:
    avg_pause = float(speech_quality_metrics.get("averagePauseDuration", 0.0))
    speaking_rate = float(speech_quality_metrics.get("speakingRateWpm", 0.0))

    pause_score = _clamp(100.0 - (avg_pause * 65.0), 0.0, 100.0)
    speaking_rate_score = _clamp(100.0 - (abs(speaking_rate - 135.0) / 135.0) * 100.0, 0.0, 100.0)

    pitch_values = [float(item.get("pitch", 0.0)) for item in speech_timeline if item.get("pitch") is not None]
    pitch_variance = statistics.pvariance(pitch_values) if len(pitch_values) > 1 else 0.0
    pitch_variance_score = _clamp(100.0 - (pitch_variance / 9.0), 0.0, 100.0)

    score = (pause_score * 0.35) + (speaking_rate_score * 0.45) + (pitch_variance_score * 0.2)
    return _clamp(score, 0.0, 100.0), {
        "pauseScore": round(pause_score, 2),
        "speakingRateScore": round(speaking_rate_score, 2),
        "pitchVarianceScore": round(pitch_variance_score, 2),
        "pitchVariance": round(pitch_variance, 4),
    }


def compute_content_relevance_score(segment_labels: list[dict], fused_feature_vectors: list[dict]) -> tuple[float, dict]:
    if segment_labels:
        values = [float(item.get("textRelevanceScore", 0.0)) for item in segment_labels]
        score = statistics.mean(values) if values else 0.0
        return _clamp(score, 0.0, 100.0), {
            "source": "segmentLabels",
            "segmentCount": len(segment_labels),
            "avgSegmentRelevance": round(score, 2),
        }

    semantic_values = [
        float(item.get("textScores", {}).get("semantic_relevance", 0.0)) * 100.0
        for item in fused_feature_vectors
    ]
    score = statistics.mean(semantic_values) if semantic_values else 0.0
    return _clamp(score, 0.0, 100.0), {
        "source": "fusedFeatureVectors",
        "segmentCount": len(fused_feature_vectors),
        "avgSegmentRelevance": round(score, 2),
    }


def compute_overall_performance_score(
    engagement_score: float,
    emotional_regulation_score: float,
    speech_clarity_score: float,
    content_relevance_score: float,
) -> float:
    weighted = (
        (engagement_score * 0.3)
        + (emotional_regulation_score * 0.2)
        + (speech_clarity_score * 0.25)
        + (content_relevance_score * 0.25)
    )
    return _clamp(weighted, 0.0, 100.0)


def audit_scoring_bias(session_context: dict, summary_scores: dict) -> dict:
    return BIAS_AUDITOR.audit(session_context=session_context, summary_scores=summary_scores)


def _normalize_percent(value: float) -> float:
    if value <= 1.0:
        return _clamp(value * 100.0, 0.0, 100.0)
    return _clamp(value, 0.0, 100.0)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
