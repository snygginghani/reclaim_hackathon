import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..ai.memory import complete_text, provider_for
from ..deps import CurrentUser, DbSession, require_membership
from ..models import AiSettings
from .ai import resolve_provider

router = APIRouter(prefix="/api/ai", tags=["inline"])

ACTIONS = {
    "improve": "Improve this text: clearer, tighter, more natural. Keep the meaning and voice.",
    "fix": "Fix spelling, grammar, and punctuation. Change nothing else.",
    "shorten": "Make this text noticeably shorter while keeping the key points.",
    "lengthen": "Expand this text with more detail and explanation.",
    "summarize": "Summarize this text in a sentence or two.",
    "continue": "Continue writing naturally from where this text leaves off. Output only the continuation.",
    "translate": "Translate this text into {arg}. Output only the translation.",
    "tone": "Rewrite this text in a {arg} tone.",
}


class RewriteIn(BaseModel):
    workspace_id: uuid.UUID
    text: str = Field(min_length=1, max_length=8000)
    action: str
    arg: str = ""


@router.post("/rewrite")
async def rewrite(body: RewriteIn, user: CurrentUser, db: DbSession) -> StreamingResponse:
    await require_membership(db, body.workspace_id, user.id)
    provider, settings = await resolve_provider(db, user.id)
    template = ACTIONS.get(body.action)
    if template is None:
        template = ACTIONS["improve"]
    instruction = template.replace("{arg}", body.arg or "plain English")

    messages = [
        {
            "role": "system",
            "content": (
                "You are Lore, a writing assistant. "
                + instruction
                + " Output ONLY the resulting text — no preamble, no quotes, no explanation."
            ),
        },
        {"role": "user", "content": body.text},
    ]

    async def stream():
        try:
            async for ev in provider.chat_stream(messages, settings.default_model, temperature=0.5):
                if ev.get("type") == "text":
                    yield f"data: {json.dumps({'type': 'text', 'text': ev['text']})}\n\n"
                elif ev.get("type") == "error":
                    yield f"data: {json.dumps({'type': 'error', 'error': ev.get('error', 'model error')})}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


class AutocompleteIn(BaseModel):
    workspace_id: uuid.UUID
    context: str = Field(max_length=4000)


@router.post("/autocomplete")
async def autocomplete(body: AutocompleteIn, user: CurrentUser, db: DbSession) -> dict:
    """Ghost-text: predict the next few words. Uses the user's fast model."""
    await require_membership(db, body.workspace_id, user.id)
    settings = await db.get(AiSettings, user.id)
    if settings is None or settings.provider is None:
        return {"completion": ""}
    model = settings.fast_model or settings.default_model
    provider = provider_for(settings)
    if provider is None or not model:
        return {"completion": ""}

    context = body.context[-1500:]
    if not context.strip():
        return {"completion": ""}
    text = await complete_text(
        provider,
        model,
        [
            {
                "role": "system",
                "content": (
                    "You autocomplete the user's note. Continue their text with the single most "
                    "likely short continuation (a few words up to one sentence). "
                    "Output ONLY the continuation, no quotes, and do not repeat their text."
                ),
            },
            {"role": "user", "content": context},
        ],
    )
    # Keep ghost text short and on the same thought.
    completion = text.strip().strip('"').split("\n")[0][:160]
    return {"completion": completion}
