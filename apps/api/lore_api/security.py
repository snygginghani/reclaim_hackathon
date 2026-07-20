import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Response

from .config import get_settings

_hasher = PasswordHasher()

ACCESS_COOKIE = "lore_access"
REFRESH_COOKIE = "lore_refresh"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _make_token(user_id: uuid.UUID, kind: str, ttl_seconds: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "kind": kind,
            "iat": now,
            "exp": now + timedelta(seconds=ttl_seconds),
            "jti": uuid.uuid4().hex,
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )


def decode_token(token: str, expected_kind: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("kind") != expected_kind:
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


def set_auth_cookies(response: Response, user_id: uuid.UUID) -> None:
    s = get_settings()
    # httpOnly + SameSite=Lax: JS never reads tokens; localhost:3000 -> localhost:8300
    # is same-site (ports are ignored for SameSite), so cookies flow in dev.
    response.set_cookie(
        ACCESS_COOKIE,
        _make_token(user_id, "access", s.access_token_ttl_seconds),
        max_age=s.access_token_ttl_seconds,
        httponly=True,
        samesite="lax",
        path="/api",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        _make_token(user_id, "refresh", s.refresh_token_ttl_seconds),
        max_age=s.refresh_token_ttl_seconds,
        httponly=True,
        samesite="lax",
        path="/api/auth",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/api")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
