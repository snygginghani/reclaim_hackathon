import json
import re
import uuid
from dataclasses import asdict

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..ai.crypto import decrypt_secret, encrypt_secret
from ..ai.hardware import probe_hardware
from ..ai.hardware_calc import MODEL_LADDER, compute_budget, fit_check, recommend
from ..ai.providers import (
    OLLAMA_URL,
    OPENROUTER_URL,
    ChatMessage,
    LLMProvider,
    OllamaProvider,
    OpenRouterProvider,
)
from ..deps import CurrentUser, DbSession, require_membership
from ..models import AiSettings

router = APIRouter(prefix="/api/ai", tags=["ai"])


# --- hardware & recommendations ---


@router.get("/hardware")
async def hardware(user: CurrentUser) -> dict:
    return asdict(probe_hardware())


@router.get("/recommendations")
async def recommendations(user: CurrentUser) -> dict:
    hw = probe_hardware()
    budget = compute_budget(hw)
    return {
        "hardware": asdict(hw),
        "budget": {"gpu_gb": budget.gpu_gb, "cpu_gb": budget.cpu_gb, "gpu_name": budget.gpu_name},
        "recommendations": [
            {"model": asdict(r.model), "fit": _fit_dict(r.fit), "reasoning": r.reasoning}
            for r in recommend(hw)
        ],
        "ladder": [
            {"model": asdict(f.model), "fit": _fit_dict(f)}
            for f in (fit_check(m, hw) for m in MODEL_LADDER)
        ],
    }


def _fit_dict(fit) -> dict:
    return {
        "footprint_gb": fit.footprint_gb,
        "fits_gpu": fit.fits_gpu,
        "fits_cpu": fit.fits_cpu,
        "fits_disk": fit.fits_disk,
        "speed": fit.speed,
    }


# --- settings ---


class AiSettingsOut(BaseModel):
    provider: str | None
    default_model: str | None
    fast_model: str | None
    has_openrouter_key: bool


class AiSettingsIn(BaseModel):
    provider: str | None = Field(default=None, pattern="^(ollama|openrouter)$")
    default_model: str | None = None
    fast_model: str | None = None
    # Present = replace; absent = keep; empty string = clear.
    openrouter_key: str | None = None


def _settings_out(s: AiSettings | None) -> AiSettingsOut:
    return AiSettingsOut(
        provider=s.provider if s else None,
        default_model=s.default_model if s else None,
        fast_model=s.fast_model if s else None,
        has_openrouter_key=bool(s and s.openrouter_key_encrypted),
    )


@router.get("/settings", response_model=AiSettingsOut)
async def get_ai_settings(user: CurrentUser, db: DbSession) -> AiSettingsOut:
    """AI config belongs to the user, so no workspace scoping here."""
    return _settings_out(await db.get(AiSettings, user.id))


@router.put("/settings", response_model=AiSettingsOut)
async def put_ai_settings(
    body: AiSettingsIn, user: CurrentUser, db: DbSession
) -> AiSettingsOut:
    settings = await db.get(AiSettings, user.id)
    if settings is None:
        settings = AiSettings(user_id=user.id)
        db.add(settings)

    if body.openrouter_key is not None:
        key = body.openrouter_key.strip()
        if key == "":
            settings.openrouter_key_encrypted = None
        else:
            if not await _validate_openrouter_key(key):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "OpenRouter rejected this key — double-check it and try again",
                )
            settings.openrouter_key_encrypted = encrypt_secret(key)
    if body.provider is not None:
        settings.provider = body.provider
    if body.default_model is not None:
        settings.default_model = body.default_model or None
    if body.fast_model is not None:
        settings.fast_model = body.fast_model or None
    await db.commit()
    return _settings_out(settings)


async def _validate_openrouter_key(key: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{OPENROUTER_URL}/key", headers={"Authorization": f"Bearer {key}"}
            )
            return r.status_code == 200
    except httpx.HTTPError:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Couldn’t reach OpenRouter to validate the key"
        )


# --- OpenRouter catalog ---

FEATURED: list[tuple[str, str]] = [
    ("DeepSeek V4 Pro", r"deepseek.*v4.*pro"),
    ("DeepSeek V4 Flash", r"deepseek.*v4.*flash"),
    ("Claude Sonnet 5", r"claude[-.]?sonnet[-.]?5"),
    ("Claude Opus 4.8", r"claude[-.]?opus[-.]?4[.-]8"),
    ("Claude Fable 5", r"claude[-.]?fable[-.]?5"),
]
_GPT_ID = re.compile(r"^openai/gpt-[\d.]+", re.IGNORECASE)
_GPT_EXCLUDE = re.compile(r"audio|realtime|image|search|transcribe|tts|mini-tts", re.IGNORECASE)


