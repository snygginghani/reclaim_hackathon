# Build "Lore" — a Notion-class, AI-native workspace (final product, not a demo)

**Lore** — your second brain, with a memory. The app is named Lore because that's what it does: the built-in AI learns your lore — your projects, context, and history — and works with you inside your workspace.

You are acting as three principal engineers in one: a **senior full-stack engineer**, a **senior frontend engineer**, and a **senior engineer who has built Notion-class editors before**. Every decision you make should be the one that person would make. You make all decisions yourself — do not stop to ask questions. Record every non-obvious decision in `docs/decisions.md` as you go.

**Before writing any frontend code, invoke the `ui-ux-pro-max` skill** and use it to define the design system (style, palette, typography, spacing, motion) for a premium productivity app. Re-invoke it for every major UI surface (editor, sidebar, command palette, AI panel, settings) and for the final polish pass. The UI bar is: indistinguishable from a funded product's public launch. Not "hackathon clean" — **Notion/Linear/Superhuman tier**.

---

## 1. Product definition

A local-first, real-time collaborative workspace like Notion, with a deeply integrated AI system (RAG + agent + persistent memory, like NotebookLM fused into Notion). Multi-user, workspaces, nested pages, block editor, databases with views, instant search, and an AI layer that reads the whole workspace, cites its sources, takes actions, and predicts what you'll do next.

**Anti-demo rules (hard requirements):**
- No placeholder text, no lorem ipsum, no dead buttons, no "coming soon", no TODO/FIXME left in code.
- Every feature listed below is fully wired end-to-end: UI → API → DB → back.
- Empty states, loading skeletons, error states, and keyboard access designed for every screen.
- `docker compose up` (or one documented script) starts the entire stack; a seed script creates a demo workspace with realistic content.
- Tests: pytest (API, RAG pipeline, hardware calculator) + Playwright smoke tests (auth → create page → edit → search → AI chat). All green before you call anything done.

## 2. Tech stack (locked — do not substitute)

- **Frontend:** Next.js 15+ (App Router, TypeScript, strict), Tailwind CSS, shadcn/ui as the component base, Framer Motion for motion, TanStack Query for server state, Zustand for local state.
- **Editor:** **BlockNote** (ProseMirror/Tiptap-based, Notion-style out of the box, native Yjs support). Do NOT hand-roll a block editor; extend BlockNote with custom blocks where needed.
- **Backend:** Python 3.12, **FastAPI** (async), SQLAlchemy 2.0 async + Alembic, Pydantic v2.
- **Database:** PostgreSQL 16 + **pgvector** (one database for relational data, full-text search, and vectors — no separate vector DB).
- **Real-time:** Yjs in the browser ↔ **`pycrdt` / `pycrdt-websocket`** on FastAPI (this is what Jupyter uses; it interoperates with Yjs). WebSockets for collab + presence; SSE for AI token streaming.
- **AI runtimes:** **Ollama** for local models; **OpenRouter** for cloud models. Embeddings run locally via **fastembed** (ONNX, CPU-friendly) in BOTH modes so RAG never depends on the cloud.
- **Auth:** email + password (argon2), JWT access/refresh, httpOnly cookies. Structure so OAuth can be added later; do not build OAuth now.

Monorepo layout: `apps/web` (Next.js), `apps/api` (FastAPI), `packages/shared` (shared types via OpenAPI-generated client), `docker-compose.yml`, `docs/`.

## 3. Workspace features (Notion parity scope)

