from fastapi import APIRouter, HTTPException, status

from app.models.reports import InterviewReportRequest, InterviewReportResponse
from app.services.reports_utils import build_interview_report_payload
from app.services.session_store import session_store

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/{sessionId}/generate", response_model=InterviewReportResponse)
def generate_interview_report(
    sessionId: str,
    payload: InterviewReportRequest | None = None,
) -> InterviewReportResponse:
    session = session_store.get_session(sessionId)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    analysis_result = session_store.get_analysis_result(sessionId)
    if analysis_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis result not found. Run /analysis/video first.",
        )

    scoring_result = session_store.get_scoring_result(sessionId)
    request_payload = payload or InterviewReportRequest()

    report_payload = build_interview_report_payload(
        session_id=sessionId,
        session_data=session,
        analysis_result=analysis_result,
        scoring_result=scoring_result,
        request_payload=request_payload,
    )
    session_store.set_report_result(sessionId, report_payload)
    return InterviewReportResponse(**report_payload)
