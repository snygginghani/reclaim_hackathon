# Setup

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
- Demo login (after seeding): `demo@example.com` / `demo-password-1`

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
| `docs/` | brief · architecture · decisions · design system · setup |
| `scripts/dev.ps1` | one-command dev stack |

## Stack

Next.js 15 (App Router, TS) · Tailwind v4 · shadcn/ui · BlockNote · Yjs ·
TanStack Query · Zustand · Framer Motion · **FastAPI** · SQLAlchemy 2 async ·
pycrdt-websocket · fastembed · **PostgreSQL 16 + pgvector** · Ollama / OpenRouter.
