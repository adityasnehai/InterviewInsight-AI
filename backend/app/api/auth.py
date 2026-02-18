from fastapi import APIRouter, Depends, HTTPException, status

from app.api.security import get_current_user
from app.models.auth import (
    AuthLoginRequest,
    AuthLogoutRequest,
    AuthRefreshRequest,
    AuthRegisterRequest,
    AuthResponse,
    AuthUser,
)
from app.services.session_store import session_store

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: AuthRegisterRequest) -> AuthResponse:
    try:
        registered = session_store.register_auth_user(
            user_id=payload.userId,
            password=payload.password,
            display_name=payload.displayName,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AuthResponse(
        tokenType="bearer",
        token=registered["token"],
        accessToken=registered["accessToken"],
        refreshToken=registered["refreshToken"],
        expiresIn=int(registered["expiresIn"]),
        user=AuthUser(**registered["user"]),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthLoginRequest) -> AuthResponse:
    try:
        logged_in = session_store.login_auth_user(
            user_id=payload.userId,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return AuthResponse(
        tokenType="bearer",
        token=logged_in["token"],
        accessToken=logged_in["accessToken"],
        refreshToken=logged_in["refreshToken"],
        expiresIn=int(logged_in["expiresIn"]),
        user=AuthUser(**logged_in["user"]),
    )


@router.post("/refresh", response_model=AuthResponse)
def refresh(payload: AuthRefreshRequest) -> AuthResponse:
    try:
        refreshed = session_store.refresh_auth_token(payload.refreshToken)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return AuthResponse(
        tokenType="bearer",
        token=refreshed["token"],
        accessToken=refreshed["accessToken"],
        refreshToken=refreshed["refreshToken"],
        expiresIn=int(refreshed["expiresIn"]),
        user=AuthUser(**refreshed["user"]),
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(payload: AuthLogoutRequest | None = None) -> dict[str, bool]:
    refresh_token = payload.refreshToken if payload else None
    if not refresh_token:
        return {"success": True}
    revoked = session_store.revoke_refresh_token(refresh_token)
    return {"success": bool(revoked)}


@router.get("/me", response_model=AuthUser)
def me(current_user: dict = Depends(get_current_user)) -> AuthUser:
    return AuthUser(**current_user)
