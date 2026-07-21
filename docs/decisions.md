# Lore — engineering decisions log

Non-obvious decisions, newest last. Each entry: what was decided, why, and what it forecloses.

## 0.1 — Repo root is the existing `reclaim` PyCharm folder
The app is **Lore**; the containing folder happens to be named `reclaim` (it previously held the hackathon project this product supersedes). Folder name is cosmetic — all package names, compose project name, and docs say `lore`. Renaming the folder would break the PyCharm project and the session working directory for no product benefit.

## 0.2 — Python 3.13 (brief said 3.12)
The machine has CPython 3.13.3. Everything in our dependency set (FastAPI, SQLAlchemy 2, pycrdt, fastembed) supports 3.13. Using the installed interpreter beats installing a second toolchain. `requires-python = ">=3.12"` so 3.12 environments still work.

## 0.3 — Dev topology: DB in Docker, api/web run natively
Docker Desktop on Windows makes bind-mounted hot-reload painfully slow. Dev flow: `docker compose up db` for Postgres+pgvector; FastAPI (uvicorn --reload) and Next.js run natively via one documented script (`scripts/dev.ps1`). This satisfies the "one documented script" requirement; a containerized full-stack profile can be added for deployment later without changing app code.

## 0.4 — Postgres exposed on host port 5433
Avoids colliding with any local Postgres on 5432. Connection strings in `.env.example` use 5433.

## 0.5 — uv for Python dependency management
`uv` is installed on the machine; it is faster and reproducible (`uv.lock`). `apps/api/pyproject.toml` is the single source of truth for backend deps.

## 0.6 — Design system: "Calm Precision" minimalism, not the generator's "Liquid Glass"
`ui-ux-pro-max --design-system` recommended Liquid Glass (translucency, morphing, 400–600ms fluid animations). Rejected for the core UI: its own metadata flags Moderate-Poor performance and text-contrast risk, and Lore is a text-dense keyboard-first tool where blur-heavy chrome fights readability and 60fps editing. Kept from the generator: the slate neutral palette, Plus Jakarta Sans, and the indigo #5E6AD2 accent (from its Modern-Dark/Linear-style entry). Glass effects are confined to transient overlays. Full synthesis in docs/design-system.md; raw generator output in design-system/lore/MASTER.md.

## 0.7 — API on port 8300 (8000 is taken on this machine)
An unrelated local app owns port 8000 on the dev machine, so the Lore API binds 8300 (web stays on 3000). All scripts and env defaults use 8300.

## 2.1 — Windows: never kill the uvicorn wrapper, kill the tree
`uvicorn --reload` on Windows spawns a worker that inherits the listen socket. Killing the wrapper (or the PID that owns the port per netstat) leaves an orphaned worker serving STALE code on the port — netstat even attributes the socket to the dead parent PID. Symptom: edits "don't apply" after restart. Fix: `taskkill /PID <wrapper> /T /F` (tree kill) or stop the python worker itself; `scripts/dev.ps1` runs servers in their own windows so closing the window kills the tree.

## 3.1 — Collab session registry, not per-component providers
React StrictMode's mount→unmount→remount destroyed the WebsocketProvider that the remounted component's preserved state still referenced: the editor typed into a dead Y.Doc while looking healthy. Sessions now live in a module-level refcounted registry (src/lib/collab-session.ts): render-safe getCollabSession (creation grace timer), retain/release from effects, deferred destroy so fast remounts adopt the live socket. This also dedupes connections when multiple views of one page mount.

## 3.2 — documents.blocks stays a client-maintained read model
The Yjs log (ydoc_updates) is the merge source of truth; the BlockNote JSON snapshot is maintained by connected clients' debounced autosave, because BlockNote's fragment↔JSON conversion only exists in TypeScript. Consequence: export/search/RAG read at-most-800ms-stale content, and a page edited then instantly closed can be slightly staler until reopened. Accepted for v1; a Node sidecar converter could close the gap later.

## 3.3 — Viewer write-blocking happens in the socket adapter
Role "viewer" gets a ReadOnlyWebsocket that swallows y-protocol SYNC_STEP2/UPDATE messages server-side. Viewers receive live edits and cursors but their (hypothetically forged) writes never reach the room, regardless of client behavior.

## 3.4 — One-shot server-granted seeding for legacy pages
Reclaim v1's fixed-clientID trick is replaced by POST /collab-seed: the first editor client to open a legacy/imported page wins a transactional grant and inserts the JSON snapshot into the fragment; racers are denied. Cold-open duplication is structurally impossible.

## 4.1 — Rows are pages
A database row is a Page with kind="row" and parent = the database page. "Open any row as a page" costs nothing, rows get titles/icons/documents/collab for free, and the sidebar simply filters kind="row" out. Cell data lives in db_values (row_id × property_id → JSONB), typed per property.

