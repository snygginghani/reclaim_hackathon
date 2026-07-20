import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select

from ..deps import CurrentUser, DbSession, require_membership
from ..models import Favorite, Page
from ..schemas import FavoriteOut, PageCreate, PageMove, PageOut, PageUpdate

router = APIRouter(prefix="/api/pages", tags=["pages"])

POSITION_GAP = 1024.0


async def _get_page_checked(
    db, page_id: uuid.UUID, user_id: uuid.UUID, min_role: str = "viewer"
) -> Page:
    page = await db.get(Page, page_id)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    await require_membership(db, page.workspace_id, user_id, min_role)
    return page


async def _next_position(db, workspace_id: uuid.UUID, parent_id: uuid.UUID | None) -> float:
    current_max = (
        await db.execute(
            select(func.max(Page.position)).where(
                Page.workspace_id == workspace_id,
                Page.parent_id == parent_id,
                Page.deleted_at.is_(None),
            )
        )
    ).scalar()
    return (current_max or 0.0) + POSITION_GAP


@router.post("", response_model=PageOut, status_code=status.HTTP_201_CREATED)
async def create_page(body: PageCreate, user: CurrentUser, db: DbSession) -> Page:
    await require_membership(db, body.workspace_id, user.id, min_role="editor")
    if body.parent_id is not None:
        parent = await db.get(Page, body.parent_id)
        if parent is None or parent.workspace_id != body.workspace_id or parent.deleted_at:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid parent page")
    page = Page(
        workspace_id=body.workspace_id,
        parent_id=body.parent_id,
        title=body.title,
        position=await _next_position(db, body.workspace_id, body.parent_id),
        created_by=user.id,
    )
    db.add(page)
    await db.commit()
    return page


@router.get("", response_model=list[PageOut])
async def list_pages(
    workspace_id: uuid.UUID, user: CurrentUser, db: DbSession, trashed: bool = False
) -> list[Page]:
    """Flat list of the workspace's pages; the client assembles the tree."""
    await require_membership(db, workspace_id, user.id)
    cond = Page.deleted_at.is_not(None) if trashed else Page.deleted_at.is_(None)
    rows = (
        await db.execute(
            select(Page)
            .where(Page.workspace_id == workspace_id, cond)
            .order_by(Page.position, Page.created_at)
        )
    ).scalars()
    return list(rows)


@router.get("/{page_id}", response_model=PageOut)
async def get_page(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Page:
    return await _get_page_checked(db, page_id, user.id)


@router.patch("/{page_id}", response_model=PageOut)
async def update_page(
    page_id: uuid.UUID, body: PageUpdate, user: CurrentUser, db: DbSession
) -> Page:
    page = await _get_page_checked(db, page_id, user.id, min_role="editor")
    if body.title is not None:
        page.title = body.title
    if body.icon is not None:
        page.icon = body.icon or None  # "" clears the icon
    await db.commit()
    return page


@router.post("/{page_id}/move", response_model=PageOut)
async def move_page(page_id: uuid.UUID, body: PageMove, user: CurrentUser, db: DbSession) -> Page:
    page = await _get_page_checked(db, page_id, user.id, min_role="editor")

    # A page cannot become a child of itself or of its own descendant.
    if body.parent_id is not None:
        ancestor_id = body.parent_id
        while ancestor_id is not None:
            if ancestor_id == page.id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot move a page inside itself")
            ancestor = await db.get(Page, ancestor_id)
            if ancestor is None or ancestor.workspace_id != page.workspace_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid target parent")
            ancestor_id = ancestor.parent_id

    siblings = list(
        (
            await db.execute(
                select(Page)
                .where(
                    Page.workspace_id == page.workspace_id,
                    Page.parent_id == body.parent_id,
                    Page.deleted_at.is_(None),
                    Page.id != page.id,
                )
                .order_by(Page.position, Page.created_at)
            )
        ).scalars()
    )

    if body.after_id is None:
        before = siblings[0].position if siblings else POSITION_GAP * 2
        new_pos = before / 2
    else:
        idx = next((i for i, s in enumerate(siblings) if s.id == body.after_id), None)
        if idx is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "after_id is not a sibling")
        after = siblings[idx].position
        nxt = siblings[idx + 1].position if idx + 1 < len(siblings) else after + POSITION_GAP * 2
        new_pos = (after + nxt) / 2

    page.parent_id = body.parent_id
    page.position = new_pos
    await db.commit()
    return page


@router.delete("/{page_id}", response_model=PageOut)
async def trash_page(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Page:
    """Soft delete: the page and its whole subtree go to trash."""
    page = await _get_page_checked(db, page_id, user.id, min_role="editor")
    now = datetime.now(timezone.utc)
    for p in await _subtree(db, page):
        p.deleted_at = now
    await db.commit()
    return page


@router.post("/{page_id}/restore", response_model=PageOut)
async def restore_page(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Page:
    page = await _get_page_checked(db, page_id, user.id, min_role="editor")
    # If an ancestor is still trashed, restore to workspace root.
    if page.parent_id is not None:
        parent = await db.get(Page, page.parent_id)
        if parent is None or parent.deleted_at is not None:
            page.parent_id = None
            page.position = await _next_position(db, page.workspace_id, None)
    for p in await _subtree(db, page):
        p.deleted_at = None
    await db.commit()
    return page


@router.delete("/{page_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def hard_delete_page(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    page = await _get_page_checked(db, page_id, user.id, min_role="editor")
    if page.deleted_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Move the page to trash first")
    await db.execute(delete(Page).where(Page.id == page.id))  # children cascade in the DB
    await db.commit()


async def _subtree(db, root: Page) -> list[Page]:
    """The page plus all descendants (BFS; trees are shallow in practice)."""
    result = [root]
    frontier = [root.id]
    while frontier:
        children = list(
            (await db.execute(select(Page).where(Page.parent_id.in_(frontier)))).scalars()
        )
        result.extend(children)
        frontier = [c.id for c in children]
    return result


# --- favorites ---


@router.get("/favorites/mine", response_model=list[FavoriteOut])
async def list_favorites(
    workspace_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[Favorite]:
    await require_membership(db, workspace_id, user.id)
    rows = (
        await db.execute(
            select(Favorite)
            .join(Page, Page.id == Favorite.page_id)
            .where(
                Favorite.user_id == user.id,
                Page.workspace_id == workspace_id,
                Page.deleted_at.is_(None),
            )
            .order_by(Favorite.position)
        )
    ).scalars()
    return list(rows)


@router.put("/{page_id}/favorite", response_model=FavoriteOut)
async def add_favorite(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Favorite:
    await _get_page_checked(db, page_id, user.id)
    existing = (
        await db.execute(
            select(Favorite).where(Favorite.user_id == user.id, Favorite.page_id == page_id)
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    max_pos = (
        await db.execute(select(func.max(Favorite.position)).where(Favorite.user_id == user.id))
    ).scalar()
    fav = Favorite(user_id=user.id, page_id=page_id, position=(max_pos or 0.0) + POSITION_GAP)
    db.add(fav)
    await db.commit()
    return fav


@router.delete("/{page_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    await db.execute(
        delete(Favorite).where(Favorite.user_id == user.id, Favorite.page_id == page_id)
    )
    await db.commit()
