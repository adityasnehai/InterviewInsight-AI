from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class VideoAnalysisRequest(BaseModel):
    sessionId: str = Field(..., min_length=1)
    videoFilePath: str = Field(..., min_length=1)
    audioFilePath: str | None = None
    frameFps: int = Field(default=2, ge=1, le=10)
    windowSizeSeconds: float = Field(default=3.0, ge=0.5, le=30.0)
    useLearnedFusion: bool = False


class AudioAnalysisRequest(BaseModel):
    sessionId: str = Field(..., min_length=1)
    audioFilePath: str | None = None
    videoFilePath: str | None = None


class EngagementMetrics(BaseModel):
    overallEngagement: float
    eyeContactRatio: float
    avgHeadStability: float
    avgSpeakingRateWpm: float


class EmotionTrajectoryPoint(BaseModel):
    timestamp: float
    dominantEmotion: str
    emotionScores: dict[str, float]


class SpeechQualityMetrics(BaseModel):
    averagePitch: float
    averagePauseDuration: float
    speakingRateWpm: float
    prosodyScore: float


class FusedFeatureVector(BaseModel):
    startTime: float
    endTime: float
    facialEmotionScores: dict[str, float]
    headPose: dict[str, float]
    gazeDirection: str
    speechFeatures: dict[str, float]
    textScores: dict[str, float]
    fusedVector: list[float]


class SessionMeta(BaseModel):
    sessionId: str
    jobRole: str
    domain: str
    dateTime: datetime


class SummaryScores(BaseModel):
    engagementScore: float
    confidenceScore: float
    speechFluency: float
    emotionalStability: float
    contentRelevanceScore: float = 0.0
    overallPerformanceScore: float = 0.0
    communicationEffectiveness: float = 0.0
    interviewReadiness: float = 0.0


class SegmentLabelValues(BaseModel):
    segmentId: str
    label: str
    startTime: float
    endTime: float
    engagementScore: float
    speechFluency: float
    textRelevanceScore: float
    dominantEmotion: str
    emotionAverages: dict[str, float]
    speechQualityMetrics: dict[str, float]


class EngagementTimelinePoint(BaseModel):
    timestamp: float
    engagement: float
    confidence: float


class SpeechTimelinePoint(BaseModel):
    timestamp: float
    speakingRate: float
    pitch: float
    pauseDuration: float
    fluency: float


class GazeHeadPoseTimelinePoint(BaseModel):
    timestamp: float
    headYaw: float
    headPitch: float
    headRoll: float
    eyeContact: float
    gazeDirection: str


class TimelineArrays(BaseModel):
    emotionTimeline: list[EmotionTrajectoryPoint]
    engagementTimeline: list[EngagementTimelinePoint]
    speechTimeline: list[SpeechTimelinePoint]
    gazeHeadPoseTimeline: list[GazeHeadPoseTimelinePoint]


class FeedbackSummary(BaseModel):
    strengths: list[str]
    improvements: list[str]
    suggestedFeedbackText: str


class DetailedScore(BaseModel):
    score: float
    components: dict[str, float | str]


class DetailedScores(BaseModel):
    engagement: DetailedScore
    emotionalRegulation: DetailedScore
    speechClarity: DetailedScore
    contentRelevance: DetailedScore
    modelPredictions: dict[str, float]
    weights: dict[str, float]
    biasAudit: dict[str, Any] = Field(default_factory=dict)


class ScoreSummaryResponse(BaseModel):
    summaryScores: SummaryScores
    detailedScores: DetailedScores


class FeedbackResponse(BaseModel):
    feedbackMessages: list[str]
    strengths: list[str]
    improvements: list[str]
    rationale: dict[str, dict[str, float]]


class SessionScoresResponse(BaseModel):
    summaryScores: SummaryScores
    detailedScores: DetailedScores
    feedbackMessages: list[str]


class AnalysisJobResponse(BaseModel):
    jobId: str
    sessionId: str
    status: str
    taskId: str | None = None
    errorMessage: str | None = None
    resultSummary: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime
    updatedAt: datetime


class MultimodalAnalysisResult(BaseModel):
    sessionId: str
    videoFilePath: str
    audioFilePath: str | None = None
    transcriptText: str
    sessionMeta: SessionMeta
    engagementMetrics: EngagementMetrics
    emotionTrajectory: list[EmotionTrajectoryPoint]
    speechQualityMetrics: SpeechQualityMetrics
    fusedFeatureVectors: list[FusedFeatureVector]
    summaryScores: SummaryScores
    segmentLabels: list[SegmentLabelValues]
    timelineArrays: TimelineArrays
    feedbackSummary: FeedbackSummary
    detailedScores: DetailedScores | None = None
    feedbackMessages: list[str] = Field(default_factory=list)
    generatedAt: datetime
