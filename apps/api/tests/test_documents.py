from httpx import AsyncClient

from .test_pages import make_page, make_workspace

SAMPLE_BLOCKS = [
    {
        "id": "b1",
        "type": "heading",
        "props": {"level": 1},
        "content": [{"type": "text", "text": "Hello", "styles": {}}],
        "children": [],
    },
    {
        "id": "b2",
        "type": "paragraph",
        "props": {},
        "content": [{"type": "text", "text": "World", "styles": {}}],
        "children": [],
    },
]


async def test_content_roundtrip(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Doc")

    # A new page has an empty document, not a 404.
    r = await user_client.get(f"/api/pages/{page['id']}/content")
    assert r.status_code == 200
    assert r.json()["blocks"] == []

    r = await user_client.put(
        f"/api/pages/{page['id']}/content", json={"blocks": SAMPLE_BLOCKS}
    )
    assert r.status_code == 200

    r = await user_client.get(f"/api/pages/{page['id']}/content")
    assert r.json()["blocks"] == SAMPLE_BLOCKS

    # Overwrite persists the latest version.
    r = await user_client.put(f"/api/pages/{page['id']}/content", json={"blocks": []})
    assert (await user_client.get(f"/api/pages/{page['id']}/content")).json()["blocks"] == []


async def test_content_requires_membership(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "doc-owner@example.com", "password": "long-enough-1", "name": "O"},
    )
    ws = await make_workspace(client)
    page = await make_page(client, ws, "Private doc")
    await client.put(f"/api/pages/{page['id']}/content", json={"blocks": SAMPLE_BLOCKS})

    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={"email": "doc-intruder@example.com", "password": "long-enough-1", "name": "I"},
    )
    assert (await client.get(f"/api/pages/{page['id']}/content")).status_code == 404
    assert (
        await client.put(f"/api/pages/{page['id']}/content", json={"blocks": []})
    ).status_code == 404


async def test_content_of_trashed_page_survives_restore(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Doc")
    await user_client.put(f"/api/pages/{page['id']}/content", json={"blocks": SAMPLE_BLOCKS})
    await user_client.delete(f"/api/pages/{page['id']}")
    await user_client.post(f"/api/pages/{page['id']}/restore")
    r = await user_client.get(f"/api/pages/{page['id']}/content")
    assert r.json()["blocks"] == SAMPLE_BLOCKS
