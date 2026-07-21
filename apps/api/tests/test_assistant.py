import json
import uuid
from types import SimpleNamespace

from httpx import AsyncClient

from lore_api.ai.ingest import ingest_page
from lore_api.ai.rag import build_sources, system_prompt, used_citations
from lore_api.ai.retrieval import Retrieved
from lore_api.routers import assistant as assistant_router

from .test_pages import make_page, make_workspace
from .test_rag import para


# --------------------------------------------------------------------------- rag units


def _fake_retrieved(page_id: str, title: str, block_ids: list[str], text: str) -> Retrieved:
    chunk = SimpleNamespace(page_id=uuid.UUID(page_id), block_ids=block_ids, text=text, heading=None)
    return Retrieved(chunk=chunk, page_title=title)


def test_build_sources_and_citation_filtering():
    r = [
        _fake_retrieved(str(uuid.uuid4()), "Budget", ["b1"], "Q3 budget is 40k."),
        _fake_retrieved(str(uuid.uuid4()), "Team", ["b2"], "Ada leads eng."),
    ]
    sources = build_sources(r)
    assert [s["n"] for s in sources] == [1, 2]
    prompt = system_prompt(sources, ["Prefers concise answers"])
    assert "[1] Budget" in prompt and "Prefers concise" in prompt
    # Only cited sources are kept.
    used = used_citations("The budget is 40k [1]. Nothing else.", sources)
    assert [s["n"] for s in used] == [1]


def test_system_prompt_handles_no_sources():
    p = system_prompt([], [])
    assert "No workspace sources" in p


# --------------------------------------------------------------------------- memory CRUD


async def test_memory_crud_and_isolation(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await user_client.post(
        f"/api/ai/memory?workspace_id={ws}",
        json={"content": "Works in Pacific time", "kind": "fact"},
    )
    assert r.status_code == 201
    mem_id = r.json()["id"]
    assert r.json()["source"] == "manual"

    r = await user_client.get(f"/api/ai/memory?workspace_id={ws}")
    assert [m["content"] for m in r.json()] == ["Works in Pacific time"]

    r = await user_client.patch(
        f"/api/ai/memory/{mem_id}", json={"content": "Works in Eastern time", "kind": "preference"}
    )
    assert r.json()["content"] == "Works in Eastern time"

    assert (await user_client.delete(f"/api/ai/memory/{mem_id}")).status_code == 204
    assert (await user_client.get(f"/api/ai/memory?workspace_id={ws}")).json() == []


async def test_memory_is_per_user(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "mem-a@example.com", "password": "long-enough-1", "name": "A"},
    )
    ws = await make_workspace(client)
    await client.post(f"/api/ai/memory?workspace_id={ws}", json={"content": "A's secret fact"})
    invite = (await client.post(f"/api/workspaces/{ws}/invites", json={"role": "editor"})).json()

    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={"email": "mem-b@example.com", "password": "long-enough-1", "name": "B"},
    )
    await client.post(f"/api/workspaces/invites/{invite['id']}/accept")
    # B is in the same workspace but sees none of A's memories.
    assert (await client.get(f"/api/ai/memory?workspace_id={ws}")).json() == []


# --------------------------------------------------------------------------- streamed chat


class FakeProvider:
    """Emits a canned grounded answer that cites source [1]."""

    def __init__(self, reply: str):
        self.reply = reply
        self.seen_system = ""

    async def chat_stream(self, messages, model, tools=None, temperature=0.7, max_tokens=None):
        self.seen_system = messages[0]["content"]
        for word in self.reply.split(" "):
            yield {"type": "text", "text": word + " "}
        yield {"type": "usage", "usage": {"input_tokens": 10, "output_tokens": 5}}


def _sse_events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


async def test_chat_streams_sources_text_and_citations(user_client: AsyncClient, monkeypatch):
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Ops runbook")
    await user_client.put(
        f"/api/pages/{page['id']}/content",
        json={"blocks": [para("The deploy pipeline runs on GitHub Actions every Friday.", "d1")]},
    )
    await ingest_page(uuid.UUID(page["id"]))

    fake = FakeProvider("Deploys run on GitHub Actions every Friday [1].")

    async def fake_resolve(db, wsid):
        return fake, SimpleNamespace(default_model="fake-model", provider="ollama")

    monkeypatch.setattr(assistant_router, "resolve_provider", fake_resolve)

    async with user_client.stream(
        "POST",
        "/api/ai/chat",
        json={"workspace_id": ws, "message": "when do we deploy?"},
    ) as resp:
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk
    events = _sse_events(body)

    kinds = [e["type"] for e in events]
    assert kinds[0] == "conversation" and "sources" in kinds and "done" in kinds
    sources_ev = next(e for e in events if e["type"] == "sources")
    assert sources_ev["sources"][0]["block_ids"] == ["d1"]
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "GitHub Actions" in text
    done = next(e for e in events if e["type"] == "done")
    assert done["citations"] and done["citations"][0]["page_title"] == "Ops runbook"
    # The system prompt actually carried the retrieved source.
    assert "GitHub Actions" in fake.seen_system

    # The exchange was persisted as a conversation.
    convs = (await user_client.get(f"/api/ai/conversations?workspace_id={ws}")).json()
    assert len(convs) == 1
    msgs = (await user_client.get(f"/api/ai/conversations/{convs[0]['id']}")).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["citations"][0]["page_title"] == "Ops runbook"


async def test_chat_requires_configured_ai(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await user_client.post(
        "/api/ai/chat", json={"workspace_id": ws, "message": "hello"}
    )
    assert r.status_code == 409
