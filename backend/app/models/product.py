from datetime import datetime

from pydantic import BaseModel, Field


class ProductSessionStartRequest(BaseModel):
    jobRole: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)


class ProductSessionSummary(BaseModel):
    sessionId: str
    jobRole: str
    domain: str
    status: str
    startedAt: datetime
    analysisReady: bool = False
    scoringReady: bool = False
    overallPerformanceScore: float = 0.0


class ProductSessionStartResponse(BaseModel):
    sessionId: str
    status: str
    jobRole: str
    domain: str
