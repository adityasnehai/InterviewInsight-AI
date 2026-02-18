from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.models.scoring import AdvancedScoreResponse
from app.scoring.advanced_scoring import compute_advanced_multimodal_scores, generate_score_explanations
from app.scoring.fairness import analyze_score_fairness
from app.scoring.llm_judge import evaluate_llm_judge
from app.scoring.rubric import map_scores_to_rubric
from app.services.session_store import session_store

router = APIRouter(prefix="/scores", tags=["Scoring"])


@router.get("/{sessionId}/explain", response_model=AdvancedScoreResponse)
def get_score_explanations(sessionId: str) -> AdvancedScoreResponse:
    session = session_store.get_session(sessionId)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    advanced_payload = session_store.get_advanced_scoring_result(sessionId)
    if advanced_payload is None:
        scoring_payload = session_store.get_scoring_result(sessionId) or {}
        advanced_payload = scoring_payload.get("advancedScoring")

    if advanced_payload is None:
        analysis_payload = session_store.get_analysis_result(sessionId)
        if analysis_payload is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis result not found")
        advanced_payload = _build_advanced_payload(
            session_id=sessionId,
            session=session,
            analysis_payload=analysis_payload,
        )
        session_store.set_advanced_scoring_result(sessionId, advanced_payload)
    elif "rubricEvaluation" not in advanced_payload:
        scoring_payload = session_store.get_scoring_result(sessionId) or {}
        summary_scores = scoring_payload.get("summaryScores", {})
        advanced_payload["rubricEvaluation"] = scoring_payload.get("rubricEvaluation") or map_scores_to_rubric(
            summary_scores=summary_scores,
            advanced_scores=advanced_payload.get("numericScores", {}),
        )

    return AdvancedScoreResponse(**advanced_payload)


def _build_advanced_payload(session_id: str, session: dict, analysis_payload: dict) -> dict:
    engagement_metrics = analysis_payload.get("engagementMetrics", {})
    speech_quality_metrics = analysis_payload.get("speechQualityMetrics", {})
    segment_labels = analysis_payload.get("segmentLabels", [])
    fused_feature_vectors = analysis_payload.get("fusedFeatureVectors", [])
    transcript_text = str(analysis_payload.get("transcriptText", ""))
    summary_scores = analysis_payload.get("summaryScores", {})

    advanced_scores = compute_advanced_multimodal_scores(
        engagement_metrics=engagement_metrics,
        speech_quality_metrics=speech_quality_metrics,
        segment_labels=segment_labels,
        fused_feature_vectors=fused_feature_vectors,
    )
    llm_result = evaluate_llm_judge(
        transcript_text=transcript_text,
        job_role=str(session.get("jobRole", "Unknown Role")),
        domain=str(session.get("domain", "General")),
    )
    fairness_report = analyze_score_fairness(
        session_id=session_id,
        core_scores=advanced_scores,
        engagement_metrics=engagement_metrics,
        speech_quality_metrics=speech_quality_metrics,
        segment_labels=segment_labels,
    )
    explanations = generate_score_explanations(
        numeric_scores=advanced_scores,
        engagement_metrics=engagement_metrics,
        speech_quality_metrics=speech_quality_metrics,
        segment_labels=segment_labels,
        llm_scores=llm_result,
    )

    numeric_scores = {
        "engagement": float(advanced_scores.get("engagement", 0.0)),
        "communicationClarity": float(advanced_scores.get("communicationClarity", 0.0)),
        "interviewComprehension": float(advanced_scores.get("interviewComprehension", 0.0)),
        "overallPerformance": float(advanced_scores.get("overallPerformance", 0.0)),
    }
    scoring_payload = session_store.get_scoring_result(session_id) or {}
    rubric_evaluation = scoring_payload.get("rubricEvaluation") or map_scores_to_rubric(
        summary_scores=summary_scores,
        advanced_scores=advanced_scores,
    )

    return {
        "sessionId": session_id,
        "numericScores": numeric_scores,
        "rubricEvaluation": rubric_evaluation,
        "textualExplanations": explanations,
        "llmRationale": llm_result,
        "fairnessReport": fairness_report,
        "generatedAt": datetime.now(timezone.utc),
    }
