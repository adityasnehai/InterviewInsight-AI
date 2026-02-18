from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InterviewReportRequest(BaseModel):
    includeChartSnapshots: bool = False
    chartSnapshots: dict[str, str] | None = None
    userName: str | None = None
    format: str = "pdf"


class SegmentReportSummary(BaseModel):
    segmentId: str
    label: str
    startTime: float
    endTime: float
    scores: dict[str, float] = Field(default_factory=dict)
    dominantEmotion: str = "neutral"


class InterviewReportResponse(BaseModel):
    title: str
    generatedAt: datetime
    sessionMetadata: dict[str, Any]
    overallScores: dict[str, float]
    detailedScores: dict[str, Any]
    segmentSummaries: list[SegmentReportSummary]
    feedbackMessages: list[str]
    strengths: list[str]
    improvements: list[str]
    chartSnapshots: dict[str, str] | None = None