1. **Workspaces & members** — create/join workspaces, member roles (owner/editor/viewer), invite by email link.
2. **Page tree** — infinitely nestable pages in a collapsible sidebar; drag to reorder/re-nest; favorites; trash with restore; page icons (emoji picker) and cover images.
3. **Block editor** — paragraphs, headings 1–3, bulleted/numbered/todo lists, toggles, quotes, callouts, dividers, code blocks with syntax highlight, images (upload + drag-drop), tables, embeds. Slash-command menu (`/`), drag handles, block selection, markdown shortcuts (`#`, `-`, `[]`, ` ``` `), `@`-mention pages (creates backlinks).
4. **Databases** — Notion-style: properties (text, number, select, multi-select, date, checkbox, URL, relation), views: **table, board (kanban), list, calendar**, with filters, sorts, and grouping. Inline and full-page databases. Open any row as a page.
5. **Real-time collaboration** — live cursors with names/colors, presence avatars, character-level CRDT merge (Yjs), offline edits merge on reconnect. Server is the CRDT source of truth: persist the Yjs update log in Postgres, compact to snapshots periodically. (Lesson from v1: when a doc is first created, seed initial content deterministically so concurrent first-opens can't duplicate content.)
6. **Search** — Cmd+K command palette: instant hybrid search (Postgres FTS + pgvector semantic) across pages and database rows, plus quick actions (create page, jump, toggle theme, ask AI). Sub-100 ms perceived.
7. **Import/export** — import `.md` files (and a folder of them) into pages; export any page/subtree as markdown. This must round-trip the vault format of the original Reclaim app.
8. **Comments** — inline block comments with resolve; a page-level activity/updates panel.

## 4. The AI system (the centerpiece)

### 4.1 Provider layer — local vs cloud, chosen intelligently

A single `LLMProvider` abstraction in the backend with two implementations (Ollama, OpenRouter) and one config surface in Settings → AI. Streaming, tool-calling, and token accounting work identically through both.

**Option A — Local (Ollama), with a real hardware calculator.** On setup, the backend probes the host machine:
- RAM total/available (psutil), CPU cores + arch, GPU vendor + VRAM (pynvml for NVIDIA; `system_profiler`/Metal on macOS; rocm-smi for AMD; graceful "no GPU" fallback), free disk.
- **Recommendation calculator** (implement as a pure, unit-tested module `apps/api/ai/hardware_calc.py`):
  - Memory budget = GPU present ? VRAM × 0.9 : available RAM × 0.6.
  - Model footprint ≈ params(B) × 0.55 GB (Q4_K_M) + KV-cache overhead ≈ 1–2 GB at 8k context.
  - Score every candidate model on: fits-in-budget (hard gate), quality tier, expected speed class (GPU-fit ≫ CPU-fit), disk cost.
  - Maintain a candidate ladder of current best open models across ~1B–70B (research the current best at build time — e.g. Qwen, Llama, DeepSeek distills, Mistral, Gemma, Phi families) with quality tiers.
  - Output: top-3 recommendations with plain-English reasoning ("Your RTX 3060 has 12 GB VRAM → a 14B model at Q4 fits with room for 8k context; expect fast responses"), one-click "Install via Ollama" with download progress, and a live "will it fit" meter shown as the user browses other models.
- Show the detected specs to the user in a beautiful settings panel (GPU, VRAM, RAM, CPU) before recommending.

**Option B — Cloud (OpenRouter).** User pastes an API key (stored encrypted at rest, never sent to the frontend after save, validated with a live test call). Model picker fetches the **live catalog from OpenRouter's `/models` endpoint** — never hardcode IDs — and pins a **Featured** section matched by name from the catalog: **DeepSeek V4 Pro, DeepSeek V4 Flash, Claude Sonnet 5, Claude Opus 4.8, Claude Fable 5, and the latest OpenAI GPT models**. Show pricing and context length per model from the catalog; handle a featured model being unavailable gracefully. Let the user set a default model plus a separate cheap/fast model for background tasks (autocomplete, tagging).

### 4.2 RAG over the workspace

- Ingestion pipeline: on block/page change (debounced), chunk content block-aware (respect headings/blocks, ~400–800 token chunks with overlap), embed with fastembed, upsert into pgvector with `(workspace_id, page_id, block_id)` metadata. Handle deletes/moves. Backfill job for imported content.
- Retrieval: hybrid (vector + FTS, reciprocal rank fusion), scoped to the workspace and the user's permissions.
- **Citations are mandatory**: every AI answer grounded in workspace content links each claim to the exact source block; clicking a citation jumps to that block and highlights it (NotebookLM behavior).

### 4.3 The assistant — "Ask Lore" — NotebookLM-style, with memory

The assistant shares the app's name: users "ask Lore". Its persona is calm, precise, and grounded — it cites, it never invents workspace content.

- Dockable chat panel (right side) + full-page mode. Scope selector: this page / a picked set of pages ("sources", NotebookLM-style) / whole workspace.
- **Persistent memory**: a memory store (Postgres table) of distilled facts — user preferences, recurring topics, project context — written by a background summarizer after conversations, retrieved into the system prompt of every chat. User can view/edit/delete every memory in Settings → AI Memory (full transparency).
- Conversation history persisted per user, searchable.
- Notebook features: "generate study guide / summary / FAQ / outline from these sources", each output created as a real page with citations.

### 4.4 Agentic capabilities

Tool-calling agent loop in the backend with tools: `search_workspace`, `read_page`, `create_page`, `edit_blocks`, `query_database`, `add_database_rows`, `create_database`.
- Reads execute freely; **writes always show a preview diff card in the chat ("Lore wants to create page X / change these 3 blocks") that the user approves or rejects** before anything is committed.
- Multi-step tasks stream progress ("Searching… reading 3 pages… drafting…") with a visible, cancelable plan.
- Slash-integrated: `/ai` block in the editor for inline generation; select any text → floating AI menu (improve, summarize, translate, change tone, continue).

### 4.5 Prediction layer

- **Ghost-text autocomplete** in the editor (debounced, uses the cheap/fast model, Tab to accept, Esc to dismiss, never blocks typing).
- Suggested next actions on page open ("Continue this draft?", "3 unfinished todos from yesterday").
- Auto-suggested tags/backlinks when a page mentions concepts that exist elsewhere in the workspace (one-click apply, never automatic).

## 5. UX details that separate Notion-tier from average (all required)

- Keyboard-first: every action reachable without a mouse; shortcut cheat-sheet (`?`).
- 60 fps interactions; virtualize long pages and large database views; optimistic updates everywhere with rollback on failure.
- Light + dark theme (system-aware, toggleable, no flash on load).
- Beautiful onboarding: first-run creates a guided "Getting started" workspace; AI setup wizard (detect hardware → recommend, or paste key) as a polished flow, not a settings afterthought.
- Micro-interactions: hover affordances on blocks, smooth sidebar collapse, spring-physics drag, toast system, cmd-palette animations — tasteful, fast, never gratuitous.
- Full a11y pass: focus rings, ARIA on the editor/menus, contrast AA+.

## 6. Build order (verify each phase in the running app before the next)

0. Monorepo scaffold, docker-compose (postgres+pgvector, api, web), CI scripts, seed script skeleton.
1. Auth + workspaces + page tree CRUD (sidebar working end-to-end).
2. BlockNote editor + persistence + markdown import/export.
3. Real-time collab: Yjs ↔ pycrdt-websocket, presence cursors, snapshot compaction.
4. Databases + all four views + filters/sorts.
5. Hybrid search + command palette.
6. AI provider layer + hardware calculator + settings/onboarding wizard (both providers working with a real streamed chat).
7. RAG pipeline + the Lore assistant with citations + persistent memory.
8. Agent tools with approval diffs + ghost-text autocomplete + suggestions.
9. Final pass: invoke `ui-ux-pro-max` again and do a screen-by-screen polish audit, a11y sweep, performance profiling, full Playwright suite, README + architecture doc.

At the end of every phase: run the stack, exercise the new feature in the browser yourself, run all tests, then commit with a clear message. If something can't work as specified, choose the best alternative and document it in `docs/decisions.md` — never silently downgrade the product.

Now build it. Take as long as it needs — completeness beats speed, and "it works" is the floor, not the goal. The finished product should make Notion users jealous.
