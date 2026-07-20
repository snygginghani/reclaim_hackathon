import uuid

from httpx import AsyncClient


def unique_email() -> str:
    return f"u{uuid.uuid4().hex[:10]}@example.com"


async def test_register_login_me_flow(client: AsyncClient):
    email = unique_email()
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": "long-enough-1", "name": "Rex"}
    )
    assert r.status_code == 201
    assert r.json()["email"] == email

    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["name"] == "Rex"

    r = await client.post("/api/auth/logout")
    assert r.status_code == 204
    r = await client.get("/api/auth/me")
    assert r.status_code == 401

    r = await client.post("/api/auth/login", json={"email": email, "password": "long-enough-1"})
    assert r.status_code == 200
    r = await client.get("/api/auth/me")
    assert r.status_code == 200


async def test_register_duplicate_email_conflicts(client: AsyncClient):
    email = unique_email()
    body = {"email": email, "password": "long-enough-1", "name": "One"}
    assert (await client.post("/api/auth/register", json=body)).status_code == 201
    assert (await client.post("/api/auth/register", json=body)).status_code == 409


async def test_login_wrong_password_is_401_without_leaking(client: AsyncClient):
    email = unique_email()
    await client.post(
        "/api/auth/register", json={"email": email, "password": "long-enough-1", "name": "X"}
    )
    r_wrong_pw = await client.post("/api/auth/login", json={"email": email, "password": "wrong-pw-1"})
    r_no_user = await client.post(
        "/api/auth/login", json={"email": unique_email(), "password": "wrong-pw-1"}
    )
    assert r_wrong_pw.status_code == r_no_user.status_code == 401
    assert r_wrong_pw.json() == r_no_user.json()  # identical: no account enumeration


async def test_refresh_rotates_session(client: AsyncClient):
    email = unique_email()
    await client.post(
        "/api/auth/register", json={"email": email, "password": "long-enough-1", "name": "R"}
    )
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_password_too_short_rejected(client: AsyncClient):
    r = await client.post(
        "/api/auth/register", json={"email": unique_email(), "password": "short", "name": "S"}
    )
    assert r.status_code == 422
