"""RAG prompt assembly and citation grounding for the Lore assistant."""

from __future__ import annotations

import re

from .retrieval import Retrieved

SNIPPET_CHARS = 500


def build_sources(retrieved: list[Retrieved]) -> list[dict]:
    """Number the retrieved chunks [1..n] and shape them for the prompt + the
    frontend citation UI (which needs page + block ids to jump-and-highlight)."""
    return [
        {
            "n": i + 1,
            "page_id": str(r.chunk.page_id),
            "page_title": r.page_title,
            "heading": r.chunk.heading,
            "block_ids": r.chunk.block_ids,
            "snippet": r.chunk.text[:SNIPPET_CHARS],
        }
        for i, r in enumerate(retrieved)
    ]


def system_prompt(sources: list[dict], memories: list[str]) -> str:
    parts = [
        "You are Lore, the user's calm and precise workspace assistant.",
        "Answer the question using ONLY the numbered sources below.",
        "Cite every factual claim with bracketed source numbers like [1] or [2][3].",
        "If the sources do not contain the answer, say so plainly — never invent workspace content.",
        "Be concise and grounded.",
    ]
    if memories:
        parts.append("\nWhat you remember about this user (use naturally, don't recite):")
        parts.extend(f"- {m}" for m in memories)
    if sources:
        parts.append("\nSources:")
        for s in sources:
            head = f" › {s['heading']}" if s["heading"] else ""
            parts.append(f"[{s['n']}] {s['page_title']}{head}\n{s['snippet']}")
    else:
        parts.append("\n(No workspace sources matched this question.)")
    return "\n".join(parts)


_CITE = re.compile(r"\[(\d+)\]")


def cited_source_numbers(answer: str) -> set[int]:
    return {int(m) for m in _CITE.findall(answer)}


def used_citations(answer: str, sources: list[dict]) -> list[dict]:
    """The subset of sources the answer actually cited (for storage + display)."""
    used = cited_source_numbers(answer)
    return [s for s in sources if s["n"] in used]
