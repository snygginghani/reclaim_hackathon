"""Notion source adapter: walks a Notion workspace and yields normalized
`SourceItem`s for the import engine. All Notion-shape knowledge lives here (or in
`notion/convert.py`); the engine stays source-agnostic.

`prepare()` does the workspace scan; `fetch_items()` fetches each page/database's
blocks lazily as it yields, so the import streams rather than buffering."""

from __future__ import annotations

import uuid
from typing import AsyncIterator

from ...notion import convert
from ...notion.client import NotionClient
from ..base import CellSpec, PropSpec, RowSpec, SourceItem


class NotionAdapter:
    link_scheme = convert.PAGE_LINK_SCHEME
    scan_label = "Scanning your Notion workspace…"

    def __init__(self, token: str) -> None:
        self.client = NotionClient(token)
        self._children: dict[str | None, list[dict]] = {}
        self._roots: list[dict] = []
        self._total = 0

    async def prepare(self) -> int:
        items = await self.client.search()
        self._children = self._plan(items)
        self._roots = self._children.get(None, [])
        # Every tree node we will emit (pages + databases), excluding database rows
        # (they're counted within their database).
        self._total = sum(
            1
            for it in items
            if not (it["object"] == "page" and it.get("parent", {}).get("type") == "database_id")
        )
        return self._total

    def _plan(self, items: list[dict]) -> dict[str | None, list[dict]]:
        """Partition Notion search results into a parent->children tree. Database
        rows (pages parented to a database) are excluded — they come in via the
        database query path, not the page tree."""
        by_id = {it["id"]: it for it in items}
        children: dict[str | None, list[dict]] = {}
        for it in items:
            parent = it.get("parent", {})
            ptype = parent.get("type")
            if it["object"] == "page" and ptype == "database_id":
                continue
            parent_id: str | None = None
            if ptype in ("page_id", "database_id"):
                pid = parent.get(ptype)
                parent_id = pid if pid in by_id else None
            children.setdefault(parent_id, []).append(it)
        # Stable ordering for deterministic output.
        for group in children.values():
            group.sort(key=lambda x: x.get("created_time", ""))
        return children

    async def fetch_items(self) -> AsyncIterator[SourceItem]:
        for item in self._roots:
            async for si in self._walk(item, None):
                yield si

    async def _walk(self, item: dict, parent_source_id: str | None) -> AsyncIterator[SourceItem]:
        if item["object"] == "database":
            # Databases carry their rows inline; they have no page-tree children.
            yield await self._database_item(item, parent_source_id)
        else:
            yield await self._page_item(item, parent_source_id)
            for child in self._children.get(item["id"], []):
                async for si in self._walk(child, item["id"]):
                    yield si

    async def _page_item(self, item: dict, parent_source_id: str | None) -> SourceItem:
        return SourceItem(
            source_id=item["id"],
            title=convert.title_of(item),
            kind="doc",
            parent_source_id=parent_source_id,
            blocks=await self._build_blocks(item["id"]),
        )

    async def _database_item(self, item: dict, parent_source_id: str | None) -> SourceItem:
        title = convert.rich_text_to_plain(item.get("title")) or "Untitled"
        schema: list[PropSpec] = []
        prop_types: dict[str, str] = {}  # notion prop name -> notion type
        for name, cfg in item.get("properties", {}).items():
            ntype = cfg.get("type", "rich_text")
            if ntype == "title":  # the title column becomes the row page title
                continue
            schema.append(
                PropSpec(
                    source_id=name,
                    name=name,
                    type=convert.PROPERTY_TYPE_MAP.get(ntype, "text"),
                    options=convert.options_for(ntype, cfg),
                )
            )
            prop_types[name] = ntype

        rows: list[RowSpec] = []
        for row in await self.client.query_database(item["id"]):
            values: list[CellSpec] = []
            for name, ntype in prop_types.items():
                value = row.get("properties", {}).get(name)
                if not value:
                    continue
                cell = convert.cell_value(ntype, value)
                if cell is None:
                    continue
                values.append(CellSpec(source_id=name, value=cell, is_relation=(ntype == "relation")))
            rows.append(
                RowSpec(
                    source_id=row["id"],
                    title=convert.title_of(row),
                    values=values,
                    blocks=await self._build_blocks(row["id"]),
                )
            )

        return SourceItem(
            source_id=item["id"],
            title=title,
            kind="database",
            parent_source_id=parent_source_id,
            db_schema=schema,
            db_rows=rows,
        )

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

    async def download_asset(self, ref: str) -> bytes:
        return await self.client.download_asset(ref)
