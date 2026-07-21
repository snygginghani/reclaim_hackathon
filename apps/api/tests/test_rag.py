import uuid

from httpx import AsyncClient

from lore_api.ai.chunking import chunk_document
from lore_api.ai.ingest import ingest_page
from lore_api.ai.retrieval import hybrid_search
from lore_api.db import SessionLocal

from .test_pages import make_page, make_workspace


def para(text: str, bid: str) -> dict:
    return {
        "id": bid,
        "type": "paragraph",
        "content": [{"type": "text", "text": text, "styles": {}}],
        "children": [],
    }


def heading(text: str, bid: str) -> dict:
    return {
        "id": bid,
        "type": "heading",
        "props": {"level": 1},
        "content": [{"type": "text", "text": text, "styles": {}}],
        "children": [],
    }


def test_chunking_tracks_headings_and_block_ids():
    blocks = [
        heading("Budget", "h1"),
        para("The Q3 budget is forty thousand dollars.", "b1"),
        heading("Team", "h2"),
        para("Ada leads engineering.", "b2"),
    ]
    chunks = chunk_document(blocks)
    assert chunks
    joined = " ".join(c.text for c in chunks)
    assert "forty thousand" in joined and "Ada leads" in joined
    all_ids = [b for c in chunks for b in c.block_ids]
    assert "b1" in all_ids and "b2" in all_ids
    # A chunk carries its section heading for context.
    assert any(c.heading in ("Budget", "Team") for c in chunks)


def test_chunking_splits_long_documents():
    blocks = [para("Sentence number %d about various topics. " % i * 6, f"b{i}") for i in range(40)]
    chunks = chunk_document(blocks)
    assert len(chunks) > 1  # a 40-block doc must produce multiple chunks


def test_chunking_empty_doc():
    assert chunk_document([]) == []


async def test_ingest_and_semantic_retrieval(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    marketing = await make_page(user_client, ws, "Marketing plan")
    engineering = await make_page(user_client, ws, "Engineering notes")
    await user_client.put(
        f"/api/pages/{marketing['id']}/content",
        json={"blocks": [para("Our launch campaign targets small shops through email newsletters and social posts.", "m1")]},
    )
    await user_client.put(
        f"/api/pages/{engineering['id']}/content",
        json={"blocks": [para("The backend stores document vector embeddings in Postgres using the pgvector extension.", "e1")]},
    )
    await ingest_page(uuid.UUID(marketing["id"]))
    await ingest_page(uuid.UUID(engineering["id"]))

    async with SessionLocal() as db:
        # A semantic query with NO shared keywords should still find the eng page.
        hits = await hybrid_search(
            db, uuid.UUID(ws), "where do we keep the AI search index", k=3
        )
    assert hits, "retrieval returned nothing"
    assert hits[0].page_title == "Engineering notes"
    assert hits[0].chunk.block_ids == ["e1"]


async def test_ingest_replaces_and_clears_on_delete(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Doc")
    await user_client.put(
        f"/api/pages/{page['id']}/content",
        json={"blocks": [para("original searchable content here", "x1")]},
    )
    n = await ingest_page(uuid.UUID(page["id"]))
    assert n == 1

    # Rewrite -> old chunks replaced.
    await user_client.put(
        f"/api/pages/{page['id']}/content",
        json={"blocks": [para("completely different words now", "x2")]},
    )
    await ingest_page(uuid.UUID(page["id"]))
    async with SessionLocal() as db:
        hits = await hybrid_search(db, uuid.UUID(ws), "original searchable content", k=5)
    assert all(h.chunk.block_ids != ["x1"] for h in hits)

    # Trash -> chunks cleared.
    await user_client.delete(f"/api/pages/{page['id']}")
    assert await ingest_page(uuid.UUID(page["id"])) == 0
