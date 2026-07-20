import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import User, WorkspaceMember
from .security import ACCESS_COOKIE, decode_token

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    user_id = decode_token(token, "access") if token else None
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

ROLE_RANK = {"viewer": 0, "editor": 1, "owner": 2}


async def require_membership(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, min_role: str = "viewer"
) -> WorkspaceMember:
    member = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    if ROLE_RANK[member.role] < ROLE_RANK[min_role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return member
