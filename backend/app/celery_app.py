import os
import logging

from celery import Celery
from dotenv import load_dotenv

from app.db import init_db

load_dotenv()
logger = logging.getLogger(__name__)

# Keep worker logs readable during first-time HF model initialization.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)


def _broker_url() -> str:
    return os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _backend_url() -> str:
    return os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379/0"))


celery_app = Celery(
    "interviewinsight",
    broker=_broker_url(),
    backend=_backend_url(),
    include=["app.tasks.analysis_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    imports=("app.tasks.analysis_tasks",),
)

try:
    init_db()
except Exception as exc:  # pragma: no cover - startup guard for local/dev race conditions
    logger.warning("Celery startup continuing without immediate DB init: %s", exc)
celery_app.autodiscover_tasks(["app.tasks"])
