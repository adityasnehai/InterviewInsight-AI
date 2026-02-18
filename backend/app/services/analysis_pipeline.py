import os
from datetime import datetime, timezone
from pathlib import Path

from app.analysis.audio_processor import process_audio
from app.analysis.multimodal_fusion import fuse_multimodal_features
from app.analysis.transcript_processor import process_transcript
from app.analysis.video_processor import process_video
from app.models.analysis import MultimodalAnalysisResult, VideoAnalysisRequest
from app.scoring.advanced_scoring import compute_advanced_multimodal_scores, generate_score_explanations
from app.scoring.fairness import analyze_score_fairness
from app.scoring.feedback_generator import generate_feedback_payload
from app.scoring.llm_judge import evaluate_llm_judge
from app.scoring.score_calculator import audit_scoring_bias, compute_session_scores
from app.services.session_store import session_store


def execute_video_analysis(payload: VideoAnalysisRequest) -> MultimodalAnalysisResult:
    session = session_store.get_session(payload.sessionId)
    if session is None:
        raise ValueError("Session not found")

    video_path = Path(payload.videoFilePath).expanduser()
    if not video_path.exists():
        raise FileNotFoundError("Video file path does not exist")

    if payload.audioFilePath:
        audio_path = Path(payload.audioFilePath).expanduser()
        if not audio_path.exists():
            raise FileNotFoundError("Audio file path does not exist")
        audio_file_path = str(audio_path)
    else:
        audio_file_path = None

    fast_mode_enabled = os.getenv("IIA_FAST_ANALYSIS", "1") == "1"
    effective_frame_fps = max(1, min(int(payload.frameFps), 2 if fast_mode_enabled else int(payload.frameFps)))
    effective_window_size = (
        max(float(payload.windowSizeSeconds), 3.0)
        if fast_mode_enabled
        else float(payload.windowSizeSeconds)
    )

    video_features = process_video(video_file_path=str(video_path), target_fps=effective_frame_fps)
    audio_output = process_audio(video_file_path=str(video_path), audio_file_path=audio_file_path)
    transcript_output = process_transcript(
        transcript_text=audio_output["transcript_text"],
        transcript_segments=audio_output["transcript_segments"],
        job_role=session.get("jobRole"),
        domain=session.get("domain"),
    )
    fused = fuse_multimodal_features(
        video_features=video_features,
        audio_segment_features=audio_output["segment_features"],
        text_segment_features=transcript_output["segment_scores"],
        window_size_seconds=effective_window_size,
        use_learned_fusion=payload.useLearnedFusion,
    )

    score_payload = compute_session_scores(
        engagement_metrics=fused["engagement_metrics"],
        emotion_trajectory=fused["emotion_trajectory"],
        speech_quality_metrics=fused["speech_quality_metrics"],
        segment_labels=fused["segment_labels"],
        fused_feature_vectors=fused["fused_feature_vectors"],
        timeline_arrays=fused.get("timeline_arrays", {}),
    )
    bias_audit = audit_scoring_bias(session_context=session, summary_scores=score_payload["summaryScores"])
    score_payload["detailedScores"]["biasAudit"] = bias_audit
    feedback_payload = generate_feedback_payload(
        summary_scores=score_payload["summaryScores"],
        detailed_scores=score_payload["detailedScores"],
    )
    advanced_scores = compute_advanced_multimodal_scores(
        engagement_metrics=fused["engagement_metrics"],
        speech_quality_metrics=fused["speech_quality_metrics"],
        segment_labels=fused["segment_labels"],
        fused_feature_vectors=fused["fused_feature_vectors"],
    )
    llm_judge_output = evaluate_llm_judge(
        transcript_text=transcript_output["transcript_text"],
        job_role=str(session.get("jobRole", "Unknown Role")),
        domain=str(session.get("domain", "General")),
        allow_remote=not fast_mode_enabled,
    )
    fairness_report = analyze_score_fairness(
        session_id=payload.sessionId,
        core_scores=advanced_scores,
        engagement_metrics=fused["engagement_metrics"],
        speech_quality_metrics=fused["speech_quality_metrics"],
        segment_labels=fused["segment_labels"],
    )
    explanations = generate_score_explanations(
        numeric_scores=advanced_scores,
        engagement_metrics=fused["engagement_metrics"],
        speech_quality_metrics=fused["speech_quality_metrics"],
        segment_labels=fused["segment_labels"],
        llm_scores=llm_judge_output,
    )

    result = MultimodalAnalysisResult(
        sessionId=payload.sessionId,
        videoFilePath=str(video_path),
        audioFilePath=audio_output.get("audio_file_path"),
        transcriptText=transcript_output["transcript_text"],
        sessionMeta={
            "sessionId": payload.sessionId,
            "jobRole": str(session.get("jobRole", "Unknown Role")),
            "domain": str(session.get("domain", "General")),
            "dateTime": session.get("startedAt", datetime.now(timezone.utc)),
        },
        engagementMetrics=fused["engagement_metrics"],
        emotionTrajectory=fused["emotion_trajectory"],
        speechQualityMetrics=fused["speech_quality_metrics"],
        fusedFeatureVectors=fused["fused_feature_vectors"],
        summaryScores=score_payload["summaryScores"],
        segmentLabels=fused["segment_labels"],
        timelineArrays=fused["timeline_arrays"],
        feedbackSummary={
            "strengths": feedback_payload["strengths"],
            "improvements": feedback_payload["improvements"],
            "suggestedFeedbackText": feedback_payload["suggestedFeedbackText"],
        },
        detailedScores=score_payload["detailedScores"],
        feedbackMessages=feedback_payload["feedbackMessages"],
        generatedAt=datetime.now(timezone.utc),
    )

    session_store.set_analysis_result(payload.sessionId, result.model_dump(mode="json"))
    session_store.set_scoring_result(
        payload.sessionId,
        {
            "summaryScores": score_payload["summaryScores"],
            "detailedScores": score_payload["detailedScores"],
            "feedbackMessages": feedback_payload["feedbackMessages"],
            "strengths": feedback_payload["strengths"],
            "improvements": feedback_payload["improvements"],
            "rationale": feedback_payload["rationale"],
            "suggestedFeedbackText": feedback_payload["suggestedFeedbackText"],
            "rubricEvaluation": score_payload.get("rubricEvaluation", {}),
            "advancedScoring": {
                "sessionId": payload.sessionId,
                "numericScores": {
                    "engagement": float(advanced_scores.get("engagement", 0.0)),
                    "communicationClarity": float(advanced_scores.get("communicationClarity", 0.0)),
                    "interviewComprehension": float(advanced_scores.get("interviewComprehension", 0.0)),
                    "overallPerformance": float(advanced_scores.get("overallPerformance", 0.0)),
                },
                "textualExplanations": explanations,
                "llmRationale": llm_judge_output,
                "fairnessReport": fairness_report,
                "generatedAt": datetime.now(timezone.utc),
            },
        },
    )
    session_store.set_advanced_scoring_result(
        payload.sessionId,
        {
            "sessionId": payload.sessionId,
            "numericScores": {
                "engagement": float(advanced_scores.get("engagement", 0.0)),
                "communicationClarity": float(advanced_scores.get("communicationClarity", 0.0)),
                "interviewComprehension": float(advanced_scores.get("interviewComprehension", 0.0)),
                "overallPerformance": float(advanced_scores.get("overallPerformance", 0.0)),
            },
            "textualExplanations": explanations,
            "llmRationale": llm_judge_output,
            "fairnessReport": fairness_report,
            "generatedAt": datetime.now(timezone.utc),
        },
    )
    return result
