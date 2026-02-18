from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.security import get_current_user
from app.models.analysis import VideoAnalysisRequest
from app.models.live import (
    LiveAnswerRequest,
    LiveAnswerResponse,
    LiveInterviewEndResponse,
    LiveInterviewStartRequest,
    LiveInterviewStartResponse,
    LiveInterviewStateResponse,
    LiveSkipRequest,
    LiveTurnEvaluationRequest,
    LiveTurnEvaluationResponse,
)
from app.models.session import SessionStartRequest
from app.services.ai_interviewer import (
    evaluate_answer_quality,
    generate_clarification_question,
    generate_followup_question,
)
from app.services.analysis_queue import enqueue_video_analysis
from app.services.session_store import session_store

router = APIRouter(prefix="/app/live", tags=["Live Interview"])

VIDEO_EXTENSIONS = {".mp4", ".webm"}
STORAGE_ROOT = Path(__file__).resolve().parents[1] / "storage"
MAX_LIVE_QUESTIONS = 5
MAX_CLARIFICATIONS_PER_QUESTION = 1
DEFAULT_TURN_MIN_WORDS = 6
TURN_SUBMIT_SILENCE_MS = 1200
TURN_ECHO_OVERLAP_THRESHOLD = 0.74


@router.post("/start", response_model=LiveInterviewStartResponse, status_code=status.HTTP_201_CREATED)
def start_live_interview(
    payload: LiveInterviewStartRequest,
    current_user: dict = Depends(get_current_user),
) -> LiveInterviewStartResponse:
    user_id = str(current_user["userId"])
    session = session_store.create_session(
        SessionStartRequest(userId=user_id, jobRole=payload.jobRole, domain=payload.domain)
    )
    live_state = session_store.initialize_live_interview(session["sessionId"])
    if live_state is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to initialize live interview")
    return LiveInterviewStartResponse(
        sessionId=session["sessionId"],
        userId=user_id,
        currentQuestion=str(live_state["currentQuestionText"]),
        questionId=str(live_state["currentQuestionId"]),
        questionIndex=int(live_state["questionIndex"]),
        totalQuestions=MAX_LIVE_QUESTIONS,
        status="live_started",
    )


@router.get("/{sessionId}/state", response_model=LiveInterviewStateResponse)
def get_live_interview_state(
    sessionId: str,
    current_user: dict = Depends(get_current_user),
) -> LiveInterviewStateResponse:
    user_id = str(current_user["userId"])
    if not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    live_state = session_store.get_live_state(sessionId)
    if live_state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Live interview state not found")
    return LiveInterviewStateResponse(
        sessionId=sessionId,
        status="live_completed" if live_state.get("complete") else "live_in_progress",
        questionIndex=int(live_state.get("questionIndex", 0)),
        currentQuestion=live_state.get("currentQuestionText"),
        turns=live_state.get("turns", []),
        timelineMarkers=live_state.get("timelineMarkers", []),
    )


