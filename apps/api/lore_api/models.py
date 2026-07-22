import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from .db import Base

EMBED_DIM = 384


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    # Deterministic avatar hue (0-360) picked at signup; avatars are initials on a colored disc.
    avatar_hue: Mapped[int] = mapped_column(default=220)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list["WorkspaceMember"]] = relationship(back_populates="user")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    icon: Mapped[str | None] = mapped_column(String(16), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    members: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16))  # "owner" | "editor" | "viewer"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class WorkspaceInvite(Base):
    __tablename__ = "workspace_invites"

    # The id doubles as the invite token in the join URL.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="editor")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Page(Base):
    __tablename__ = "pages"
    # Fetch server-generated timestamps via RETURNING on insert/update — the async
    # session cannot lazily load expired columns during response serialization.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True, default=None
    )
    title: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str | None] = mapped_column(String(16), default=None)
    # "doc" = normal page, "database" = full-page database, "row" = a database row
    # (rows are pages, so any row opens as a page with an editor body).
    kind: Mapped[str] = mapped_column(String(16), default="doc", server_default="doc")
    # Fractional ordering among siblings: insert at end = max+1024, move = midpoint.
    position: Mapped[float] = mapped_column(Float, default=1024.0)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Soft delete = in trash. Hard delete removes the row (children cascade).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Document(Base):
    """A page's body. `blocks` is the BlockNote JSON snapshot — the read model used
    for export, search, and RAG. Phase 3 adds the Yjs update log as the merge
    source of truth; this snapshot stays maintained alongside it."""

    __tablename__ = "documents"
    __mapper_args__ = {"eager_defaults": True}

    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), primary_key=True
    )
    blocks: Mapped[list] = mapped_column(JSONB, default=list)
    # Plain text extracted from `blocks` on every save — the substrate for
    # full-text search now and embedding chunks in the RAG pipeline.
    text_content: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Set when a client seeded the collaborative Y.Doc from `blocks` (legacy /
    # imported pages). Grants exactly one seeder; see POST /{page_id}/collab-seed.
    collab_seeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class YDocUpdate(Base):
    """Append-only Yjs update log per page — the merge source of truth for
    real-time collaboration. Compacted into a single merged update when the
    log grows past a threshold (see collab.PostgresYStore)."""

    __tablename__ = "ydoc_updates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    data: Mapped[bytes] = mapped_column(LargeBinary)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DbProperty(Base):
    """A column of a database. `database_id` is the database PAGE's id.
    `options` holds type-specific config: select/multi_select -> {"choices":
    [{"id","name","color"}]}, relation -> {"target": <database page id>}."""

    __tablename__ = "db_properties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    database_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(16))
    position: Mapped[float] = mapped_column(Float, default=1024.0)
    options: Mapped[dict] = mapped_column(JSONB, default=dict)


class DbView(Base):
    """A saved view of a database. `config` holds filters, sorts, grouping,
    visible columns, and per-view settings like the calendar's date property."""

    __tablename__ = "db_views"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    database_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(16))  # table | board | list | calendar
    position: Mapped[float] = mapped_column(Float, default=1024.0)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class DbValue(Base):
    """One cell: the value of one property for one row page."""

    __tablename__ = "db_values"
    __table_args__ = (UniqueConstraint("row_id", "property_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    row_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("db_properties.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[dict] = mapped_column(JSONB, default=dict)


class Chunk(Base):
    """An embedded slice of a page's document — the RAG retrieval unit.
    `block_ids` lets a citation jump to the exact block that grounded a claim."""

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(default=0)
    text: Mapped[str] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(Text, default=None)
    block_ids: Mapped[list] = mapped_column(JSONB, default=list)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text, default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    # Citations: [{n, page_id, page_title, block_ids, snippet}] for assistant turns.
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Memory(Base):
    """A distilled durable fact Lore remembers about the user/workspace,
    retrieved into the system prompt. Fully user-inspectable and editable."""

    __tablename__ = "memories"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(24), default="fact")  # fact|preference|project
    source: Mapped[str] = mapped_column(String(16), default="auto")  # auto|manual
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiSettings(Base):
    """Per-user AI configuration, shared across every workspace that user opens.
    The OpenRouter key is Fernet-encrypted at rest and never returned to clients
    after being saved."""

    __tablename__ = "ai_settings"
    __mapper_args__ = {"eager_defaults": True}

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str | None] = mapped_column(String(16), default=None)  # "ollama"|"openrouter"
    openrouter_key_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    default_model: Mapped[str | None] = mapped_column(String(120), default=None)
    fast_model: Mapped[str | None] = mapped_column(String(120), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "page_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    position: Mapped[float] = mapped_column(Float, default=1024.0)
