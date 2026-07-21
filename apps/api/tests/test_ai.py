import json

from httpx import AsyncClient

from lore_api.ai.crypto import decrypt_secret, encrypt_secret
from lore_api.ai.hardware import GpuInfo, HardwareInfo
from lore_api.ai.hardware_calc import (
    MODEL_LADDER,
    compute_budget,
    fit_check,
    model_footprint_gb,
    recommend,
)
from lore_api.ai.providers import parse_ollama_chunk, parse_openrouter_line, flush_pending_tools
from lore_api.routers.ai import match_featured

from .test_pages import make_workspace


def hw(ram=32.0, avail=20.0, vram: float | None = None, disk=500.0) -> HardwareInfo:
    gpus = [GpuInfo(vendor="nvidia", name="RTX Test", vram_gb=vram)] if vram else []
    return HardwareInfo(
        os="TestOS", cpu="TestCPU", cores=8, ram_total_gb=ram,
        ram_available_gb=avail, disk_free_gb=disk, gpus=gpus,
    )


# --- calculator ---


def test_footprint_formula():
    assert model_footprint_gb(8.0) == 8.0 * 0.55 + 1.5  # 5.9


def test_budget_prefers_gpu_when_vram_known():
    b = compute_budget(hw(vram=12.0))
    assert b.gpu_gb == 10.8 and b.gpu_name == "RTX Test"
    assert compute_budget(hw()).gpu_gb is None


def test_fit_gating_and_speed():
    machine = hw(avail=20.0, vram=12.0)
    m14 = next(m for m in MODEL_LADDER if m.params_b == 14.0)
    m70 = next(m for m in MODEL_LADDER if m.params_b == 70.0)
    f14 = fit_check(m14, machine)
    assert f14.fits_gpu and f14.speed == "fast"  # 9.2GB fits 10.8GB budget
    f70 = fit_check(m70, machine)
    assert not f70.fits_gpu and not f70.fits_cpu and f70.speed == "no"  # 40GB nowhere to go


def test_cpu_only_small_models_are_ok_not_fast():
    machine = hw(avail=10.0)  # 6GB budget, no GPU
    m8 = next(m for m in MODEL_LADDER if m.tag == "llama3.1:8b")
    f = fit_check(m8, machine)
    assert not f.fits_gpu and f.fits_cpu and f.speed == "ok"


def test_disk_gates_hard():
    machine = hw(vram=24.0, disk=1.0)
    assert all(fit_check(m, machine).speed == "no" for m in MODEL_LADDER if m.disk_gb > 1.0)


def test_recommendations_shape_and_reasoning():
    recs = recommend(hw(vram=12.0))
    assert len(recs) == 3
    # Best pick is GPU-resident and high quality; a small background model is included.
    assert recs[0].fit.fits_gpu and recs[0].model.quality >= 4
    assert any(r.model.params_b <= 4 for r in recs)
    assert "RTX Test" in recs[0].reasoning and "GB" in recs[0].reasoning


def test_recommendations_empty_on_hopeless_hardware():
    assert recommend(hw(avail=0.4, disk=0.2)) == []


# --- provider stream parsing ---


def test_parse_ollama_text_and_done():
    events = parse_ollama_chunk(json.dumps({"message": {"content": "Hi"}, "done": False}))
    assert events == [{"type": "text", "text": "Hi"}]
    done = parse_ollama_chunk(
        json.dumps({"message": {"content": ""}, "done": True, "prompt_eval_count": 5, "eval_count": 9})
    )
    assert done[-1]["usage"] == {"input_tokens": 5, "output_tokens": 9}


def test_parse_ollama_tool_call():
    line = json.dumps(
        {"message": {"tool_calls": [{"function": {"name": "search", "arguments": {"q": "x"}}}]}}
    )
    [event] = parse_ollama_chunk(line)
    assert event["tool_call"]["name"] == "search"
    assert event["tool_call"]["arguments"] == {"q": "x"}


