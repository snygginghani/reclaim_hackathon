"""End-to-end AFFiNE import: assemble a real `.affine`-shaped SQLite snapshot in
memory (BlockSuite Yjs docs encoded with pycrdt), POST it as multipart, and assert
pages, cross-doc link resolution, and image blob re-host."""

import sqlite3

import pytest
from httpx import AsyncClient
from pycrdt import Array, Doc, Map, Text

from .test_pages import make_workspace

WS_ID = "WS1"


def _page_doc(content: list[dict]) -> bytes:
    """A page's Yjs doc: affine:page -> affine:note(displayMode both) -> content."""
    doc = Doc()
    blocks = doc.get("blocks", type=Map)

    def add(bid, flavour, **props):
        m = Map()
        blocks[bid] = m
        m["sys:id"] = bid
        m["sys:flavour"] = flavour
        children = props.pop("children", None)
        if children is not None:
            m["sys:children"] = Array(children)
        text = props.pop("text", None)
        for k, v in props.items():
            m[f"prop:{k}"] = v
        if text is not None:
            m["prop:text"] = Text(text)

    add("root", "affine:page", children=["note"], title="")
    add("note", "affine:note", displayMode="both", children=[c["id"] for c in content])
    for c in content:
        add(c.pop("id"), c.pop("flavour"), **c)
    return doc.get_update()


def _ws_doc(pages: list[tuple[str, str]]) -> bytes:
    doc = Doc()
    meta = doc.get("meta", type=Map)
    meta["name"] = "Test Workspace"
    meta["pages"] = Array([Map({"id": pid, "title": title}) for pid, title in pages])
    return doc.get_update()


def _affine_bytes() -> bytes:
    con = sqlite3.connect(":memory:")
    con.executescript(
        """
        CREATE TABLE meta (space_id VARCHAR PRIMARY KEY NOT NULL);
        CREATE TABLE snapshots (doc_id VARCHAR PRIMARY KEY NOT NULL, data BLOB NOT NULL);
        CREATE TABLE updates (doc_id VARCHAR NOT NULL, created_at INTEGER NOT NULL DEFAULT 0,
                              data BLOB NOT NULL, PRIMARY KEY (doc_id, created_at));
        CREATE TABLE blobs (key VARCHAR PRIMARY KEY NOT NULL, data BLOB NOT NULL, mime VARCHAR NOT NULL);
        """
    )
    con.execute("INSERT INTO meta VALUES (?)", (WS_ID,))
    con.execute("INSERT INTO snapshots VALUES (?, ?)",
                (WS_ID, _ws_doc([("home", "Home"), ("other", "Other")])))
    home = _page_doc([
        {"id": "p1", "flavour": "affine:paragraph", "type": "text", "text": "Home intro"},
        {"id": "img", "flavour": "affine:image", "sourceId": "BLOBKEY"},
        {"id": "ld", "flavour": "affine:embed-linked-doc", "pageId": "other"},
    ])
    other = _page_doc([
        {"id": "p2", "flavour": "affine:paragraph", "type": "text", "text": "Other body"},
    ])
    con.execute("INSERT INTO snapshots VALUES (?, ?)", ("home", home))
    con.execute("INSERT INTO snapshots VALUES (?, ?)", ("other", other))
    con.execute("INSERT INTO blobs VALUES (?, ?, ?)", ("BLOBKEY", b"\x89PNG-bytes", "image/png"))
    data = bytes(con.serialize())
    con.close()
    return data


def _sse_events(text: str) -> list[dict]:
    import json
    return [json.loads(l.strip()[5:].strip()) for l in text.splitlines()
            if l.strip().startswith("data:")]


@pytest.fixture(autouse=True)
def _patch_affine(monkeypatch):
    import lore_api.migrate.engine as engine
    import lore_api.routers.affine as router

    monkeypatch.setattr(engine, "save_bytes", lambda data, ext=None: "/uploads/fake.png")

    async def fake_ingest(page_id) -> None:
        return None

    monkeypatch.setattr(router, "ingest_page", fake_ingest)


async def _import(client: AsyncClient, ws: str, data: bytes):
    return await client.post(
        "/api/affine/import",
        data={"workspace_id": ws},
        files={"file": ("workspace.affine", data, "application/octet-stream")},
    )


async def test_full_import(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await _import(user_client, ws, _affine_bytes())
    assert r.status_code == 200, r.text
    events = _sse_events(r.text)
    done = [e for e in events if e["type"] == "done"]
    assert done and done[0]["pages"] == 2, events

    pages = (await user_client.get("/api/pages", params={"workspace_id": ws})).json()
    by_title = {p["title"]: p for p in pages}
    assert {"Home", "Other"} <= set(by_title)

    # Home body: linked-doc rewired to Other, and the image blob re-hosted.
    home = (await user_client.get(f"/api/pages/{by_title['Home']['id']}/content")).json()
    blocks = home["blocks"]
    img = next(b for b in blocks if b["type"] == "image")
    assert img["props"]["url"] == "/uploads/fake.png"
    link = next(i for b in blocks if isinstance(b.get("content"), list)
                for i in b["content"] if i.get("type") == "link")
    assert link["href"] == f"/w/{ws}/p/{by_title['Other']['id']}"


async def test_rejects_non_affine(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await _import(user_client, ws, b"not a sqlite database at all")
    assert r.status_code == 400
