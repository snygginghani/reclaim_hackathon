"""End-to-end Obsidian import: build an in-memory .zip vault, POST it as multipart,
and assert the pages, folder hierarchy, wikilink resolution, and embed re-host."""

import io
import json
import zipfile

import pytest
from httpx import AsyncClient

from .test_pages import make_workspace


def _vault(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def _sse_events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


# A vault wrapped in a single top-level folder (which the adapter strips), with a
# nested note, a wikilink, a standalone image embed, and an .obsidian config to skip.
VAULT = _vault({
    "MyVault/Home.md": b"# Home\n\nSee [[Projects/Roadmap]]\n\n![[logo.png]]\n",
    "MyVault/Projects/Roadmap.md": b"# Roadmap\n\n- [x] ship it\n- [ ] later\n",
    "MyVault/logo.png": b"PNGBYTES",
    "MyVault/.obsidian/app.json": b"{}",
})


@pytest.fixture(autouse=True)
def _patch_obsidian(monkeypatch):
    import lore_api.migrate.engine as engine
    import lore_api.routers.obsidian as router

    monkeypatch.setattr(engine, "save_bytes", lambda data, ext=None: "/uploads/fake.png")

    async def fake_ingest(page_id) -> None:
        return None

    monkeypatch.setattr(router, "ingest_page", fake_ingest)


async def _import(client: AsyncClient, ws: str, data: bytes):
    return await client.post(
        "/api/obsidian/import",
        data={"workspace_id": ws},
        files={"file": ("vault.zip", data, "application/zip")},
    )


async def test_full_import(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await _import(user_client, ws, VAULT)
    assert r.status_code == 200, r.text
    events = _sse_events(r.text)
    done = [e for e in events if e["type"] == "done"]
    assert done and done[0]["pages"] == 3, events  # Projects folder + Home + Roadmap

    pages = (await user_client.get("/api/pages", params={"workspace_id": ws})).json()
    by_title = {p["title"]: p for p in pages}
    assert {"Home", "Projects", "Roadmap"} <= set(by_title)
    # Root note has no parent; the nested note hangs off its folder container.
    assert by_title["Home"]["parent_id"] is None
    assert by_title["Projects"]["parent_id"] is None
    assert by_title["Roadmap"]["parent_id"] == by_title["Projects"]["id"]

    # Home body: the wikilink resolved to the Roadmap page, and the image re-hosted.
    home = (await user_client.get(f"/api/pages/{by_title['Home']['id']}/content")).json()
    blocks = home["blocks"]
    link = next(
        i for b in blocks if isinstance(b.get("content"), list)
        for i in b["content"] if i.get("type") == "link"
    )
    assert link["href"] == f"/w/{ws}/p/{by_title['Roadmap']['id']}"
    img = next(b for b in blocks if b["type"] == "image")
    assert img["props"]["url"] == "/uploads/fake.png"

    # Roadmap body carried its task list over.
    roadmap = (await user_client.get(f"/api/pages/{by_title['Roadmap']['id']}/content")).json()
    checks = [b for b in roadmap["blocks"] if b["type"] == "checkListItem"]
    assert any(b["props"]["checked"] for b in checks)
    assert any(not b["props"]["checked"] for b in checks)


async def test_rejects_non_zip(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    r = await _import(user_client, ws, b"this is not a zip")
    assert r.status_code == 400
