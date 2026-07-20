import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

from ..deps import CurrentUser, DbSession, require_membership
from ..models import DbProperty, DbValue, DbView, Page
from ..routers.pages import POSITION_GAP, _get_page_checked, _next_position
from ..schemas import PageOut

router = APIRouter(prefix="/api/databases", tags=["databases"])

PROPERTY_TYPES = {"text", "number", "select", "multi_select", "date", "checkbox", "url", "relation"}
VIEW_TYPES = {"table", "board", "list", "calendar"}


# --- schemas ---


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PropertyOut(ORM):
    id: uuid.UUID
    name: str
    type: str
    position: float
    options: dict


class ViewOut(ORM):
    id: uuid.UUID
    name: str
    type: str
    position: float
    config: dict


class DatabaseOut(BaseModel):
    page: PageOut
    properties: list[PropertyOut]
    views: list[ViewOut]


class DatabaseCreate(BaseModel):
    workspace_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    title: str = ""


class PropertyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str
    options: dict = {}


class PropertyPatch(BaseModel):
    name: str | None = None
    type: str | None = None
    options: dict | None = None
    position: float | None = None


class ViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str


class ViewPatch(BaseModel):
    name: str | None = None
    config: dict | None = None
    position: float | None = None


class RowCreate(BaseModel):
    title: str = ""
    values: dict[uuid.UUID, dict | None] = {}


class RowOut(ORM):
    id: uuid.UUID
    title: str
    icon: str | None
    position: float
    updated_at: datetime
    values: dict[uuid.UUID, dict]


class ValuesPatch(BaseModel):
    values: dict[uuid.UUID, dict | None]


# --- helpers ---


async def _get_database_checked(db, page_id: uuid.UUID, user_id: uuid.UUID, min_role="viewer") -> Page:
    page = await _get_page_checked(db, page_id, user_id, min_role)
    if page.kind != "database":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a database")
    return page


DEFAULT_STATUS_CHOICES = [
    {"id": "todo", "name": "To do", "color": "#64748B"},
    {"id": "doing", "name": "In progress", "color": "#5E6AD2"},
    {"id": "done", "name": "Done", "color": "#16A34A"},
]


# --- database lifecycle ---


@router.post("", response_model=DatabaseOut, status_code=status.HTTP_201_CREATED)
async def create_database(body: DatabaseCreate, user: CurrentUser, db: DbSession) -> DatabaseOut:
    await require_membership(db, body.workspace_id, user.id, min_role="editor")
    if body.parent_id is not None:
        parent = await db.get(Page, body.parent_id)
        if parent is None or parent.workspace_id != body.workspace_id or parent.deleted_at:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid parent page")
    page = Page(
        workspace_id=body.workspace_id,
        parent_id=body.parent_id,
        title=body.title,
        kind="database",
        position=await _next_position(db, body.workspace_id, body.parent_id),
        created_by=user.id,
    )
    db.add(page)
    await db.flush()
    status_prop = DbProperty(
        database_id=page.id,
        name="Status",
        type="select",
        position=POSITION_GAP,
        options={"choices": DEFAULT_STATUS_CHOICES},
    )
    table_view = DbView(database_id=page.id, name="Table", type="table", position=POSITION_GAP)
    db.add_all([status_prop, table_view])
    await db.commit()
    return DatabaseOut(
        page=PageOut.model_validate(page),
        properties=[PropertyOut.model_validate(status_prop)],
        views=[ViewOut.model_validate(table_view)],
    )


