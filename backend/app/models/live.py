from typing import Literal

from pydantic import BaseModel, Field


class LiveInterviewStartRequest(BaseModel):
    jobRole: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)


class LiveInterviewStartResponse(BaseModel):
    sessionId: str
    userId: str
    currentQuestion: str
    questionId: str
    questionIndex: int
    totalQuestions: int
    status: str


class LiveAnswerRequest(BaseModel):
    answerText: str = Field(..., min_length=1)
    questionAskedAt: str | None = None
    answerStartedAt: str | None = None
    answerEndedAt: str | None = None
    transcriptConfidence: float | None = None


class LiveSkipRequest(BaseModel):
    questionAskedAt: str | None = None
    skippedAt: str | None = None


class LiveTurnEvaluationRequest(BaseModel):
    transcript: str = Field(default="")
    listeningMs: int | None = Field(default=None, ge=0)
    silenceMs: int | None = Field(default=None, ge=0)
    isFinal: bool = False
    minWords: int | None = Field(default=None, ge=1, le=32)


class LiveTurnEvaluationResponse(BaseModel):
    action: Literal["keep_listening", "submit", "ignore_echo"]
    shouldSubmit: bool
    shouldKeepListening: bool
    reason: str
    normalizedTranscript: str = ""
    wordCount: int = 0
    confidenceHint: float = Field(default=0.0, ge=0.0, le=1.0)


class LiveAnswerResponse(BaseModel):
    sessionId: str
    nextQuestion: str | None = None
    questionId: str | None = None
    questionIndex: int
    isInterviewComplete: bool
    status: str


class LiveInterviewStateResponse(BaseModel):
    sessionId: str
    status: str
    questionIndex: int = 0
    currentQuestion: str | None = None
    turns: list[dict] = Field(default_factory=list)
    timelineMarkers: list[dict] = Field(default_factory=list)


class LiveInterviewEndResponse(BaseModel):
    sessionId: str
    status: str
    analysisReady: bool
    analysisJobId: str | None = None
    analysisJobStatus: str | None = None
    summaryScores: dict[str, float] = Field(default_factory=dict)
