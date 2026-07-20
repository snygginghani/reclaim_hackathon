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
