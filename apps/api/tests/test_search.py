from httpx import AsyncClient

from lore_api.blocks import blocks_to_text

from .test_documents import SAMPLE_BLOCKS
from .test_pages import make_page, make_workspace


def test_blocks_to_text_extracts_nested_content():
    blocks = [
        {
            "type": "heading",
            "content": [{"type": "text", "text": "Quarterly plan", "styles": {}}],
            "children": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Grow ", "styles": {}},
                        {
                            "type": "link",
                            "content": [{"type": "text", "text": "revenue", "styles": {}}],
                        },
                    ],
                    "children": [],
                }
            ],
        }
    ]
    text = blocks_to_text(blocks)
    assert "Quarterly plan" in text
    assert "Grow" in text and "revenue" in text


async def write_doc(client: AsyncClient, page_id: str, sentence: str) -> None:
    blocks = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": sentence, "styles": {}}],
            "children": [],
        }
    ]
    r = await client.put(f"/api/pages/{page_id}/content", json={"blocks": blocks})
    assert r.status_code == 200


async def test_search_finds_titles_and_content(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    keel = await make_page(user_client, ws, "Keelhaul protocol")
    other = await make_page(user_client, ws, "Meeting notes")
    await write_doc(user_client, other["id"], "The zeppelin fleet departs at dawn.")

    r = await user_client.get("/api/search", params={"workspace_id": ws, "q": "keelhaul"})
    assert [h["page_id"] for h in r.json()] == [keel["id"]]

    r = await user_client.get("/api/search", params={"workspace_id": ws, "q": "zeppelin"})
    hits = r.json()
    assert [h["page_id"] for h in hits] == [other["id"]]
    assert "[[" in (hits[0]["snippet"] or "")  # highlighted snippet markers

    # Prefix typing hits titles before a full word is typed.
    r = await user_client.get("/api/search", params={"workspace_id": ws, "q": "keelh"})
    assert any(h["page_id"] == keel["id"] for h in r.json())


async def test_search_excludes_trash_and_other_workspaces(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Vanishing act")
    await user_client.delete(f"/api/pages/{page['id']}")
    r = await user_client.get("/api/search", params={"workspace_id": ws, "q": "vanishing"})
    assert r.json() == []

    ws2 = await make_workspace(user_client, "Second")
    await make_page(user_client, ws2, "Crosstalk check")
    r = await user_client.get("/api/search", params={"workspace_id": ws, "q": "crosstalk"})
    assert r.json() == []


async def test_search_requires_membership(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "search-a@example.com", "password": "long-enough-1", "name": "A"},
    )
    ws = await make_workspace(client)
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={"email": "search-b@example.com", "password": "long-enough-1", "name": "B"},
    )
    r = await client.get("/api/search", params={"workspace_id": ws, "q": "anything"})
    assert r.status_code == 404


async def test_search_empty_query_returns_nothing(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await user_client.get("/api/search", params={"workspace_id": ws, "q": "   "})
    assert r.json() == []


async def test_put_content_updates_search_text(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Doc")
    await user_client.put(f"/api/pages/{page['id']}/content", json={"blocks": SAMPLE_BLOCKS})
    r = await user_client.get("/api/search", params={"workspace_id": ws, "q": "world"})
    assert any(h["page_id"] == page["id"] for h in r.json())
    # Overwriting removes stale hits.
    await write_doc(user_client, page["id"], "completely different now")
    r = await user_client.get("/api/search", params={"workspace_id": ws, "q": "world"})
    assert all(h["page_id"] != page["id"] for h in r.json())