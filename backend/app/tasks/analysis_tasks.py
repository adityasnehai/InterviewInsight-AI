from app.celery_app import celery_app
from app.models.analysis import VideoAnalysisRequest
from app.services.analysis_pipeline import execute_video_analysis
from app.services.session_store import session_store


@celery_app.task(bind=True, name="analysis.run_video_analysis")
def run_video_analysis_task(self, job_id: str, payload: dict) -> dict:
    session_store.mark_analysis_job_running(job_id=job_id, task_id=str(self.request.id))
    try:
        request_model = VideoAnalysisRequest(**payload)
        result = execute_video_analysis(request_model)
        summary = result.summaryScores.model_dump()
        session_store.mark_analysis_job_success(
            job_id=job_id,
            result_summary={
                "sessionId": result.sessionId,
                "summaryScores": summary,
            },
        )
        return {
            "jobId": job_id,
            "sessionId": result.sessionId,
            "summaryScores": summary,
            "status": "completed",
        }
    except Exception as exc:
        session_store.mark_analysis_job_failed(job_id=job_id, error_message=str(exc))
        raise
