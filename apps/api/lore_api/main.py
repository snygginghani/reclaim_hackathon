from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import get_settings
from .db import engine

app = FastAPI(title="Lore API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
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
