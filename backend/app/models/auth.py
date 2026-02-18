from pydantic import BaseModel, Field


class AuthRegisterRequest(BaseModel):
    userId: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    displayName: str | None = Field(default=None, max_length=100)


class AuthLoginRequest(BaseModel):
    userId: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class AuthUser(BaseModel):
    userId: str
    displayName: str | None = None


class AuthResponse(BaseModel):
    tokenType: str = "bearer"
    token: str
    accessToken: str
    refreshToken: str
    expiresIn: int
    user: AuthUser


class AuthRefreshRequest(BaseModel):
    refreshToken: str = Field(..., min_length=16)


class AuthLogoutRequest(BaseModel):
    refreshToken: str | None = None
