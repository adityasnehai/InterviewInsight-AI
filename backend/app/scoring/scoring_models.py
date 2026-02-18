import math
from dataclasses import dataclass

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None


@dataclass
class RegressionHead:
    """Lightweight linear regression head with optional fitting support."""

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
        """Optional fitting method (normal equation) for local experimentation."""
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

        self.weights = [float(value) for value in coeffs[:-1].tolist()]
        self.bias = float(coeffs[-1])


class InterviewReadinessModel:
    """Small ensemble-like scoring model over fused feature vectors."""

    def __init__(self) -> None:
        # Feature order expected from fusion vectors:
        # [happy, neutral, sad, speaking_rate, pitch, pause_duration,
        #  semantic_relevance, sentiment_score, answer_coherence, eye_contact]
        self.confidence_head = RegressionHead(
            weights=[0.45, 0.32, -0.3, 0.004, 0.001, -0.25, 0.28, 0.35, 0.24, 0.42],
            bias=-0.15,
        )
        self.communication_head = RegressionHead(
            weights=[0.28, 0.22, -0.18, 0.005, 0.0006, -0.2, 0.55, 0.26, 0.5, 0.25],
            bias=-0.12,
        )
        self.readiness_head = RegressionHead(
            weights=[0.3, 0.25, -0.22, 0.004, 0.0008, -0.18, 0.4, 0.22, 0.4, 0.35],
            bias=-0.1,
        )

    def predict(self, fused_feature_vectors: list[dict]) -> dict[str, float]:
        pooled_features = _pool_fused_vectors(fused_feature_vectors)

        confidence = self.confidence_head.predict(pooled_features)
        communication = self.communication_head.predict(pooled_features)
        readiness = self.readiness_head.predict(pooled_features)

        return {
            "confidence": round(confidence, 2),
            "communicationEffectiveness": round(communication, 2),
            "interviewReadiness": round(readiness, 2),
        }


def _pool_fused_vectors(fused_feature_vectors: list[dict]) -> list[float]:
    if not fused_feature_vectors:
        return [0.0] * 10

    vectors = [item.get("fusedVector", []) for item in fused_feature_vectors]
    vectors = [list(map(float, vector)) for vector in vectors if vector]
    if not vectors:
        return [0.0] * 10

    length = max(len(vector) for vector in vectors)
    padded = []
    for vector in vectors:
        if len(vector) < length:
            vector = vector + [0.0] * (length - len(vector))
        padded.append(vector)

    pooled = [sum(column) / len(padded) for column in zip(*padded)]
    if len(pooled) < 10:
        pooled += [0.0] * (10 - len(pooled))
    return pooled[:10]


def _sigmoid_to_100(value: float) -> float:
    transformed = 1.0 / (1.0 + math.exp(-value))
    return max(0.0, min(100.0, transformed * 100.0))
