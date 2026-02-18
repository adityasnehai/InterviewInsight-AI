from app.celery_app import celery_app
from app.models.analysis import VideoAnalysisRequest
from app.services.session_store import session_store


def enqueue_video_analysis(
    payload: VideoAnalysisRequest,
    *,
    user_id: str | None = None,
) -> dict:
    session = session_store.get_session(payload.sessionId)
    if session is None:
        raise ValueError("Session not found")

    job = session_store.create_analysis_job(
        session_id=payload.sessionId,
        user_id=user_id or str(session.get("userId", "")) or None,
        payload=payload.model_dump(mode="json"),
    )
    try:
        task = celery_app.send_task(
            "analysis.run_video_analysis",
            args=[job["jobId"], payload.model_dump(mode="json")],
        )
    except Exception as exc:
        session_store.mark_analysis_job_failed(job_id=job["jobId"], error_message=str(exc))
        raise
    session_store.mark_analysis_job_running(job_id=job["jobId"], task_id=str(task.id))
    latest = session_store.get_analysis_job(job["jobId"])
    if latest is None:
        return job
    return latest
