import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..deps import CurrentUser, DbSession, require_membership
from ..models import User, Workspace, WorkspaceInvite, WorkspaceMember
from ..schemas import (
    InviteCreate,
    InviteOut,
    InvitePreview,
    MemberOut,
    WorkspaceCreate,
    WorkspaceOut,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(body: WorkspaceCreate, user: CurrentUser, db: DbSession) -> WorkspaceOut:
    ws = Workspace(name=body.name.strip(), icon=body.icon)
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    await db.commit()
    return WorkspaceOut(id=ws.id, name=ws.name, icon=ws.icon, role="owner")


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(user: CurrentUser, db: DbSession) -> list[WorkspaceOut]:
    rows = (
        await db.execute(
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user.id)
            .order_by(Workspace.created_at)
        )
    ).all()
    return [WorkspaceOut(id=ws.id, name=ws.name, icon=ws.icon, role=role) for ws, role in rows]


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(workspace_id: uuid.UUID, user: CurrentUser, db: DbSession) -> WorkspaceOut:
    member = await require_membership(db, workspace_id, user.id)
    ws = await db.get(Workspace, workspace_id)
    return WorkspaceOut(id=ws.id, name=ws.name, icon=ws.icon, role=member.role)


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def list_members(workspace_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[MemberOut]:
    await require_membership(db, workspace_id, user.id)
    rows = (
        await db.execute(
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.created_at)
        )
    ).all()
    return [
        MemberOut(
            user_id=u.id, role=m.role, name=u.name, username=u.username, avatar_hue=u.avatar_hue
        )
        for m, u in rows
    ]


@router.post("/{workspace_id}/invites", response_model=InviteOut, status_code=201)
async def create_invite(
    workspace_id: uuid.UUID, body: InviteCreate, user: CurrentUser, db: DbSession
) -> WorkspaceInvite:
    await require_membership(db, workspace_id, user.id, min_role="owner")
    invite = WorkspaceInvite(workspace_id=workspace_id, role=body.role, created_by=user.id)
    db.add(invite)
    await db.commit()
    return invite


@router.get("/invites/{invite_id}", response_model=InvitePreview)
async def preview_invite(invite_id: uuid.UUID, db: DbSession) -> InvitePreview:
    invite = await db.get(WorkspaceInvite, invite_id)
    if invite is None or (
        invite.expires_at is not None and invite.expires_at < datetime.now(timezone.utc)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found or expired")
    ws = await db.get(Workspace, invite.workspace_id)
    return InvitePreview(workspace_name=ws.name, workspace_icon=ws.icon, role=invite.role)


@router.post("/invites/{invite_id}/accept", response_model=WorkspaceOut)
async def accept_invite(invite_id: uuid.UUID, user: CurrentUser, db: DbSession) -> WorkspaceOut:
    invite = await db.get(WorkspaceInvite, invite_id)
    if invite is None or (
        invite.expires_at is not None and invite.expires_at < datetime.now(timezone.utc)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found or expired")
    existing = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == invite.workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            WorkspaceMember(workspace_id=invite.workspace_id, user_id=user.id, role=invite.role)
        )
        await db.commit()
        role = invite.role
    else:
        role = existing.role
    ws = await db.get(Workspace, invite.workspace_id)
    return WorkspaceOut(id=ws.id, name=ws.name, icon=ws.icon, role=role)
