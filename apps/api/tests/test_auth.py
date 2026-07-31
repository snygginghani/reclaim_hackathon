import uuid

from httpx import AsyncClient


def unique_username() -> str:
    return f"u{uuid.uuid4().hex[:10]}"


async def test_register_login_me_flow(client: AsyncClient):
    username = unique_username()
    r = await client.post(
        "/api/auth/register", json={"username": username, "password": "long-enough-1", "name": "Rex"}
    )
    assert r.status_code == 201
    assert r.json()["username"] == username

    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["name"] == "Rex"

    r = await client.post("/api/auth/logout")
    assert r.status_code == 204
    r = await client.get("/api/auth/me")
    assert r.status_code == 401

    r = await client.post(
        "/api/auth/login", json={"username": username, "password": "long-enough-1"}
    )
    assert r.status_code == 200
    r = await client.get("/api/auth/me")
    assert r.status_code == 200


async def test_register_duplicate_username_conflicts(client: AsyncClient):
    username = unique_username()
    body = {"username": username, "password": "long-enough-1", "name": "One"}
    assert (await client.post("/api/auth/register", json=body)).status_code == 201
    assert (await client.post("/api/auth/register", json=body)).status_code == 409


async def test_login_wrong_password_is_401_without_leaking(client: AsyncClient):
    username = unique_username()
    await client.post(
        "/api/auth/register", json={"username": username, "password": "long-enough-1", "name": "X"}
    )
    r_wrong_pw = await client.post(
        "/api/auth/login", json={"username": username, "password": "wrong-pw-1"}
    )
    r_no_user = await client.post(
        "/api/auth/login", json={"username": unique_username(), "password": "wrong-pw-1"}
    )
    assert r_wrong_pw.status_code == r_no_user.status_code == 401
    assert r_wrong_pw.json() == r_no_user.json()  # identical: no account enumeration


async def test_refresh_rotates_session(client: AsyncClient):
    username = unique_username()
    await client.post(
        "/api/auth/register", json={"username": username, "password": "long-enough-1", "name": "R"}
    )
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_password_too_short_rejected(client: AsyncClient):
    r = await client.post(
        "/api/auth/register", json={"username": unique_username(), "password": "short", "name": "S"}
    )
    assert r.status_code == 422


async def test_username_is_normalized_to_lowercase(client: AsyncClient):
    raw = unique_username()
    r = await client.post(
        "/api/auth/register",
        json={"username": f"  {raw.upper()}  ", "password": "long-enough-1", "name": "Ada"},
    )
    assert r.status_code == 201
    assert r.json()["username"] == raw

    await client.post("/api/auth/logout")
    r = await client.post("/api/auth/login", json={"username": raw, "password": "long-enough-1"})
    assert r.status_code == 200


async def test_register_rejects_malformed_usernames(client: AsyncClient):
    for bad in ("ab", "has space", "-leading", "_leading", "way" + "y" * 30, "Ünicode", ""):
        r = await client.post(
            "/api/auth/register",
            json={"username": bad, "password": "long-enough-1", "name": "N"},
        )
        assert r.status_code == 422, f"{bad!r} should be rejected"


async def test_register_rejects_reserved_username(client: AsyncClient):
    r = await client.post(
        "/api/auth/register", json={"username": "admin", "password": "long-enough-1", "name": "A"}
    )
    assert r.status_code == 422


async def test_login_with_malformed_username_is_401_not_422(client: AsyncClient):
    # A 422 here would distinguish "not a valid username" from "wrong password".
    r = await client.post(
        "/api/auth/login", json={"username": "not a username", "password": "long-enough-1"}
    )
    assert r.status_code == 401
