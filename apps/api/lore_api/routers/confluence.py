"""Confluence migration endpoints: OAuth (Atlassian 3LO) connect, status, streamed
import, disconnect.

The connection is transient: no refresh token is requested (no `offline_access`
scope), so the access token self-expires (~1h), and the stored row is deleted on
manual disconnect and automatically after a successful import — Lore keeps no
ongoing access to the user's Confluence. The import runs through the shared engine
in `migrate/` driven by a `ConfluenceAdapter`."""

import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select

from ..ai.crypto import decrypt_secret, encrypt_secret
from ..ai.ingest import ingest_page
from ..config import get_settings
from ..confluence.client import AUTH_BASE, OAUTH_SCOPES, ConfluenceError, exchange_code, resolve_site
from ..db import SessionLocal
from ..deps import CurrentUser, DbSession, require_membership
from ..migrate.adapters.confluence import ConfluenceAdapter
from ..migrate.engine import run_import
from ..migrate.oauth import require_configured, sign_state, sse, verify_state
from ..models import ConfluenceConnection

router = APIRouter(prefix="/api/confluence", tags=["confluence"])

CONFLUENCE_AUTHORIZE_URL = f"{AUTH_BASE}/authorize"


def _require_configured() -> None:
    s = get_settings()
    require_configured(s.confluence_client_id, s.confluence_client_secret, "Confluence")


# --- connect ---


@router.get("/authorize-url")
async def authorize_url(workspace_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict:
    _require_configured()
    await require_membership(db, workspace_id, user.id, min_role="editor")
    s = get_settings()
    params = {
        "audience": "api.atlassian.com",
        "client_id": s.confluence_client_id,
        "scope": OAUTH_SCOPES,
        "redirect_uri": s.confluence_redirect_uri,
        "state": sign_state(user.id, workspace_id),
        "response_type": "code",
        "prompt": "consent",
    }
    return {"url": f"{CONFLUENCE_AUTHORIZE_URL}?{urlencode(params)}"}


@router.get("/oauth/callback")
async def oauth_callback(request: Request, db: DbSession) -> RedirectResponse:
    """Atlassian redirects the browser here. We trust the Fernet-signed `state`
    for the user/workspace binding (the access cookie may have expired mid-flow)."""
    s = get_settings()
    code = request.query_params.get("code")
    state = request.query_params.get("state") or ""
    err_redirect = f"{s.web_base_url}/onboarding"

    verified = verify_state(state)
    if verified is None or not code:
        return RedirectResponse(f"{err_redirect}?confluence_error=invalid_state")
    user_id, workspace_id = verified
    settings_url = f"{s.web_base_url}/w/{workspace_id}/settings/confluence"

    try:
        await require_membership(db, workspace_id, user_id, min_role="editor")
    except HTTPException:
        return RedirectResponse(f"{settings_url}?confluence_error=forbidden")

    try:
        token_data = await exchange_code(code)
    except ConfluenceError:
        return RedirectResponse(f"{settings_url}?confluence_error=exchange_failed")

    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(f"{settings_url}?confluence_error=no_token")

    try:
        site = await resolve_site(access_token)
    except ConfluenceError:
        site = None
    if site is None:
        return RedirectResponse(f"{settings_url}?confluence_error=no_site")
    cloud_id, site_name = site

    # Upsert the (workspace, user) connection.
    existing = (
        await db.execute(
            select(ConfluenceConnection).where(
                ConfluenceConnection.workspace_id == workspace_id,
                ConfluenceConnection.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.token_encrypted = encrypt_secret(access_token)
        existing.cloud_id = cloud_id
        existing.site_name = site_name
    else:
        db.add(
            ConfluenceConnection(
                workspace_id=workspace_id,
                user_id=user_id,
                token_encrypted=encrypt_secret(access_token),
                cloud_id=cloud_id,
                site_name=site_name,
            )
        )
    await db.commit()
    return RedirectResponse(f"{settings_url}?connected=1")


# --- status / disconnect ---


async def _get_connection(db, workspace_id: uuid.UUID, user_id: uuid.UUID) -> ConfluenceConnection | None:
    return (
        await db.execute(
            select(ConfluenceConnection).where(
                ConfluenceConnection.workspace_id == workspace_id,
                ConfluenceConnection.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


@router.get("/status")
async def status_endpoint(workspace_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict:
    await require_membership(db, workspace_id, user.id, min_role="editor")
    conn = await _get_connection(db, workspace_id, user.id)
    s = get_settings()
    return {
        "configured": bool(s.confluence_client_id and s.confluence_client_secret),
        "connected": conn is not None,
        "site_name": conn.site_name if conn else None,
    }


async def _delete_connection(conn_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(ConfluenceConnection).where(ConfluenceConnection.id == conn_id))
        await db.commit()


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(workspace_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    await require_membership(db, workspace_id, user.id, min_role="editor")
    conn = await _get_connection(db, workspace_id, user.id)
    if conn is not None:
        await _delete_connection(conn.id)


# --- import (SSE) ---


class ImportBody(BaseModel):
    workspace_id: uuid.UUID


@router.post("/import")
async def start_import(body: ImportBody, user: CurrentUser, db: DbSession) -> StreamingResponse:
    await require_membership(db, body.workspace_id, user.id, min_role="editor")
    conn = await _get_connection(db, body.workspace_id, user.id)
    if conn is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not connected to Confluence")
    token = decrypt_secret(conn.token_encrypted)
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stored Confluence token is unreadable")
    conn_id = conn.id
    cloud_id = conn.cloud_id
    workspace_id = body.workspace_id
    user_id = user.id

    async def stream():
        page_ids: list[str] = []
        try:
            async for ev in run_import(workspace_id, user_id, ConfluenceAdapter(token, cloud_id)):
                if ev.get("type") == "imported":
                    page_ids = ev.get("page_ids", [])
                yield sse(ev)
        except Exception as exc:  # noqa: BLE001
            # Keep the connection so the user can retry without reconnecting.
            yield sse({"type": "error", "error": str(exc)})
            return

        # Success: index imported pages, then delete the token (no Atlassian revoke
        # endpoint; the token self-expires because we never requested offline_access).
        for pid in page_ids:
            try:
                await ingest_page(uuid.UUID(pid))
            except Exception:  # noqa: BLE001
                pass
        await _delete_connection(conn_id)
        yield sse({"type": "done", "pages": len(page_ids), "revoked": True})

    return StreamingResponse(stream(), media_type="text/event-stream")
