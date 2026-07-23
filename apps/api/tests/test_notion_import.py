"""End-to-end Notion import against the DB, driven by a scripted fake Notion
client (no network). Also asserts the self-revoke-on-success behavior."""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from lore_api.ai.crypto import encrypt_secret
from lore_api.db import SessionLocal
from lore_api.models import NotionConnection, WorkspaceMember

from .test_pages import make_workspace

# Notion ids used by the fake workspace.
HOME, PROJECTS, DB, ROW_A, ROW_B, TABLE = (f"n-{x}" for x in ("home", "proj", "db", "ra", "rb", "tbl"))


def _text(s: str) -> dict:
    return {"type": "text", "text": {"content": s}, "plain_text": s, "annotations": {}}


def _title_prop(s: str) -> dict:
    return {"type": "title", "title": [_text(s)]}


class FakeNotionClient:
    """Implements the surface the importer uses. Constructed as NotionClient(token)."""

    def __init__(self, token: str) -> None:
        self.token = token

    async def search(self) -> list[dict]:
        return [
            {"id": HOME, "object": "page", "created_time": "1",
             "parent": {"type": "workspace"}, "properties": {"title": _title_prop("Home")}},
            {"id": PROJECTS, "object": "page", "created_time": "2",
             "parent": {"type": "page_id", "page_id": HOME},
             "properties": {"title": _title_prop("Projects")}},
            {"id": DB, "object": "database", "created_time": "3",
             "parent": {"type": "workspace"}, "title": [_text("Tasks")],
             "properties": {
                 "Name": {"id": "t", "type": "title", "title": {}},
                 "Status": {"id": "s", "type": "select",
                            "select": {"options": [
                                {"id": "todo", "name": "To do", "color": "gray"},
                                {"id": "done", "name": "Done", "color": "green"}]}},
                 "Assignee": {"id": "a", "type": "rich_text", "rich_text": {}},
                 "Rel": {"id": "r", "type": "relation", "relation": {"database_id": DB}},
             }},
            # Rows also surface in search; the importer must ignore them here.
            {"id": ROW_A, "object": "page", "created_time": "4",
             "parent": {"type": "database_id", "database_id": DB}, "properties": {}},
            {"id": ROW_B, "object": "page", "created_time": "5",
             "parent": {"type": "database_id", "database_id": DB}, "properties": {}},
        ]

    async def get_block_children(self, block_id: str) -> list[dict]:
        if block_id == HOME:
            return [
                {"id": "b1", "type": "paragraph", "has_children": False,
                 "paragraph": {"rich_text": [
                     {"type": "mention", "mention": {"type": "page", "page": {"id": PROJECTS}},
                      "plain_text": "Projects", "annotations": {}}]}},
                {"id": "b2", "type": "image", "has_children": False,
                 "image": {"type": "file", "file": {"url": "https://s3/notion.png?sig=1"},
                           "caption": []}},
            ]
        if block_id == PROJECTS:
            return [
                {"id": "h1", "type": "heading_1", "has_children": False,
                 "heading_1": {"rich_text": [_text("Roadmap")]}},
                {"id": "t1", "type": "table", "has_children": True, "table": {}},
            ]
        if block_id == TABLE or block_id == "t1":
            return [{"id": "tr1", "type": "table_row",
                     "table_row": {"cells": [[_text("A1")], [_text("B1")]]}}]
        return []

    async def query_database(self, database_id: str) -> list[dict]:
        return [
            {"id": ROW_A, "properties": {
                "Name": _title_prop("Task A"),
                "Status": {"type": "select", "select": {"id": "todo", "name": "To do"}},
                "Assignee": {"type": "rich_text", "rich_text": [_text("Ada")]},
                "Rel": {"type": "relation", "relation": [{"id": PROJECTS}]},
            }},
            {"id": ROW_B, "properties": {
                "Name": _title_prop("Task B"),
                "Status": {"type": "select", "select": {"id": "done", "name": "Done"}},
            }},
        ]

    async def download_asset(self, url: str) -> bytes:
        return b"fake-image-bytes"


async def _seed_connection(workspace_id: str) -> uuid.UUID:
    async with SessionLocal() as db:
        member = (
            await db.execute(
                select(WorkspaceMember).where(WorkspaceMember.workspace_id == uuid.UUID(workspace_id))
            )
        ).scalars().first()
        user_id = member.user_id
        db.add(NotionConnection(
            workspace_id=uuid.UUID(workspace_id),
            user_id=user_id,
            token_encrypted=encrypt_secret("fake-token"),
            notion_workspace_name="Ada's Notion",
        ))
        await db.commit()
        return user_id


