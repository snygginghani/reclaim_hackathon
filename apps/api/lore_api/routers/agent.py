import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..ai.tools import READ_TOOLS, TOOL_SCHEMAS, WRITE_TOOLS, run_read_tool, write_preview
from ..deps import CurrentUser, DbSession, require_membership
from .ai import resolve_provider

router = APIRouter(prefix="/api/ai", tags=["agent"])

MAX_STEPS = 5

SYSTEM = (
    "You are Lore, an agent working inside the user's workspace. You can search and read "
    "pages with tools, and PROPOSE edits (creating pages/databases, appending content). "
    "Always search or read before answering questions about workspace content. "
    "When the user asks you to write or change something, call the appropriate write tool to "
    "propose it — never claim you already did it; the user approves proposals themselves. "
    "Keep spoken replies short; let the proposals carry the detail."
)


class AgentIn(BaseModel):
    workspace_id: uuid.UUID
    message: str = Field(min_length=1, max_length=8000)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@router.post("/agent")
async def agent(body: AgentIn, user: CurrentUser, db: DbSession) -> StreamingResponse:
    await require_membership(db, body.workspace_id, user.id, min_role="editor")
    provider, settings = await resolve_provider(db, body.workspace_id)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": body.message},
    ]

    async def stream():
        proposed = False
        for _step in range(MAX_STEPS):
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            try:
                async for ev in provider.chat_stream(
                    messages, settings.default_model, tools=TOOL_SCHEMAS, temperature=0.3
                ):
                    if ev.get("type") == "text":
                        text_parts.append(ev["text"])
                        yield _sse({"type": "text", "text": ev["text"]})
                    elif ev.get("type") == "tool_call":
                        tool_calls.append(ev["tool_call"])
                    elif ev.get("type") == "error":
                        yield _sse({"type": "error", "error": ev.get("error", "model error")})
                        yield _sse({"type": "done"})
                        return
            except Exception as exc:  # noqa: BLE001
                yield _sse({"type": "error", "error": str(exc)})
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
                            "preview": write_preview(name, args),
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
                        yield _sse({"type": "text", "text": ev["text"]})
                break

        yield _sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream")
