# Lore

**Your second brain, with a memory.** A local-first, real-time collaborative workspace — Notion-class
pages, databases, and search, with a deeply integrated AI assistant (RAG + agent + persistent memory)
that runs on a local model or your own OpenRouter key.

> Status: under active construction. See `docs/brief.md` for the product spec,
> `docs/decisions.md` for the engineering decision log, and `docs/design-system.md` for the design system.

## Stack

- **Web:** Next.js (App Router, TS), Tailwind v4, shadcn/ui, BlockNote, Yjs, TanStack Query, Zustand, Framer Motion
- **API:** Python / FastAPI, SQLAlchemy 2 async, pycrdt-websocket, fastembed
- **DB:** PostgreSQL 16 + pgvector (relational + FTS + vectors in one place)
- **AI:** Ollama (local) or OpenRouter (cloud) behind one provider layer

## Run it (dev)

Prereqs: Docker Desktop, Node 20+, Python 3.12+, [uv](https://docs.astral.sh/uv/).

```powershell
# first time only
cd apps/api; uv sync; cd ../web; npm install; cd ../..

# every time — starts db + api + web in separate windows
powershell -File scripts/dev.ps1
```

- Web: http://localhost:3000
- API docs: http://localhost:8300/docs
- Postgres: localhost:5433 (`lore` / `lore_dev_password`)

## Repository layout

| Path | What |
|---|---|
| `apps/web` | Next.js frontend |
| `apps/api` | FastAPI backend (`lore_api/`) |
| `packages/shared` | OpenAPI-generated API client (generated, do not edit) |
| `docs/` | Brief, decision log, design system, architecture |
| `scripts/` | Dev/seed scripts |
