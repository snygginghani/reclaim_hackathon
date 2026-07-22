import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update

from ..ai.ingest import backfill_workspace
from ..ai.memory import extract_memories
from ..ai.rag import build_sources, system_prompt, used_citations
from ..ai.retrieval import hybrid_search
from ..deps import CurrentUser, DbSession, require_membership
from ..db import SessionLocal
from ..models import Conversation, Memory, Message
from .ai import resolve_provider

router = APIRouter(prefix="/api/ai", tags=["assistant"])

HISTORY_TURNS = 6


# --------------------------------------------------------------------------- chat


class Scope(BaseModel):
    type: str = Field(default="workspace", pattern="^(workspace|page|sources)$")
    page_ids: list[uuid.UUID] = []


class ChatIn(BaseModel):
    workspace_id: uuid.UUID
    message: str = Field(min_length=1, max_length=8000)
    scope: Scope = Scope()
    conversation_id: uuid.UUID | None = None


@router.post("/chat")
async def chat(
    body: ChatIn, user: CurrentUser, db: DbSession, background: BackgroundTasks
) -> StreamingResponse:
    await require_membership(db, body.workspace_id, user.id)
    provider, settings = await resolve_provider(db, body.workspace_id)

    scoped_pages = body.scope.page_ids if body.scope.type != "workspace" else None
    retrieved = await hybrid_search(
        db, body.workspace_id, body.message, page_ids=scoped_pages, k=8
    )
    sources = build_sources(retrieved)

    memories = (
        await db.execute(
            select(Memory.content)
            .where(Memory.workspace_id == body.workspace_id, Memory.user_id == user.id)
            .order_by(Memory.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    # Resolve / create the conversation and pull recent history.
    conv = None
    if body.conversation_id:
        conv = await db.get(Conversation, body.conversation_id)
        if conv is None or conv.user_id != user.id:
            conv = None
    if conv is None:
        conv = Conversation(
            workspace_id=body.workspace_id, user_id=user.id, title=body.message[:60]
        )
        db.add(conv)
        await db.commit()
    history = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(HISTORY_TURNS * 2)
        )
    ).scalars().all()
    history = list(reversed(history))

    messages = [{"role": "system", "content": system_prompt(sources, list(memories))}]
    for m in history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": body.message})

    conv_id = conv.id
    model = settings.default_model

    async def stream():
        yield _sse({"type": "conversation", "id": str(conv_id)})
        yield _sse({"type": "sources", "sources": sources})
        answer_parts: list[str] = []
        try:
            async for ev in provider.chat_stream(messages, model, temperature=0.4):
                if ev.get("type") == "text":
                    answer_parts.append(ev["text"])
                    yield _sse({"type": "text", "text": ev["text"]})
                elif ev.get("type") == "error":
                    yield _sse({"type": "error", "error": ev.get("error", "model error")})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "error": str(exc)})

        answer = "".join(answer_parts)
        citations = used_citations(answer, sources)
        if answer.strip():
            async with SessionLocal() as s:
                s.add(Message(conversation_id=conv_id, role="user", content=body.message))
                s.add(
                    Message(
                        conversation_id=conv_id,
                        role="assistant",
                        content=answer,
                        citations=citations,
                    )
                )
                # Inserting child rows doesn't trigger the model's `onupdate`, so
                # history stayed ordered by creation instead of last activity.
                await s.execute(
                    update(Conversation)
                    .where(Conversation.id == conv_id)
                    .values(updated_at=datetime.now(timezone.utc))
                )
                await s.commit()
        yield _sse({"type": "done", "citations": citations})

    if body.message.strip():
        background.add_task(
            extract_memories, body.workspace_id, user.id, body.message, "(pending)"
        )
    return StreamingResponse(stream(), media_type="text/event-stream")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


# --------------------------------------------------------------------------- conversations


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    content: str
    citations: list
    created_at: datetime


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    workspace_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[Conversation]:
    await require_membership(db, workspace_id, user.id)
    rows = (
        await db.execute(
            select(Conversation)
            .where(Conversation.workspace_id == workspace_id, Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(50)
        )
    ).scalars().all()
    return list(rows)


@router.get("/conversations/{conversation_id}", response_model=list[MessageOut])
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[Message]:
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    rows = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    ).scalars().all()
    return list(rows)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    await db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await db.commit()