def match_featured(models: list[dict]) -> dict[str, str]:
    """Map featured label -> live model id, matched against the current catalog.
    Missing models are simply absent — never hardcode ids."""
    out: dict[str, str] = {}
    for label, pattern in FEATURED:
        rx = re.compile(pattern, re.IGNORECASE)
        hits = [m for m in models if rx.search(m.get("id", "")) or rx.search(m.get("name", ""))]
        if hits:
            # Prefer the shortest id (base model over :variants and previews).
            out[label] = min(hits, key=lambda m: len(m["id"]))["id"]
    gpts = [
        m for m in models
        if _GPT_ID.match(m.get("id", "")) and not _GPT_EXCLUDE.search(m.get("id", ""))
    ]
    if gpts:
        latest = max(gpts, key=lambda m: m.get("created", 0))
        out[f"OpenAI {latest.get('name', latest['id'])}"] = latest["id"]
    return out


@router.get("/openrouter/models")
async def openrouter_models(user: CurrentUser) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{OPENROUTER_URL}/models")
            r.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Couldn’t reach the OpenRouter catalog")
    raw = r.json().get("data", [])
    featured = match_featured(raw)
    featured_ids = set(featured.values())
    models = [
        {
            "id": m["id"],
            "name": m.get("name", m["id"]),
            "context_length": m.get("context_length"),
            "prompt_price": (m.get("pricing") or {}).get("prompt"),
            "completion_price": (m.get("pricing") or {}).get("completion"),
            "featured": m["id"] in featured_ids,
        }
        for m in raw
    ]
    return {
        "featured": [{"label": label, "id": mid} for label, mid in featured.items()],
        "models": models,
    }


# --- Ollama ---


@router.get("/ollama/status")
async def ollama_status(user: CurrentUser) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            return {"running": True, "models": models}
    except httpx.HTTPError:
        return {"running": False, "models": []}


class PullIn(BaseModel):
    model: str = Field(min_length=1, max_length=120)


@router.post("/ollama/pull")
async def ollama_pull(body: PullIn, user: CurrentUser) -> StreamingResponse:
    """SSE proxy of Ollama's pull progress."""

    async def stream():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10)) as client:
                async with client.stream(
                    "POST", f"{OLLAMA_URL}/api/pull", json={"model": body.model, "stream": True}
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.strip():
                            yield f"data: {line}\n\n"
        except httpx.HTTPError as e:
            yield f'data: {{"error": "Ollama unreachable: {e}"}}\n\n'
        yield 'data: {"done": true}\n\n'

    return StreamingResponse(stream(), media_type="text/event-stream")


# --- provider resolution + test chat ---


async def resolve_provider(db, user_id: uuid.UUID) -> tuple[LLMProvider, AiSettings]:
    """Resolve the caller's own AI config — it follows them across workspaces."""
    settings = await db.get(AiSettings, user_id)
    if settings is None or settings.provider is None or not settings.default_model:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "AI isn’t set up yet — add a provider in AI settings"
        )
    if settings.provider == "ollama":
        return OllamaProvider(), settings
    key = decrypt_secret(settings.openrouter_key_encrypted or "")
    if not key:
        raise HTTPException(status.HTTP_409_CONFLICT, "The stored OpenRouter key is missing")
    return OpenRouterProvider(key), settings


class TestChatIn(BaseModel):
    workspace_id: uuid.UUID
    prompt: str = Field(min_length=1, max_length=4000)


@router.post("/chat/test")
async def chat_test(body: TestChatIn, user: CurrentUser, db: DbSession) -> StreamingResponse:
    await require_membership(db, body.workspace_id, user.id)
    provider, settings = await resolve_provider(db, user.id)
    messages: list[ChatMessage] = [
        {"role": "system", "content": "You are Lore, a concise helpful assistant. Reply briefly."},
        {"role": "user", "content": body.prompt},
    ]

    async def stream():
        async for event in provider.chat_stream(messages, settings.default_model, max_tokens=500):
            yield f"data: {json.dumps(event)}\n\n"
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(stream(), media_type="text/event-stream")
