#!/usr/bin/env bash
# Lore — start the full dev stack (db in Docker, api + web natively).
# Usage: ./scripts/dev.sh   (from anywhere in the repo)
set -euo pipefail

# Job control, so each background service gets its own process group and can be
# torn down as a tree. uvicorn --reload spawns a worker that inherits the listen
# socket; killing only the wrapper leaves it serving stale code on the port.
set -m

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for cmd in docker uv npm; do
  command -v "$cmd" >/dev/null || { echo "[lore] missing required command: $cmd" >&2; exit 1; }
done

echo "[lore] starting Postgres (docker compose)..."
docker compose -f "$root/docker-compose.yml" up -d db

echo "[lore] waiting for Postgres to accept connections..."
for _ in $(seq 60); do
  if docker compose -f "$root/docker-compose.yml" exec -T db pg_isready -U lore -d lore >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

pids=()
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "[lore] shutting down..."
  for pid in "${pids[@]}"; do
    kill -- "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "[lore] starting API on http://localhost:8300 ..."
(cd "$root/apps/api" && uv run uvicorn lore_api.main:app --reload --port 8300) 2>&1 \
  | sed -u 's/^/[api] /' &
pids+=("$!")

echo "[lore] starting web on http://localhost:3000 ..."
(cd "$root/apps/web" && npm run dev) 2>&1 | sed -u 's/^/[web] /' &
pids+=("$!")

echo "[lore] all services launching. Web: http://localhost:3000  API: http://localhost:8300/docs"
echo "[lore] press Ctrl-C to stop everything (Postgres keeps running; 'docker compose down' to stop it)."
wait
