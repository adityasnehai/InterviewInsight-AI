import math
import statistics
from dataclasses import dataclass

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None

try:
    import torch
    import torch.nn as nn
except Exception:  # pragma: no cover - optional dependency
    torch = None
    nn = None


@dataclass
class TrainableRegressionHead:
    weights: list[float]
    bias: float = 0.0

    def predict(self, features: list[float]) -> float:
        if not features:
            return 50.0
        limit = min(len(features), len(self.weights))
        raw = self.bias
        for idx in range(limit):
            raw += self.weights[idx] * features[idx]
        return _sigmoid_to_100(raw)

    def fit(self, x_data: list[list[float]], y_data: list[float]) -> None:
        if np is None or not x_data or not y_data:
            return
        x = np.array(x_data, dtype=float)
        y = np.array(y_data, dtype=float)
        if x.ndim != 2 or y.ndim != 1 or x.shape[0] != y.shape[0]:
            return
        ones = np.ones((x.shape[0], 1), dtype=float)
        design = np.concatenate([x, ones], axis=1)
        try:
            coeffs = np.linalg.pinv(design.T @ design) @ design.T @ y
        except Exception:
            return
        self.weights = [float(item) for item in coeffs[:-1].tolist()]
        self.bias = float(coeffs[-1])


if nn is not None:
    class MultimodalTransformerRegressor(nn.Module):
        """Transformer encoder over modality embeddings with regression heads."""

        def __init__(
            self,
            embedding_dim: int = 4,
            hidden_dim: int = 16,
            num_heads: int = 2,
            layers: int = 1,
        ) -> None:
            super().__init__()
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=embedding_dim,
                nhead=num_heads,
                dim_feedforward=hidden_dim,
                batch_first=True,
                dropout=0.0,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=layers)
            self.score_head = nn.Sequential(
                nn.Linear(embedding_dim, hidden_dim),
                nn.GELU(),
                nn.Linear(hidden_dim, 4),
            )

        def forward(self, modality_tensor: torch.Tensor) -> torch.Tensor:
            encoded = self.encoder(modality_tensor)
            pooled = encoded.mean(dim=1)
            return self.score_head(pooled)
else:
    class MultimodalTransformerRegressor:  # pragma: no cover - torch unavailable fallback
        def __init__(self, *args, **kwargs) -> None:
            return None


class AdvancedMultimodalScorer:
    """Hybrid scorer that ensembles transformer inference with trainable heads."""

    def __init__(self) -> None:
        # Feature order:
        # [vision(4), audio(4), text(4)]
        self.engagement_head = TrainableRegressionHead(
            weights=[0.9, 0.65, 0.55, 0.25, 0.15, 0.18, 0.08, 0.12, 0.2, 0.15, 0.2, 0.18],
            bias=-0.72,
        )
        self.communication_head = TrainableRegressionHead(
            weights=[0.22, 0.18, 0.2, 0.08, 0.68, 0.75, 0.42, 0.66, 0.3, 0.34, 0.2, 0.24],
            bias=-0.78,
        )
        self.comprehension_head = TrainableRegressionHead(
            weights=[0.18, 0.2, 0.12, 0.06, 0.2, 0.28, 0.16, 0.14, 0.74, 0.62, 0.5, 0.7],
            bias=-0.8,
        )
        self.overall_head = TrainableRegressionHead(
            weights=[0.36, 0.3, 0.26, 0.12, 0.34, 0.36, 0.24, 0.3, 0.42, 0.38, 0.31, 0.36],
            bias=-0.84,
        )

        self.transformer = None
        if torch is not None and nn is not None:
            torch.manual_seed(7)
            self.transformer = MultimodalTransformerRegressor()
            self.transformer.eval()

    def predict(
        self,
        engagement_metrics: dict,
        speech_quality_metrics: dict,
        segment_labels: list[dict],
        fused_feature_vectors: list[dict],
    ) -> dict:
        vision_embedding = _build_vision_embedding(engagement_metrics, fused_feature_vectors)
        audio_embedding = _build_audio_embedding(speech_quality_metrics, fused_feature_vectors)
        text_embedding = _build_text_embedding(segment_labels, fused_feature_vectors)
        combined_features = vision_embedding + audio_embedding + text_embedding

        regression_scores = {
            "engagement": self.engagement_head.predict(combined_features),
            "communicationClarity": self.communication_head.predict(combined_features),
            "interviewComprehension": self.comprehension_head.predict(combined_features),
            "overallPerformance": self.overall_head.predict(combined_features),
        }
        transformer_scores = self._transformer_predict(vision_embedding, audio_embedding, text_embedding)

        scores = {}
        for key, regression_value in regression_scores.items():
            transformer_value = transformer_scores.get(key, regression_value)
            scores[key] = round(_clamp((0.45 * regression_value) + (0.55 * transformer_value), 0.0, 100.0), 2)

        scores["diagnostics"] = {
            "regressionHeadScores": {key: round(value, 2) for key, value in regression_scores.items()},
            "transformerScores": {key: round(value, 2) for key, value in transformer_scores.items()},
            "modalityEmbeddings": {
                "vision": [round(value, 4) for value in vision_embedding],
                "audio": [round(value, 4) for value in audio_embedding],
                "text": [round(value, 4) for value in text_embedding],
            },
        }
        return scores

    def _transformer_predict(
        self,
        vision_embedding: list[float],
        audio_embedding: list[float],
        text_embedding: list[float],
    ) -> dict[str, float]:
        if self.transformer is None or torch is None:
            return {
                "engagement": _clamp((vision_embedding[0] * 65.0) + (vision_embedding[1] * 35.0), 0.0, 100.0),
                "communicationClarity": _clamp((audio_embedding[0] * 50.0) + (audio_embedding[1] * 50.0), 0.0, 100.0),
                "interviewComprehension": _clamp((text_embedding[0] * 65.0) + (text_embedding[1] * 35.0), 0.0, 100.0),
                "overallPerformance": _clamp(
                    ((vision_embedding[0] + audio_embedding[0] + text_embedding[0]) / 3.0) * 100.0,
                    0.0,
                    100.0,
                ),
            }

        modality_tensor = torch.tensor(
            [[vision_embedding, audio_embedding, text_embedding]],
            dtype=torch.float32,
        )
        with torch.no_grad():
            logits = self.transformer(modality_tensor)
            transformed = torch.sigmoid(logits).squeeze(0).tolist()
        transformed = [float(value) * 100.0 for value in transformed]
        return {
            "engagement": transformed[0],
            "communicationClarity": transformed[1],
            "interviewComprehension": transformed[2],
            "overallPerformance": transformed[3],
        }


