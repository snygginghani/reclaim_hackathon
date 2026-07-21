import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text as sql

from ..deps import CurrentUser, DbSession, require_membership

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchHit(BaseModel):
    page_id: uuid.UUID
    title: str
    icon: str | None
    kind: str
    parent_id: uuid.UUID | None
    # Snippet with [[match]] markers around hits (safe to render after splitting).
    snippet: str | None


# FTS over title + extracted document text, with an ILIKE fallback so prefix
# typing ("data" -> "database") hits before a full lexeme exists. Semantic
# (pgvector) fuses into this endpoint in the RAG phase via RRF.
SEARCH_SQL = sql("""
WITH q AS (
    SELECT websearch_to_tsquery('english', :query) AS tsq, :like AS like_pat
)
SELECT p.id AS page_id, p.title, p.icon, p.kind, p.parent_id,
       CASE
         WHEN d.text_content IS NOT NULL AND d.text_content != ''
              AND to_tsvector('english', d.text_content) @@ (SELECT tsq FROM q)
         THEN ts_headline('english', d.text_content, (SELECT tsq FROM q),
                          'StartSel=[[, StopSel=]], MaxWords=18, MinWords=8')
         ELSE NULL
       END AS snippet,
       ts_rank(to_tsvector('english', p.title || ' ' || coalesce(d.text_content, '')),
               (SELECT tsq FROM q)) AS rank,
       (p.title ILIKE (SELECT like_pat FROM q)) AS title_hit
FROM pages p
LEFT JOIN documents d ON d.page_id = p.id
WHERE p.workspace_id = :workspace_id
  AND p.deleted_at IS NULL
  AND (
    to_tsvector('english', p.title || ' ' || coalesce(d.text_content, '')) @@ (SELECT tsq FROM q)
    OR p.title ILIKE (SELECT like_pat FROM q)
  )
ORDER BY title_hit DESC, rank DESC, p.updated_at DESC
LIMIT 20
""")


@router.get("", response_model=list[SearchHit])
async def search(
    workspace_id: uuid.UUID, q: str, user: CurrentUser, db: DbSession
) -> list[SearchHit]:
    await require_membership(db, workspace_id, user.id)
    q = q.strip()
    if not q:
        return []
    rows = (
        await db.execute(
            SEARCH_SQL, {"workspace_id": str(workspace_id), "query": q, "like": f"%{q}%"}
        )
    ).mappings()
    return [
        SearchHit(
            page_id=r["page_id"],
            title=r["title"],
            icon=r["icon"],
            kind=r["kind"],
            parent_id=r["parent_id"],
            snippet=r["snippet"],
        )
        for r in rows
    ]
