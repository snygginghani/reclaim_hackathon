"""Source-agnostic import engine: consumes a `SourceAdapter` and recreates its
content as native Lore pages/documents/databases, re-hosts assets, then rewrites
internal links and database relations to Lore ids. Emits progress dicts for SSE.

Runs inside a streaming response (after the request handler returns), so it opens
its own DB session."""

from __future__ import annotations

import os
import uuid
from typing import AsyncIterator

from sqlalchemy.orm.attributes import flag_modified

from ..blocks import blocks_to_text
from ..db import SessionLocal
from ..models import DbProperty, DbValue, DbView, Document, Page
from ..storage import save_bytes
from .base import SourceAdapter, SourceItem

POSITION_GAP = 1024.0
_MEDIA_BLOCK_TYPES = {"image", "video", "audio", "file"}


def _progress(stage: str, done: int, total: int, label: str = "") -> dict:
    return {"type": "progress", "stage": stage, "done": done, "total": total, "label": label}


def _guess_ext(url: str) -> str:
    _, ext = os.path.splitext(url.split("?")[0])
    return ext


class ImportEngine:
    def __init__(self, db, adapter: SourceAdapter, workspace_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.adapter = adapter
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.link_scheme = adapter.link_scheme
        # source object id -> created Lore page id (for link/relation resolution).
        self.id_map: dict[str, uuid.UUID] = {}
        # DbValues holding raw source relation ids, fixed up in pass 2.
        self.pending_relations: list[DbValue] = []
        # Documents whose blocks contain {link_scheme} links, fixed up in pass 2.
        self.pending_link_docs: list[Document] = []
        self.created_page_ids: list[uuid.UUID] = []
        # Fractional sibling ordering, tracked per parent.
        self._next_pos_for: dict[uuid.UUID | None, float] = {}
        self.done = 0
        self.total = 0

    # --- pages ---

    def _next_pos(self, parent_id: uuid.UUID | None) -> float:
        pos = self._next_pos_for.get(parent_id, POSITION_GAP)
        self._next_pos_for[parent_id] = pos + POSITION_GAP
        return pos

    async def _add_page(self, title: str, kind: str, parent_id: uuid.UUID | None) -> Page:
        page = Page(
            id=uuid.uuid4(),
            workspace_id=self.workspace_id,
            parent_id=parent_id,
            title=title[:2000],
            kind=kind,
            position=self._next_pos(parent_id),
            created_by=self.user_id,
        )
        self.db.add(page)
        # Flush so dependent rows (Document, DbProperty, DbValue, child pages) can
        # reference this page's id within the same transaction.
        await self.db.flush()
        self.created_page_ids.append(page.id)
        return page

    # --- assets & documents ---

    async def _rehost_media(self, blocks: list[dict]) -> None:
        """Download source-hosted media and replace props.url with a permanent
        local URL. Best-effort: on failure the original url is left in place."""
        for blk in blocks:
            if blk.get("type") in _MEDIA_BLOCK_TYPES:
                url = (blk.get("props") or {}).get("url")
                if url and not url.startswith("/uploads/"):
                    try:
                        data = await self.adapter.download_asset(url)
                        blk["props"]["url"] = save_bytes(data, _guess_ext(url))
                    except Exception:  # noqa: BLE001
                        pass
            for child in blk.get("children") or []:
                await self._rehost_media([child])

    def _has_page_links(self, blocks: list[dict]) -> bool:
        for blk in blocks:
            content = blk.get("content")
            if isinstance(content, list):
                for inline in content:
                    if inline.get("type") == "link" and str(inline.get("href", "")).startswith(
                        self.link_scheme
                    ):
                        return True
            if self._has_page_links(blk.get("children") or []):
                return True
        return False

    async def _write_document(self, page_id: uuid.UUID, blocks: list[dict]) -> None:
        await self._rehost_media(blocks)
        doc = Document(page_id=page_id, blocks=blocks, text_content=blocks_to_text(blocks))
        self.db.add(doc)
        if self._has_page_links(blocks):
            self.pending_link_docs.append(doc)

    # --- emit one item ---

    def _parent_lore_id(self, item: SourceItem) -> uuid.UUID | None:
        return self.id_map.get(item.parent_source_id) if item.parent_source_id else None

    async def _emit_doc(self, item: SourceItem) -> dict:
        page = await self._add_page(item.title, "doc", self._parent_lore_id(item))
        self.id_map[item.source_id] = page.id
        await self._write_document(page.id, item.blocks)
        self.done += 1
        return _progress("pages", self.done, self.total, item.title)

    async def _emit_database(self, item: SourceItem) -> AsyncIterator[dict]:
        db_page = await self._add_page(item.title, "database", self._parent_lore_id(item))
        self.id_map[item.source_id] = db_page.id

        prop_ids: dict[str, uuid.UUID] = {}  # PropSpec.source_id -> Lore property id
        for i, spec in enumerate(item.db_schema or [], start=1):
            prop = DbProperty(
                id=uuid.uuid4(),
                database_id=db_page.id,
                name=spec.name[:120],
                type=spec.type,
                position=i * POSITION_GAP,
                options=spec.options,
            )
            self.db.add(prop)
            prop_ids[spec.source_id] = prop.id
        self.db.add(DbView(database_id=db_page.id, name="Table", type="table", position=POSITION_GAP))
        self.done += 1
        yield _progress("databases", self.done, self.total, item.title)

        rows = item.db_rows or []
        for row in rows:
            row_page = await self._add_page(row.title, "row", db_page.id)
            self.id_map[row.source_id] = row_page.id
            for cell in row.values:
                prop_id = prop_ids.get(cell.source_id)
                if prop_id is None:
                    continue
                dbv = DbValue(row_id=row_page.id, property_id=prop_id, value=cell.value)
                self.db.add(dbv)
                if cell.is_relation:
                    self.pending_relations.append(dbv)
            if row.blocks:
                await self._write_document(row_page.id, row.blocks)
        if rows:
            yield _progress("databases", self.done, self.total, f"{item.title} ({len(rows)} rows)")

    # --- pass 2: resolve internal links & relations ---

    def _resolve_links(self, blocks: list[dict]) -> None:
        for blk in blocks:
            content = blk.get("content")
            if isinstance(content, list):
                for inline in content:
                    href = inline.get("href", "") if inline.get("type") == "link" else ""
                    if href.startswith(self.link_scheme):
                        source_id = href[len(self.link_scheme):]
                        lore_id = self.id_map.get(source_id)
                        inline["href"] = f"/w/{self.workspace_id}/p/{lore_id}" if lore_id else "#"
            self._resolve_links(blk.get("children") or [])

    def _resolve_relations(self) -> None:
        for dbv in self.pending_relations:
            source_ids = dbv.value.get("relation", [])
            lore_ids = [str(self.id_map[sid]) for sid in source_ids if sid in self.id_map]
            dbv.value = {"relation": lore_ids}

    # --- drive ---

    async def run(self) -> AsyncIterator[dict]:
        yield _progress("scanning", 0, 0, self.adapter.scan_label)
        self.total = await self.adapter.prepare()

        async for item in self.adapter.fetch_items():
            if item.kind == "database":
                async for ev in self._emit_database(item):
                    yield ev
            else:
                yield await self._emit_doc(item)

        yield _progress("linking", self.done, self.total, "Resolving internal links…")
        for doc in self.pending_link_docs:
            self._resolve_links(doc.blocks)
            # In-place JSONB edits aren't auto-tracked; mark the column dirty.
            flag_modified(doc, "blocks")
            doc.text_content = blocks_to_text(doc.blocks)
        self._resolve_relations()
        await self.db.commit()


async def run_import(
    workspace_id: uuid.UUID, user_id: uuid.UUID, adapter: SourceAdapter
) -> AsyncIterator[dict]:
    """Run a full migration for `adapter`, yielding progress dicts. On completion,
    yields a final summary carrying the created page ids (so the caller can index
    them)."""
    async with SessionLocal() as db:
        engine = ImportEngine(db, adapter, workspace_id, user_id)
        async for ev in engine.run():
            yield ev
        yield {
            "type": "imported",
            "pages": len(engine.created_page_ids),
            "page_ids": [str(pid) for pid in engine.created_page_ids],
        }
