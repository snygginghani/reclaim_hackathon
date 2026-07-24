"""End-to-end Confluence import against the DB, driven by a scripted fake client
(no network). Also asserts the connection is deleted on success (self-revoke
equivalent — Atlassian has no revoke endpoint)."""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from lore_api.ai.crypto import encrypt_secret
from lore_api.db import SessionLocal
from lore_api.models import ConfluenceConnection, WorkspaceMember

from .test_pages import make_workspace

SPACE, HOME, CHILD = "S1", "101", "102"


def _adf(*content) -> dict:
    return {"atlas_doc_format": {"value": json.dumps({"type": "doc", "content": list(content)})}}


def _p(*inline) -> dict:
    return {"type": "paragraph", "content": list(inline)}


class FakeConfluenceClient:
    """Implements the surface the adapter uses. Constructed as ConfluenceClient(token, cloud_id)."""

    def __init__(self, token: str, cloud_id: str) -> None:
        self.token = token
        self.cloud_id = cloud_id

    async def list_spaces(self) -> list[dict]:
        return [{"id": SPACE, "key": "ENG", "name": "Engineering"}]

    async def list_pages(self, space_id: str) -> list[dict]:
        home_link = {"type": "link", "attrs": {
            "href": f"https://acme.atlassian.net/wiki/spaces/ENG/pages/{CHILD}/Child"}}
        return [
            {"id": HOME, "title": "Home", "parentId": None, "spaceId": SPACE,
             "body": _adf(
                 {"type": "heading", "attrs": {"level": 2},
                  "content": [{"type": "text", "text": "Welcome"}]},
                 _p({"type": "text", "text": "See ", }, {"type": "text", "text": "Child", "marks": [home_link]}),
                 {"type": "mediaSingle", "content": [
                     {"type": "media", "attrs": {"type": "file", "id": "F1", "alt": "pic"}}]},
             )},
            {"id": CHILD, "title": "Child", "parentId": HOME, "spaceId": SPACE,
             "body": _adf(
                 {"type": "taskList", "content": [
                     {"type": "taskItem", "attrs": {"state": "DONE"},
                      "content": [{"type": "text", "text": "ship it"}]}]},
             )},
        ]

    async def list_attachments(self, page_id: str) -> list[dict]:
        if page_id == HOME:
            return [{"fileId": "F1", "id": "att1",
                     "downloadLink": "/download/attachments/101/pic.png", "title": "pic.png"}]
        return []

    async def download_attachment(self, download_link: str) -> bytes:
        return b"fake-image-bytes"


async def _seed_connection(workspace_id: str) -> uuid.UUID:
    async with SessionLocal() as db:
        member = (
            await db.execute(
                select(WorkspaceMember).where(WorkspaceMember.workspace_id == uuid.UUID(workspace_id))
            )
        ).scalars().first()
        user_id = member.user_id
        db.add(ConfluenceConnection(
            workspace_id=uuid.UUID(workspace_id),
            user_id=user_id,
            token_encrypted=encrypt_secret("fake-token"),
            cloud_id="cloud-123",
            site_name="Acme Wiki",
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
def _patch_confluence(monkeypatch):
    import lore_api.migrate.adapters.confluence as confluence_adapter
    import lore_api.migrate.engine as engine
    import lore_api.routers.confluence as router

    monkeypatch.setattr(confluence_adapter, "ConfluenceClient", FakeConfluenceClient)
    monkeypatch.setattr(engine, "save_bytes", lambda data, ext=None: "/uploads/fake.png")

    async def fake_ingest(page_id) -> None:
        return None

    monkeypatch.setattr(router, "ingest_page", fake_ingest)


async def test_full_migration(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    await _seed_connection(ws)

    st = (await user_client.get("/api/confluence/status", params={"workspace_id": ws})).json()
    assert st["connected"] is True and st["site_name"] == "Acme Wiki"

    r = await user_client.post("/api/confluence/import", json={"workspace_id": ws})
    assert r.status_code == 200, r.text
    events = _sse_events(r.text)
    done = [e for e in events if e["type"] == "done"]
    assert done and done[0]["revoked"] is True, events

    # Connection deleted after a successful import (self-revoke equivalent).
    st2 = (await user_client.get("/api/confluence/status", params={"workspace_id": ws})).json()
    assert st2["connected"] is False

    # Space became a container page; pages nested by their Confluence hierarchy.
    pages = (await user_client.get("/api/pages", params={"workspace_id": ws})).json()
    by_title = {p["title"]: p for p in pages}
    assert {"Engineering", "Home", "Child"} <= set(by_title)
    assert by_title["Home"]["parent_id"] == by_title["Engineering"]["id"]
    assert by_title["Child"]["parent_id"] == by_title["Home"]["id"]

    # Home body: image re-hosted, and the internal page link resolved to Child.
    home_doc = (await user_client.get(f"/api/pages/{by_title['Home']['id']}/content")).json()
    blocks = home_doc["blocks"]
    img = next(b for b in blocks if b["type"] == "image")
    assert img["props"]["url"] == "/uploads/fake.png"
    para = next(b for b in blocks if b["type"] == "paragraph")
    link = next(i for i in para["content"] if i.get("type") == "link")
    assert link["href"] == f"/w/{ws}/p/{by_title['Child']['id']}"

    # Child body carried its task item over as a checklist.
    child_doc = (await user_client.get(f"/api/pages/{by_title['Child']['id']}/content")).json()
    assert any(b["type"] == "checkListItem" and b["props"]["checked"] for b in child_doc["blocks"])


async def test_import_requires_connection(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await user_client.post("/api/confluence/import", json={"workspace_id": ws})
    assert r.status_code == 400


async def test_disconnect(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    await _seed_connection(ws)
    r = await user_client.post("/api/confluence/disconnect", params={"workspace_id": ws})
    assert r.status_code == 204
    st = (await user_client.get("/api/confluence/status", params={"workspace_id": ws})).json()
    assert st["connected"] is False
