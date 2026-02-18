from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExplanationDetail(BaseModel):
    scoreKey: str
    scoreValue: float
    explanation: str
    drivers: dict[str, float | str] = Field(default_factory=dict)


class AdvancedScoreResponse(BaseModel):
    sessionId: str
    numericScores: dict[str, float]
    rubricEvaluation: dict[str, Any] = Field(default_factory=dict)
    textualExplanations: list[ExplanationDetail]
    llmRationale: dict[str, Any]
    fairnessReport: dict[str, Any]
    generatedAt: datetime