@router.post("/{sessionId}/turn-evaluate", response_model=LiveTurnEvaluationResponse)
def evaluate_live_turn(
    sessionId: str,
    payload: LiveTurnEvaluationRequest,
    current_user: dict = Depends(get_current_user),
) -> LiveTurnEvaluationResponse:
    user_id = str(current_user["userId"])
    session = session_store.get_session(sessionId)
    if session is None or not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    live_state = session_store.get_live_state(sessionId)
    if live_state is None or not live_state.get("active"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Live interview not active")

    decision = _evaluate_turn_capture(
        transcript=payload.transcript,
        current_question=str(live_state.get("currentQuestionText") or ""),
        listening_ms=int(payload.listeningMs or 0),
        silence_ms=int(payload.silenceMs or 0),
        is_final=bool(payload.isFinal),
        min_words=int(payload.minWords or DEFAULT_TURN_MIN_WORDS),
    )
    return LiveTurnEvaluationResponse(**decision)


@router.post("/{sessionId}/answer", response_model=LiveAnswerResponse)
def submit_live_answer(
    sessionId: str,
    payload: LiveAnswerRequest,
    current_user: dict = Depends(get_current_user),
) -> LiveAnswerResponse:
    user_id = str(current_user["userId"])
    session = session_store.get_session(sessionId)
    if session is None or not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    live_state = session_store.record_live_answer(
        session_id=sessionId,
        answer_text=payload.answerText.strip(),
        question_asked_at=payload.questionAskedAt,
        answer_started_at=payload.answerStartedAt,
        answer_ended_at=payload.answerEndedAt,
        transcript_confidence=payload.transcriptConfidence,
    )
    if live_state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Live interview not active")

    return _advance_live_interview(
        session_id=sessionId,
        session=session,
        live_state=live_state,
        latest_answer_text=payload.answerText.strip(),
        was_skipped=False,
    )


@router.post("/{sessionId}/skip", response_model=LiveAnswerResponse)
def skip_live_question(
    sessionId: str,
    payload: LiveSkipRequest,
    current_user: dict = Depends(get_current_user),
) -> LiveAnswerResponse:
    user_id = str(current_user["userId"])
    session = session_store.get_session(sessionId)
    if session is None or not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    live_state = session_store.record_live_skip(
        session_id=sessionId,
        question_asked_at=payload.questionAskedAt,
        skipped_at=payload.skippedAt,
    )
    if live_state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Live interview not active")

    return _advance_live_interview(
        session_id=sessionId,
        session=session,
        live_state=live_state,
        latest_answer_text="[Question skipped by user]",
        was_skipped=True,
    )


@router.post("/{sessionId}/end", response_model=LiveInterviewEndResponse)
def end_live_interview(
    sessionId: str,
    video: UploadFile = File(...),
    audio: UploadFile | None = File(default=None),
    frameFps: int = Form(default=2),
    windowSizeSeconds: float = Form(default=3.0),
    useLearnedFusion: bool = Form(default=False),
    current_user: dict = Depends(get_current_user),
) -> LiveInterviewEndResponse:
    user_id = str(current_user["userId"])
    session = session_store.get_session(sessionId)
    if session is None or not session_store.session_belongs_to_user(sessionId, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    video_extension = Path(video.filename or "").suffix.lower()
    if video_extension not in VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video file must be .mp4 or .webm",
        )

    session_folder = STORAGE_ROOT / sessionId
    session_folder.mkdir(parents=True, exist_ok=True)

    timestamp_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    video_path = session_folder / f"live_video_{timestamp_slug}{video_extension}"
    _save_upload(video, video_path)
    video_relative = str(video_path.relative_to(STORAGE_ROOT))

    audio_relative: str | None = None
    audio_abs_path: str | None = None
    if audio and audio.filename:
        audio_extension = Path(audio.filename).suffix.lower()
        audio_path = session_folder / f"live_audio_{timestamp_slug}{audio_extension if audio_extension else ''}"
        _save_upload(audio, audio_path)
        audio_relative = str(audio_path.relative_to(STORAGE_ROOT))
        audio_abs_path = str(audio_path.resolve())

    session_store.add_upload(sessionId, video_relative, audio_relative)
    session_store.mark_live_complete(sessionId)

    try:
        analysis_job = enqueue_video_analysis(
            payload=VideoAnalysisRequest(
                sessionId=sessionId,
                videoFilePath=str(video_path.resolve()),
                audioFilePath=audio_abs_path,
                frameFps=frameFps,
                windowSizeSeconds=windowSizeSeconds,
                useLearnedFusion=useLearnedFusion,
            ),
            user_id=user_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to enqueue analysis: {exc}") from exc
    return LiveInterviewEndResponse(
        sessionId=sessionId,
        status="analysis_queued",
        analysisReady=False,
        analysisJobId=analysis_job.get("jobId"),
        analysisJobStatus=analysis_job.get("status"),
        summaryScores={},
    )


def _save_upload(upload: UploadFile, destination: Path) -> None:
    upload.file.seek(0)
    with destination.open("wb") as output_file:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            output_file.write(chunk)
    upload.file.close()


def _advance_live_interview(
    session_id: str,
    session: dict,
    live_state: dict,
    latest_answer_text: str,
    was_skipped: bool,
) -> LiveAnswerResponse:
    current_index = int(live_state.get("questionIndex", 0))
    current_question_id = str(live_state.get("currentQuestionId") or f"q{current_index + 1}")
    current_question_text = str(live_state.get("currentQuestionText") or "")

    if not was_skipped:
        clarification_count = session_store.get_live_clarification_count(session_id, current_index)
        quality = evaluate_answer_quality(
            answer_text=latest_answer_text,
            current_question=current_question_text,
        )
        if bool(quality.get("needsClarification")) and clarification_count < MAX_CLARIFICATIONS_PER_QUESTION:
            clarification_question = generate_clarification_question(
                job_role=str(session.get("jobRole", "")),
                domain=str(session.get("domain", "")),
                current_question=current_question_text,
                candidate_answer=latest_answer_text,
                turns=live_state.get("turns", []),
            )
            next_clarification_count = session_store.increment_live_clarification_count(session_id, current_index)
            clarification_question_id = f"{current_question_id}-clarify-{next_clarification_count}"
            session_store.set_live_next_question(
                session_id=session_id,
                question_id=clarification_question_id,
                question_text=clarification_question,
                question_index=current_index,
            )
            return LiveAnswerResponse(
                sessionId=session_id,
                nextQuestion=clarification_question,
                questionId=clarification_question_id,
                questionIndex=current_index,
                isInterviewComplete=False,
                status="live_in_progress",
            )

    next_index = current_index + 1

    next_question: str | None = None
    next_question_id: str | None = None
    questions = session.get("questions", [])
    if next_index < len(questions):
        question = questions[next_index]
        next_question = str(question.get("questionText", ""))
        next_question_id = str(question.get("questionId", f"q{next_index + 1}"))
    elif next_index < MAX_LIVE_QUESTIONS:
        turns = live_state.get("turns", [])
        next_question = generate_followup_question(
            job_role=str(session.get("jobRole", "")),
            domain=str(session.get("domain", "")),
            turns=turns,
            current_question_index=next_index,
        )
        next_question_id = f"f{next_index + 1}"

    if next_question and next_question_id:
        session_store.set_live_next_question(
            session_id=session_id,
            question_id=next_question_id,
            question_text=next_question,
            question_index=next_index,
        )
        return LiveAnswerResponse(
            sessionId=session_id,
            nextQuestion=next_question,
            questionId=next_question_id,
            questionIndex=next_index,
            isInterviewComplete=False,
            status="live_in_progress",
        )

    session_store.mark_live_complete(session_id)
    return LiveAnswerResponse(
        sessionId=session_id,
        questionIndex=next_index,
        isInterviewComplete=True,
        status="live_completed",
    )


def _evaluate_turn_capture(
    *,
    transcript: str,
    current_question: str,
    listening_ms: int,
    silence_ms: int,
    is_final: bool,
    min_words: int,
) -> dict:
    normalized_transcript = _normalize_text(transcript)
    normalized_question = _normalize_text(current_question)
    word_count = _count_words(normalized_transcript)
    overlap_ratio = _token_overlap_ratio(normalized_transcript, normalized_question)

    if word_count == 0:
        return {
            "action": "keep_listening",
            "shouldSubmit": False,
            "shouldKeepListening": True,
            "reason": "No speech detected yet",
            "normalizedTranscript": "",
            "wordCount": 0,
            "confidenceHint": 0.0,
        }

    if overlap_ratio >= TURN_ECHO_OVERLAP_THRESHOLD and word_count <= 20:
        return {
            "action": "ignore_echo",
            "shouldSubmit": False,
            "shouldKeepListening": True,
            "reason": "Likely avatar echo; keep listening for user answer",
            "normalizedTranscript": normalized_transcript,
            "wordCount": word_count,
            "confidenceHint": 0.1,
        }

    if word_count >= max(3, min_words) and (silence_ms >= TURN_SUBMIT_SILENCE_MS or is_final):
        confidence = 0.68
        if word_count >= 14:
            confidence = 0.82
        if word_count >= 24:
            confidence = 0.9
        return {
            "action": "submit",
            "shouldSubmit": True,
            "shouldKeepListening": False,
            "reason": "Speech segment appears complete",
            "normalizedTranscript": normalized_transcript,
            "wordCount": word_count,
            "confidenceHint": confidence,
        }

    if listening_ms >= 30000 and word_count >= 5:
        return {
            "action": "submit",
            "shouldSubmit": True,
            "shouldKeepListening": False,
            "reason": "Long response window reached",
            "normalizedTranscript": normalized_transcript,
            "wordCount": word_count,
            "confidenceHint": 0.72,
        }

    return {
        "action": "keep_listening",
        "shouldSubmit": False,
        "shouldKeepListening": True,
        "reason": "Collecting more speech for stronger answer",
        "normalizedTranscript": normalized_transcript,
        "wordCount": word_count,
        "confidenceHint": 0.45,
    }


def _normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "")).split())


def _count_words(value: str) -> int:
    if not value:
        return 0
    return len([token for token in value.split(" ") if token])


def _token_overlap_ratio(candidate: str, reference: str) -> float:
    candidate_tokens = {token for token in candidate.split(" ") if token}
    reference_tokens = {token for token in reference.split(" ") if token}
    if not candidate_tokens or not reference_tokens:
        return 0.0
    overlap = len(candidate_tokens.intersection(reference_tokens))
    return overlap / len(candidate_tokens)
