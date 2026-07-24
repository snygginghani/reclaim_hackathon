"""AFFiNE source adapter: decodes an uploaded `.affine` workspace snapshot (a
SQLite DB of BlockSuite Yjs docs) and yields normalized `SourceItem`s.

No OAuth and no database concept — the file is uploaded and imported. V1 imports
pages flat; the edgeless canvas, native databases, and folder hierarchy are
deferred (see affine/convert.py). Image/attachment blobs are re-hosted from the
snapshot's blob table."""

from __future__ import annotations

import mimetypes
from typing import AsyncIterator

import httpx

from ...affine import convert
from ...affine.snapshot import AffineSnapshot
from ..base import SourceItem


class AffineAdapter:
    link_scheme = convert.AFFINE_LINK_SCHEME
    scan_label = "Reading your AFFiNE workspace…"

    def __init__(self, data: bytes) -> None:
        self._snap = AffineSnapshot(data)
        self._pages = self._snap.pages()
        self._titles = {p.page_id: (p.title or "Untitled") for p in self._pages}

    async def prepare(self) -> int:
        return len(self._pages)

    async def fetch_items(self) -> AsyncIterator[SourceItem]:
        for page in self._pages:
            blocks = convert.page_to_blocks(self._snap.page_blocks(page.page_id), self._titles)
            self._annotate_media(blocks)
            yield SourceItem(
                source_id=page.page_id,
                title=page.title or "Untitled",
                kind="doc",
                parent_source_id=None,
                blocks=blocks,
            )

    def _annotate_media(self, blocks: list[dict]) -> None:
        """Append a file extension (derived from the blob's mime) to each
        `affine-blob:{sourceId}` ref so the engine re-hosts it with a real
        extension and the image renders."""
        for blk in blocks:
            if blk.get("type") in ("image", "file", "video", "audio"):
                url = (blk.get("props") or {}).get("url", "")
                if url.startswith(convert.ATTACHMENT_REF):
                    source_id = url[len(convert.ATTACHMENT_REF):]
                    mime = self._snap.blob_mime(source_id)
                    ext = mimetypes.guess_extension(mime) if mime else None
                    if ext:
                        blk["props"]["url"] = f"{url}{ext}"
            self._annotate_media(blk.get("children") or [])

    async def download_asset(self, ref: str) -> bytes:
        if ref.startswith(convert.ATTACHMENT_REF):
            source_id = ref[len(convert.ATTACHMENT_REF):].rsplit(".", 1)[0]
            data = self._snap.blob(source_id)
            if data is None:
                raise FileNotFoundError(ref)
            return data
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0),
                                     follow_redirects=True) as client:
            resp = await client.get(ref)
        if resp.status_code != 200:
            raise RuntimeError(f"asset download failed: {resp.status_code}")
        return resp.content
