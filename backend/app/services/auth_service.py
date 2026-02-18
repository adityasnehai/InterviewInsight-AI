import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import jwt

ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jwt_secret() -> str:
    return os.getenv("JWT_SECRET_KEY", "change-me-in-production")


def _access_ttl_minutes() -> int:
    return int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


def _refresh_ttl_days() -> int:
    return int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30"))


def _bcrypt_input(password: str) -> bytes:
    # Pre-hash to fixed length so bcrypt never hits the 72-byte password limit.
    digest_hex = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return digest_hex.encode("ascii")


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_input(plain_password), hashed_password.encode("utf-8"))
    except Exception:
        return False


def hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def create_access_token(*, user_id: str, display_name: str | None = None) -> tuple[str, datetime]:
    issued_at = _utc_now()
    expires_at = issued_at + timedelta(minutes=_access_ttl_minutes())
    payload: dict[str, Any] = {
        "sub": user_id,
        "displayName": display_name,
        "tokenType": TOKEN_TYPE_ACCESS,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid4()),
    }
    encoded = jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)
    return encoded, expires_at


def create_refresh_token(*, user_id: str) -> tuple[str, str, datetime]:
    issued_at = _utc_now()
    expires_at = issued_at + timedelta(days=_refresh_ttl_days())
    jti = str(uuid4())
    payload: dict[str, Any] = {
        "sub": user_id,
        "tokenType": TOKEN_TYPE_REFRESH,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": jti,
    }
    encoded = jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)
    return encoded, jti, expires_at


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    payload = jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
    token_type = str(payload.get("tokenType", ""))
    if expected_type and token_type != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


def access_expires_in_seconds() -> int:
    return _access_ttl_minutes() * 60