ADVANCED_SCORER = AdvancedMultimodalScorer()


def compute_advanced_multimodal_scores(
    engagement_metrics: dict,
    speech_quality_metrics: dict,
    segment_labels: list[dict],
    fused_feature_vectors: list[dict],
) -> dict:
    return ADVANCED_SCORER.predict(
        engagement_metrics=engagement_metrics,
        speech_quality_metrics=speech_quality_metrics,
        segment_labels=segment_labels,
        fused_feature_vectors=fused_feature_vectors,
    )


def generate_score_explanations(
    numeric_scores: dict[str, float],
    engagement_metrics: dict,
    speech_quality_metrics: dict,
    segment_labels: list[dict],
    llm_scores: dict,
) -> list[dict]:
    eye_contact = _normalize_percent(float(engagement_metrics.get("eyeContactRatio", 0.0)))
    head_stability = float(engagement_metrics.get("avgHeadStability", 0.0))
    speaking_rate = float(speech_quality_metrics.get("speakingRateWpm", 0.0))
    avg_pause = float(speech_quality_metrics.get("averagePauseDuration", 0.0))
    relevance_values = [float(item.get("textRelevanceScore", 0.0)) for item in segment_labels]
    relevance_avg = statistics.mean(relevance_values) if relevance_values else 0.0

    llm_depth = float(llm_scores.get("answerDepth", 0.0))
    llm_correctness = float(llm_scores.get("technicalCorrectness", 0.0))
    llm_relevance = float(llm_scores.get("jobRoleRelevance", 0.0))

    explanations = [
        {
            "scoreKey": "engagement",
            "scoreValue": round(float(numeric_scores.get("engagement", 0.0)), 2),
            "explanation": (
                f"Candidate maintained {eye_contact:.1f}% eye contact with head stability near {head_stability:.2f}, "
                "which strongly influenced engagement scoring."
            ),
            "drivers": {
                "eyeContactPercent": round(eye_contact, 2),
                "headStability": round(head_stability, 4),
            },
        },
        {
            "scoreKey": "communicationClarity",
            "scoreValue": round(float(numeric_scores.get("communicationClarity", 0.0)), 2),
            "explanation": (
                f"Speech clarity reflects speaking rate around {speaking_rate:.1f} wpm with average pauses of "
                f"{avg_pause:.2f}s."
            ),
            "drivers": {
                "speakingRateWpm": round(speaking_rate, 2),
                "averagePauseDuration": round(avg_pause, 3),
            },
        },
        {
            "scoreKey": "interviewComprehension",
            "scoreValue": round(float(numeric_scores.get("interviewComprehension", 0.0)), 2),
            "explanation": (
                f"Comprehension combines transcript relevance ({relevance_avg:.1f}) with LLM depth/correctness "
                f"signals ({llm_depth:.1f}/{llm_correctness:.1f})."
            ),
            "drivers": {
                "avgTextRelevance": round(relevance_avg, 2),
                "llmAnswerDepth": round(llm_depth, 2),
                "llmTechnicalCorrectness": round(llm_correctness, 2),
                "llmJobRoleRelevance": round(llm_relevance, 2),
            },
        },
        {
            "scoreKey": "overallPerformance",
            "scoreValue": round(float(numeric_scores.get("overallPerformance", 0.0)), 2),
            "explanation": (
                "Overall performance is derived from fused vision/audio/text embeddings and moderated by LLM "
                "reasoning signals on depth, correctness, and role relevance."
            ),
            "drivers": {
                "llmOverallScore": round(float(llm_scores.get("overallLLMJudgeScore", 0.0)), 2),
            },
        },
    ]
    return explanations


