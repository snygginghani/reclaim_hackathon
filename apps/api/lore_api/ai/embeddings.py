"""Local embeddings via fastembed (ONNX, CPU) — used in BOTH provider modes so
RAG never depends on the cloud. The model is lazy-loaded once and calls run in a
threadpool so they don't block the event loop."""

from __future__ import annotations

import asyncio
import threading

EMBED_DIM = 384
_MODEL_NAME = "BAAI/bge-small-en-v1.5"

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from fastembed import TextEmbedding

                _model = TextEmbedding(_MODEL_NAME)
    return _model


def _embed_documents_sync(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [v.tolist() for v in _get_model().embed(texts)]


def _embed_query_sync(text: str) -> list[float]:
    return list(_get_model().query_embed([text]))[0].tolist()


async def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return await asyncio.to_thread(_embed_documents_sync, texts)


async def embed_query(text: str) -> list[float]:
    return await asyncio.to_thread(_embed_query_sync, text)


def warm() -> None:
    """Trigger the one-time model load/download eagerly (called at startup)."""
    try:
        _get_model()
    except Exception:
        pass
