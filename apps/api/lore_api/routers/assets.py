"""Asset uploads. Backs the editor's image/file blocks and the Notion importer.
Files are stored locally (see storage.py) and served statically at /uploads."""

import os

from fastapi import APIRouter, HTTPException, UploadFile, status

from ..deps import CurrentUser
from ..storage import save_bytes

router = APIRouter(prefix="/api/assets", tags=["assets"])

# 25 MB ceiling — generous for images/PDFs while bounding a single upload.
MAX_ASSET_BYTES = 25 * 1024 * 1024


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_asset(file: UploadFile, user: CurrentUser) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    if len(data) > MAX_ASSET_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")
    _, ext = os.path.splitext(file.filename or "")
    url = save_bytes(data, ext)
    return {"url": url}
