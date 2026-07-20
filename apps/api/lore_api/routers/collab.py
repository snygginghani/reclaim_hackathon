import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel
from sqlalchemy import select

from ..collab import FastAPIWebsocket, ReadOnlyWebsocket
from ..db import SessionLocal
from ..deps import CurrentUser, DbSession
from ..models import Document, Page, WorkspaceMember
from ..routers.pages import _get_page_checked
from ..security import ACCESS_COOKIE, decode_token

router = APIRouter(tags=["collab"])

WS_UNAUTHORIZED = 4401
WS_NOT_FOUND = 4404


@router.websocket("/api/collab/{page_id}")
async def collab_ws(websocket: WebSocket, page_id: uuid.UUID) -> None:
    """Yjs sync endpoint (y-websocket protocol). Auth via the access cookie;
    viewers get a read-only channel enforced server-side."""
    token = websocket.cookies.get(ACCESS_COOKIE)
    user_id = decode_token(token, "access") if token else None
    if user_id is None:
        await websocket.close(code=WS_UNAUTHORIZED)
        return

    async with SessionLocal() as db:
        page = await db.get(Page, page_id)
        member = None
        if page is not None and page.deleted_at is None:
            member = (
                await db.execute(
                    select(WorkspaceMember).where(
                        WorkspaceMember.workspace_id == page.workspace_id,
                        WorkspaceMember.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
    if page is None or page.deleted_at is not None or member is None:
        await websocket.close(code=WS_NOT_FOUND)
        return

    await websocket.accept()
    channel_cls = ReadOnlyWebsocket if member.role == "viewer" else FastAPIWebsocket
    channel = channel_cls(websocket, str(page_id))
    server = websocket.app.state.collab_server
    await server.serve(channel)


class SeedResult(BaseModel):
    granted: bool


@router.post("/api/pages/{page_id}/collab-seed", response_model=SeedResult)
async def collab_seed(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SeedResult:
    """Grant exactly one client the right to seed the collaborative Y.Doc from
    the stored JSON snapshot (legacy or imported pages). Every later caller —
    including concurrent racers — is denied, which is what prevents the
    duplicated-content bug two cold-opening clients would otherwise cause."""
    await _get_page_checked(db, page_id, user.id, min_role="editor")
    doc = await db.get(Document, page_id, with_for_update=True)
    if doc is None:
        doc = Document(page_id=page_id, blocks=[], collab_seeded_at=datetime.now(timezone.utc))
        db.add(doc)
        await db.commit()
        return SeedResult(granted=True)
    if doc.collab_seeded_at is None:
        doc.collab_seeded_at = datetime.now(timezone.utc)
        await db.commit()
        return SeedResult(granted=True)
    return SeedResult(granted=False)
