import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.reports import generate_interview_report
from app.api.security import get_current_user
from app.api.scoring import get_score_explanations
from app.models.product import (
    ProductSessionStartRequest,
    ProductSessionStartResponse,
    ProductSessionSummary,
)
from app.models.reports import InterviewReportRequest, InterviewReportResponse
from app.models.scoring import AdvancedScoreResponse
from app.models.session import SessionStartRequest
from app.models.session import SessionStatusResponse
from app.services.session_store import session_store

router = APIRouter(prefix="/app", tags=["Product"])

STORAGE_ROOT = Path(__file__).resolve().parents[1] / "storage"


@router.get("/me/sessions", response_model=list[ProductSessionSummary])
def list_my_sessions(current_user: dict = Depends(get_current_user)) -> list[ProductSessionSummary]:
    user_id = str(current_user["userId"])
    sessions = session_store.get_sessions_for_user(user_id=user_id)
    return [ProductSessionSummary(**item) for item in sessions]


@router.post("/me/sessions/start", response_model=ProductSessionStartResponse, status_code=status.HTTP_201_CREATED)
def start_my_session(
    payload: ProductSessionStartRequest,
    current_user: dict = Depends(get_current_user),
) -> ProductSessionStartResponse:
    user_id = str(current_user["userId"])
    created = session_store.create_session(
        SessionStartRequest(userId=user_id, jobRole=payload.jobRole, domain=payload.domain)
    )
    return ProductSessionStartResponse(
        sessionId=created["sessionId"],
        status=created["status"],
        jobRole=created["jobRole"],
        domain=created["domain"],
    )


@router.get("/me/sessions/{sessionId}/analysis")
def get_my_session_analysis(
    sessionId: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    user_id = str(current_user["userId"])
    if not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    analysis = session_store.get_analysis_result(sessionId)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return analysis


@router.get("/me/sessions/{sessionId}/video")
def get_my_session_video(
    sessionId: str,
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    user_id = str(current_user["userId"])
    session = session_store.get_session(sessionId)
    if session is None or not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    uploads = list(session.get("uploads") or [])
    for upload in reversed(uploads):
        rel_video = str(upload.get("videoFile") or "").strip()
        if not rel_video:
            continue
        abs_video = (STORAGE_ROOT / rel_video).resolve()
        storage_root_resolved = STORAGE_ROOT.resolve()
        if storage_root_resolved not in abs_video.parents and abs_video != storage_root_resolved:
            continue
        if not abs_video.exists() or not abs_video.is_file():
            continue
        media_type, _ = mimetypes.guess_type(str(abs_video))
        return FileResponse(
            path=str(abs_video),
            media_type=media_type or "application/octet-stream",
            filename=abs_video.name,
        )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session video not found")


@router.get("/me/sessions/{sessionId}/status", response_model=SessionStatusResponse)
def get_my_session_status(
    sessionId: str,
    current_user: dict = Depends(get_current_user),
) -> SessionStatusResponse:
    user_id = str(current_user["userId"])
    if not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    status_payload = session_store.get_status(sessionId)
    if status_payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionStatusResponse(**status_payload)


@router.get("/me/sessions/{sessionId}/scores/explain", response_model=AdvancedScoreResponse)
def get_my_session_scores_explain(
    sessionId: str,
    current_user: dict = Depends(get_current_user),
) -> AdvancedScoreResponse:
    user_id = str(current_user["userId"])
    if not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return get_score_explanations(sessionId=sessionId)


@router.post("/me/sessions/{sessionId}/report", response_model=InterviewReportResponse)
def generate_my_session_report(
    sessionId: str,
    payload: InterviewReportRequest | None = None,
    current_user: dict = Depends(get_current_user),
) -> InterviewReportResponse:
    user_id = str(current_user["userId"])
    if not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return generate_interview_report(sessionId=sessionId, payload=payload)
