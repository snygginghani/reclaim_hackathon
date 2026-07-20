# Lore — start the full dev stack (db in Docker, api + web natively).
# Usage: powershell -File scripts/dev.ps1   (from the repo root)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Write-Host "[lore] starting Postgres (docker compose)..." -ForegroundColor Cyan
docker compose -f "$root\docker-compose.yml" up -d db

Write-Host "[lore] starting API on http://localhost:8300 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command",
  "cd '$root\apps\api'; uv run uvicorn lore_api.main:app --reload --port 8300"

Write-Host "[lore] starting web on http://localhost:3000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command",
  "cd '$root\apps\web'; npm run dev"

Write-Host "[lore] all services launching. Web: http://localhost:3000  API: http://localhost:8300/docs" -ForegroundColor Green
