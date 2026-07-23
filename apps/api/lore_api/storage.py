"""Local asset storage. Files are written under `settings.upload_dir` with
uuid-based names and served as static files at `/uploads` (mounted in main.py).
Used by the assets upload route and by the Notion importer, which re-hosts
Notion's temporary (signed, ~1h) asset URLs into permanent local files."""

import re
import uuid
from pathlib import Path

from .config import get_settings

# Conservative allow-list of extensions we preserve; anything else stores as .bin.
_SAFE_EXT = re.compile(r"^\.[A-Za-z0-9]{1,8}$")


def upload_root() -> Path:
    root = Path(get_settings().upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _clean_ext(ext: str | None) -> str:
    if not ext:
        return ""
    ext = ext if ext.startswith(".") else f".{ext}"
    return ext.lower() if _SAFE_EXT.match(ext) else ""


def public_url(name: str) -> str:
    """Absolute URL for a stored file, so it resolves from the browser and
    survives even after the Notion connection is revoked."""
    return f"{get_settings().api_base_url.rstrip('/')}/uploads/{name}"


def save_bytes(data: bytes, ext: str | None = None) -> str:
    """Persist bytes under a uuid name; return the public URL."""
    name = f"{uuid.uuid4().hex}{_clean_ext(ext)}"
    (upload_root() / name).write_bytes(data)
    return public_url(name)
