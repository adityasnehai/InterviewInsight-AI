import os

try:
    import torch
    from torch import nn
except Exception:  # pragma: no cover - optional dependency
    torch = None
    nn = None


def fuse_multimodal_features(
    video_features: list[dict],
    audio_segment_features: list[dict],
    text_segment_features: list[dict],
    window_size_seconds: float = 2.0,
    use_learned_fusion: bool = False,
) -> dict:
    """Align and merge video/audio/text features into time-window vectors."""
    window_size = max(0.5, float(window_size_seconds))
    max_time = _max_time(video_features, audio_segment_features, text_segment_features)
    fused_segments: list[dict] = []

    cursor = 0.0
    while cursor <= max_time:
        end_time = cursor + window_size
        video_slice = [item for item in video_features if cursor <= float(item.get("timestamp", 0.0)) < end_time]
        audio_slice = [
            item
            for item in audio_segment_features
            if _overlap(cursor, end_time, float(item.get("start", 0.0)), float(item.get("end", 0.0)))
        ]
        text_slice = [
            item
            for item in text_segment_features
            if _overlap(cursor, end_time, float(item.get("start", 0.0)), float(item.get("end", 0.0)))
        ]

        facial_emotions = _mean_emotions(video_slice)
        head_pose = _mean_head_pose(video_slice)
        gaze_direction = _dominant_gaze(video_slice)
        speech_features = _mean_speech(audio_slice)
        text_scores = _mean_text_scores(text_slice)

        raw_vector = [
            facial_emotions.get("happy", 0.0),
            facial_emotions.get("neutral", 0.0),
            facial_emotions.get("sad", 0.0),
            speech_features.get("speaking_rate", 0.0),
            speech_features.get("pitch", 0.0),
            speech_features.get("pause_duration", 0.0),
            text_scores.get("semantic_relevance", 0.0),
            text_scores.get("sentiment_score", 0.0),
            text_scores.get("answer_coherence", 0.0),
            1.0 if gaze_direction == "center" else 0.0,
        ]
        fused_vector = _apply_fusion(raw_vector, use_learned_fusion=use_learned_fusion)

        fused_segments.append(
            {
                "startTime": round(cursor, 3),
                "endTime": round(end_time, 3),
                "facialEmotionScores": facial_emotions,
                "headPose": head_pose,
                "gazeDirection": gaze_direction,
                "speechFeatures": speech_features,
                "textScores": text_scores,
                "fusedVector": fused_vector,
            }
        )
        cursor = end_time

    emotion_trajectory = [
        {
            "timestamp": float(item.get("timestamp", 0.0)),
            "dominantEmotion": _dominant_emotion(item.get("facial_emotion_scores", {})),
            "emotionScores": item.get("facial_emotion_scores", {}),
        }
        for item in video_features
    ]
    if not emotion_trajectory:
        emotion_trajectory = [{"timestamp": 0.0, "dominantEmotion": "neutral", "emotionScores": {"neutral": 1.0}}]

    engagement_metrics = _engagement_metrics(video_features, fused_segments)
    speech_quality_metrics = _speech_quality_metrics(audio_segment_features)
    summary_scores = _summary_scores(engagement_metrics, speech_quality_metrics, fused_segments)
    segment_labels = _segment_labels(fused_segments)
    timeline_arrays = _timeline_arrays(video_features, emotion_trajectory, fused_segments)
    feedback_summary = _feedback_summary(summary_scores, speech_quality_metrics, engagement_metrics)

    return {
        "engagement_metrics": engagement_metrics,
        "emotion_trajectory": emotion_trajectory,
        "speech_quality_metrics": speech_quality_metrics,
        "fused_feature_vectors": fused_segments,
        "summary_scores": summary_scores,
        "segment_labels": segment_labels,
        "timeline_arrays": timeline_arrays,
        "feedback_summary": feedback_summary,
    }


def _max_time(video_features: list[dict], audio_segments: list[dict], text_segments: list[dict]) -> float:
    values = [0.0]
    values.extend(float(item.get("timestamp", 0.0)) for item in video_features)
    values.extend(float(item.get("end", 0.0)) for item in audio_segments)
    values.extend(float(item.get("end", 0.0)) for item in text_segments)
    return max(values)


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return max(start_a, start_b) < min(end_a, end_b)


