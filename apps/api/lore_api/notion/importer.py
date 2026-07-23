"""Drives a Notion -> Lore migration: walk the Notion workspace, recreate pages
and databases natively, re-host assets, then rewrite internal links/relations to
Lore ids. Emits progress dicts for SSE. Uses its own DB session (it runs inside a
streaming response, after the request handler returns)."""

from __future__ import annotations

import os
import uuid
from typing import AsyncIterator

from sqlalchemy.orm.attributes import flag_modified

from ..blocks import blocks_to_text
from ..db import SessionLocal
from ..models import DbProperty, DbValue, DbView, Document, Page
from ..storage import save_bytes
from . import convert
from .client import NotionClient

POSITION_GAP = 1024.0
_MEDIA_BLOCK_TYPES = {"image", "video", "audio", "file"}


def _progress(stage: str, done: int, total: int, label: str = "") -> dict:
    return {"type": "progress", "stage": stage, "done": done, "total": total, "label": label}


class _Importer:
    def __init__(self, db, client: NotionClient, workspace_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.client = client
        self.workspace_id = workspace_id
        self.user_id = user_id
        # notion object id -> created Lore page id (for link/relation resolution).
        self.id_map: dict[str, uuid.UUID] = {}
        # DbValues holding raw Notion relation ids, fixed up in pass 2.
        self.pending_relations: list[DbValue] = []
        # (document, ) whose blocks contain notion-page: links, fixed up in pass 2.
        self.pending_link_docs: list[Document] = []
        self.created_page_ids: list[uuid.UUID] = []
        self.done = 0
        self.total = 0

    # --- tree construction ---

    def _plan(self, items: list[dict]) -> tuple[dict[str, dict], dict[str | None, list[dict]]]:
        """Partition Notion search results into a parent->children tree. Database
        rows (pages parented to a database) are excluded — they come in via the
        database query path, not the page tree."""
        by_id = {it["id"]: it for it in items}
        children: dict[str | None, list[dict]] = {}
        for it in items:
            parent = it.get("parent", {})
            ptype = parent.get("type")
            if it["object"] == "page" and ptype == "database_id":
                continue  # a database row, handled by its database
            parent_id: str | None = None
            if ptype in ("page_id", "database_id"):
                pid = parent.get(ptype)
                parent_id = pid if pid in by_id else None
            children.setdefault(parent_id, []).append(it)
        # Stable ordering for deterministic output.
        for group in children.values():
            group.sort(key=lambda x: x.get("created_time", ""))
        return by_id, children

    # --- blocks ---

    async def _build_blocks(self, block_id: str) -> list[dict]:
        out: list[dict] = []
        for blk in await self.client.get_block_children(block_id):
            t = blk.get("type", "")
            if t in convert.FLATTEN_TYPES:
                out.extend(await self._build_blocks(blk["id"]))
                continue
            if t in convert.CHILD_PAGE_TYPES or t in convert.SKIP_TYPES:
                continue  # child pages/databases become tree nodes; skips carry no body
            if t == "table":
                rows = await self.client.get_block_children(blk["id"]) if blk.get("has_children") else []
                row_cells = [r["table_row"]["cells"] for r in rows if r.get("type") == "table_row"]
                out.append(convert.build_table(row_cells))
                continue
            sub = await self._build_blocks(blk["id"]) if blk.get("has_children") else []
            node = convert.convert_block(blk, sub)
            if node:
                out.append(node)
        return out

    async def _rehost_media(self, blocks: list[dict]) -> None:
        """Download Notion-hosted media and replace props.url with a permanent
        local URL. Best-effort: on failure the original url is left in place."""
        for blk in blocks:
            if blk.get("type") in _MEDIA_BLOCK_TYPES:
                url = (blk.get("props") or {}).get("url")
                if url and not url.startswith("/uploads/"):
                    try:
                        data = await self.client.download_asset(url)
                        _, ext = os.path.splitext(url.split("?")[0])
                        blk["props"]["url"] = save_bytes(data, ext)
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
                        convert.PAGE_LINK_SCHEME
                    ):
                        return True
            if self._has_page_links(blk.get("children") or []):
                return True
        return False

    async def _write_document(self, page_id: uuid.UUID, blocks: list[dict]) -> None:
        await self._rehost_media(blocks)
        text = blocks_to_text(blocks)
        doc = Document(page_id=page_id, blocks=blocks, text_content=text)
        self.db.add(doc)
        if self._has_page_links(blocks):
            self.pending_link_docs.append(doc)

    # --- pages & databases ---

    async def _add_page(
        self, title: str, kind: str, parent_id: uuid.UUID | None, position: float
    ) -> Page:
        page = Page(
            id=uuid.uuid4(),
            workspace_id=self.workspace_id,
            parent_id=parent_id,
            title=title[:2000],
            kind=kind,
            position=position,
            created_by=self.user_id,
        )
        self.db.add(page)
        # Flush so dependent rows (Document, DbProperty, DbValue, child pages) can
        # reference this page's id within the same transaction.
        await self.db.flush()
        self.created_page_ids.append(page.id)
        return page

    async def _emit_page(
        self, item: dict, lore_parent: uuid.UUID | None, children_map: dict, position: float
    ) -> AsyncIterator[dict]:
        title = convert.title_of(item)
        page = await self._add_page(title, "doc", lore_parent, position)
        self.id_map[item["id"]] = page.id
        blocks = await self._build_blocks(item["id"])
        await self._write_document(page.id, blocks)
        self.done += 1
        yield _progress("pages", self.done, self.total, title)
        pos = POSITION_GAP
        for child in children_map.get(item["id"], []):
            if child["object"] == "database":
                async for ev in self._emit_database(child, page.id, children_map, pos):
                    yield ev
            else:
                async for ev in self._emit_page(child, page.id, children_map, pos):
                    yield ev
            pos += POSITION_GAP

    async def _emit_database(
        self, item: dict, lore_parent: uuid.UUID | None, children_map: dict, position: float
    ) -> AsyncIterator[dict]:
        title = convert.rich_text_to_plain(item.get("title")) or "Untitled"
        db_page = await self._add_page(title, "database", lore_parent, position)
        self.id_map[item["id"]] = db_page.id

        # One property per Notion schema column (the title column becomes the row
        # page title, so it's not recreated as a property).
        prop_map: dict[str, tuple[uuid.UUID, str]] = {}  # notion prop name -> (lore id, notion type)
        pos = POSITION_GAP
        for name, schema in item.get("properties", {}).items():
            ntype = schema.get("type", "rich_text")
            if ntype == "title":
                continue
            lore_type = convert.PROPERTY_TYPE_MAP.get(ntype, "text")
            prop = DbProperty(
                id=uuid.uuid4(),
                database_id=db_page.id,
                name=name[:120],
                type=lore_type,
                position=pos,
                options=convert.options_for(ntype, schema),
            )
            self.db.add(prop)
            prop_map[name] = (prop.id, ntype)
            pos += POSITION_GAP
        self.db.add(DbView(database_id=db_page.id, name="Table", type="table", position=POSITION_GAP))
        self.done += 1
        yield _progress("databases", self.done, self.total, title)

        # Rows.
        rows = await self.client.query_database(item["id"])
        row_pos = POSITION_GAP
        for row in rows:
            row_title = convert.title_of(row)
            row_page = await self._add_page(row_title, "row", db_page.id, row_pos)
            self.id_map[row["id"]] = row_page.id
            row_pos += POSITION_GAP
            for name, (lore_prop_id, ntype) in prop_map.items():
                value = (row.get("properties", {}).get(name))
                if not value:
                    continue
                cell = convert.cell_value(ntype, value)
                if cell is None:
                    continue
                dbv = DbValue(row_id=row_page.id, property_id=lore_prop_id, value=cell)
                self.db.add(dbv)
                if ntype == "relation":
                    self.pending_relations.append(dbv)
            # A row is a page: import its body too.
            blocks = await self._build_blocks(row["id"])
            if blocks:
                await self._write_document(row_page.id, blocks)
        if rows:
            yield _progress("databases", self.done, self.total, f"{title} ({len(rows)} rows)")

    # --- pass 2: resolve internal links & relations ---

    def _resolve_links(self, blocks: list[dict]) -> None:
        for blk in blocks:
            content = blk.get("content")
            if isinstance(content, list):
                for inline in content:
                    href = inline.get("href", "") if inline.get("type") == "link" else ""
                    if href.startswith(convert.PAGE_LINK_SCHEME):
                        notion_id = href[len(convert.PAGE_LINK_SCHEME):]
                        lore_id = self.id_map.get(notion_id)
                        inline["href"] = (
                            f"/w/{self.workspace_id}/p/{lore_id}" if lore_id else "#"
                        )
            self._resolve_links(blk.get("children") or [])

    def _resolve_relations(self) -> None:
        for dbv in self.pending_relations:
            notion_ids = dbv.value.get("relation", [])
            lore_ids = [str(self.id_map[nid]) for nid in notion_ids if nid in self.id_map]
            dbv.value = {"relation": lore_ids}

    async def run(self) -> AsyncIterator[dict]:
        yield _progress("scanning", 0, 0, "Scanning your Notion workspace…")
        items = await self.client.search()
        _by_id, children_map = self._plan(items)
        roots = children_map.get(None, [])
        # Every tree node we will emit (pages + databases), excluding database rows
        # which are counted within their database.
        self.total = sum(
            1
            for it in items
            if not (it["object"] == "page" and it.get("parent", {}).get("type") == "database_id")
        )

        pos = POSITION_GAP
        for item in roots:
            if item["object"] == "database":
                async for ev in self._emit_database(item, None, children_map, pos):
                    yield ev
            else:
                async for ev in self._emit_page(item, None, children_map, pos):
                    yield ev
            pos += POSITION_GAP

        yield _progress("linking", self.done, self.total, "Resolving internal links…")
        for doc in self.pending_link_docs:
            self._resolve_links(doc.blocks)
            # In-place JSONB edits aren't auto-tracked; mark the column dirty.
            flag_modified(doc, "blocks")
            doc.text_content = blocks_to_text(doc.blocks)
        self._resolve_relations()
        await self.db.commit()


async def import_workspace(
    workspace_id: uuid.UUID, user_id: uuid.UUID, token: str
) -> AsyncIterator[dict]:
    """Run a full migration, yielding progress dicts. On completion, yields a
    final summary carrying the created page ids (so the caller can index them)."""
    async with SessionLocal() as db:
        importer = _Importer(db, NotionClient(token), workspace_id, user_id)
        async for ev in importer.run():
            yield ev
        yield {
            "type": "imported",
            "pages": len(importer.created_page_ids),
            "page_ids": [str(pid) for pid in importer.created_page_ids],
        }
