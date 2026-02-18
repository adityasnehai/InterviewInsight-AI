from typing import Any

from pydantic import BaseModel, Field


class AvatarConfigResponse(BaseModel):
    enabled: bool = False
    provider: str = "browser"
    mode: str = "browser_tts"
    message: str = ""


class AvatarSpeakRequest(BaseModel):
    text: str = Field(..., min_length=1)
    sessionId: str | None = None


class AvatarVisemeFrame(BaseModel):
    start: float = 0.0
    end: float = 0.0
    viseme: str = "rest"
    intensity: float = 0.0


class AvatarSpeakResponse(BaseModel):
    mode: str = "browser_tts"
    provider: str = "browser"
    text: str
    requestId: str | None = None
    videoUrl: str | None = None
    audioUrl: str | None = None
    statusUrl: str | None = None
    emotion: str | None = None
    speakingStyle: str | None = None
    visemeTimeline: list[AvatarVisemeFrame] = Field(default_factory=list)
    providerPayload: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    fallbackReason: str | None = None


class AvatarStatusRequest(BaseModel):
    requestId: str = Field(..., min_length=1)
    provider: str | None = None


class AvatarStatusResponse(BaseModel):
    provider: str
    requestId: str
    status: str
    isReady: bool = False
    videoUrl: str | None = None
    audioUrl: str | None = None
    emotion: str | None = None
    speakingStyle: str | None = None
    visemeTimeline: list[AvatarVisemeFrame] = Field(default_factory=list)
    providerPayload: dict[str, Any] | None = None
    error: str | None = None


class SimliSessionRequest(BaseModel):
    sessionId: str = Field(..., min_length=1)


class SimliSessionResponse(BaseModel):
    provider: str = "simli"
    roomName: str
    participantIdentity: str
    participantToken: str
    wsUrl: str
    faceId: str
