# Lore — architecture

A local-first, real-time collaborative workspace (Notion-class) with a deeply
integrated AI layer (RAG + agent + memory). This document is the map; the
decision log (`docs/decisions.md`) is the "why" for every non-obvious call.

## Shape

```
┌─────────────── apps/web (Next.js) ───────────────┐      ┌──────── apps/api (FastAPI) ────────┐
│  React 19 · Tailwind v4 · shadcn/ui              │      │  routers/  auth workspaces pages   │
│  BlockNote editor  ◄── Yjs ──►  y-websocket ─────┼─WS──►│  collab (pycrdt rooms)             │
│  TanStack Query · Zustand · Framer Motion        │      │  documents databases search        │
│  Ask Lore panel · command palette · databases    │─HTTP►│  ai (provider/hardware) assistant  │
└──────────────────────────────────────────────────┘  SSE │  agent inline                      │
                                                          └──────┬─────────────┬───────────────┘
                                                                 │             │
                                                   ┌─────────────▼───┐   ┌─────▼──────────────┐
                                                   │ Postgres 16 +   │   │ Ollama / OpenRouter │
                                                   │ pgvector        │   │ (LLM, user-chosen)  │
                                                   │ relational+FTS+ │   │ fastembed (local)   │
                                                   │ vectors         │   └─────────────────────┘
                                                   └─────────────────┘
```

One Postgres holds **everything**: relational data, full-text search (tsvector
GIN), and vector embeddings (pgvector HNSW). No separate search or vector store.

## Data model (Postgres)

- **users, workspaces, workspace_members, workspace_invites** — auth + membership
  (owner/editor/viewer). Argon2 passwords; JWT access/refresh in httpOnly cookies.
- **pages** — the spine. `kind ∈ {doc, database, row}`. A database **row is a page**,
  so rows get titles, icons, editor bodies, and collaboration for free; the sidebar
  filters `kind='row'` out. Fractional `position` for ordering; soft-delete trash.
- **documents** — one per page: BlockNote block JSON (`blocks`), extracted plain
  text (`text_content`, GIN-indexed for FTS/RAG), and a one-shot collab-seed marker.
- **ydoc_updates** — append-only Yjs update log per page (the CRDT source of truth),
  compacted into a single merged update past a threshold.
- **db_properties / db_views / db_values** — Notion databases: typed columns,
  saved views (table/board/list/calendar) with filter/sort/group config, and
  one JSONB cell per (row, property).
- **chunks** — embedded slices of documents for RAG: `embedding vector(384)`
  (HNSW cosine index) + FTS index, with `block_ids` for citation jumps.
- **conversations / messages** — Ask Lore chat history per user (messages carry
  citations). **memories** — distilled durable facts, per user+workspace.
- **ai_settings** — per-workspace provider choice, default/fast model, and the
  Fernet-encrypted OpenRouter key.

## Real-time collaboration (Phase 3)

Yjs in the browser ↔ `pycrdt` rooms on FastAPI over WebSocket. One room per page
(name = page id), hydrated from `ydoc_updates` before it accepts sync. Live
cursors + presence via Yjs awareness. Viewers get a socket adapter that drops
document-modifying y-protocol frames, so read-only is enforced server-side.
Legacy/imported pages are seeded into the CRDT by exactly one server-granted
client (prevents the duplicate-content race). The BlockNote JSON snapshot is
kept fresh by connected clients' debounced autosave — it's the read model for
export, search, and RAG.

## Search (Phase 5) and RAG (Phase 7)

`/api/search` is Postgres FTS (`websearch_to_tsquery` + `ts_headline` snippets)
over titles and extracted text, with an ILIKE prefix fallback. The **AI**
retrieval path (`ai/retrieval.py`) fuses pgvector cosine search with the same FTS
via **Reciprocal Rank Fusion**, scoped to the workspace/pages. Embeddings are
local (**fastembed**, bge-small, 384-d) in both provider modes, run in a
threadpool. Ingestion re-chunks + re-embeds a page on content change (background,
only when text changed); a workspace backfill/reindex exists too.

The **Ask Lore** assistant (`routers/assistant.py`) retrieves sources, injects
the user's memories, streams a grounded answer over SSE, emits `[n]` citations
(clickable → jump-and-flash the source block), and persists the conversation. A
background summarizer distills durable facts after each exchange. Notebook
generators (summary/study-guide/faq/outline) stream markdown the frontend turns
into a real page.

## AI providers, hardware, and the agent (Phases 6 & 8)

`ai/providers.py` is one `LLMProvider` abstraction over **Ollama** (local) and
**OpenRouter** (cloud), normalizing streaming + tool-calls to one event
vocabulary. `ai/hardware.py` probes the host accurately (real CPU name,
physical/logical cores, true VRAM via the driver registry on Windows);
`ai/hardware_calc.py` is a pure, unit-pinned calculator recommending local
models that fit. OpenRouter's Featured models resolve by pattern against the
live catalog (never hardcoded ids); keys are Fernet-encrypted at rest.

The **agent** (`routers/agent.py`) runs read tools (search/read/list) inline and
**proposes** writes as approval cards; the frontend applies approved actions
through the normal APIs, keeping a human in the loop for every mutation. Inline
AI (`routers/inline.py`): text rewrite (selection menu) and ghost-text
autocomplete via the fast model.

## Frontend structure

- `app/w/[workspaceId]/` — the authed shell: sidebar (tree, drawer on mobile),
  page view (editor / database / row properties), settings (AI, memory).
- `components/editor` — BlockNote bound to the collab session; custom AI
  formatting-toolbar button.
- `components/database` — table/board/list/calendar views + a client-side view
  engine (`lib/database-query.ts`).
- `components/assistant` — the Ask Lore panel (chat + agent modes, citations,
  approvals, generators).
- State: TanStack Query for server data (optimistic mutations), Zustand for UI
  (sidebar/palette/assistant/highlight), a refcounted registry for collab sessions.

## Testing

67 backend tests (pytest) cover auth + isolation, pages/tree/trash, databases,
collab CRDT convergence + compaction, search, the hardware calculator + provider
stream parsers, RAG retrieval (semantic match with zero keyword overlap),
chat-with-citations, memory, and the agent flow (scripted-provider). Model
generation is exercised through a fake provider so the pipeline is tested without
a live LLM.
