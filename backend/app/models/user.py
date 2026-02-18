from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    userId: str
    displayName: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionScoreEntry(BaseModel):
    sessionId: str
    timestamp: datetime
    summaryScores: dict[str, float]
    rubricEvaluation: dict[str, Any] = Field(default_factory=dict)


class UserPerformanceHistoryResponse(BaseModel):
    userId: str
    profile: UserProfile | None = None
    sessionHistory: list[SessionScoreEntry] = Field(default_factory=list)


class ReflectionRequest(BaseModel):
    reflectionText: str = Field(..., min_length=3)


class ReflectionEntry(BaseModel):
    sessionId: str
    userId: str
    reflectionText: str
    coachingFeedback: dict[str, Any]
    summaryScores: dict[str, float] = Field(default_factory=dict)
    createdAt: datetime


class ReflectiveSummaryResponse(BaseModel):
    userId: str
    totalReflections: int
    reflectionEntries: list[ReflectionEntry] = Field(default_factory=list)
    aggregatedInsights: list[str] = Field(default_factory=list)
    feedbackHighlights: list[str] = Field(default_factory=list)
