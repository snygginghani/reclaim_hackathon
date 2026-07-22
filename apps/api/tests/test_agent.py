import json
from types import SimpleNamespace

from httpx import AsyncClient

from lore_api.routers import agent as agent_router
from lore_api.routers import inline as inline_router

from .test_pages import make_page, make_workspace


def _events(body: str) -> list[dict]:
    out = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


class ScriptedProvider:
    """Yields a scripted list of events per successive chat_stream call."""

    def __init__(self, script):
        self.script = script
        self.calls = 0

    async def chat_stream(self, messages, model, tools=None, temperature=0.7, max_tokens=None):
        step = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        for ev in step:
            yield ev


async def test_agent_searches_then_proposes_write(user_client: AsyncClient, monkeypatch):
    ws = await make_workspace(user_client)

    script = [
        # 1) search first
        [{"type": "tool_call", "tool_call": {"id": "t1", "name": "search_workspace", "arguments": {"query": "deploys"}}}],
        # 2) propose a new page (write -> approval)
        [
            {"type": "text", "text": "Drafting that page. "},
            {
                "type": "tool_call",
                "tool_call": {
                    "id": "t2",
                    "name": "create_page",
                    "arguments": {"title": "Deploy notes", "content_markdown": "# Deploys\nEvery Friday."},
                },
            },
        ],
        # 3) wrap-up
        [{"type": "text", "text": "Proposed a page for your review."}],
    ]
    fake = ScriptedProvider(script)

    async def fake_resolve(db, wsid):
        return fake, SimpleNamespace(default_model="m", provider="ollama")

    monkeypatch.setattr(agent_router, "resolve_provider", fake_resolve)

    async with user_client.stream(
        "POST", "/api/ai/agent", json={"workspace_id": ws, "message": "make a page about deploys"}
    ) as resp:
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk
    events = _events(body)
    kinds = [e["type"] for e in events]

    assert "tool" in kinds and "approval" in kinds and kinds[-1] == "done"
    tool_ev = next(e for e in events if e["type"] == "tool")
    assert tool_ev["name"] == "search_workspace"
    approval = next(e for e in events if e["type"] == "approval")
    assert approval["tool"] == "create_page"
    assert approval["preview"]["title"] == "Deploy notes"
    assert "Deploys" in approval["preview"]["summary"]
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "review" in text


async def test_agent_requires_editor(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "agent-owner@example.com", "password": "long-enough-1", "name": "O"},
    )
    ws = await make_workspace(client)
    invite = (await client.post(f"/api/workspaces/{ws}/invites", json={"role": "viewer"})).json()
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={"email": "agent-viewer@example.com", "password": "long-enough-1", "name": "V"},
    )
    await client.post(f"/api/workspaces/invites/{invite['id']}/accept")
    r = await client.post("/api/ai/agent", json={"workspace_id": ws, "message": "do something"})
    assert r.status_code == 403


async def test_rewrite_streams(user_client: AsyncClient, monkeypatch):
    ws = await make_workspace(user_client)
    fake = ScriptedProvider([[{"type": "text", "text": "Improved sentence."}]])

    async def fake_resolve(db, wsid):
        return fake, SimpleNamespace(default_model="m", provider="ollama")

    monkeypatch.setattr(inline_router, "resolve_provider", fake_resolve)
    async with user_client.stream(
        "POST",
        "/api/ai/rewrite",
        json={"workspace_id": ws, "text": "bad sentence", "action": "improve"},
    ) as resp:
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk
    text = "".join(e["text"] for e in _events(body) if e["type"] == "text")
    assert "Improved" in text


async def test_autocomplete_uses_fast_model(user_client: AsyncClient, monkeypatch):
    ws = await make_workspace(user_client)
    await user_client.put(
        "/api/ai/settings",
        json={"provider": "ollama", "default_model": "big", "fast_model": "small"},
    )
    fake = ScriptedProvider([[{"type": "text", "text": " world of embeddings"}]])
    monkeypatch.setattr(inline_router, "provider_for", lambda settings: fake)

    r = await user_client.post(
        "/api/ai/autocomplete", json={"workspace_id": ws, "context": "Hello"}
    )
    assert r.status_code == 200
    assert "embeddings" in r.json()["completion"]


async def test_autocomplete_empty_when_unconfigured(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await user_client.post(
        "/api/ai/autocomplete", json={"workspace_id": ws, "context": "Hello"}
    )
    assert r.json() == {"completion": ""}