def _mean_emotions(video_slice: list[dict]) -> dict[str, float]:
    if not video_slice:
        return {"neutral": 1.0}
    totals: dict[str, float] = {}
    for item in video_slice:
        for label, score in item.get("facial_emotion_scores", {}).items():
            totals[label] = totals.get(label, 0.0) + float(score)
    count = float(len(video_slice))
    return {label: score / count for label, score in totals.items()}


def _mean_head_pose(video_slice: list[dict]) -> dict[str, float]:
    if not video_slice:
        return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
    yaw = _mean(float(item.get("head_pose", {}).get("yaw", 0.0)) for item in video_slice)
    pitch = _mean(float(item.get("head_pose", {}).get("pitch", 0.0)) for item in video_slice)
    roll = _mean(float(item.get("head_pose", {}).get("roll", 0.0)) for item in video_slice)
    return {"yaw": yaw, "pitch": pitch, "roll": roll}


def _dominant_gaze(video_slice: list[dict]) -> str:
    if not video_slice:
        return "unknown"
    counts: dict[str, int] = {}
    for item in video_slice:
        gaze = str(item.get("gaze_direction", "unknown"))
        counts[gaze] = counts.get(gaze, 0) + 1
    return max(counts, key=counts.get)


def _mean_speech(audio_slice: list[dict]) -> dict[str, float]:
    if not audio_slice:
        return {"pitch": 0.0, "pause_duration": 0.0, "speaking_rate": 0.0, "prosody_score": 0.0}

    pitch = _mean(float(item.get("pitch", 0.0)) for item in audio_slice)
    pause = _mean(float(item.get("pause_duration", 0.0)) for item in audio_slice)
    speaking_rate = _mean(float(item.get("speaking_rate", 0.0)) for item in audio_slice)
    prosody = _mean(float(item.get("prosody", {}).get("log_mel_std", 0.0)) for item in audio_slice)

    return {
        "pitch": pitch,
        "pause_duration": pause,
        "speaking_rate": speaking_rate,
        "prosody_score": prosody,
    }


def _mean_text_scores(text_slice: list[dict]) -> dict[str, float]:
    if not text_slice:
        return {"semantic_relevance": 0.0, "sentiment_score": 0.0, "answer_coherence": 0.0}
    return {
        "semantic_relevance": _mean(float(item.get("semantic_relevance", 0.0)) for item in text_slice),
        "sentiment_score": _mean(float(item.get("sentiment_score", 0.0)) for item in text_slice),
        "answer_coherence": _mean(float(item.get("answer_coherence", 0.0)) for item in text_slice),
    }


def _engagement_metrics(video_features: list[dict], fused_segments: list[dict]) -> dict[str, float]:
    eye_contact_ratio = _mean(float(item.get("eye_contact", 0.0)) for item in video_features) if video_features else 0.0
    head_stability = (
        _mean(
            1.0
            / (
                1.0
                + abs(float(item.get("head_pose", {}).get("yaw", 0.0)))
                + abs(float(item.get("head_pose", {}).get("pitch", 0.0)))
            )
            for item in video_features
        )
        if video_features
        else 0.0
    )
    avg_speaking_rate = _mean(float(seg.get("speechFeatures", {}).get("speaking_rate", 0.0)) for seg in fused_segments)
    speaking_component = min(1.0, avg_speaking_rate / 140.0) if avg_speaking_rate > 0 else 0.0
    overall = max(0.0, min(1.0, (eye_contact_ratio * 0.5) + (head_stability * 0.3) + (speaking_component * 0.2)))

    return {
        "overallEngagement": overall,
        "eyeContactRatio": eye_contact_ratio,
        "avgHeadStability": head_stability,
        "avgSpeakingRateWpm": avg_speaking_rate,
    }


def _speech_quality_metrics(audio_segments: list[dict]) -> dict[str, float]:
    if not audio_segments:
        return {
            "averagePitch": 0.0,
            "averagePauseDuration": 0.0,
            "speakingRateWpm": 0.0,
            "prosodyScore": 0.0,
        }
    return {
        "averagePitch": _mean(float(item.get("pitch", 0.0)) for item in audio_segments),
        "averagePauseDuration": _mean(float(item.get("pause_duration", 0.0)) for item in audio_segments),
        "speakingRateWpm": _mean(float(item.get("speaking_rate", 0.0)) for item in audio_segments),
        "prosodyScore": _mean(float(item.get("prosody", {}).get("log_mel_std", 0.0)) for item in audio_segments),
    }


