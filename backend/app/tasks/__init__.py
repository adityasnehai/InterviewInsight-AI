"""Celery task package."""

# Ensure task decorators are imported when package is loaded.
from app.tasks.analysis_tasks import run_video_analysis_task

__all__ = ["run_video_analysis_task"]
