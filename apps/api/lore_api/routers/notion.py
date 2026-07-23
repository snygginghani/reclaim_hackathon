"""Notion migration endpoints: OAuth connect, status, streamed import, disconnect.

The connection is transient — the encrypted token is deleted on disconnect and
automatically after a successful import, so Lore keeps no ongoing access to the
user's Notion (see NotionConnection)."""

import json
import time
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select

from ..ai.crypto import decrypt_secret, encrypt_secret
from ..ai.ingest import ingest_page
from ..config import get_settings
from ..deps import CurrentUser, DbSession, require_membership
from ..db import SessionLocal
from ..models import NotionConnection
from ..notion.client import NotionError, exchange_code, revoke_token
from ..notion.importer import import_workspace

router = APIRouter(prefix="/api/notion", tags=["notion"])

NOTION_AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
STATE_TTL_SECONDS = 15 * 60


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _sign_state(user_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    payload = {"u": str(user_id), "w": str(workspace_id), "t": int(time.time())}
    return encrypt_secret(json.dumps(payload))


def _verify_state(state: str) -> tuple[uuid.UUID, uuid.UUID] | None:
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


def _require_configured() -> None:
    s = get_settings()
    if not s.notion_client_id or not s.notion_client_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Notion integration is not configured on this server.",
        )


# --- connect ---


@router.get("/authorize-url")
async def authorize_url(workspace_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict:
    _require_configured()
    await require_membership(db, workspace_id, user.id, min_role="editor")
    s = get_settings()
    params = {
        "client_id": s.notion_client_id,
        "response_type": "code",
        "owner": "user",
        "redirect_uri": s.notion_redirect_uri,
        "state": _sign_state(user.id, workspace_id),
    }
    return {"url": f"{NOTION_AUTHORIZE_URL}?{urlencode(params)}"}


@router.get("/oauth/callback")
async def oauth_callback(request: Request, db: DbSession) -> RedirectResponse:
    """Notion redirects the browser here. We trust the Fernet-signed `state` for
    the user/workspace binding (the access cookie may have expired mid-flow)."""
    s = get_settings()
    code = request.query_params.get("code")
    state = request.query_params.get("state") or ""
    err_redirect = f"{s.web_base_url}/onboarding"

    verified = _verify_state(state)
    if verified is None or not code:
        return RedirectResponse(f"{err_redirect}?notion_error=invalid_state")
    user_id, workspace_id = verified
    settings_url = f"{s.web_base_url}/w/{workspace_id}/settings/notion"

    # Confirm the membership still holds before storing anything.
    try:
        await require_membership(db, workspace_id, user_id, min_role="editor")
    except HTTPException:
        return RedirectResponse(f"{settings_url}?notion_error=forbidden")

    try:
        token_data = await exchange_code(code)
    except NotionError:
        return RedirectResponse(f"{settings_url}?notion_error=exchange_failed")

    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(f"{settings_url}?notion_error=no_token")

    # Upsert the (workspace, user) connection.
    existing = (
        await db.execute(
            select(NotionConnection).where(
                NotionConnection.workspace_id == workspace_id,
                NotionConnection.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.token_encrypted = encrypt_secret(access_token)
        existing.notion_workspace_name = token_data.get("workspace_name")
        existing.bot_id = token_data.get("bot_id")
    else:
        db.add(
            NotionConnection(
                workspace_id=workspace_id,
                user_id=user_id,
                token_encrypted=encrypt_secret(access_token),
                notion_workspace_name=token_data.get("workspace_name"),
                bot_id=token_data.get("bot_id"),
            )
        )
    await db.commit()
    return RedirectResponse(f"{settings_url}?connected=1")


# --- status / disconnect ---


async def _get_connection(db, workspace_id: uuid.UUID, user_id: uuid.UUID) -> NotionConnection | None:
    return (
        await db.execute(
            select(NotionConnection).where(
                NotionConnection.workspace_id == workspace_id,
                NotionConnection.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


@router.get("/status")
async def status_endpoint(workspace_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict:
    await require_membership(db, workspace_id, user.id, min_role="editor")
    conn = await _get_connection(db, workspace_id, user.id)
    return {
        "configured": bool(get_settings().notion_client_id and get_settings().notion_client_secret),
        "connected": conn is not None,
        "notion_workspace_name": conn.notion_workspace_name if conn else None,
    }


async def _revoke_and_delete(conn_id: uuid.UUID, token: str) -> None:
    await revoke_token(token)
    async with SessionLocal() as db:
        await db.execute(delete(NotionConnection).where(NotionConnection.id == conn_id))
        await db.commit()


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(workspace_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    await require_membership(db, workspace_id, user.id, min_role="editor")
    conn = await _get_connection(db, workspace_id, user.id)
    if conn is not None:
        token = decrypt_secret(conn.token_encrypted) or ""
        await _revoke_and_delete(conn.id, token)


# --- import (SSE) ---


class ImportBody(BaseModel):
    workspace_id: uuid.UUID


@router.post("/import")
async def start_import(body: ImportBody, user: CurrentUser, db: DbSession) -> StreamingResponse:
    await require_membership(db, body.workspace_id, user.id, min_role="editor")
    conn = await _get_connection(db, body.workspace_id, user.id)
    if conn is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not connected to Notion")
    token = decrypt_secret(conn.token_encrypted)
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stored Notion token is unreadable")
    conn_id = conn.id
    workspace_id = body.workspace_id
    user_id = user.id

    async def stream():
        page_ids: list[str] = []
        try:
            async for ev in import_workspace(workspace_id, user_id, token):
                if ev.get("type") == "imported":
                    page_ids = ev.get("page_ids", [])
                yield _sse(ev)
        except Exception as exc:  # noqa: BLE001
            # Keep the connection so the user can retry without reconnecting.
            yield _sse({"type": "error", "error": str(exc)})
            return

        # Success: index imported pages, then revoke + delete the token.
        for pid in page_ids:
            try:
                await ingest_page(uuid.UUID(pid))
            except Exception:  # noqa: BLE001
                pass
        await _revoke_and_delete(conn_id, token)
        yield _sse({"type": "done", "pages": len(page_ids), "revoked": True})

    return StreamingResponse(stream(), media_type="text/event-stream")
