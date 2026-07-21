"""Hybrid retrieval: pgvector semantic search fused with Postgres FTS via
Reciprocal Rank Fusion. Scoped to a workspace (and optionally a set of pages)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Chunk, Page
from .embeddings import embed_query

RRF_K = 60


@dataclass
class Retrieved:
    chunk: Chunk
    page_title: str


async def hybrid_search(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    query: str,
    page_ids: list[uuid.UUID] | None = None,
    k: int = 8,
    pool: int = 24,
) -> list[Retrieved]:
    query = query.strip()
    if not query:
        return []
    qvec = await embed_query(query)

    scope = [Chunk.workspace_id == workspace_id]
    if page_ids:
        scope.append(Chunk.page_id.in_(page_ids))

    vec_rows = (
        await db.execute(
            select(Chunk).where(*scope).order_by(Chunk.embedding.cosine_distance(qvec)).limit(pool)
        )
    ).scalars().all()

    fts_cond = sqltext(
        "to_tsvector('english', chunks.text) @@ websearch_to_tsquery('english', :q)"
    ).bindparams(q=query)
    fts_rows = (
        await db.execute(select(Chunk).where(*scope).where(fts_cond).limit(pool))
    ).scalars().all()

    # Reciprocal Rank Fusion.
    scores: dict[uuid.UUID, float] = {}
    by_id: dict[uuid.UUID, Chunk] = {}
    for rank, c in enumerate(vec_rows):
        scores[c.id] = scores.get(c.id, 0.0) + 1.0 / (RRF_K + rank)
        by_id[c.id] = c
    for rank, c in enumerate(fts_rows):
        scores[c.id] = scores.get(c.id, 0.0) + 1.0 / (RRF_K + rank)
        by_id[c.id] = c

    top_ids = sorted(scores, key=lambda i: scores[i], reverse=True)[:k]
    top = [by_id[i] for i in top_ids]
    if not top:
        return []

    titles = dict(
        (
            await db.execute(
                select(Page.id, Page.title).where(Page.id.in_({c.page_id for c in top}))
            )
        ).all()
    )
    return [Retrieved(chunk=c, page_title=titles.get(c.page_id) or "Untitled") for c in top]
