"""Utilities over BlockNote JSON (the document read model)."""

from __future__ import annotations

from typing import Any


def blocks_to_text(blocks: list[Any]) -> str:
    """Flatten a BlockNote block tree to plain text for search/embedding.
    Walks `content` inline arrays (text runs, links) and `children` recursively."""
    parts: list[str] = []

    def walk_inline(content: Any) -> None:
        if isinstance(content, list):
            for item in content:
                walk_inline(item)
        elif isinstance(content, dict):
            text = item_text(content)
            if text:
                parts.append(text)

    def item_text(item: dict) -> str:
        if isinstance(item.get("text"), str):
            return item["text"]
        if isinstance(item.get("content"), list):  # links wrap their own runs
            return " ".join(
                sub.get("text", "") for sub in item["content"] if isinstance(sub, dict)
            )
        return ""

    def walk_block(block: Any) -> None:
        if not isinstance(block, dict):
            return
        walk_inline(block.get("content"))
        # Table blocks nest rows under content.rows[].cells[][]
        content = block.get("content")
        if isinstance(content, dict) and isinstance(content.get("rows"), list):
            for row in content["rows"]:
                for cell in row.get("cells", []):
                    walk_inline(cell)
        for child in block.get("children") or []:
            walk_block(child)

    for b in blocks:
        walk_block(b)
    return "\n".join(p for p in (s.strip() for s in parts) if p)
