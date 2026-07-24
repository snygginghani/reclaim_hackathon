"""Shared OAuth-migration helpers used by every source router.

The signed `state` binds an OAuth round-trip to a (user, workspace) without
trusting the access cookie (which may expire mid-flow); it reuses the app's
Fernet key via `ai.crypto`. `sse()` frames a dict as a Server-Sent Event."""

from __future__ import annotations

import json
import time
import uuid

from fastapi import HTTPException, status

from ..ai.crypto import decrypt_secret, encrypt_secret

STATE_TTL_SECONDS = 15 * 60


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def sign_state(user_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    payload = {"u": str(user_id), "w": str(workspace_id), "t": int(time.time())}
    return encrypt_secret(json.dumps(payload))


def verify_state(state: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    raw = decrypt_secret(state)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        if int(time.time()) - int(data["t"]) > STATE_TTL_SECONDS:
            return None
        return uuid.UUID(data["u"]), uuid.UUID(data["w"])
    except (KeyError, ValueError, TypeError):
        return None


def require_configured(client_id: str | None, client_secret: str | None, provider: str) -> None:
    """503 when the source's OAuth app isn't configured on this server (so the
    frontend can show a friendly 'not configured' state instead of failing)."""
    if not client_id or not client_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"{provider} integration is not configured on this server.",
        )
