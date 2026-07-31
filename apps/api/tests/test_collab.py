import uuid

from httpx import AsyncClient
from pycrdt import Doc, Text

from lore_api import collab as collab_module
from lore_api.collab import PostgresYStore

from .test_pages import make_page, make_workspace


async def store_updates(store: PostgresYStore) -> list[bytes]:
    return [update async for update, _meta, _ts in store.read()]


async def test_ystore_roundtrip_converges(user_client: AsyncClient):
    """Updates written by one doc replay into a fresh doc identically."""
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Collab")
    store = PostgresYStore(page["id"])

    doc = Doc()
    doc["content"] = text = Text()
    sub = doc.observe(lambda event: None)  # noqa: F841 — keep the doc live
    with doc.transaction():
        text += "Hello"
    await store.write(doc.get_update())
    with doc.transaction():
        text += ", world"
    await store.write(doc.get_update())

    replica = Doc()
    await store.apply_updates(replica)
    replica["content"] = replica_text = Text()
    assert str(replica_text) == "Hello, world"


async def test_ystore_compaction_preserves_content(user_client: AsyncClient, monkeypatch):
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Compact me")
    store = PostgresYStore(page["id"])
    monkeypatch.setattr(collab_module, "COMPACT_AFTER", 5)

    doc = Doc()
    doc["content"] = text = Text()
    for i in range(8):
        with doc.transaction():
            text += f"w{i} "
        await store.write(doc.get_update())

    remaining = await store_updates(store)
    assert len(remaining) < 8  # the log was squashed at least once

    replica = Doc()
    await store.apply_updates(replica)
    replica["content"] = replica_text = Text()
    assert str(replica_text) == "w0 w1 w2 w3 w4 w5 w6 w7 "


async def test_collab_seed_granted_exactly_once(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Legacy")
    first = await user_client.post(f"/api/pages/{page['id']}/collab-seed")
    second = await user_client.post(f"/api/pages/{page['id']}/collab-seed")
    assert first.json() == {"granted": True}
    assert second.json() == {"granted": False}


async def test_collab_seed_requires_editor(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"username": "seed-owner", "password": "long-enough-1", "name": "O"},
    )
    ws = await make_workspace(client)
    page = await make_page(client, ws, "Doc")
    invite = (await client.post(f"/api/workspaces/{ws}/invites", json={"role": "viewer"})).json()

    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={"username": "seed-viewer", "password": "long-enough-1", "name": "V"},
    )
    await client.post(f"/api/workspaces/invites/{invite['id']}/accept")
    r = await client.post(f"/api/pages/{page['id']}/collab-seed")
    assert r.status_code == 403


def _all_paths(routes) -> list[str]:
    out: list[str] = []
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            out.extend(_all_paths(inner.routes))
        else:
            path = getattr(r, "path", None)
            if path:
                out.append(path)
    return out


async def test_ws_route_registered():
    """The collab WS route is wired into the app (routers may be lazily included)."""
    from lore_api.main import app

    assert "/api/collab/{page_id}" in _all_paths(app.routes)


async def test_readonly_channel_drops_writes():
    from lore_api.collab import ReadOnlyWebsocket

    sent: list[bytes] = []

    class FakeWS:
        def __init__(self, messages: list[bytes]):
            self._messages = list(messages)

        async def receive_bytes(self) -> bytes:
            if not self._messages:
                raise RuntimeError("closed")
            return self._messages.pop(0)

        async def send_bytes(self, data: bytes) -> None:
            sent.append(data)

    step1 = bytes([0, 0, 1, 0])
    step2 = bytes([0, 1, 1, 0])
    update = bytes([0, 2, 1, 0])
    awareness = bytes([1, 1, 0])
    channel = ReadOnlyWebsocket(FakeWS([step1, step2, update, awareness]), str(uuid.uuid4()))

    received = [await anext(channel)]
    received.append(await anext(channel))
    # step2 and update were swallowed: only step1 and awareness came through.
    assert received == [step1, awareness]
