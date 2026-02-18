import logging
import math
import os
from collections import Counter

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None

try:
    from transformers import pipeline
except Exception:  # pragma: no cover - optional dependency
    pipeline = None

LOGGER = logging.getLogger(__name__)
_SENTIMENT_PIPELINE = None
_SENTIMENT_INITIALIZED = False
_EMBEDDING_PIPELINE = None
_EMBEDDING_INITIALIZED = False


def process_transcript(
    transcript_text: str,
    transcript_segments: list[dict],
    job_role: str | None = None,
    domain: str | None = None,
) -> dict:
    """Compute semantic relevance, sentiment, and coherence per transcript segment."""
    context = " ".join(part for part in [job_role, domain] if part)
    sentiment_fn = _build_sentiment_pipeline()
    embed_fn = _build_embedding_pipeline()
    context_vector = _text_vector(context, embed_fn)

    segment_scores: list[dict] = []
    previous_vector = None
    for segment in transcript_segments:
        text = str(segment.get("text", "")).strip()
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", 0.0))
        text_vector = _text_vector(text, embed_fn)

        relevance = _cosine_similarity(text_vector, context_vector) if context else 0.5
        sentiment = _sentiment_score(text, sentiment_fn)
        coherence = _cosine_similarity(text_vector, previous_vector) if previous_vector is not None else 1.0
        previous_vector = text_vector

        segment_scores.append(
            {
                "start": start,
                "end": end,
                "text": text,
                "semantic_relevance": relevance,
                "sentiment_score": sentiment,
                "answer_coherence": coherence,
            }
        )

    if not segment_scores:
        segment_scores = [
            {
                "start": 0.0,
                "end": 0.0,
                "text": transcript_text,
                "semantic_relevance": 0.0,
                "sentiment_score": 0.0,
                "answer_coherence": 0.0,
            }
        ]

    return {
        "transcript_text": transcript_text,
        "segment_scores": segment_scores,
        "overall": {
            "semantic_relevance": _mean(item["semantic_relevance"] for item in segment_scores),
            "sentiment_score": _mean(item["sentiment_score"] for item in segment_scores),
            "answer_coherence": _mean(item["answer_coherence"] for item in segment_scores),
        },
    }


def _build_sentiment_pipeline():
    global _SENTIMENT_PIPELINE, _SENTIMENT_INITIALIZED
    if _SENTIMENT_INITIALIZED:
        return _SENTIMENT_PIPELINE
    _SENTIMENT_INITIALIZED = True
    if pipeline is None or os.getenv("IIA_DISABLE_MODEL_LOADING", "0") == "1":
        _SENTIMENT_PIPELINE = None
        return None
    try:
        _SENTIMENT_PIPELINE = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Sentiment pipeline unavailable; using lexical fallback: %s", exc)
        _SENTIMENT_PIPELINE = None
    return _SENTIMENT_PIPELINE


def _build_embedding_pipeline():
    global _EMBEDDING_PIPELINE, _EMBEDDING_INITIALIZED
    if _EMBEDDING_INITIALIZED:
        return _EMBEDDING_PIPELINE
    _EMBEDDING_INITIALIZED = True
    if pipeline is None or os.getenv("IIA_DISABLE_MODEL_LOADING", "0") == "1":
        _EMBEDDING_PIPELINE = None
        return None
    try:
        _EMBEDDING_PIPELINE = pipeline("feature-extraction", model="sentence-transformers/all-MiniLM-L6-v2")
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Embedding pipeline unavailable; using token-count vectors: %s", exc)
        _EMBEDDING_PIPELINE = None
    return _EMBEDDING_PIPELINE


def _text_vector(text: str, embed_pipeline) -> list[float]:
    if not text:
        return [0.0]

    if embed_pipeline is not None and np is not None:
        try:
            features = embed_pipeline(text)
            arr = np.array(features)
            if arr.ndim == 3:
                arr = arr[0]
            pooled = np.mean(arr, axis=0)
            return [float(x) for x in pooled]
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Embedding inference failed; using fallback vector: %s", exc)

    # Fallback: deterministic bag-of-words vector projection into fixed bins.
    bins = 16
    counts = Counter(token.lower() for token in text.split())
    vector = [0.0] * bins
    for token, count in counts.items():
        vector[hash(token) % bins] += float(count)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def _sentiment_score(text: str, sentiment_pipeline) -> float:
    if not text:
        return 0.0

    if sentiment_pipeline is not None:
        try:
            pred = sentiment_pipeline(text)[0]
            label = str(pred.get("label", "")).upper()
            score = float(pred.get("score", 0.0))
            return score if label == "POSITIVE" else -score
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Sentiment inference failed; using lexical fallback: %s", exc)

    positive_tokens = {"good", "great", "strong", "improved", "success", "positive", "confident"}
    negative_tokens = {"bad", "weak", "issue", "failed", "negative", "uncertain", "problem"}
    words = [word.strip(".,!?;:").lower() for word in text.split()]
    if not words:
        return 0.0
    pos = sum(1 for token in words if token in positive_tokens)
    neg = sum(1 for token in words if token in negative_tokens)
    raw = (pos - neg) / max(1, len(words))
    return max(-1.0, min(1.0, raw * 5.0))


def _cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    limit = min(len(a), len(b))
    if limit == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(limit))
    norm_a = math.sqrt(sum(value * value for value in a[:limit]))
    norm_b = math.sqrt(sum(value * value for value in b[:limit]))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    similarity = dot / (norm_a * norm_b)
    return max(-1.0, min(1.0, float(similarity)))


def _mean(values) -> float:
    values = list(values)
    if not values:
        return 0.0
    return float(sum(values) / len(values))
