"""Obsidian source adapter: reads a vault (an uploaded .zip of Markdown files +
attachments) and yields normalized `SourceItem`s for the import engine.

There's no OAuth and no database concept — Obsidian is local files. Folders become
container pages; each `.md` file becomes a doc nested under its folder. Wikilinks
`[[Note]]` and image embeds `![[img]]` are resolved by name against the vault."""

from __future__ import annotations

import io
import posixpath
import zipfile
from typing import AsyncIterator

import httpx

from ...obsidian import convert
from ..base import SourceItem

_FOLDER_PREFIX = "folder:"


def _is_hidden(path: str) -> bool:
    return any(part.startswith(".") for part in path.split("/"))


def _strip_common_root(paths: list[str]) -> str:
    """If every file sits under a single top-level directory (a vault folder that
    the zip wrapped everything in), return that prefix to strip; else ""."""
    tops = {p.split("/", 1)[0] for p in paths if "/" in p}
    has_top_level_file = any("/" not in p for p in paths)
    if len(tops) == 1 and not has_top_level_file:
        return next(iter(tops)) + "/"
    return ""


class ObsidianAdapter:
    link_scheme = convert.OBSIDIAN_LINK_SCHEME
    scan_label = "Reading your Obsidian vault…"

    def __init__(self, vault_bytes: bytes) -> None:
        self._zip = zipfile.ZipFile(io.BytesIO(vault_bytes))
        # relpath (display) -> original zip entry name
        self._zip_names: dict[str, str] = {}
        self._notes: list[tuple[str, str]] = []  # (source_id, relpath)
        self._folders: list[str] = []  # folder relpaths, shallow-first
        self._note_by_relpath: dict[str, str] = {}  # lower relpath-no-ext -> source_id
        self._note_by_name: dict[str, str] = {}  # lower basename-no-ext -> source_id
        self._att_by_relpath: dict[str, str] = {}  # lower relpath -> relpath
        self._att_by_name: dict[str, str] = {}  # lower basename -> relpath
        self._total = 0

    async def prepare(self) -> int:
        names = [
            n for n in self._zip.namelist()
            if not n.endswith("/") and not _is_hidden(n)
        ]
        root = _strip_common_root(names)
        folders: set[str] = set()
        for name in names:
            rel = name[len(root):] if root else name
            if not rel:
                continue
            self._zip_names[rel] = name
            directory = posixpath.dirname(rel)
            # register every ancestor folder
            d = directory
            while d:
                folders.add(d)
                d = posixpath.dirname(d)

            if rel.lower().endswith(".md"):
                source_id = rel[:-3]  # relpath without extension
                self._notes.append((source_id, rel))
                self._note_by_relpath[source_id.lower()] = source_id
                self._note_by_name[posixpath.basename(source_id).lower()] = source_id
            else:
                self._att_by_relpath[rel.lower()] = rel
                self._att_by_name[posixpath.basename(rel).lower()] = rel

        self._folders = sorted(folders, key=lambda d: (d.count("/"), d))
        self._total = len(self._folders) + len(self._notes)
        return self._total

    async def fetch_items(self) -> AsyncIterator[SourceItem]:
        # Folder containers first, shallow-first, so each parent exists before its
        # children (subfolders and notes) are created.
        for folder in self._folders:
            parent = posixpath.dirname(folder)
            yield SourceItem(
                source_id=f"{_FOLDER_PREFIX}{folder}",
                title=posixpath.basename(folder),
                kind="doc",
                parent_source_id=f"{_FOLDER_PREFIX}{parent}" if parent else None,
                blocks=[],
            )
        for source_id, rel in self._notes:
            yield self._note_item(source_id, rel)

    def _note_item(self, source_id: str, rel: str) -> SourceItem:
        text = self._zip.read(self._zip_names[rel]).decode("utf-8", errors="replace")
        blocks = convert.markdown_to_blocks(
            text, resolve_link=self._resolve_link, resolve_embed=self._resolve_embed
        )
        directory = posixpath.dirname(rel)
        return SourceItem(
            source_id=source_id,
            title=posixpath.basename(source_id),
            kind="doc",
            parent_source_id=f"{_FOLDER_PREFIX}{directory}" if directory else None,
            blocks=blocks,
        )

    def _resolve_link(self, target: str) -> str:
        key = target.strip()
        if key.lower().endswith(".md"):
            key = key[:-3]
        match = self._note_by_relpath.get(key.lower()) or self._note_by_name.get(
            posixpath.basename(key).lower()
        )
        return f"{convert.OBSIDIAN_LINK_SCHEME}{match if match else key}"

    def _resolve_embed(self, target: str) -> str | None:
        key = target.strip().split("|", 1)[0].strip()
        match = self._att_by_relpath.get(key.lower()) or self._att_by_name.get(
            posixpath.basename(key).lower()
        )
        return f"{convert.ATTACHMENT_REF}{match}" if match else None

    async def download_asset(self, ref: str) -> bytes:
        if ref.startswith(convert.ATTACHMENT_REF):
            rel = ref[len(convert.ATTACHMENT_REF):]
            name = self._zip_names.get(rel)
            if not name:
                raise FileNotFoundError(ref)
            return self._zip.read(name)
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0),
                                     follow_redirects=True) as client:
            resp = await client.get(ref)
        if resp.status_code != 200:
            raise RuntimeError(f"asset download failed: {resp.status_code}")
        return resp.content
