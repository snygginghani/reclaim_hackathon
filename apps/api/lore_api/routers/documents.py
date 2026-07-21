import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from ..blocks import blocks_to_text
from ..deps import CurrentUser, DbSession
from ..models import Document
from .pages import _get_page_checked

router = APIRouter(prefix="/api/pages", tags=["documents"])


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_id: uuid.UUID
    blocks: list
    updated_at: datetime


class DocumentIn(BaseModel):
    blocks: list


@router.get("/{page_id}/content", response_model=DocumentOut)
async def get_content(page_id: uuid.UUID, user: CurrentUser, db: DbSession) -> DocumentOut:
    await _get_page_checked(db, page_id, user.id)
    doc = await db.get(Document, page_id)
    if doc is None:
        # A page with no saved body yet is an empty document, not an error.
        return DocumentOut(page_id=page_id, blocks=[], updated_at=datetime.now())
    return DocumentOut.model_validate(doc)


@router.put("/{page_id}/content", response_model=DocumentOut)
async def put_content(
    page_id: uuid.UUID, body: DocumentIn, user: CurrentUser, db: DbSession
) -> Document:
    await _get_page_checked(db, page_id, user.id, min_role="editor")
    text = blocks_to_text(body.blocks)
    doc = await db.get(Document, page_id)
    if doc is None:
        doc = Document(page_id=page_id, blocks=body.blocks, text_content=text)
        db.add(doc)
    else:
        doc.blocks = body.blocks
        doc.text_content = text
    await db.commit()
    return doc