@router.get("/{page_id}", response_model=DatabaseOut)
async def get_database(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> DatabaseOut:
    page = await _get_database_checked(db, page_id, user.id)
    properties = (
        (
            await db.execute(
                select(DbProperty)
                .where(DbProperty.database_id == page_id)
                .order_by(DbProperty.position)
            )
        )
        .scalars()
        .all()
    )
    views = (
        (
            await db.execute(
                select(DbView).where(DbView.database_id == page_id).order_by(DbView.position)
            )
        )
        .scalars()
        .all()
    )
    return DatabaseOut(
        page=PageOut.model_validate(page),
        properties=[PropertyOut.model_validate(p) for p in properties],
        views=[ViewOut.model_validate(v) for v in views],
    )


# --- properties ---


@router.post("/{page_id}/properties", response_model=PropertyOut, status_code=201)
async def create_property(
    page_id: uuid.UUID, body: PropertyCreate, user: CurrentUser, db: DbSession
) -> DbProperty:
    await _get_database_checked(db, page_id, user.id, min_role="editor")
    if body.type not in PROPERTY_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown property type '{body.type}'")
    max_pos = (
        await db.execute(
            select(func.max(DbProperty.position)).where(DbProperty.database_id == page_id)
        )
    ).scalar()
    prop = DbProperty(
        database_id=page_id,
        name=body.name.strip(),
        type=body.type,
        options=body.options,
        position=(max_pos or 0.0) + POSITION_GAP,
    )
    db.add(prop)
    await db.commit()
    return prop


@router.patch("/{page_id}/properties/{prop_id}", response_model=PropertyOut)
async def patch_property(
    page_id: uuid.UUID, prop_id: uuid.UUID, body: PropertyPatch, user: CurrentUser, db: DbSession
) -> DbProperty:
    await _get_database_checked(db, page_id, user.id, min_role="editor")
    prop = await db.get(DbProperty, prop_id)
    if prop is None or prop.database_id != page_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    if body.type is not None:
        if body.type not in PROPERTY_TYPES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown property type '{body.type}'")
        prop.type = body.type
    if body.name is not None:
        prop.name = body.name.strip()
    if body.options is not None:
        prop.options = body.options
    if body.position is not None:
        prop.position = body.position
    await db.commit()
    return prop


@router.delete("/{page_id}/properties/{prop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    page_id: uuid.UUID, prop_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    await _get_database_checked(db, page_id, user.id, min_role="editor")
    prop = await db.get(DbProperty, prop_id)
    if prop is None or prop.database_id != page_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    await db.delete(prop)
    await db.commit()


# --- views ---


@router.post("/{page_id}/views", response_model=ViewOut, status_code=201)
async def create_view(
    page_id: uuid.UUID, body: ViewCreate, user: CurrentUser, db: DbSession
) -> DbView:
    await _get_database_checked(db, page_id, user.id, min_role="editor")
    if body.type not in VIEW_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown view type '{body.type}'")
    max_pos = (
        await db.execute(select(func.max(DbView.position)).where(DbView.database_id == page_id))
    ).scalar()
    view = DbView(
        database_id=page_id,
        name=body.name.strip(),
        type=body.type,
        position=(max_pos or 0.0) + POSITION_GAP,
    )
    db.add(view)
    await db.commit()
    return view


@router.patch("/{page_id}/views/{view_id}", response_model=ViewOut)
async def patch_view(
    page_id: uuid.UUID, view_id: uuid.UUID, body: ViewPatch, user: CurrentUser, db: DbSession
) -> DbView:
    await _get_database_checked(db, page_id, user.id, min_role="editor")
    view = await db.get(DbView, view_id)
    if view is None or view.database_id != page_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "View not found")
    if body.name is not None:
        view.name = body.name.strip()
    if body.config is not None:
        view.config = body.config
    if body.position is not None:
        view.position = body.position
    await db.commit()
    return view


@router.delete("/{page_id}/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    page_id: uuid.UUID, view_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    await _get_database_checked(db, page_id, user.id, min_role="editor")
    count = (
        await db.execute(
            select(func.count()).select_from(DbView).where(DbView.database_id == page_id)
        )
    ).scalar()
    if count is not None and count <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A database needs at least one view")
    view = await db.get(DbView, view_id)
    if view is None or view.database_id != page_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "View not found")
    await db.delete(view)
    await db.commit()


# --- rows ---


async def _validate_values(db, page_id: uuid.UUID, values: dict[uuid.UUID, dict | None]) -> None:
    if not values:
        return
    props = {
        p.id: p
        for p in (
            await db.execute(select(DbProperty).where(DbProperty.database_id == page_id))
        ).scalars()
    }
    for prop_id in values:
        if prop_id not in props:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown property in values")


@router.post("/{page_id}/rows", response_model=RowOut, status_code=201)
async def create_row(
    page_id: uuid.UUID, body: RowCreate, user: CurrentUser, db: DbSession
) -> RowOut:
    await _get_database_checked(db, page_id, user.id, min_role="editor")
    await _validate_values(db, page_id, body.values)
    page = await db.get(Page, page_id)
    row = Page(
        workspace_id=page.workspace_id,
        parent_id=page_id,
        title=body.title,
        kind="row",
        position=await _next_position(db, page.workspace_id, page_id),
        created_by=user.id,
    )
    db.add(row)
    await db.flush()
    stored: dict[uuid.UUID, dict] = {}
    for prop_id, value in body.values.items():
        if value is not None:
            db.add(DbValue(row_id=row.id, property_id=prop_id, value=value))
            stored[prop_id] = value
    await db.commit()
    return RowOut(
        id=row.id,
        title=row.title,
        icon=row.icon,
        position=row.position,
        updated_at=row.updated_at,
        values=stored,
    )


@router.get("/{page_id}/rows", response_model=list[RowOut])
async def list_rows(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[RowOut]:
    await _get_database_checked(db, page_id, user.id)
    rows = (
        (
            await db.execute(
                select(Page)
                .where(Page.parent_id == page_id, Page.kind == "row", Page.deleted_at.is_(None))
                .order_by(Page.position, Page.created_at)
            )
        )
        .scalars()
        .all()
    )
    row_ids = [r.id for r in rows]
    values: dict[uuid.UUID, dict[uuid.UUID, dict]] = {rid: {} for rid in row_ids}
    if row_ids:
        for v in (
            await db.execute(select(DbValue).where(DbValue.row_id.in_(row_ids)))
        ).scalars():
            values[v.row_id][v.property_id] = v.value
    return [
        RowOut(
            id=r.id,
            title=r.title,
            icon=r.icon,
            position=r.position,
            updated_at=r.updated_at,
            values=values[r.id],
        )
        for r in rows
    ]


@router.patch("/{page_id}/rows/{row_id}/values", response_model=RowOut)
async def patch_row_values(
    page_id: uuid.UUID, row_id: uuid.UUID, body: ValuesPatch, user: CurrentUser, db: DbSession
) -> RowOut:
    await _get_database_checked(db, page_id, user.id, min_role="editor")
    row = await db.get(Page, row_id)
    if row is None or row.parent_id != page_id or row.kind != "row" or row.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Row not found")
    await _validate_values(db, page_id, body.values)

    for prop_id, value in body.values.items():
        existing = (
            await db.execute(
                select(DbValue).where(DbValue.row_id == row_id, DbValue.property_id == prop_id)
            )
        ).scalar_one_or_none()
        if value is None:
            if existing is not None:
                await db.delete(existing)
        elif existing is None:
            db.add(DbValue(row_id=row_id, property_id=prop_id, value=value))
        else:
            existing.value = value
    await db.commit()

    stored = {
        v.property_id: v.value
        for v in (
            await db.execute(select(DbValue).where(DbValue.row_id == row_id))
        ).scalars()
    }
    return RowOut(
        id=row.id,
        title=row.title,
        icon=row.icon,
        position=row.position,
        updated_at=row.updated_at,
        values=stored,
    )


@router.get("/rows/{row_id}/context", response_model=DatabaseOut)
async def row_context(row_id: uuid.UUID, user: CurrentUser, db: DbSession) -> DatabaseOut:
    """For a row page: its database's schema (used by the row-page property panel)."""
    row = await db.get(Page, row_id)
    if row is None or row.kind != "row" or row.parent_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Row not found")
    return await get_database(row.parent_id, user, db)


@router.delete("/{page_id}/rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(
    page_id: uuid.UUID, row_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Hard delete a row (values cascade). Rows skip the page trash on purpose:
    a half-deleted grid is more confusing than an undo toast."""
    await _get_database_checked(db, page_id, user.id, min_role="editor")
    row = await db.get(Page, row_id)
    if row is None or row.parent_id != page_id or row.kind != "row":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Row not found")
    await db.execute(delete(Page).where(Page.id == row_id))
    await db.commit()
