"""Confluence source adapter: walks a Confluence Cloud site and yields normalized
`SourceItem`s for the import engine. All ADF-shape knowledge lives here (or in
`confluence/convert.py`); the engine stays source-agnostic.

Confluence has no database concept, so this adapter only emits `doc` items: one
container page per space, then that space's pages nested by `parentId`.

`prepare()` lists spaces + pages (bodies come inline as ADF); `fetch_items()`
converts each page and resolves its attachments as it yields."""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from ...confluence import convert
from ...confluence.client import ConfluenceClient, ConfluenceError, parse_adf
from ..base import SourceItem

_SPACE_PREFIX = "space:"


class ConfluenceAdapter:
    link_scheme = convert.CONFLUENCE_LINK_SCHEME
    scan_label = "Scanning your Confluence site…"

    def __init__(self, token: str, cloud_id: str) -> None:
        self.client = ConfluenceClient(token, cloud_id)
        self._spaces: list[dict] = []
        self._pages_by_space: dict[str, list[dict]] = {}
        self._page_ids: set[str] = set()
        # media fileId/id -> (downloadLink, filename)
        self._attachments: dict[str, tuple[str, str]] = {}
        self._total = 0

    async def prepare(self) -> int:
        self._spaces = await self.client.list_spaces()
        for space in self._spaces:
            sid = str(space["id"])
            pages = await self.client.list_pages(sid)
            self._pages_by_space[sid] = pages
            self._page_ids.update(str(p["id"]) for p in pages)
        self._total = len(self._spaces) + len(self._page_ids)
        return self._total

    async def fetch_items(self) -> AsyncIterator[SourceItem]:
        for space in self._spaces:
            sid = str(space["id"])
            yield SourceItem(
                source_id=f"{_SPACE_PREFIX}{sid}",
                title=space.get("name") or space.get("key") or "Space",
                kind="doc",
                parent_source_id=None,
                blocks=[],
            )
            for page in self._order_pages(self._pages_by_space.get(sid, []), sid):
                yield await self._page_item(page, sid)

    def _order_pages(self, pages: list[dict], space_id: str) -> list[dict]:
        """Depth-first page order (parents before children) so the engine has the
        parent's Lore id ready. Top-level pages hang off the space container."""
        by_id = {str(p["id"]): p for p in pages}
        children: dict[str, list[dict]] = {}
        for p in pages:
            pid = p.get("parentId")
            key = str(pid) if pid and str(pid) in by_id else f"{_SPACE_PREFIX}{space_id}"
            children.setdefault(key, []).append(p)

        ordered: list[dict] = []

        def walk(key: str) -> None:
            for child in children.get(key, []):
                ordered.append(child)
                walk(str(child["id"]))

        walk(f"{_SPACE_PREFIX}{space_id}")
        return ordered

    async def _page_item(self, page: dict, space_id: str) -> SourceItem:
        page_id = str(page["id"])
        blocks = convert.adf_to_blocks(parse_adf(page.get("body")))
        await self._load_attachments(page_id)
        self._annotate_media(blocks)
        pid = page.get("parentId")
        parent = str(pid) if pid and str(pid) in self._page_ids else f"{_SPACE_PREFIX}{space_id}"
        return SourceItem(
            source_id=page_id,
            title=page.get("title") or "Untitled",
            kind="doc",
            parent_source_id=parent,
            blocks=blocks,
        )

    async def _load_attachments(self, page_id: str) -> None:
        for att in await self.client.list_attachments(page_id):
            link = att.get("downloadLink")
            if not link:
                continue
            filename = att.get("title") or ""
            for key in (att.get("fileId"), att.get("id")):
                if key:
                    self._attachments[str(key)] = (link, filename)

    def _annotate_media(self, blocks: list[dict]) -> None:
        """Append the attachment filename to each `attachment:{id}` ref so the
        engine can derive a file extension when re-hosting."""
        for blk in blocks:
            if blk.get("type") in ("image", "video", "audio", "file"):
                url = (blk.get("props") or {}).get("url", "")
                if url.startswith(convert.ATTACHMENT_REF):
                    file_id = url[len(convert.ATTACHMENT_REF):].split("/", 1)[0]
                    entry = self._attachments.get(file_id)
                    if entry and entry[1]:
                        blk["props"]["url"] = f"{convert.ATTACHMENT_REF}{file_id}/{entry[1]}"
            self._annotate_media(blk.get("children") or [])

    async def download_asset(self, ref: str) -> bytes:
        if ref.startswith(convert.ATTACHMENT_REF):
            file_id = ref[len(convert.ATTACHMENT_REF):].split("/", 1)[0]
            entry = self._attachments.get(file_id)
            if not entry:
                raise ConfluenceError(f"unknown attachment {file_id}")
            return await self.client.download_attachment(entry[0])
        # External media: a direct URL.
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0),
                                     follow_redirects=True) as client:
            resp = await client.get(ref)
        if resp.status_code != 200:
            raise ConfluenceError(f"asset download failed: {resp.status_code}")
        return resp.content
