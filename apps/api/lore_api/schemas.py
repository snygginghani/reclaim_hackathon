import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth ---

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,29}$")

# Names that would collide with routes or read as official.
RESERVED_USERNAMES = frozenset(
    {"admin", "api", "root", "me", "login", "logout", "register", "settings", "new", "null"}
)


def _normalize_username(v: object) -> object:
    """Fold to the canonical form before validation, so "Ada " registers as "ada"."""
    return v.strip().lower() if isinstance(v, str) else v


class RegisterIn(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)

    _normalize = field_validator("username", mode="before")(_normalize_username)

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        # Hand-rolled rather than Field(pattern=...) so the form shows prose
        # instead of the raw regex.
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-30 characters: lowercase letters, numbers, "
                "underscores or hyphens, starting with a letter or number"
            )
        if v in RESERVED_USERNAMES:
            raise ValueError("This username is reserved")
        return v


class LoginIn(BaseModel):
    # Deliberately unvalidated beyond normalization: a malformed username must fall
    # through to the same 401 as a wrong password, not a distinguishable 422.
    username: str
    password: str

    _normalize = field_validator("username", mode="before")(_normalize_username)


class UserOut(ORMModel):
    id: uuid.UUID
    username: str
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
    username: str
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
    kind: str
    position: float
    updated_at: datetime
    deleted_at: datetime | None


class FavoriteOut(ORMModel):
    page_id: uuid.UUID
    position: float
