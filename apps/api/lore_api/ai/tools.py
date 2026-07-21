"""Agent tools. Read tools run immediately in the loop; write tools are only
ever PROPOSED — the server emits an approval card and the frontend commits the
action through the normal APIs after the user says yes. Nothing here mutates
the workspace."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..blocks import blocks_to_text
from ..models import Document, Page
from .retrieval import hybrid_search

# Everything listed here survives the frontend's markdown -> BlockNote conversion
# (see apps/web/src/lib/markdown.ts); spelling it out is what makes the model
# actually reach for checklists instead of flattening everything into bullets.
MARKDOWN_HINT = (
    "Page body as markdown. Build a structured document, not a wall of text: "
    "`#`/`##` headings for sections, `- [ ] item` for checklists (use these for "
    "anything the user will tick off — tasks, sets, steps, packing lists), "
    "`-` bullets, `1.` numbered lists, `**bold**`, and `> ` quotes. "
    "Nest list items by indenting two spaces. "
    "Keep it to the essentials, roughly 20-30 lines."
)

# Tool schemas in the OpenAI/Ollama function-calling format.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_workspace",
            "description": "Semantic + keyword search across the workspace. Use this first to find relevant pages before answering or editing.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to look for"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_page",
            "description": "Read the full text of one page by its id.",
            "parameters": {
                "type": "object",
                "properties": {"page_id": {"type": "string"}},
                "required": ["page_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pages",
            "description": "List all pages and databases in the workspace with their ids.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_page",
            "description": "PROPOSE creating a new page. Requires user approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content_markdown": {"type": "string", "description": MARKDOWN_HINT},
                },
                "required": ["title", "content_markdown"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_to_page",
            "description": "PROPOSE appending markdown to an existing page. Requires user approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string"},
                    "content_markdown": {"type": "string", "description": MARKDOWN_HINT},
                },
                "required": ["page_id", "content_markdown"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_database",
            "description": "PROPOSE creating a database with named columns. Requires user approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "columns": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "columns"],
            },
        },
    },
]

READ_TOOLS = {"search_workspace", "read_page", "list_pages"}
WRITE_TOOLS = {"create_page", "append_to_page", "create_database"}


async def run_read_tool(
    db: AsyncSession, workspace_id: uuid.UUID, name: str, args: dict
) -> str:
    """Execute a read tool and return a compact text result for the model."""
    if name == "search_workspace":
        hits = await hybrid_search(db, workspace_id, str(args.get("query", "")), k=6)
        if not hits:
            return "No matching pages."
        return "\n".join(
            f"- [{h.page_title}] (page_id={h.chunk.page_id}): {h.chunk.text[:160]}" for h in hits
        )
    if name == "read_page":
        try:
            pid = uuid.UUID(str(args.get("page_id")))
        except (ValueError, TypeError):
            return "Invalid page_id."
        page = await db.get(Page, pid)
        if page is None or page.workspace_id != workspace_id or page.deleted_at:
            return "Page not found."
        doc = await db.get(Document, pid)
        text = doc.text_content if doc else ""
        return f"# {page.title}\n{text[:4000]}"
    if name == "list_pages":
        rows = (
            await db.execute(
                select(Page.id, Page.title, Page.kind).where(
                    Page.workspace_id == workspace_id,
                    Page.deleted_at.is_(None),
                    Page.kind != "row",
                )
            )
        ).all()
        return "\n".join(f"- {t or 'Untitled'} ({k}, id={i})" for i, t, k in rows) or "No pages."
    return f"Unknown tool {name}."


def write_preview(name: str, args: dict) -> dict:
    """A human-readable approval card for a proposed write."""
    if name == "create_page":
        body = str(args.get("content_markdown", ""))
        return {
            "action": "Create page",
            "title": args.get("title", "Untitled"),
            "summary": _clip(body, 400),
        }
    if name == "append_to_page":
        return {
            "action": "Append to page",
            "title": None,
            "page_id": args.get("page_id"),
            "summary": _clip(str(args.get("content_markdown", "")), 400),
        }
    if name == "create_database":
        cols = args.get("columns", [])
        return {
            "action": "Create database",
            "title": args.get("title", "Untitled"),
            "summary": "Columns: " + ", ".join(str(c) for c in cols),
        }
    return {"action": name, "title": None, "summary": ""}


def _clip(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[:n] + "…"