# --------------------------------------------------------------------------- memory


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    content: str
    kind: str
    source: str
    created_at: datetime


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    kind: str = Field(default="fact", pattern="^(fact|preference|project)$")


@router.get("/memory", response_model=list[MemoryOut])
async def list_memory(
    workspace_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[Memory]:
    await require_membership(db, workspace_id, user.id)
    rows = (
        await db.execute(
            select(Memory)
            .where(Memory.workspace_id == workspace_id, Memory.user_id == user.id)
            .order_by(Memory.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post("/memory", response_model=MemoryOut, status_code=201)
async def add_memory(
    workspace_id: uuid.UUID, body: MemoryIn, user: CurrentUser, db: DbSession
) -> Memory:
    await require_membership(db, workspace_id, user.id)
    mem = Memory(
        workspace_id=workspace_id,
        user_id=user.id,
        content=body.content.strip(),
        kind=body.kind,
        source="manual",
    )
    db.add(mem)
    await db.commit()
    return mem


@router.patch("/memory/{memory_id}", response_model=MemoryOut)
async def edit_memory(
    memory_id: uuid.UUID, body: MemoryIn, user: CurrentUser, db: DbSession
) -> Memory:
    mem = await db.get(Memory, memory_id)
    if mem is None or mem.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found")
    mem.content = body.content.strip()
    mem.kind = body.kind
    await db.commit()
    return mem


@router.delete("/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    mem = await db.get(Memory, memory_id)
    if mem is None or mem.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found")
    await db.execute(delete(Memory).where(Memory.id == memory_id))
    await db.commit()


# --------------------------------------------------------------------------- reindex


@router.post("/reindex")
async def reindex(
    workspace_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> dict:
    await require_membership(db, workspace_id, user.id, min_role="editor")
    count = await backfill_workspace(workspace_id)
    return {"chunks": count}


# --------------------------------------------------------------------------- generators


GENERATORS = {
    "summary": "Write a clear, well-structured summary of the sources as markdown with a short intro and key points.",
    "study_guide": "Create a study guide from the sources as markdown: key concepts, definitions, and a few review questions.",
    "faq": "Write a FAQ from the sources as markdown: 5-8 realistic questions with grounded answers.",
    "outline": "Produce a hierarchical markdown outline of everything covered by the sources.",
}


class GenerateIn(BaseModel):
    workspace_id: uuid.UUID
    kind: str = Field(pattern="^(summary|study_guide|faq|outline)$")
    scope: Scope = Scope()


@router.post("/generate")
async def generate(body: GenerateIn, user: CurrentUser, db: DbSession) -> StreamingResponse:
    await require_membership(db, body.workspace_id, user.id)
    provider, settings = await resolve_provider(db, body.workspace_id)
    scoped_pages = body.scope.page_ids if body.scope.type != "workspace" else None
    # Broad retrieval — generators want coverage, not just the top few.
    retrieved = await hybrid_search(
        db, body.workspace_id, GENERATORS[body.kind], page_ids=scoped_pages, k=16
    )
    sources = build_sources(retrieved)
    instruction = GENERATORS[body.kind]
    messages = [
        {
            "role": "system",
            "content": (
                "You are Lore, generating a document from a workspace. "
                + instruction
                + " Cite claims with [n] matching the sources. Output only markdown.\n\n"
                + system_prompt(sources, [])
            ),
        },
        {"role": "user", "content": "Generate the document now."},
    ]

    async def stream():
        yield _sse({"type": "sources", "sources": sources})
        try:
            async for ev in provider.chat_stream(messages, settings.default_model, temperature=0.5):
                if ev.get("type") == "text":
                    yield _sse({"type": "text", "text": ev["text"]})
                elif ev.get("type") == "error":
                    yield _sse({"type": "error", "error": ev.get("error", "model error")})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "error": str(exc)})
        yield _sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream")
