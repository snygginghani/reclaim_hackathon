"""Block-aware chunking of BlockNote documents for embedding.

Chunks respect block boundaries, carry the nearest heading for context, and
record which block ids they cover so a citation can jump to the exact block.
Overlap of one block preserves continuity across chunk seams.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TARGET_CHARS = 1600  # ~400 tokens at ~4 chars/token
MAX_CHARS = 2400


@dataclass
class DocChunk:
    text: str
    block_ids: list[str] = field(default_factory=list)
    heading: str | None = None

    @property
    def embed_text(self) -> str:
        # Prepend the section heading so retrieval sees the local context.
        return f"{self.heading}\n{self.text}" if self.heading else self.text


def _inline_text(content) -> str:
    if isinstance(content, list):
        return "".join(_inline_text(c) for c in content)
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), list):
            return _inline_text(content["content"])
    return ""


def _block_text(block: dict) -> str:
    content = block.get("content")
    parts = [_inline_text(content)]
    if isinstance(content, dict) and isinstance(content.get("rows"), list):
        for row in content["rows"]:
            for cell in row.get("cells", []):
                parts.append(_inline_text(cell))
    return " ".join(p for p in parts if p).strip()


def _flatten(blocks, heading, out):
    for b in blocks:
        if not isinstance(b, dict):
            continue
        text = _block_text(b)
        btype = b.get("type")
        if btype == "heading" and text:
            heading = text
        out.append((b.get("id"), btype, text, heading))
        for child in b.get("children") or []:
            _flatten([child], heading, out)


def chunk_document(blocks: list) -> list[DocChunk]:
    units: list[tuple] = []
    _flatten(blocks, None, units)

    chunks: list[DocChunk] = []
    cur: list[str] = []
    cur_ids: list[str] = []
    cur_heading: str | None = None
    cur_len = 0

    def flush(overlap_from: tuple | None):
        nonlocal cur, cur_ids, cur_heading, cur_len
        if cur and "".join(cur).strip():
            chunks.append(DocChunk("\n".join(cur), list(dict.fromkeys(cur_ids)), cur_heading))
        cur, cur_ids, cur_len = [], [], 0
        cur_heading = None
        if overlap_from:
            bid, _btype, text, heading = overlap_from
            if text.strip():
                cur.append(text)
                if bid:
                    cur_ids.append(bid)
                cur_len = len(text)
                cur_heading = heading

    for unit in units:
        bid, btype, text, heading = unit
        if not text.strip():
            continue
        if cur_len == 0:
            cur_heading = heading
        # Emit before adding if this block would overflow (and we have content).
        if cur and cur_len + len(text) > TARGET_CHARS:
            flush(overlap_from=unit if len(text) < MAX_CHARS else None)
            if cur_heading is None:
                cur_heading = heading
        cur.append(text)
        if bid:
            cur_ids.append(bid)
        cur_len += len(text) + 1
        # A single huge block: hard cap.
        if cur_len > MAX_CHARS:
            flush(overlap_from=None)

    flush(overlap_from=None)
    return chunks
