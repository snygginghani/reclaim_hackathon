from httpx import AsyncClient

from .test_pages import make_workspace


async def make_db(client: AsyncClient, ws: str, title: str = "Tasks") -> dict:
    r = await client.post("/api/databases", json={"workspace_id": ws, "title": title})
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_database_with_defaults(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    d = await make_db(user_client, ws)
    assert d["page"]["kind"] == "database"
    assert [v["type"] for v in d["views"]] == ["table"]
    assert d["properties"][0]["name"] == "Status"
    assert len(d["properties"][0]["options"]["choices"]) == 3
    # The database page appears in the sidebar list; no rows do.
    pages = (await user_client.get("/api/pages", params={"workspace_id": ws})).json()
    assert any(p["id"] == d["page"]["id"] for p in pages)


async def test_property_crud_and_validation(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    d = await make_db(user_client, ws)
    db_id = d["page"]["id"]

    r = await user_client.post(
        f"/api/databases/{db_id}/properties", json={"name": "Due", "type": "date"}
    )
    assert r.status_code == 201
    due = r.json()

    r = await user_client.post(
        f"/api/databases/{db_id}/properties", json={"name": "Bad", "type": "wormhole"}
    )
    assert r.status_code == 400

    r = await user_client.patch(
        f"/api/databases/{db_id}/properties/{due['id']}", json={"name": "Deadline"}
    )
    assert r.json()["name"] == "Deadline"

    r = await user_client.delete(f"/api/databases/{db_id}/properties/{due['id']}")
    assert r.status_code == 204
    d2 = (await user_client.get(f"/api/databases/{db_id}")).json()
    assert all(p["id"] != due["id"] for p in d2["properties"])


async def test_rows_values_roundtrip(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    d = await make_db(user_client, ws)
    db_id = d["page"]["id"]
    status_prop = d["properties"][0]["id"]

    r = await user_client.post(
        f"/api/databases/{db_id}/rows",
        json={"title": "Ship Phase 4", "values": {status_prop: {"select": "doing"}}},
    )
    assert r.status_code == 201
    row = r.json()
    assert row["values"][status_prop] == {"select": "doing"}

    rows = (await user_client.get(f"/api/databases/{db_id}/rows")).json()
    assert [x["title"] for x in rows] == ["Ship Phase 4"]

    # Update + clear values.
    r = await user_client.patch(
        f"/api/databases/{db_id}/rows/{row['id']}/values",
        json={"values": {status_prop: {"select": "done"}}},
    )
    assert r.json()["values"][status_prop] == {"select": "done"}
    r = await user_client.patch(
        f"/api/databases/{db_id}/rows/{row['id']}/values",
        json={"values": {status_prop: None}},
    )
    assert r.json()["values"] == {}

    # Unknown property id rejected.
    r = await user_client.patch(
        f"/api/databases/{db_id}/rows/{row['id']}/values",
        json={"values": {db_id: {"select": "x"}}},
    )
    assert r.status_code == 400


async def test_rows_hidden_from_sidebar_but_open_as_pages(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    d = await make_db(user_client, ws)
    db_id = d["page"]["id"]
    row = (
        await user_client.post(f"/api/databases/{db_id}/rows", json={"title": "Row page"})
    ).json()

    pages = (await user_client.get("/api/pages", params={"workspace_id": ws})).json()
    assert all(p["id"] != row["id"] for p in pages)

    # ...but the row IS a page: it opens, has a document, and can be edited.
    r = await user_client.get(f"/api/pages/{row['id']}")
    assert r.status_code == 200 and r.json()["kind"] == "row"
    r = await user_client.get(f"/api/pages/{row['id']}/content")
    assert r.status_code == 200
    ctx = (await user_client.get(f"/api/databases/rows/{row['id']}/context")).json()
    assert ctx["page"]["id"] == db_id


async def test_views_crud_and_last_view_protection(user_client: AsyncClient):
    ws = await make_workspace(user_client)
    d = await make_db(user_client, ws)
    db_id = d["page"]["id"]
    table_view = d["views"][0]["id"]

    r = await user_client.post(
        f"/api/databases/{db_id}/views", json={"name": "Board", "type": "board"}
    )
    assert r.status_code == 201
    board = r.json()

    r = await user_client.patch(
        f"/api/databases/{db_id}/views/{board['id']}",
        json={"config": {"group_by": d["properties"][0]["id"]}},
    )
    assert r.json()["config"]["group_by"] == d["properties"][0]["id"]

    assert (
        await user_client.delete(f"/api/databases/{db_id}/views/{board['id']}")
    ).status_code == 204
    # The last remaining view cannot be deleted.
    assert (
        await user_client.delete(f"/api/databases/{db_id}/views/{table_view}")
    ).status_code == 400


async def test_database_isolation(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"username": "db-owner", "password": "long-enough-1", "name": "O"},
    )
    ws = await make_workspace(client)
    d = await make_db(client, ws)
    db_id = d["page"]["id"]

    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={"username": "db-intruder", "password": "long-enough-1", "name": "I"},
    )
    assert (await client.get(f"/api/databases/{db_id}")).status_code == 404
    assert (await client.get(f"/api/databases/{db_id}/rows")).status_code == 404
    assert (
        await client.post(f"/api/databases/{db_id}/rows", json={"title": "sneak"})
    ).status_code == 404