def _summary_scores(engagement_metrics: dict, speech_quality_metrics: dict, fused_segments: list[dict]) -> dict[str, float]:
    engagement = _clamp01(float(engagement_metrics.get("overallEngagement", 0.0)))
    avg_sentiment = _mean(float(seg.get("textScores", {}).get("sentiment_score", 0.0)) for seg in fused_segments)
    sentiment_component = _clamp01((avg_sentiment + 1.0) / 2.0)
    eye_contact = _clamp01(float(engagement_metrics.get("eyeContactRatio", 0.0)))
    head_stability = _clamp01(float(engagement_metrics.get("avgHeadStability", 0.0)))
    confidence = _clamp01((eye_contact * 0.45) + (head_stability * 0.25) + (sentiment_component * 0.3))

    speaking_rate = float(speech_quality_metrics.get("speakingRateWpm", 0.0))
    avg_pause = float(speech_quality_metrics.get("averagePauseDuration", 0.0))
    rate_quality = _clamp01(1.0 - min(abs(speaking_rate - 135.0) / 135.0, 1.0))
    pause_quality = _clamp01(1.0 - min(avg_pause / 1.5, 1.0))
    speech_fluency = _clamp01((rate_quality * 0.7) + (pause_quality * 0.3))

    emotions = [seg.get("facialEmotionScores", {}) for seg in fused_segments if seg.get("facialEmotionScores")]
    neutral_scores = [_clamp01(float(item.get("neutral", 0.0))) for item in emotions] if emotions else [0.5]
    emotional_stability = _clamp01(_mean(neutral_scores))

    return {
        "engagementScore": round(engagement * 100.0, 2),
        "confidenceScore": round(confidence * 100.0, 2),
        "speechFluency": round(speech_fluency * 100.0, 2),
        "emotionalStability": round(emotional_stability * 100.0, 2),
    }


def _segment_labels(fused_segments: list[dict]) -> list[dict]:
    labels: list[dict] = []
    for idx, segment in enumerate(fused_segments, start=1):
        text_scores = segment.get("textScores", {})
        speech = segment.get("speechFeatures", {})
        facial = segment.get("facialEmotionScores", {})
        dominant_emotion = _dominant_emotion(facial)
        speaking_rate = float(speech.get("speaking_rate", 0.0))
        pause_duration = float(speech.get("pause_duration", 0.0))
        speech_fluency = _clamp01(1.0 - min(abs(speaking_rate - 135.0) / 135.0, 1.0))
        speech_fluency = (speech_fluency * 0.8) + (_clamp01(1.0 - min(pause_duration / 1.5, 1.0)) * 0.2)
        sentiment_component = _clamp01((float(text_scores.get("sentiment_score", 0.0)) + 1.0) / 2.0)
        engagement = _clamp01((float(facial.get("happy", 0.0)) * 0.4) + (float(facial.get("neutral", 0.0)) * 0.3) + sentiment_component * 0.3)

        labels.append(
            {
                "segmentId": f"segment_{idx}",
                "label": f"Question Segment {idx}",
                "startTime": float(segment.get("startTime", 0.0)),
                "endTime": float(segment.get("endTime", 0.0)),
                "engagementScore": round(engagement * 100.0, 2),
                "speechFluency": round(_clamp01(speech_fluency) * 100.0, 2),
                "textRelevanceScore": round(_clamp01(float(text_scores.get("semantic_relevance", 0.0))) * 100.0, 2),
                "dominantEmotion": dominant_emotion,
                "emotionAverages": facial,
                "speechQualityMetrics": speech,
            }
        )
    return labels


