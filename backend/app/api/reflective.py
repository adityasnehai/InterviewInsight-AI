from fastapi import APIRouter, Depends, HTTPException, status

from app.api.security import get_current_user
from app.models.user import ReflectionEntry, ReflectionRequest, ReflectiveSummaryResponse
from app.scoring.llm_feedback import generate_reflective_coaching
from app.services.session_store import session_store

router = APIRouter(prefix="/reflective", tags=["Reflective Learning"])


@router.post("/{sessionId}/responses", response_model=ReflectionEntry, status_code=status.HTTP_201_CREATED)
def submit_reflective_response(
    sessionId: str,
    payload: ReflectionRequest,
    current_user: dict = Depends(get_current_user),
) -> ReflectionEntry:
    session = session_store.get_session(sessionId)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if not session_store.session_belongs_to_user(sessionId, str(current_user["userId"])):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed for this user")

    scoring_result = session_store.get_scoring_result(sessionId) or {}
    summary_scores = scoring_result.get("summaryScores", {})
    feedback_messages = scoring_result.get("feedbackMessages", [])

    coaching_feedback = generate_reflective_coaching(
        session_id=sessionId,
        reflection_text=payload.reflectionText,
        summary_scores=summary_scores,
        feedback_messages=feedback_messages,
    )
    saved_entry = session_store.add_reflection(
        session_id=sessionId,
        reflection_text=payload.reflectionText,
        coaching_feedback=coaching_feedback,
    )
    if saved_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return ReflectionEntry(**saved_entry)


@router.get("/{userId}/summaries", response_model=ReflectiveSummaryResponse)
def get_reflective_summary(
    userId: str,
    current_user: dict = Depends(get_current_user),
) -> ReflectiveSummaryResponse:
    if str(current_user["userId"]) != str(userId):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed for this user")
    summary = session_store.summarize_user_reflections(userId)
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reflective summary not found")
    return ReflectiveSummaryResponse(**summary)
