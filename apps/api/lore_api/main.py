from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import asyncio

from .ai.embeddings import warm
from .collab import make_server
from .config import get_settings
from .db import engine
from .routers import (
    agent,
    ai,
    assistant,
    auth,
    collab,
    databases,
    documents,
    inline,
    pages,
    search,
    workspaces,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model off the event loop so the first chat isn't slow.
    asyncio.get_event_loop().run_in_executor(None, warm)
    async with make_server() as collab_server:
        app.state.collab_server = collab_server
        yield


app = FastAPI(title="Lore API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(pages.router)
app.include_router(documents.router)
app.include_router(collab.router)
app.include_router(databases.router)
app.include_router(search.router)
app.include_router(ai.router)
app.include_router(assistant.router)
app.include_router(agent.router)
app.include_router(inline.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_origin_regex=get_settings().cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    async with engine.connect() as conn:
        db_ok = (await conn.execute(text("SELECT 1"))).scalar() == 1
        vector_ok = (
            await conn.execute(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'"))
        ).scalar() == 1
    return {"status": "ok", "db": db_ok, "pgvector": vector_ok}
