def generate_feedback_payload(summary_scores: dict, detailed_scores: dict) -> dict:
    feedback_messages: list[str] = []
    strengths: list[str] = []
    improvements: list[str] = []

    engagement = float(summary_scores.get("engagementScore", 0.0))
    emotional_regulation = float(summary_scores.get("emotionalStability", 0.0))
    speech_clarity = float(summary_scores.get("speechFluency", 0.0))
    content_relevance = float(summary_scores.get("contentRelevanceScore", 0.0))
    overall = float(summary_scores.get("overallPerformanceScore", 0.0))

    if engagement < 60:
        improvements.append(
            "Improve eye contact consistency and reduce off-screen gaze to strengthen interviewer connection."
        )
        feedback_messages.append(
            "Engagement is below target. Focus on stable gaze and calm head movement to improve presence."
        )
    else:
        strengths.append("You maintained strong engagement with stable visual focus.")

    if speech_clarity < 60:
        improvements.append("Reduce long pauses and keep your speaking pace within a steady conversational range.")
        feedback_messages.append(
            "Speech clarity can improve with smoother pacing and shorter silent gaps between ideas."
        )
    else:
        strengths.append("Speech delivery is clear with an effective pace.")

    if emotional_regulation < 60:
        improvements.append("Maintain a steadier emotional tone when discussing difficult topics.")
        feedback_messages.append(
            "Emotional variation appears high. Try controlled breathing and brief pauses before key answers."
        )
    else:
        strengths.append("Emotional regulation is steady and professional.")

    if content_relevance < 65:
        improvements.append("Increase answer relevance by aligning examples more directly with the question intent.")
        feedback_messages.append(
            "Content relevance is moderate. Prioritize concise examples tied to role-specific outcomes."
        )
    else:
        strengths.append("Responses were well aligned with interview content expectations.")

    if overall >= 80:
        feedback_messages.append(
            "Overall performance is strong. Keep this structure and polish deeper storytelling for top-tier delivery."
        )
    elif overall >= 65:
        feedback_messages.append(
            "Overall performance is solid with clear growth potential in targeted areas listed above."
        )
    else:
        feedback_messages.append(
            "Overall performance is developing. Address the top improvement actions to quickly raise your score."
        )

    strengths = strengths[:3] or ["You completed the interview session and produced analyzable responses."]
    improvements = improvements[:3] or ["Continue practicing scenario-specific examples to improve impact."]

    rationale = _build_rationale(detailed_scores)
    suggested_feedback_text = (
        f"Strengths: {' '.join(strengths)} "
        f"Improvements: {' '.join(improvements)}"
    )

    return {
        "feedbackMessages": feedback_messages,
        "strengths": strengths,
        "improvements": improvements,
        "rationale": rationale,
        "suggestedFeedbackText": suggested_feedback_text,
    }


def _build_rationale(detailed_scores: dict) -> dict:
    engagement = detailed_scores.get("engagement", {}).get("components", {})
    speech = detailed_scores.get("speechClarity", {}).get("components", {})
    emotion = detailed_scores.get("emotionalRegulation", {}).get("components", {})

    return {
        "engagementDrivers": {
            "eyeContactScore": engagement.get("eyeContactScore", 0.0),
            "gazeStabilityScore": engagement.get("gazeStabilityScore", 0.0),
            "headMotionScore": engagement.get("headMotionScore", 0.0),
        },
        "speechDrivers": {
            "pauseScore": speech.get("pauseScore", 0.0),
            "speakingRateScore": speech.get("speakingRateScore", 0.0),
            "pitchVarianceScore": speech.get("pitchVarianceScore", 0.0),
        },
        "emotionDrivers": {
            "dominantEmotionVariance": emotion.get("dominantEmotionVariance", 0.0),
            "averageEmotionVariance": emotion.get("averageEmotionVariance", 0.0),
        },
    }