def test_parse_openrouter_fragmented_tool_call():
    pending: dict = {}
    parse_openrouter_line(
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"read_page","arguments":"{\\"id\\":"}}]}}]}',
        pending,
    )
    parse_openrouter_line(
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"42\\"}"}}]}}]}',
        pending,
    )
    [event] = flush_pending_tools(pending)
    assert event["tool_call"] == {"id": "c1", "name": "read_page", "arguments": {"id": "42"}}


def test_parse_openrouter_text_and_usage():
    events = parse_openrouter_line('data: {"choices":[{"delta":{"content":"Hey"}}]}', {})
    assert events == [{"type": "text", "text": "Hey"}]
    events = parse_openrouter_line(
        'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":7}}', {}
    )
    assert events[0]["usage"] == {"input_tokens": 3, "output_tokens": 7}


# --- featured catalog matching ---


def test_match_featured_finds_by_pattern_not_hardcoded_ids():
    catalog = [
        {"id": "anthropic/claude-sonnet-5", "name": "Claude Sonnet 5", "created": 10},
        {"id": "anthropic/claude-opus-4.8", "name": "Claude Opus 4.8", "created": 11},
        {"id": "anthropic/claude-fable-5", "name": "Claude Fable 5", "created": 12},
        {"id": "deepseek/deepseek-v4-pro", "name": "DeepSeek V4 Pro", "created": 13},
        {"id": "deepseek/deepseek-v4-flash", "name": "DeepSeek V4 Flash", "created": 14},
        {"id": "openai/gpt-6.1", "name": "GPT-6.1", "created": 20},
        {"id": "openai/gpt-5.2", "name": "GPT-5.2", "created": 15},
        {"id": "openai/gpt-6.1-audio", "name": "GPT-6.1 Audio", "created": 21},
    ]
    featured = match_featured(catalog)
    assert featured["Claude Fable 5"] == "anthropic/claude-fable-5"
    assert featured["DeepSeek V4 Flash"] == "deepseek/deepseek-v4-flash"
    # Latest non-audio GPT wins.
    assert "openai/gpt-6.1" in featured.values()
    assert "openai/gpt-6.1-audio" not in featured.values()


def test_match_featured_tolerates_missing_models():
    featured = match_featured([{"id": "mistralai/mistral-large", "name": "Mistral", "created": 1}])
    assert featured == {}


# --- crypto + settings endpoint ---


def test_secret_roundtrip_and_tamper_rejection():
    token = encrypt_secret("sk-or-secret")
    assert token != "sk-or-secret"
    assert decrypt_secret(token) == "sk-or-secret"
    assert decrypt_secret("garbage") is None


async def test_ai_settings_roundtrip_without_key(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await user_client.get("/api/ai/settings", params={"workspace_id": ws})
    assert r.json() == {
        "provider": None, "default_model": None, "fast_model": None, "has_openrouter_key": False,
    }
    r = await user_client.put(
        f"/api/ai/settings?workspace_id={ws}",
        json={"provider": "ollama", "default_model": "qwen3:8b", "fast_model": "gemma3:1b"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["provider"] == "ollama" and out["default_model"] == "qwen3:8b"
    assert out["has_openrouter_key"] is False


async def test_ai_settings_owner_only(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "ai-owner@example.com", "password": "long-enough-1", "name": "O"},
    )
    ws = await make_workspace(client)
    invite = (await client.post(f"/api/workspaces/{ws}/invites", json={"role": "editor"})).json()
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={"email": "ai-editor@example.com", "password": "long-enough-1", "name": "E"},
    )
    await client.post(f"/api/workspaces/invites/{invite['id']}/accept")
    r = await client.put(f"/api/ai/settings?workspace_id={ws}", json={"provider": "ollama"})
    assert r.status_code == 403
    # Members can still read the (key-free) settings.
    assert (await client.get("/api/ai/settings", params={"workspace_id": ws})).status_code == 200


async def test_chat_test_conflict_when_unconfigured(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await user_client.post(
        "/api/ai/chat/test", json={"workspace_id": ws, "prompt": "hello"}
    )
    assert r.status_code == 409