def _timeline_arrays(video_features: list[dict], emotion_trajectory: list[dict], fused_segments: list[dict]) -> dict:
    engagement_timeline: list[dict] = []
    speech_timeline: list[dict] = []
    for segment in fused_segments:
        mid = (float(segment.get("startTime", 0.0)) + float(segment.get("endTime", 0.0))) / 2.0
        text_scores = segment.get("textScores", {})
        sentiment = _clamp01((float(text_scores.get("sentiment_score", 0.0)) + 1.0) / 2.0)
        confidence = _clamp01(
            0.4 * (1.0 if str(segment.get("gazeDirection", "")).lower() == "center" else 0.0)
            + 0.2 * _clamp01(1.0 - min(abs(float(segment.get("headPose", {}).get("yaw", 0.0))) / 45.0, 1.0))
            + 0.4 * sentiment
        )
        engagement_timeline.append(
            {
                "timestamp": round(mid, 3),
                "engagement": round(
                    _clamp01(
                        float(segment.get("fusedVector", [0.0])[0])
                        + (float(segment.get("facialEmotionScores", {}).get("neutral", 0.0)) * 0.2)
                    )
                    * 100.0,
                    2,
                ),
                "confidence": round(confidence * 100.0, 2),
            }
        )
        speech = segment.get("speechFeatures", {})
        speech_timeline.append(
            {
                "timestamp": round(mid, 3),
                "speakingRate": float(speech.get("speaking_rate", 0.0)),
                "pitch": float(speech.get("pitch", 0.0)),
                "pauseDuration": float(speech.get("pause_duration", 0.0)),
                "fluency": round(
                    _clamp01(
                        1.0
                        - min(abs(float(speech.get("speaking_rate", 0.0)) - 135.0) / 135.0, 1.0)
                    )
                    * 100.0,
                    2,
                ),
            }
        )

    gaze_head_pose_timeline = [
        {
            "timestamp": round(float(item.get("timestamp", 0.0)), 3),
            "headYaw": float(item.get("head_pose", {}).get("yaw", 0.0)),
            "headPitch": float(item.get("head_pose", {}).get("pitch", 0.0)),
            "headRoll": float(item.get("head_pose", {}).get("roll", 0.0)),
            "eyeContact": round(float(item.get("eye_contact", 0.0)) * 100.0, 2),
            "gazeDirection": str(item.get("gaze_direction", "unknown")),
        }
        for item in video_features
    ]

    return {
        "emotionTimeline": emotion_trajectory,
        "engagementTimeline": engagement_timeline,
        "speechTimeline": speech_timeline,
        "gazeHeadPoseTimeline": gaze_head_pose_timeline,
    }


def _feedback_summary(summary_scores: dict, speech_quality_metrics: dict, engagement_metrics: dict) -> dict:
    strengths: list[str] = []
    improvements: list[str] = []

    if summary_scores["engagementScore"] >= 70:
        strengths.append("Strong engagement maintained across most of the interview.")
    else:
        improvements.append("Increase on-camera engagement and maintain steadier eye contact.")

    if summary_scores["confidenceScore"] >= 70:
        strengths.append("Confident delivery with good visual presence.")
    else:
        improvements.append("Boost confidence by reducing hesitation and improving posture consistency.")

    if summary_scores["speechFluency"] >= 70:
        strengths.append("Speech fluency is consistent with a professional pace.")
    else:
        improvements.append("Work on pacing and reducing long pauses between key points.")

    if summary_scores["emotionalStability"] >= 70:
        strengths.append("Emotional stability appears steady and composed.")
    else:
        improvements.append("Aim for steadier emotional tone during challenging answers.")

    if float(speech_quality_metrics.get("averagePauseDuration", 0.0)) > 0.8:
        improvements.append("Shorten pauses by practicing concise response structures.")
    if float(engagement_metrics.get("eyeContactRatio", 0.0)) > 0.75:
        strengths.append("Excellent eye contact contributes to credibility.")

    strengths = strengths[:3] or ["Consistent participation across recorded segments."]
    improvements = improvements[:3] or ["Continue refining storytelling depth for stronger impact."]

    suggested_feedback_text = (
        f"Top strengths: {' '.join(strengths)} "
        f"Primary improvements: {' '.join(improvements)}"
    )
    return {
        "strengths": strengths,
        "improvements": improvements,
        "suggestedFeedbackText": suggested_feedback_text,
    }


def _dominant_emotion(emotion_scores: dict[str, float]) -> str:
    if not emotion_scores:
        return "neutral"
    return max(emotion_scores, key=emotion_scores.get)


def _apply_fusion(raw_vector: list[float], use_learned_fusion: bool) -> list[float]:
    if not use_learned_fusion:
        return [round(value, 6) for value in raw_vector]
    if torch is None or nn is None or os.getenv("IIA_DISABLE_MODEL_LOADING", "0") == "1":
        return [round(value, 6) for value in raw_vector]

    torch.manual_seed(7)
    model = nn.Sequential(
        nn.Linear(len(raw_vector), len(raw_vector)),
        nn.ReLU(),
        nn.Linear(len(raw_vector), len(raw_vector)),
    )
    with torch.no_grad():
        tensor = torch.tensor(raw_vector, dtype=torch.float32)
        out = model(tensor).tolist()
    return [round(float(value), 6) for value in out]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mean(values) -> float:
    values = list(values)
    if not values:
        return 0.0
    return float(sum(values) / len(values))
