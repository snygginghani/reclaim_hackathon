"""Embedding ingestion: keep a page's chunks in sync with its document.
Runs as a background task after a content save, and as a workspace backfill."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from ..db import SessionLocal
from ..models import Chunk, Document, Page
from .chunking import chunk_document
from .embeddings import embed_documents


async def ingest_page(page_id: uuid.UUID) -> int:
    """Replace all chunks for one page from its current document. Returns the
    number of chunks written."""
    async with SessionLocal() as db:
        page = await db.get(Page, page_id)
        await db.execute(delete(Chunk).where(Chunk.page_id == page_id))
        if page is None or page.deleted_at is not None:
            await db.commit()
            return 0
        doc = await db.get(Document, page_id)
        chunks = chunk_document(doc.blocks) if doc else []
        if not chunks:
            await db.commit()
            return 0
        vectors = await embed_documents([c.embed_text for c in chunks])
        for i, (c, vec) in enumerate(zip(chunks, vectors)):
            db.add(
                Chunk(
                    workspace_id=page.workspace_id,
                    page_id=page_id,
                    chunk_index=i,
                    text=c.text,
                    heading=c.heading,
                    block_ids=c.block_ids,
                    embedding=vec,
                )
            )
        await db.commit()
        return len(chunks)


async def backfill_workspace(workspace_id: uuid.UUID) -> int:
    async with SessionLocal() as db:
        page_ids = (
            await db.execute(
                select(Page.id).where(
                    Page.workspace_id == workspace_id, Page.deleted_at.is_(None)
                )
            )
        ).scalars().all()
    total = 0
    for pid in page_ids:
        total += await ingest_page(pid)
    return total