## 4.2 — Views evaluate client-side
Filters/sorts/grouping run in the browser (lib/database-query.ts) over the full row set; the server stores view config verbatim. At v1 workspace scale this is faster and radically simpler than a server query DSL; the seam to push evaluation server-side later is applyView().

## 4.3 — Row deletion is hard delete
Rows skip the page trash: restoring individual grid rows piecemeal is more confusing than helpful, and the grid UX expects immediate removal. Docs/databases keep the trash flow.

## 5.1 — Search ships FTS-first; the semantic leg joins with the RAG pipeline
/api/search runs Postgres FTS (websearch_to_tsquery + ts_headline snippets with [[..]] markers) over titles + text extracted from BlockNote JSON on every save (documents.text_content, GIN-indexed), with an ILIKE fallback so prefix typing hits titles instantly. pgvector fusion (RRF) lands in the same endpoint once Phase 7's embedding ingestion exists — sequencing, not scope reduction. The palette also merges instant client-side title matches ahead of the server round-trip.

## 6.1 — AI settings are workspace-scoped; keys encrypted with Fernet
ai_settings lives per workspace (the assistant is a collaboration feature); only owners write, members read a key-free view. The OpenRouter key is validated live (GET /key) before being Fernet-encrypted at rest with a key derived from the app secret; it is never returned to clients.

## 6.2 — Featured cloud models resolve by pattern against the live catalog
Never hardcode model ids: /api/ai/openrouter/models fetches the live catalog and matches DeepSeek V4 Pro/Flash, Claude Sonnet 5 / Opus 4.8 / Fable 5 by regex (shortest-id wins over :variants) plus the newest non-audio OpenAI GPT by created timestamp. Verified against the real catalog: all six resolve today.

## 6.3 — The calculator is the contract
hardware_calc.py is pure and unit-pinned: Q4 footprint = params×0.55GB + 1.5GB KV@8k; budget = VRAM×0.9 (GPU) or available-RAM×0.6 (CPU). Non-NVIDIA VRAM is reported as unknown rather than guessed (Windows lies about AdapterRAM) — such GPUs fall back to the CPU path instead of poisoning fits. Verified on real hardware: RTX 4060 8GB → Llama/Qwen 8B "GPU · fast" with correct arithmetic in the reasoning strings.

## 6.4 — Hardware specifier rebuilt for real accuracy
The probe now reports the marketing CPU name (winreg ProcessorNameString / sysctl / /proc/cpuinfo), physical+logical core counts, and accurate VRAM for every GPU. On Windows, VRAM comes from the driver registry's HardwareInformation.qwMemorySize (what GPU-Z reads) rather than Win32_VideoController.AdapterRAM, which is a uint32 that silently caps at 4 GB. NVIDIA still goes through NVML (authoritative); non-NVIDIA cards whose VRAM genuinely can't be read report None and fall back to the CPU budget rather than being guessed. Verified on the dev machine: i5-12400F (6C/12T) + RTX 4060 8 GB, all correct.

## 6.5 — AI settings redesigned to feel real (not "fake")
The provider panel now shows a live spec sheet (CPU/RAM-meter/GPU-VRAM-meter/disk) built from the real probe, an Ollama connected/offline pill, and recommendation cards whose reasoning names the detected GPU with the actual fit arithmetic. This replaced a flat pill row that read as placeholder.

## 6.6 — Rebrand to the hexagram Lore mark; mobile sidebar is now a drawer
Replaced the book icon with `<LoreMark>` everywhere + SVG favicon. Fixed a real responsive bug: below md the 260px sidebar crushed content into an unusable strip — it is now an off-canvas overlay drawer (hamburger to open, scrim/X/link-tap to close) while desktop keeps the in-flow collapsible column. Drawer dismissal on navigation is handled by an onClick link check, not a pathname effect (avoids setState-in-effect).

## 7.1 — Ask Lore is a docked panel; citations jump to the exact block
The assistant is a right-side dock (⌘J), coexisting with the sidebar + editor. Answers render [n] markers as clickable chips resolved against the streamed sources; clicking one navigates to the page and flashes the source block via a small highlight store the editor subscribes to (targets BlockNote `data-id`). Scope is derived (workspace vs current page) not held in an effect.

## 7.2 — Notebook generators reuse the frontend markdown→blocks path
/api/ai/generate streams markdown; the panel converts it with the existing BlockNote markdownToBlocks and creates a real page, rather than teaching the backend to emit BlockNote JSON. Citation markers are stripped from the generated page body.

## 7.3 — Memory is user-owned and transparent
Per-user, per-workspace facts, auto-distilled after each exchange by the fast model (best-effort, deduped) and fully editable in Settings → Lore's memory. Retrieved into every chat's system prompt. Verified: manual add/edit/delete + reindex work with no LLM; the full grounded-chat-with-citations path is covered by a fake-provider test.