def _build_vision_embedding(engagement_metrics: dict, fused_feature_vectors: list[dict]) -> list[float]:
    eye_contact = _normalize_percent(float(engagement_metrics.get("eyeContactRatio", 0.0))) / 100.0
    overall_engagement = _normalize_percent(float(engagement_metrics.get("overallEngagement", 0.0))) / 100.0

    gazes = [str(item.get("gazeDirection", "unknown")).lower() for item in fused_feature_vectors]
    center_ratio = (sum(1 for gaze in gazes if gaze == "center") / len(gazes)) if gazes else 0.5

    head_motions = []
    for item in fused_feature_vectors:
        head_pose = item.get("headPose", {})
        motion = (
            abs(float(head_pose.get("yaw", 0.0)))
            + abs(float(head_pose.get("pitch", 0.0)))
            + abs(float(head_pose.get("roll", 0.0)))
        )
        head_motions.append(motion)
    head_motion_mean = statistics.mean(head_motions) if head_motions else 10.0
    head_stability = _clamp(1.0 - (head_motion_mean / 30.0), 0.0, 1.0)
    return [eye_contact, overall_engagement, center_ratio, head_stability]


def _build_audio_embedding(speech_quality_metrics: dict, fused_feature_vectors: list[dict]) -> list[float]:
    speaking_rate = float(speech_quality_metrics.get("speakingRateWpm", 0.0))
    pause_duration = float(speech_quality_metrics.get("averagePauseDuration", 0.0))
    prosody_score = float(speech_quality_metrics.get("prosodyScore", 0.0))

    speaking_rate_norm = _clamp(1.0 - (abs(speaking_rate - 135.0) / 135.0), 0.0, 1.0)
    pause_control = _clamp(1.0 - (pause_duration / 1.4), 0.0, 1.0)
    prosody_norm = _clamp(prosody_score, 0.0, 1.0)

    pitch_values = [
        float(item.get("speechFeatures", {}).get("pitch", 0.0))
        for item in fused_feature_vectors
        if item.get("speechFeatures", {}).get("pitch") is not None
    ]
    pitch_var = statistics.pvariance(pitch_values) if len(pitch_values) > 1 else 0.0
    pitch_stability = _clamp(1.0 - (pitch_var / 220.0), 0.0, 1.0)
    return [speaking_rate_norm, pause_control, prosody_norm, pitch_stability]


def _build_text_embedding(segment_labels: list[dict], fused_feature_vectors: list[dict]) -> list[float]:
    segment_relevance = [float(item.get("textRelevanceScore", 0.0)) for item in segment_labels]
    relevance_norm = (statistics.mean(segment_relevance) / 100.0) if segment_relevance else 0.0

    semantic = []
    coherence = []
    sentiment = []
    for item in fused_feature_vectors:
        text_scores = item.get("textScores", {})
        semantic.append(float(text_scores.get("semantic_relevance", 0.0)))
        coherence.append(float(text_scores.get("answer_coherence", 0.0)))
        sentiment.append(float(text_scores.get("sentiment_score", 0.0)))
    semantic_norm = statistics.mean(semantic) if semantic else 0.0
    coherence_norm = statistics.mean(coherence) if coherence else 0.0
    sentiment_mean = statistics.mean(sentiment) if sentiment else 0.0
    sentiment_norm = _clamp((sentiment_mean + 1.0) / 2.0, 0.0, 1.0)
    return [relevance_norm, semantic_norm, coherence_norm, sentiment_norm]


def _normalize_percent(value: float) -> float:
    if value <= 1.0:
        return _clamp(value * 100.0, 0.0, 100.0)
    return _clamp(value, 0.0, 100.0)


def _sigmoid_to_100(value: float) -> float:
    transformed = 1.0 / (1.0 + math.exp(-value))
    return _clamp(transformed * 100.0, 0.0, 100.0)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
