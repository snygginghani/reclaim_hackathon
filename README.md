# Lore

**Your second brain, with a memory.** A local-first, real-time collaborative
workspace — Notion-class pages, databases, and search — with a deeply integrated
AI assistant (RAG + agent + persistent memory) that runs on a **local model** or
**your own OpenRouter key**. Every AI answer cites the exact source block.

> Named Lore because the built-in AI learns your lore — your projects, context,
> and history — and works alongside you inside your workspace.

## What's inside

- **Editor** — a Notion-style block editor (BlockNote): slash commands, all block
  types, markdown shortcuts, drag handles, images, tables, code.
- **Real-time collaboration** — live cursors and presence, character-level CRDT
  merge (Yjs ↔ pycrdt), offline edits reconcile on reconnect.
- **Databases** — typed properties and **table / board / list / calendar** views
  with filters, sorts, and grouping; every row opens as a full page.
- **Search** — instant Cmd+K palette over hybrid full-text + semantic search.
- **Ask Lore** — a docked assistant (⌘J) that answers from your workspace with
  clickable citations, remembers durable facts about you, generates documents
  (summary/study-guide/FAQ/outline), and — in **Agent** mode — proposes edits you
  approve before anything changes. Plus inline AI on selected text.
- **Your AI, your choice** — pick a local model (Ollama) sized to your hardware by
  a built-in calculator, or bring an OpenRouter key. Embeddings always run locally.

See `docs/architecture.md` for the full map and `docs/decisions.md` for the why.

## Stack

Next.js 15 (App Router, TS) · Tailwind v4 · shadcn/ui · BlockNote · Yjs ·
TanStack Query · Zustand · Framer Motion · **FastAPI** · SQLAlchemy 2 async ·
pycrdt-websocket · fastembed · **PostgreSQL 16 + pgvector** · Ollama / OpenRouter.

## Run it (dev)

Prereqs: Docker Desktop, Node 20+, Python 3.12+, [uv](https://docs.astral.sh/uv/).

```powershell
# first time only
docker compose up -d db                 # Postgres + pgvector on :5433
cd apps/api;  uv sync;  uv run alembic upgrade head
uv run python scripts/seed.py           # optional: demo workspace + content
cd ../web;  npm install;  cd ../..

# every time — starts db + api + web in their own windows
powershell -File scripts/dev.ps1
```

- Web: http://localhost:3000  ·  API docs: http://localhost:8300/docs
- Demo login (after seeding): `demo@lore.local` / `demo-password-1`

To enable AI chat, open **Settings → AI** in the app and either install a
recommended local model (needs [Ollama](https://ollama.com/download)) or paste an
OpenRouter key. Everything else works without a model.

## Tests

```powershell
cd apps/api;  uv run pytest        # 67 backend tests
cd apps/web;  npx tsc --noEmit && npx eslint src
```

## Repository layout

| Path | What |
|---|---|
| `apps/web` | Next.js frontend |
| `apps/api` | FastAPI backend (`lore_api/`), migrations, tests, `scripts/seed.py` |
| `docs/` | brief · architecture · decisions · design system |
| `scripts/dev.ps1` | one-command dev stack |
