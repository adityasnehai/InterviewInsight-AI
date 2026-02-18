from datetime import datetime

from pydantic import BaseModel, Field


class SessionStartRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    jobRole: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)


class InterviewQuestion(BaseModel):
    questionId: str
    questionText: str


class SessionCreateResponse(BaseModel):
    sessionId: str
    message: str
    questions: list[InterviewQuestion] = Field(default_factory=list)


class QuestionResponse(BaseModel):
    questionId: str = Field(..., min_length=1)
    responseText: str = Field(..., min_length=1)


class ResponseAck(BaseModel):
    sessionId: str
    message: str
    questionId: str


class UploadResponse(BaseModel):
    sessionId: str
    message: str
    videoFile: str
    audioFile: str | None = None


class SessionStatusResponse(BaseModel):
    sessionId: str
    userId: str
    jobRole: str
    domain: str
    status: str
    startedAt: datetime
    questionsCount: int
    responsesCount: int
    analysisReady: bool = False
    scoringReady: bool = False
    advancedScoringReady: bool = False
    reportReady: bool = False
