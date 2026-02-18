from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.models.analysis import (
    AnalysisJobResponse,
    MultimodalAnalysisResult,
    SessionScoresResponse,
    VideoAnalysisRequest,
)
from app.services.analysis_queue import enqueue_video_analysis
from app.services.session_store import session_store

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.post("/video", response_model=AnalysisJobResponse, status_code=status.HTTP_202_ACCEPTED)
def run_video_analysis(payload: VideoAnalysisRequest) -> AnalysisJobResponse:
    session = session_store.get_session(payload.sessionId)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    video_path = Path(payload.videoFilePath).expanduser()
    if not video_path.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Video file path does not exist")

    if payload.audioFilePath:
        audio_path = Path(payload.audioFilePath).expanduser()
        if not audio_path.exists():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file path does not exist")
    try:
        job = enqueue_video_analysis(payload=payload, user_id=str(session.get("userId", "")))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive runtime wrapper
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enqueue analysis: {exc}",
        ) from exc
    return AnalysisJobResponse(**job)


@router.get("/jobs/{jobId}", response_model=AnalysisJobResponse)
def get_analysis_job_status(jobId: str) -> AnalysisJobResponse:
    job = session_store.get_analysis_job(jobId)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis job not found")
    return AnalysisJobResponse(**job)


@router.get("/{sessionId}/job", response_model=AnalysisJobResponse)
def get_latest_analysis_job(sessionId: str) -> AnalysisJobResponse:
    job = session_store.get_latest_analysis_job_for_session(sessionId)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analysis job found for session")
    return AnalysisJobResponse(**job)


@router.get("/{sessionId}/results", response_model=MultimodalAnalysisResult)
def get_analysis_results(sessionId: str) -> MultimodalAnalysisResult:
    stored = session_store.get_analysis_result(sessionId)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis result not found")
    hydrated = _hydrate_dashboard_fields(stored)
    return MultimodalAnalysisResult(**hydrated)


@router.get("/{sessionId}/scores", response_model=SessionScoresResponse)
def get_analysis_scores(sessionId: str) -> SessionScoresResponse:
    stored_scores = session_store.get_scoring_result(sessionId)
    if stored_scores is not None:
        return SessionScoresResponse(
            summaryScores=stored_scores["summaryScores"],
            detailedScores=stored_scores["detailedScores"],
            feedbackMessages=stored_scores["feedbackMessages"],
        )

    stored_analysis = session_store.get_analysis_result(sessionId)
    if stored_analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Score result not found")

    hydrated = _hydrate_dashboard_fields(stored_analysis)
    fallback_scores = _fallback_score_payload_from_analysis(hydrated)
    return SessionScoresResponse(**fallback_scores)


def _hydrate_dashboard_fields(stored: dict) -> dict:
    """Backfill dashboard fields if an older result payload is loaded."""
    hydrated = dict(stored)

    session_id = str(hydrated.get("sessionId", ""))
    generated_at = hydrated.get("generatedAt", datetime.now(timezone.utc))
    session_meta = hydrated.get("sessionMeta")
    if not session_meta:
        session_meta = {
            "sessionId": session_id,
            "jobRole": "Unknown Role",
            "domain": "General",
            "dateTime": generated_at,
        }

    hydrated.setdefault("summaryScores", {
        "engagementScore": round(float(hydrated.get("engagementMetrics", {}).get("overallEngagement", 0.0)) * 100.0, 2),
        "confidenceScore": 50.0,
        "speechFluency": 50.0,
        "emotionalStability": 50.0,
        "contentRelevanceScore": 50.0,
        "overallPerformanceScore": 50.0,
        "communicationEffectiveness": 50.0,
        "interviewReadiness": 50.0,
    })
    hydrated.setdefault("segmentLabels", [])
    hydrated.setdefault("timelineArrays", {
        "emotionTimeline": hydrated.get("emotionTrajectory", []),
        "engagementTimeline": [],
        "speechTimeline": [],
        "gazeHeadPoseTimeline": [],
    })
    hydrated.setdefault("feedbackSummary", {
        "strengths": ["Analysis available."],
        "improvements": ["Generate a fresh analysis to receive richer feedback."],
        "suggestedFeedbackText": "Generate a new analysis run for complete dashboard insights.",
    })
    hydrated.setdefault("detailedScores", None)
    hydrated.setdefault("feedbackMessages", [])
    hydrated["sessionMeta"] = session_meta
    return hydrated


def _fallback_score_payload_from_analysis(analysis_payload: dict) -> dict:
    summary_scores = analysis_payload.get("summaryScores", {})
    detailed_scores = analysis_payload.get("detailedScores")
    if detailed_scores is None:
        detailed_scores = {
            "engagement": {"score": float(summary_scores.get("engagementScore", 0.0)), "components": {}},
            "emotionalRegulation": {"score": float(summary_scores.get("emotionalStability", 0.0)), "components": {}},
            "speechClarity": {"score": float(summary_scores.get("speechFluency", 0.0)), "components": {}},
            "contentRelevance": {"score": float(summary_scores.get("contentRelevanceScore", 0.0)), "components": {}},
            "modelPredictions": {
                "confidence": float(summary_scores.get("confidenceScore", 0.0)),
                "communicationEffectiveness": float(summary_scores.get("communicationEffectiveness", 0.0)),
                "interviewReadiness": float(summary_scores.get("interviewReadiness", 0.0)),
            },
            "weights": {
                "engagement": 0.3,
                "emotionalRegulation": 0.2,
                "speechClarity": 0.25,
                "contentRelevance": 0.25,
            },
            "biasAudit": {},
        }
    return {
        "summaryScores": summary_scores,
        "detailedScores": detailed_scores,
        "feedbackMessages": analysis_payload.get("feedbackMessages", []),
    }
