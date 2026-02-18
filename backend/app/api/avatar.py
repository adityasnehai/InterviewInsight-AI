from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.security import get_current_user
from app.models.avatar import (
    AvatarConfigResponse,
    AvatarSpeakRequest,
    AvatarSpeakResponse,
    AvatarStatusRequest,
    AvatarStatusResponse,
    SimliSessionRequest,
    SimliSessionResponse,
)
from app.services.avatar_provider import avatar_provider_service
from app.services.livekit_session import create_simli_livekit_session

router = APIRouter(prefix="/app/live/avatar", tags=["Avatar"])


@router.get("/config", response_model=AvatarConfigResponse)
def get_avatar_config(current_user: dict = Depends(get_current_user)) -> AvatarConfigResponse:
    _ = current_user
    config = avatar_provider_service.get_config()
    return AvatarConfigResponse(
        enabled=config.enabled,
        provider=config.provider,
        mode=config.mode,
        message=config.message,
    )


@router.post("/speak", response_model=AvatarSpeakResponse)
def synthesize_avatar_speech(
    payload: AvatarSpeakRequest,
    current_user: dict = Depends(get_current_user),
) -> AvatarSpeakResponse:
    _ = current_user
    result = avatar_provider_service.synthesize_avatar_prompt(
        text=payload.text.strip(),
        session_id=payload.sessionId,
    )
    return AvatarSpeakResponse(**result)


@router.post("/status", response_model=AvatarStatusResponse)
def get_avatar_render_status(
    payload: AvatarStatusRequest,
    current_user: dict = Depends(get_current_user),
) -> AvatarStatusResponse:
    _ = current_user
    result = avatar_provider_service.get_render_status(
        request_id=payload.requestId.strip(),
        provider=(payload.provider or "").strip().lower() or None,
    )
    return AvatarStatusResponse(**result)


@router.get("/status", response_model=AvatarStatusResponse)
def get_avatar_render_status_get(
    requestId: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> AvatarStatusResponse:
    _ = current_user
    if not requestId or not requestId.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="requestId query parameter is required for GET /app/live/avatar/status.",
        )
    result = avatar_provider_service.get_render_status(
        request_id=requestId.strip(),
        provider=(provider or "").strip().lower() or None,
    )
    return AvatarStatusResponse(**result)


@router.get("/asset/{requestId}")
def get_avatar_asset(
    requestId: str,
) -> FileResponse:
    asset_path = avatar_provider_service.get_local_asset_path(requestId.strip())
    if asset_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar asset not found")
    return FileResponse(path=str(asset_path), media_type="video/mp4", filename=asset_path.name)


@router.get("/audio/{requestId}")
def get_avatar_audio(
    requestId: str,
) -> FileResponse:
    audio_path = avatar_provider_service.get_local_audio_path(requestId.strip())
    if audio_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar audio not found")
    return FileResponse(path=str(audio_path), media_type="audio/wav", filename=audio_path.name)


@router.post("/simli/session", response_model=SimliSessionResponse)
def create_simli_session(
    payload: SimliSessionRequest,
    current_user: dict = Depends(get_current_user),
) -> SimliSessionResponse:
    config = avatar_provider_service.get_config()
    if not config.enabled or config.provider != "simli":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Simli provider is not enabled. Set IIA_AVATAR_MODE=provider and IIA_AVATAR_PROVIDER=simli.",
        )

    try:
        data = create_simli_livekit_session(
            session_id=payload.sessionId.strip(),
            user_id=str(current_user["userId"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return SimliSessionResponse(**data)
