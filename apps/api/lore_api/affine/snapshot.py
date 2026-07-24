"""Reads an AFFiNE `.affine` workspace export. Despite the extension, a `.affine`
file is a **SQLite database** (AFFiNE desktop's local store), not a zip. Its docs
are Yjs (BlockSuite) binaries which we decode with pycrdt — already a dependency.

Tables used:
  meta(space_id)                -- space_id is the workspace root doc_id
  snapshots(doc_id, data)       -- merged Yjs state per doc
  updates(doc_id, data, created_at)  -- incremental updates (apply after the snapshot)
  blobs(key, data, mime)        -- attachments/images; key == a block's prop:sourceId

The workspace root doc holds `meta.pages` (the page list); each page doc holds a
`blocks` Y.Map of BlockSuite blocks. This module exposes just what the converter
and adapter need; all SQLite/Yjs specifics stay here."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pycrdt import Array, Doc, Map, Text


@dataclass
class PageMeta:
    page_id: str
    title: str


class AffineError(RuntimeError):
    """The uploaded file isn't a readable AFFiNE snapshot."""


class AffineSnapshot:
    def __init__(self, data: bytes) -> None:
        try:
            self._con = sqlite3.connect(":memory:")
            self._con.deserialize(data)
            # Probe for the expected schema so a wrong file fails fast and cleanly.
            self._con.execute("SELECT space_id FROM meta LIMIT 1")
        except sqlite3.DatabaseError as exc:
            raise AffineError("Not a valid .affine SQLite export") from exc
        row = self._con.execute("SELECT space_id FROM meta LIMIT 1").fetchone()
        if not row:
            raise AffineError("No workspace found in the .affine export")
        self._workspace_id = row[0]

    def _load_doc(self, doc_id: str) -> Doc:
        """Full Yjs state for a doc: the snapshot, then every incremental update."""
        doc = Doc()
        snap = self._con.execute(
            "SELECT data FROM snapshots WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        if snap:
            doc.apply_update(snap[0])
        for (upd,) in self._con.execute(
            "SELECT data FROM updates WHERE doc_id = ? ORDER BY created_at", (doc_id,)
        ):
            doc.apply_update(upd)
        return doc

    def pages(self) -> list[PageMeta]:
        meta = self._load_doc(self._workspace_id).get("meta", type=Map).to_py()
        out: list[PageMeta] = []
        for p in meta.get("pages", []) or []:
            if not isinstance(p, dict) or not p.get("id"):
                continue
            if p.get("trash") or p.get("inTrash"):
                continue
            out.append(PageMeta(page_id=p["id"], title=(p.get("title") or "").strip()))
        return out

    def page_blocks(self, page_id: str) -> Map:
        return self._load_doc(page_id).get("blocks", type=Map)

    def blob(self, source_id: str) -> bytes | None:
        row = self._con.execute(
            "SELECT data FROM blobs WHERE key = ?", (source_id,)
        ).fetchone()
        return row[0] if row else None

    def blob_mime(self, source_id: str) -> str | None:
        row = self._con.execute(
            "SELECT mime FROM blobs WHERE key = ?", (source_id,)
        ).fetchone()
        return row[0] if row else None


# --- block accessors (BlockSuite YBlock is a pycrdt Map) ---


def flavour(block: Map) -> str:
    return block["sys:flavour"] if "sys:flavour" in block else ""


def children_ids(block: Map) -> list[str]:
    if "sys:children" in block:
        kids = block["sys:children"]
        if isinstance(kids, Array):
            return list(kids)
    return []


def prop(block: Map, name: str, default=None):
    return block[name] if name in block else default


def text_delta(block: Map) -> list[tuple[str, dict | None]]:
    """prop:text as a list of (text, attributes) runs, or [] when absent."""
    if "prop:text" in block:
        t = block["prop:text"]
        if isinstance(t, Text):
            return t.diff()
    return []
