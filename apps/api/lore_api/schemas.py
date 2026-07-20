import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth ---


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    name: str
    avatar_hue: int


# --- workspaces ---


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=16)


class WorkspaceOut(ORMModel):
    id: uuid.UUID
    name: str
    icon: str | None
    role: str | None = None  # calling user's role, filled by the router


class MemberOut(ORMModel):
    user_id: uuid.UUID
    role: str
    name: str
    email: str
    avatar_hue: int


class InviteCreate(BaseModel):
    role: str = Field(default="editor", pattern="^(editor|viewer)$")


class InviteOut(ORMModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    role: str


class InvitePreview(BaseModel):
    workspace_name: str
    workspace_icon: str | None
    role: str


# --- pages ---


class PageCreate(BaseModel):
    workspace_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    title: str = ""


class PageUpdate(BaseModel):
    title: str | None = None
    icon: str | None = None
    # Sentinel-free explicit clears: send icon="" to remove the icon.


class PageMove(BaseModel):
    parent_id: uuid.UUID | None = None
    # Position of the sibling to insert AFTER (null = at top).
    after_id: uuid.UUID | None = None


class PageOut(ORMModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    parent_id: uuid.UUID | None
    title: str
    icon: str | None
    position: float
    updated_at: datetime
    deleted_at: datetime | None


class FavoriteOut(ORMModel):
    page_id: uuid.UUID
    position: float
