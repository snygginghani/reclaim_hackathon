FROM python:3.12-slim

# uv resolves and installs from the committed lockfile.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer: only re-resolves when the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY lore_api ./lore_api
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    # fastembed pulls BAAI/bge-small-en-v1.5 on first use; keep it on a volume
    # so a container restart doesn't re-download ~130MB.
    HF_HOME=/app/.cache/huggingface

EXPOSE 8300
CMD ["uvicorn", "lore_api.main:app", "--host", "0.0.0.0", "--port", "8300"]
