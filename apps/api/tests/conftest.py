import os

# Point the app at a dedicated test database BEFORE lore_api is imported anywhere.
os.environ["LORE_DATABASE_URL"] = "postgresql+asyncpg://lore:lore_dev_password@localhost:5433/lore_test"

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from lore_api.db import Base, engine  # noqa: E402
from lore_api.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _create_test_database():
    conn = await asyncpg.connect(
        user="lore", password="lore_dev_password", host="localhost", port=5433, database="postgres"
    )
    exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'lore_test'")
    if not exists:
        await conn.execute("CREATE DATABASE lore_test")
    await conn.close()

    # pgvector must be enabled before create_all builds the chunks.embedding column.
    test_conn = await asyncpg.connect(
        user="lore", password="lore_dev_password", host="localhost", port=5433, database="lore_test"
    )
    await test_conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await test_conn.close()

    async with engine.begin() as db:
        await db.run_sync(Base.metadata.drop_all)
        await db.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture
async def client():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def user_client(client: AsyncClient):
    """A client already registered and logged in (cookies held by httpx)."""
    import uuid

    resp = await client.post(
        "/api/auth/register",
        json={
            "username": f"ada-{uuid.uuid4().hex[:10]}",
            "password": "correct-horse-9",
            "name": "Ada",
        },
    )
    assert resp.status_code == 201, resp.text
    return client
