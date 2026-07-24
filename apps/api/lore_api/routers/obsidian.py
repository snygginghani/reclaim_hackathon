"""Obsidian migration endpoint: upload a vault (.zip of Markdown + attachments)
and stream the import as SSE.

Unlike Notion/Confluence there's no OAuth and no stored connection — the vault is
uploaded, imported through the shared engine via an `ObsidianAdapter`, and nothing
persists. The uploaded bytes live only for the duration of the request."""

import uuid
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from ..ai.ingest import ingest_page
from ..deps import CurrentUser, DbSession, require_membership
from ..migrate.adapters.obsidian import ObsidianAdapter
from ..migrate.engine import run_import
from ..migrate.oauth import sse

router = APIRouter(prefix="/api/obsidian", tags=["obsidian"])

# 100 MB ceiling — a generous vault while bounding a single upload.
MAX_VAULT_BYTES = 100 * 1024 * 1024


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
    if len(data) > MAX_VAULT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Vault is too large")
    try:
        adapter = ObsidianAdapter(data)
    except zipfile.BadZipFile:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That doesn’t look like a .zip vault")
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
