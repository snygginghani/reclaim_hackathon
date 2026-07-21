"""Background memory distillation — after a chat exchange, extract durable
facts worth remembering and store them (deduped). Best-effort: silently skips
if no model is configured or the model returns nothing useful."""

from __future__ import annotations

import json
import re
import uuid

from sqlalchemy import select

from ..db import SessionLocal
from ..models import AiSettings, Memory
from .crypto import decrypt_secret
from .providers import ChatMessage, LLMProvider, OllamaProvider, OpenRouterProvider

EXTRACT_PROMPT = (
    "From the exchange below, extract 0 to 3 DURABLE facts worth remembering long-term "
    "about the user or their projects — stable preferences, ongoing work, key context. "
    "Ignore trivia, one-off questions, and anything already obvious. "
    'Reply with ONLY a JSON array of short plain strings, e.g. ["Prefers concise answers"]. '
    "If nothing is worth remembering, reply []."
)


def provider_for(settings: AiSettings) -> LLMProvider | None:
    if settings.provider == "ollama":
        return OllamaProvider()
    if settings.provider == "openrouter":
        key = decrypt_secret(settings.openrouter_key_encrypted or "")
        return OpenRouterProvider(key) if key else None
    return None


async def complete_text(provider: LLMProvider, model: str, messages: list[ChatMessage]) -> str:
    out: list[str] = []
    async for ev in provider.chat_stream(messages, model, temperature=0.2, max_tokens=300):
        if ev.get("type") == "text":
            out.append(ev.get("text", ""))
        elif ev.get("type") == "error":
            return ""
    return "".join(out)


def _parse_json_list(text: str) -> list[str]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [str(x).strip() for x in data if isinstance(x, str) and x.strip()][:3]


async def extract_memories(
    workspace_id: uuid.UUID, user_id: uuid.UUID, user_msg: str, assistant_msg: str
) -> None:
    async with SessionLocal() as db:
        settings = await db.get(AiSettings, workspace_id)
        if settings is None or settings.provider is None:
            return
        model = settings.fast_model or settings.default_model
        provider = provider_for(settings)
        if provider is None or not model:
            return
        text = await complete_text(
            provider,
            model,
            [
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": f"User: {user_msg}\nAssistant: {assistant_msg}"},
            ],
        )
        facts = _parse_json_list(text)
        if not facts:
            return
        existing = {
            m.content.strip().lower()
            for m in (
                await db.execute(
                    select(Memory).where(
                        Memory.workspace_id == workspace_id, Memory.user_id == user_id
                    )
                )
            ).scalars()
        }
        for fact in facts:
            if fact.lower() not in existing:
                db.add(
                    Memory(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        content=fact,
                        source="auto",
                    )
                )
        await db.commit()
