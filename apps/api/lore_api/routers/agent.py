import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from ..ai.tools import READ_TOOLS, TOOL_SCHEMAS, WRITE_TOOLS, build_preview, run_read_tool
from ..db import SessionLocal
from ..deps import CurrentUser, DbSession, require_membership
from ..models import Conversation, Message
from .ai import resolve_provider

router = APIRouter(prefix="/api/ai", tags=["agent"])

MAX_STEPS = 5
HISTORY_TURNS = 6

SYSTEM_TEMPLATE = """\
You are Lore — the assistant built into Lore, a private, local-first workspace app \
for notes, pages and databases. The user's content lives in Lore and nowhere else.

Lore is not Notion, Obsidian, Evernote or any other app. Never name another product, \
never tell the user to go and do something "in Notion", and never describe another \
app's interface. If a job needs doing, either do it with a tool or say plainly that \
Lore cannot do it yet.

Today is {today}. Use this for anything dated — "this week", "tomorrow", schedules, \
plans — and never ask the user what today's date is.

## Your tools

- search_workspace / read_page / list_pages — look things up.
- create_page — ONLY for something that does not exist yet.
- update_page — edit, fix, rewrite or restructure a page that already exists.
- append_to_page — add to the end of an existing page.
- rename_page — change only a page's title, leaving the body untouched.
- trash_pages — move pages to the trash (reversible; sub-pages go too).
- create_database — a new database with named columns.

That list is the truth about what you can do. Never claim you lack a capability that \
is on it, and never invent one that is not.

Match the tool to the request, and pick the narrowest one that does the job: rename_page \
for a title-only change, append_to_page to add a section at the end, update_page only when \
the body genuinely has to change. If the user says "this page", "my X page", or otherwise \
points at existing content, find that page and update it — never answer an edit request \
by creating a second copy. To delete, list_pages for the ids and call trash_pages once \
with all of them.

For a small edit, read the page first and send the full revised body through update_page \
with the untouched parts preserved exactly — a "fix the typo" request must not come back \
as a shorter, rewritten page.

## Reading before writing

Read first ONLY when the request depends on what is already in the workspace — a \
question about existing pages, or an edit to a page you must locate. If the user asks \
for something new, call the write tool on your first turn without searching. Never \
repeat a search you have already run; if a search comes back empty, propose the write \
anyway rather than searching again.

## Writes are proposals

Every write is proposed for the user to approve — you never apply changes yourself. \
Call the tool to propose it, and never claim you already did it.

## Writing documents

The page title is stored separately from the body, so never start content_markdown \
with an H1 repeating the title — begin with the first real section.

Use headings for sections, and `- [ ] ` checklists for anything the user will work \
through or tick off (plans, workouts and their sets, steps, packing or shopping lists). \
A checkbox is only for an action the user will carry out and tick off; advice and \
criteria are plain bullets even when they sound like instructions — "Choose Postgres if \
you need joins" is a recommendation, not a task. Explainers and comparisons are prose \
and bullets throughout.

Cover what was asked in roughly 20-30 lines and stop: no filler sections, no code \
blocks or ASCII diagrams.

Keep spoken replies short; let the proposals carry the detail.\
"""


def build_system() -> str:
    """Built per request so the model always has the real current date."""
    now = datetime.now().astimezone()
    return SYSTEM_TEMPLATE.format(today=now.strftime("%A, %d %B %Y"))


class AgentIn(BaseModel):
    workspace_id: uuid.UUID
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: uuid.UUID | None = None


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@router.post("/agent")
async def agent(body: AgentIn, user: CurrentUser, db: DbSession) -> StreamingResponse:
    await require_membership(db, body.workspace_id, user.id, min_role="editor")
    provider, settings = await resolve_provider(db, body.workspace_id)

    # Agent turns were never persisted, so every agent chat vanished on reload and
    # the model had no memory of earlier turns in the same conversation.
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
    conv_id = conv.id

    history = list(
        reversed(
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conv_id)
                    .order_by(Message.created_at.desc())
                    .limit(HISTORY_TURNS * 2)
                )
            )
            .scalars()
            .all()
        )
    )

    messages: list[dict] = [{"role": "system", "content": build_system()}]
    for m in history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": body.message})

    async def save_turn(spoken: str) -> None:
        """Persist the exchange and bump the conversation so history sorts by real
        activity — `onupdate` never fires when only child rows are inserted."""
        if not spoken.strip():
            return
        async with SessionLocal() as s:
            s.add(Message(conversation_id=conv_id, role="user", content=body.message))
            s.add(Message(conversation_id=conv_id, role="assistant", content=spoken))
            await s.execute(
                update(Conversation)
                .where(Conversation.id == conv_id)
                .values(updated_at=datetime.now(timezone.utc))
            )
            await s.commit()

    async def stream():
        proposed = False
        spoken: list[str] = []
        yield _sse({"type": "conversation", "id": str(conv_id)})
        for _step in range(MAX_STEPS):
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            try:
                async for ev in provider.chat_stream(
                    messages, settings.default_model, tools=TOOL_SCHEMAS, temperature=0.3
                ):
                    if ev.get("type") == "text":
                        text_parts.append(ev["text"])
                        spoken.append(ev["text"])
                        yield _sse({"type": "text", "text": ev["text"]})
                    elif ev.get("type") == "tool_call":
                        tool_calls.append(ev["tool_call"])
                    elif ev.get("type") == "error":
                        yield _sse({"type": "error", "error": ev.get("error", "model error")})
                        await save_turn("".join(spoken))
                        yield _sse({"type": "done"})
                        return
            except Exception as exc:  # noqa: BLE001
                yield _sse({"type": "error", "error": str(exc)})
                await save_turn("".join(spoken))
                yield _sse({"type": "done"})
                return

            if not tool_calls:
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(text_parts),
                    "tool_calls": [
                        {
                            "id": tc.get("id") or tc["name"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc.get("arguments", {})),
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                name = tc["name"]
                args = tc.get("arguments", {})
                tc_id = tc.get("id") or name
                if name in READ_TOOLS:
                    yield _sse({"type": "tool", "name": name, "args": args})
                    result = await run_read_tool(db, body.workspace_id, name, args)
                    messages.append(
                        {"role": "tool", "tool_call_id": tc_id, "name": name, "content": result}
                    )
                elif name in WRITE_TOOLS:
                    proposed = True
                    yield _sse(
                        {
                            "type": "approval",
                            "tool": name,
                            "args": args,
                            "preview": await build_preview(db, body.workspace_id, name, args),
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": name,
                            "content": "Proposed to the user for approval. Do not repeat this proposal.",
                        }
                    )
                else:
                    messages.append(
                        {"role": "tool", "tool_call_id": tc_id, "name": name, "content": "Unknown tool."}
                    )

            # After proposing writes, let the model add a short wrap-up, then stop.
            if proposed:
                async for ev in provider.chat_stream(
                    messages, settings.default_model, temperature=0.3
                ):
                    if ev.get("type") == "text":
                        spoken.append(ev["text"])
                        yield _sse({"type": "text", "text": ev["text"]})
                break

        await save_turn("".join(spoken))
        yield _sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream")
