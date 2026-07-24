"""AFFiNE migration endpoint: upload a `.affine` workspace export (a SQLite
snapshot of BlockSuite Yjs docs) and stream the import as SSE.

Like Obsidian, there's no OAuth and no stored connection — the file is uploaded,
imported through the shared engine via an `AffineAdapter`, and nothing persists."""

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from ..affine.snapshot import AffineError
from ..ai.ingest import ingest_page
from ..deps import CurrentUser, DbSession, require_membership
from ..migrate.adapters.affine import AffineAdapter
from ..migrate.engine import run_import
from ..migrate.oauth import sse

router = APIRouter(prefix="/api/affine", tags=["affine"])

# 200 MB ceiling — an AFFiNE workspace with embedded blobs can be sizeable.
MAX_SNAPSHOT_BYTES = 200 * 1024 * 1024


@router.post("/import")
async def start_import(
    user: CurrentUser,
    db: DbSession,
    workspace_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> StreamingResponse:
    await require_membership(db, workspace_id, user.id, min_role="editor")
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Snapshot is too large")
    try:
        adapter = AffineAdapter(data)
    except AffineError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That doesn’t look like a .affine export")
    user_id = user.id

    async def stream():
        page_ids: list[str] = []
        try:
            async for ev in run_import(workspace_id, user_id, adapter):
                if ev.get("type") == "imported":
                    page_ids = ev.get("page_ids", [])
                yield sse(ev)
        except Exception as exc:  # noqa: BLE001
            yield sse({"type": "error", "error": str(exc)})
            return

        for pid in page_ids:
            try:
                await ingest_page(uuid.UUID(pid))
            except Exception:  # noqa: BLE001
                pass
        yield sse({"type": "done", "pages": len(page_ids)})

    return StreamingResponse(stream(), media_type="text/event-stream")
