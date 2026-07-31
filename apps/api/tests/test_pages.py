from httpx import AsyncClient


async def make_workspace(client: AsyncClient, name: str = "Acme") -> str:
    r = await client.post("/api/workspaces", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def make_page(client: AsyncClient, ws: str, title: str, parent: str | None = None) -> dict:
    r = await client.post(
        "/api/pages", json={"workspace_id": ws, "title": title, "parent_id": parent}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_workspace_create_and_list(user_client: AsyncClient):
    ws_id = await make_workspace(user_client, "Research")
    r = await user_client.get("/api/workspaces")
    assert any(w["id"] == ws_id and w["role"] == "owner" for w in r.json())


async def test_page_tree_crud(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    root = await make_page(user_client, ws, "Roadmap")
    child = await make_page(user_client, ws, "Q3", parent=root["id"])

    r = await user_client.get("/api/pages", params={"workspace_id": ws})
    pages = r.json()
    assert {p["title"] for p in pages} == {"Roadmap", "Q3"}
    assert next(p for p in pages if p["title"] == "Q3")["parent_id"] == root["id"]

    r = await user_client.patch(f"/api/pages/{child['id']}", json={"title": "Q4", "icon": "🎯"})
    assert r.json()["title"] == "Q4" and r.json()["icon"] == "🎯"


async def test_move_page_reorders_and_reparents(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    a = await make_page(user_client, ws, "A")
    b = await make_page(user_client, ws, "B")
    c = await make_page(user_client, ws, "C")

    # Move C to the top (before A).
    r = await user_client.post(f"/api/pages/{c['id']}/move", json={"after_id": None})
    assert r.status_code == 200
    r = await user_client.get("/api/pages", params={"workspace_id": ws})
    roots = [p["title"] for p in r.json() if p["parent_id"] is None]
    assert roots == ["C", "A", "B"]

    # Nest B under A.
    r = await user_client.post(f"/api/pages/{b['id']}/move", json={"parent_id": a["id"]})
    assert r.json()["parent_id"] == a["id"]

    # A cannot move into its own descendant B.
    r = await user_client.post(f"/api/pages/{a['id']}/move", json={"parent_id": b["id"]})
    assert r.status_code == 400


async def test_trash_restore_and_permanent_delete(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    parent = await make_page(user_client, ws, "Parent")
    child = await make_page(user_client, ws, "Child", parent=parent["id"])

    # Trashing the parent trashes the subtree.
    await user_client.delete(f"/api/pages/{parent['id']}")
    live = (await user_client.get("/api/pages", params={"workspace_id": ws})).json()
    assert live == []
    trashed = (
        await user_client.get("/api/pages", params={"workspace_id": ws, "trashed": True})
    ).json()
    assert {p["title"] for p in trashed} == {"Parent", "Child"}

    # Restore brings the subtree back.
    await user_client.post(f"/api/pages/{parent['id']}/restore")
    live = (await user_client.get("/api/pages", params={"workspace_id": ws})).json()
    assert {p["title"] for p in live} == {"Parent", "Child"}

    # Permanent delete requires trash first, then cascades.
    r = await user_client.delete(f"/api/pages/{parent['id']}/permanent")
    assert r.status_code == 400
    await user_client.delete(f"/api/pages/{parent['id']}")
    r = await user_client.delete(f"/api/pages/{parent['id']}/permanent")
    assert r.status_code == 204
    trashed = (
        await user_client.get("/api/pages", params={"workspace_id": ws, "trashed": True})
    ).json()
    assert trashed == []


async def test_favorites_roundtrip(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    page = await make_page(user_client, ws, "Fav me")
    r = await user_client.put(f"/api/pages/{page['id']}/favorite")
    assert r.status_code == 200
    favs = (
        await user_client.get("/api/pages/favorites/mine", params={"workspace_id": ws})
    ).json()
    assert [f["page_id"] for f in favs] == [page["id"]]
    await user_client.delete(f"/api/pages/{page['id']}/favorite")
    favs = (
        await user_client.get("/api/pages/favorites/mine", params={"workspace_id": ws})
    ).json()
    assert favs == []


async def test_workspace_isolation(client: AsyncClient):
    """A second user cannot see or touch the first user's workspace."""
    await client.post(
        "/api/auth/register",
        json={"username": "owner", "password": "long-enough-1", "name": "Owner"},
    )
    ws = await make_workspace(client, "Private")
    page = await make_page(client, ws, "Secret")

    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={"username": "intruder", "password": "long-enough-1", "name": "Intruder"},
    )
    assert (await client.get("/api/pages", params={"workspace_id": ws})).status_code == 404
    assert (await client.get(f"/api/pages/{page['id']}")).status_code == 404
    assert (
        await client.patch(f"/api/pages/{page['id']}", json={"title": "Hacked"})
    ).status_code == 404


async def test_invite_flow(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"username": "host", "password": "long-enough-1", "name": "Host"},
    )
    ws = await make_workspace(client, "Team")
    invite = (await client.post(f"/api/workspaces/{ws}/invites", json={"role": "editor"})).json()

    await client.post("/api/auth/logout")
    # Invite preview works logged out (join page shows workspace name pre-signup).
    r = await client.get(f"/api/workspaces/invites/{invite['id']}")
    assert r.json()["workspace_name"] == "Team"

    await client.post(
        "/api/auth/register",
        json={"username": "guest", "password": "long-enough-1", "name": "Guest"},
    )
    r = await client.post(f"/api/workspaces/invites/{invite['id']}/accept")
    assert r.status_code == 200 and r.json()["role"] == "editor"
    # Guest can now list pages.
    assert (await client.get("/api/pages", params={"workspace_id": ws})).status_code == 200
