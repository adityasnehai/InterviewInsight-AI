import logging
import statistics
from collections import defaultdict

LOGGER = logging.getLogger(__name__)


class NeutralFeatureFairnessAnalyzer:
    """Audits score spread across neutral feature bands (no demographics)."""

    def __init__(self) -> None:
        self._history: list[dict] = []
        self._max_samples = 1000

    def analyze(
        self,
        session_id: str,
        core_scores: dict[str, float],
        engagement_metrics: dict,
        speech_quality_metrics: dict,
        segment_labels: list[dict],
    ) -> dict:
        feature_groups = {
            "eyeContactBand": _band_eye_contact(float(engagement_metrics.get("eyeContactRatio", 0.0))),
            "speakingRateBand": _band_speaking_rate(float(speech_quality_metrics.get("speakingRateWpm", 0.0))),
            "pauseBand": _band_pause(float(speech_quality_metrics.get("averagePauseDuration", 0.0))),
            "contentRelevanceBand": _band_relevance(_average_relevance(segment_labels)),
        }
        scores = {
            "engagement": _clamp(float(core_scores.get("engagement", 0.0)), 0.0, 100.0),
            "communicationClarity": _clamp(float(core_scores.get("communicationClarity", 0.0)), 0.0, 100.0),
            "interviewComprehension": _clamp(float(core_scores.get("interviewComprehension", 0.0)), 0.0, 100.0),
            "overallPerformance": _clamp(float(core_scores.get("overallPerformance", 0.0)), 0.0, 100.0),
        }

        sample = {
            "sessionId": session_id,
            "groups": feature_groups,
            "scores": scores,
        }
        self._history.append(sample)
        self._history = self._history[-self._max_samples :]

        variance_summary: dict[str, dict] = {}
        warnings: list[str] = []

        for group_key in feature_groups:
            grouped_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
            for row in self._history:
                bucket = str(row["groups"].get(group_key, "unknown"))
                for score_name, score_value in row["scores"].items():
                    grouped_values[bucket][score_name].append(float(score_value))

            group_report: dict[str, dict] = {}
            for score_name in scores:
                means = {
                    bucket: statistics.mean(values[score_name])
                    for bucket, values in grouped_values.items()
                    if values[score_name]
                }
                if means:
                    spread = max(means.values()) - min(means.values())
                else:
                    spread = 0.0
                group_report[score_name] = {
                    "bucketMeans": {k: round(v, 2) for k, v in means.items()},
                    "spread": round(spread, 2),
                }
                if len(means) >= 2 and spread > 18.0 and len(self._history) >= 15:
                    warnings.append(
                        f"Score spread for {score_name} across {group_key} is {spread:.2f}; investigate calibration."
                    )

            variance_summary[group_key] = group_report

        if warnings:
            LOGGER.warning("Neutral fairness warnings for session %s: %s", session_id, warnings)

        return {
            "sampleCount": len(self._history),
            "neutralMetricsUsed": sorted(feature_groups.keys()),
            "groupVariance": variance_summary,
            "warnings": warnings,
        }


FAIRNESS_ANALYZER = NeutralFeatureFairnessAnalyzer()


def analyze_score_fairness(
    session_id: str,
    core_scores: dict[str, float],
    engagement_metrics: dict,
    speech_quality_metrics: dict,
    segment_labels: list[dict],
) -> dict:
    return FAIRNESS_ANALYZER.analyze(
        session_id=session_id,
        core_scores=core_scores,
        engagement_metrics=engagement_metrics,
        speech_quality_metrics=speech_quality_metrics,
        segment_labels=segment_labels,
    )


def _average_relevance(segment_labels: list[dict]) -> float:
    if not segment_labels:
        return 0.0
    values = [float(item.get("textRelevanceScore", 0.0)) for item in segment_labels]
    return statistics.mean(values) if values else 0.0


def _band_eye_contact(eye_contact: float) -> str:
    value = eye_contact * 100.0 if eye_contact <= 1.0 else eye_contact
    if value >= 75.0:
        return "high_eye_contact"
    if value >= 45.0:
        return "medium_eye_contact"
    return "low_eye_contact"


def _band_speaking_rate(rate: float) -> str:
    if rate <= 0:
        return "unknown_rate"
    if rate < 110:
        return "slow_rate"
    if rate <= 160:
        return "optimal_rate"
    return "fast_rate"


def _band_pause(pause: float) -> str:
    if pause <= 0:
        return "minimal_pause"
    if pause < 0.5:
        return "short_pause"
    if pause < 1.0:
        return "moderate_pause"
    return "long_pause"


def _band_relevance(relevance: float) -> str:
    if relevance >= 80.0:
        return "high_relevance"
    if relevance >= 60.0:
        return "medium_relevance"
    return "low_relevance"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
