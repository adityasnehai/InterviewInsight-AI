from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.models.session import (
    InterviewQuestion,
    QuestionResponse,
    ResponseAck,
    SessionCreateResponse,
    SessionStartRequest,
    SessionStatusResponse,
    UploadResponse,
)
from app.services.session_store import session_store

router = APIRouter(prefix="/interviews", tags=["Interviews"])

VIDEO_EXTENSIONS = {".mp4", ".webm"}
STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage"


@router.post("/start", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
def start_interview(payload: SessionStartRequest) -> SessionCreateResponse:
    session = session_store.create_session(payload)
    return SessionCreateResponse(
        sessionId=session["sessionId"],
        message="Interview started",
        questions=[],
    )


@router.get("/{sessionId}/questions", response_model=list[InterviewQuestion])
def get_interview_questions(sessionId: str) -> list[InterviewQuestion]:
    questions = session_store.get_questions(sessionId)
    if questions is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return [InterviewQuestion(**question) for question in questions]


@router.post("/{sessionId}/responses", response_model=ResponseAck)
def submit_interview_response(sessionId: str, payload: QuestionResponse) -> ResponseAck:
    saved_response = session_store.add_response(sessionId, payload)
    if saved_response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return ResponseAck(sessionId=sessionId, message="Response saved", questionId=saved_response["questionId"])


@router.post("/{sessionId}/upload", response_model=UploadResponse)
async def upload_interview_media(
    sessionId: str,
    video: UploadFile = File(...),
    audio: UploadFile | None = File(default=None),
) -> UploadResponse:
    if session_store.get_session(sessionId) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    video_extension = Path(video.filename or "").suffix.lower()
    if video_extension not in VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video file must be .mp4 or .webm",
        )

    session_folder = STORAGE_ROOT / sessionId
    session_folder.mkdir(parents=True, exist_ok=True)

    video_filename = f"video{video_extension}"
    video_path = session_folder / video_filename
    _save_upload(video, video_path)

    audio_relative: str | None = None
    if audio and audio.filename:
        audio_extension = Path(audio.filename).suffix.lower()
        audio_filename = f"audio{audio_extension}" if audio_extension else "audio"
        audio_path = session_folder / audio_filename
        _save_upload(audio, audio_path)
        audio_relative = str(audio_path.relative_to(STORAGE_ROOT))

    video_relative = str(video_path.relative_to(STORAGE_ROOT))
    session_store.add_upload(sessionId, video_relative, audio_relative)

    return UploadResponse(
        sessionId=sessionId,
        message="Files uploaded successfully",
        videoFile=video_relative,
        audioFile=audio_relative,
    )


@router.get("/{sessionId}/status", response_model=SessionStatusResponse)
def get_interview_status(sessionId: str) -> SessionStatusResponse:
    status_payload = session_store.get_status(sessionId)
    if status_payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionStatusResponse(**status_payload)


def _save_upload(upload: UploadFile, destination: Path) -> None:
    upload.file.seek(0)
    with destination.open("wb") as output_file:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            output_file.write(chunk)
    upload.file.close()
