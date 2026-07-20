"""Real-time collaboration: Yjs in the browser ↔ pycrdt rooms on the server.

One YRoom per page (room name = page uuid). The room's Y.Doc is the merge
source of truth while the page is open anywhere; every update is appended to
the `ydoc_updates` log and compacted past a threshold. The BlockNote JSON in
`documents.blocks` stays the read model, maintained by clients' autosave.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from logging import Logger, getLogger

from anyio import Lock
from fastapi import WebSocket
from pycrdt import Channel, Doc
from pycrdt.store import BaseYStore
from pycrdt.websocket import WebsocketServer, YRoom
from pycrdt.websocket.websocket_server import exception_logger
from sqlalchemy import delete, func, select

from .db import SessionLocal
from .models import YDocUpdate

# Compact the update log for a page once it exceeds this many rows.
COMPACT_AFTER = 500


class PostgresYStore(BaseYStore):
    """Yjs update log in Postgres. `path` is the page uuid string."""

    def __init__(self, path: str, metadata_callback=None, log: Logger | None = None):
        self.path = path
        self.metadata_callback = metadata_callback
        self.log = log or getLogger(__name__)

    @property
    def _page_id(self) -> uuid.UUID:
        return uuid.UUID(self.path)

    async def write(self, data: bytes) -> None:
        async with SessionLocal() as db:
            db.add(YDocUpdate(page_id=self._page_id, data=data))
            await db.commit()
            count = (
                await db.execute(
                    select(func.count())
                    .select_from(YDocUpdate)
                    .where(YDocUpdate.page_id == self._page_id)
                )
            ).scalar()
        if count is not None and count > COMPACT_AFTER:
            await self.compact()

    async def compact(self) -> None:
        """Merge the whole log into one update. Runs in a single transaction;
        concurrent writers just append after the merged row, which stays correct
        (Yjs updates are commutative and idempotent)."""
        async with SessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(YDocUpdate)
                        .where(YDocUpdate.page_id == self._page_id)
                        .order_by(YDocUpdate.id)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            if len(rows) <= 1:
                return
            doc = Doc()
            for row in rows:
                doc.apply_update(row.data)
            merged = doc.get_update()
            await db.execute(delete(YDocUpdate).where(YDocUpdate.id.in_([r.id for r in rows])))
            db.add(YDocUpdate(page_id=self._page_id, data=merged))
            await db.commit()
            self.log.info("compacted %d y-updates for page %s", len(rows), self.path)

    async def read(self) -> AsyncIterator[tuple[bytes, bytes, float]]:
        async with SessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(YDocUpdate)
                        .where(YDocUpdate.page_id == self._page_id)
                        .order_by(YDocUpdate.id)
                    )
                )
                .scalars()
                .all()
            )
        for row in rows:
            yield row.data, b"", row.ts.timestamp()


class LoreWebsocketServer(WebsocketServer):
    """WebsocketServer whose rooms persist to Postgres and hydrate from the log
    before accepting synchronization."""

    async def get_room(self, name: str) -> YRoom:
        if name not in self.rooms:
            ystore = PostgresYStore(name, log=self.log)
            room = YRoom(
                ready=False, ystore=ystore, exception_handler=self.exception_handler, log=self.log
            )
            self.rooms[name] = room
            await self.start_room(room)
            await ystore.apply_updates(room.ydoc)
            room.ready = True
            return room
        room = self.rooms[name]
        await self.start_room(room)
        return room


def make_server() -> LoreWebsocketServer:
    return LoreWebsocketServer(exception_handler=exception_logger)


class FastAPIWebsocket(Channel):
    """Adapts a Starlette/FastAPI WebSocket to pycrdt's Channel protocol.
    `path` carries the ROOM NAME (the page uuid), not the URL path."""

    def __init__(self, websocket: WebSocket, path: str):
        self._websocket = websocket
        self._path = path
        self._send_lock = Lock()

    @property
    def path(self) -> str:
        return self._path

    def __aiter__(self) -> "FastAPIWebsocket":
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self.recv()
        except Exception:
            raise StopAsyncIteration()

    async def send(self, message: bytes) -> None:
        async with self._send_lock:
            await self._websocket.send_bytes(message)

    async def recv(self) -> bytes:
        return bytes(await self._websocket.receive_bytes())


# y-protocol message tags (first byte = message type, second = sync subtype).
_MSG_SYNC = 0
_SYNC_STEP2 = 1
_SYNC_UPDATE = 2


class ReadOnlyWebsocket(FastAPIWebsocket):
    """Viewer connections: document-modifying messages are dropped server-side.
    Sync STEP1 (state request) and awareness pass through, so viewers see live
    edits and cursors but cannot write, whatever their client claims."""

    async def __anext__(self) -> bytes:
        while True:
            message = await super().__anext__()
            if (
                len(message) >= 2
                and message[0] == _MSG_SYNC
                and message[1] in (_SYNC_STEP2, _SYNC_UPDATE)
            ):
                continue  # swallow write attempts
            return message