def _sse_events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


@pytest.fixture(autouse=True)
def _patch_notion(monkeypatch):
    import lore_api.notion.importer as importer
    import lore_api.routers.notion as router

    monkeypatch.setattr(importer, "NotionClient", FakeNotionClient)
    monkeypatch.setattr(importer, "save_bytes", lambda data, ext=None: "/uploads/fake.png")

    revoked: list[str] = []

    async def fake_revoke(token: str) -> None:
        revoked.append(token)

    async def fake_ingest(page_id) -> None:
        return None

    monkeypatch.setattr(router, "revoke_token", fake_revoke)
    monkeypatch.setattr(router, "ingest_page", fake_ingest)
    return revoked


async def test_full_migration(user_client: AsyncClient, _patch_notion):
    ws = await make_workspace(user_client)
    await _seed_connection(ws)

    # status reflects the seeded connection
    st = (await user_client.get("/api/notion/status", params={"workspace_id": ws})).json()
    assert st["connected"] is True and st["notion_workspace_name"] == "Ada's Notion"

    r = await user_client.post("/api/notion/import", json={"workspace_id": ws})
    assert r.status_code == 200, r.text
    events = _sse_events(r.text)
    done = [e for e in events if e["type"] == "done"]
    assert done and done[0]["revoked"] is True, events

    # Token was revoked and the connection deleted (self-revoke on success).
    assert _patch_notion == ["fake-token"]
    st2 = (await user_client.get("/api/notion/status", params={"workspace_id": ws})).json()
    assert st2["connected"] is False

    # Sidebar pages: Home, Projects, and the Tasks database (rows are excluded).
    pages = (await user_client.get("/api/pages", params={"workspace_id": ws})).json()
    by_title = {p["title"]: p for p in pages}
    assert {"Home", "Projects", "Tasks"} <= set(by_title)
    assert by_title["Projects"]["parent_id"] == by_title["Home"]["id"]
    assert by_title["Tasks"]["kind"] == "database"

    # Home body: image re-hosted, and the page-mention link resolved to Projects.
    home_doc = (await user_client.get(f"/api/pages/{by_title['Home']['id']}/content")).json()
    blocks = home_doc["blocks"]
    img = next(b for b in blocks if b["type"] == "image")
    assert img["props"]["url"] == "/uploads/fake.png"
    para = next(b for b in blocks if b["type"] == "paragraph")
    link = next(i for i in para["content"] if i["type"] == "link")
    assert link["href"] == f"/w/{ws}/p/{by_title['Projects']['id']}"

    # Projects body has a table.
    proj_doc = (await user_client.get(f"/api/pages/{by_title['Projects']['id']}/content")).json()
    assert any(b["type"] == "table" for b in proj_doc["blocks"])

    # Database: title column dropped; Status choices carried over.
    db = (await user_client.get(f"/api/databases/{by_title['Tasks']['id']}")).json()
    props = {p["name"]: p for p in db["properties"]}
    assert set(props) == {"Status", "Assignee", "Rel"}
    assert {c["id"] for c in props["Status"]["options"]["choices"]} == {"todo", "done"}

    # Rows + values, including a relation remapped to the Lore Projects page id.
    rows = (await user_client.get(f"/api/databases/{by_title['Tasks']['id']}/rows")).json()
    rows_by_title = {row["title"]: row for row in rows}
    assert set(rows_by_title) == {"Task A", "Task B"}
    a = rows_by_title["Task A"]
    assert a["values"][props["Status"]["id"]] == {"select": "todo"}
    assert a["values"][props["Assignee"]["id"]] == {"text": "Ada"}
    assert a["values"][props["Rel"]["id"]] == {"relation": [by_title["Projects"]["id"]]}


async def test_import_requires_connection(user_client: AsyncClient, _patch_notion):
    ws = await make_workspace(user_client)
    r = await user_client.post("/api/notion/import", json={"workspace_id": ws})
    assert r.status_code == 400


async def test_disconnect_revokes(user_client: AsyncClient, _patch_notion):
    ws = await make_workspace(user_client)
    await _seed_connection(ws)
    r = await user_client.post("/api/notion/disconnect", params={"workspace_id": ws})
    assert r.status_code == 204
    assert _patch_notion == ["fake-token"]
    st = (await user_client.get("/api/notion/status", params={"workspace_id": ws})).json()
    assert st["connected"] is False
