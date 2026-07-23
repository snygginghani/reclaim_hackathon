"""Pure translators: Notion JSON -> Lore's BlockNote blocks and database
property/value shapes. No network here — the importer drives fetching and asset
re-hosting and calls these functions.

Internal Notion page links become placeholder hrefs `notion-page:{id}` and
relation cell values keep raw Notion ids; both are rewritten to Lore page ids in
the importer's second pass once every page has an id."""

from __future__ import annotations

import uuid
from typing import Any

# Placeholder scheme for links/mentions to other Notion pages, resolved in pass 2.
PAGE_LINK_SCHEME = "notion-page:"

# Notion color name -> hex, for database select/multi_select choice swatches.
NOTION_COLOR_HEX = {
    "default": "#64748B",
    "gray": "#64748B",
    "brown": "#92600A",
    "orange": "#C2410C",
    "yellow": "#CA8A04",
    "green": "#16A34A",
    "blue": "#2563EB",
    "purple": "#7C3AED",
    "pink": "#DB2777",
    "red": "#DC2626",
}

# BlockNote named colors (for inline text/background styles) — Notion shares these names.
_BLOCKNOTE_COLORS = set(NOTION_COLOR_HEX) | {"default"}


def _new_id() -> str:
    return str(uuid.uuid4())


# --- rich text ---


def _styles(annotations: dict[str, Any]) -> dict[str, Any]:
    styles: dict[str, Any] = {}
    if annotations.get("bold"):
        styles["bold"] = True
    if annotations.get("italic"):
        styles["italic"] = True
    if annotations.get("underline"):
        styles["underline"] = True
    if annotations.get("strikethrough"):
        styles["strike"] = True
    if annotations.get("code"):
        styles["code"] = True
    color = annotations.get("color", "default")
    if color and color != "default":
        if color.endswith("_background"):
            base = color[: -len("_background")]
            if base in _BLOCKNOTE_COLORS:
                styles["backgroundColor"] = base
        elif color in _BLOCKNOTE_COLORS:
            styles["textColor"] = color
    return styles


def _text_run(text: str, styles: dict[str, Any]) -> dict[str, Any]:
    return {"type": "text", "text": text, "styles": styles}


def rich_text_to_inline(rich: list[dict] | None) -> list[dict]:
    """Convert a Notion rich_text array to BlockNote inline content."""
    out: list[dict] = []
    for item in rich or []:
        annotations = item.get("annotations", {})
        styles = _styles(annotations)
        itype = item.get("type")

        # A mention of another Notion page/database becomes an internal link,
        # resolved to a Lore page id in pass 2.
        if itype == "mention":
            mention = item.get("mention", {})
            target = mention.get("page") or mention.get("database")
            plain = item.get("plain_text", "") or "Untitled"
            if target and target.get("id"):
                out.append({
                    "type": "link",
                    "href": f"{PAGE_LINK_SCHEME}{target['id']}",
                    "content": [_text_run(plain, styles)],
                })
            elif plain:
                out.append(_text_run(plain, styles))
            continue

        text = item.get("plain_text", "")
        if itype == "text":
            text = (item.get("text") or {}).get("content", text)
        if text == "" and itype != "text":
            text = item.get("plain_text", "")
        href = item.get("href")
        if href:
            out.append({"type": "link", "href": href, "content": [_text_run(text, styles)]})
        elif text:
            out.append(_text_run(text, styles))
    return out


def rich_text_to_plain(rich: list[dict] | None) -> str:
    return "".join(item.get("plain_text", "") for item in rich or [])


# --- blocks ---

# Notion container/structural types the importer flattens or handles specially.
FLATTEN_TYPES = {"column_list", "column", "synced_block", "template"}
SKIP_TYPES = {"table_of_contents", "breadcrumb", "divider", "unsupported"}
CHILD_PAGE_TYPES = {"child_page", "child_database"}
MEDIA_TYPES = {"image", "video", "audio", "file", "pdf"}


def _media_url(node: dict) -> str | None:
    src = node.get("file") or node.get("external") or {}
    return src.get("url")


def convert_block(block: dict, children: list[dict]) -> dict | None:
    """Translate one Notion block (with already-converted `children`) to a
    BlockNote block. Returns None for blocks that carry no content of their own.
    Media blocks keep the ORIGINAL Notion url in props.url; the importer downloads
    and re-hosts it afterward (see rehost pass)."""
    ntype = block.get("type", "")
    node = block.get(ntype, {}) if isinstance(block.get(ntype), dict) else {}
    rich = node.get("rich_text")

    def make(btype: str, props: dict | None = None, content: Any = None) -> dict:
        b: dict[str, Any] = {"id": _new_id(), "type": btype, "props": props or {}}
        b["content"] = content if content is not None else rich_text_to_inline(rich)
        if children:
            b["children"] = children
        return b

    if ntype == "paragraph":
        return make("paragraph")
    if ntype in ("heading_1", "heading_2", "heading_3"):
        level = int(ntype[-1])
        return make("heading", {"level": level})
    if ntype == "bulleted_list_item":
        return make("bulletListItem")
    if ntype == "numbered_list_item":
        return make("numberedListItem")
    if ntype == "to_do":
        return make("checkListItem", {"checked": bool(node.get("checked"))})
    if ntype == "toggle":
        # BlockNote has no toggle block; keep the summary as a paragraph and let
        # its children nest under it (content is preserved, collapsibility isn't).
        return make("paragraph")
    if ntype == "quote":
        return make("quote")
    if ntype == "callout":
        icon = (node.get("icon") or {}).get("emoji")
        content = rich_text_to_inline(rich)
        if icon:
            content = [_text_run(f"{icon} ", {})] + content
        return make("quote", content=content)
    if ntype == "code":
        lang = node.get("language") or "text"
        return make("codeBlock", {"language": str(lang).lower()}, content=rich_text_to_inline(rich))
    if ntype in MEDIA_TYPES:
        url = _media_url(node)
        if not url:
            return None
        btype = {"image": "image", "video": "video", "audio": "audio"}.get(ntype, "file")
        caption = rich_text_to_plain(node.get("caption"))
        props: dict[str, Any] = {"url": url}
        if caption:
            props["caption"] = caption
        return make(btype, props, content=[])
    if ntype in ("bookmark", "embed", "link_preview"):
        url = node.get("url", "")
        if not url:
            return None
        return make("paragraph", content=[{"type": "link", "href": url,
                                           "content": [_text_run(url, {})]}])
    if ntype == "equation":
        expr = node.get("expression", "")
        return make("paragraph", content=[_text_run(expr, {"code": True})]) if expr else None

    # Unknown/other: salvage any text so nothing is silently dropped.
    text = rich_text_to_plain(rich)
    if text:
        return make("paragraph", content=[_text_run(text, {})])
    return None


def build_table(row_cells: list[list[list[dict]]]) -> dict:
    """BlockNote table block from Notion table_row cells (each cell = a rich_text
    array). `row_cells` is rows -> cells -> notion rich_text array."""
    rows = [{"cells": [rich_text_to_inline(cell) for cell in row]} for row in row_cells]
    return {"id": _new_id(), "type": "table", "props": {}, "content": {"type": "tableContent", "rows": rows}}


# --- database schema + values ---

# Notion property type -> Lore property type. Anything absent falls back to "text".
PROPERTY_TYPE_MAP = {
    "title": "text",
    "rich_text": "text",
    "number": "number",
    "select": "select",
    "status": "select",
    "multi_select": "multi_select",
    "date": "date",
    "checkbox": "checkbox",
    "url": "url",
    "email": "text",
    "phone_number": "text",
    "relation": "relation",
}


def options_for(notion_type: str, schema_cfg: dict) -> dict:
    """Build Lore `options` JSONB for a property from its Notion schema config.
    Choice ids reuse Notion's option ids so cell values line up."""
    if notion_type in ("select", "status", "multi_select"):
        raw = (schema_cfg.get(notion_type) or {}).get("options", [])
        choices = [
            {
                "id": opt.get("id") or _new_id(),
                "name": opt.get("name", ""),
                "color": NOTION_COLOR_HEX.get(opt.get("color", "default"), NOTION_COLOR_HEX["default"]),
            }
            for opt in raw
        ]
        return {"choices": choices}
    return {}


def cell_value(notion_type: str, value: dict) -> dict | None:
    """Translate one Notion property value to Lore's cell JSONB, or None to skip
    (empty). Relation values keep raw Notion page ids for pass-2 remapping."""
    if notion_type == "number":
        n = value.get("number")
        return {"number": n} if n is not None else None
    if notion_type in ("select", "status"):
        sel = value.get(notion_type)
        return {"select": sel["id"]} if sel and sel.get("id") else None
    if notion_type == "multi_select":
        ids = [o["id"] for o in value.get("multi_select", []) if o.get("id")]
        return {"multi_select": ids} if ids else None
    if notion_type == "date":
        d = value.get("date")
        if not d or not d.get("start"):
            return None
        out = {"start": d["start"]}
        if d.get("end"):
            out["end"] = d["end"]
        return {"date": out}
    if notion_type == "checkbox":
        return {"checkbox": bool(value.get("checkbox"))}
    if notion_type == "url":
        return {"url": value["url"]} if value.get("url") else None
    if notion_type == "relation":
        ids = [r["id"] for r in value.get("relation", []) if r.get("id")]
        return {"relation": ids} if ids else None
    if notion_type in ("rich_text", "title"):
        text = rich_text_to_plain(value.get(notion_type))
        return {"text": text} if text else None
    if notion_type in ("email", "phone_number"):
        v = value.get(notion_type)
        return {"text": v} if v else None

    # Best-effort stringify for people/files/formula/rollup/created_time/etc.
    text = _stringify_unknown(notion_type, value)
    return {"text": text} if text else None


def _stringify_unknown(notion_type: str, value: dict) -> str:
    if notion_type == "people":
        return ", ".join(p.get("name", "") for p in value.get("people", []) if p.get("name"))
    if notion_type == "files":
        return ", ".join(f.get("name", "") for f in value.get("files", []) if f.get("name"))
    if notion_type in ("created_time", "last_edited_time"):
        return value.get(notion_type, "")
    if notion_type == "unique_id":
        uid = value.get("unique_id") or {}
        prefix = uid.get("prefix") or ""
        return f"{prefix}{uid.get('number', '')}" if uid.get("number") is not None else ""
    if notion_type == "formula":
        f = value.get("formula") or {}
        ftype = f.get("type")
        v = f.get(ftype) if ftype else None
        if isinstance(v, dict):  # e.g. date
            return v.get("start", "")
        return "" if v is None else str(v)
    return ""


def title_of(page: dict) -> str:
    """Extract a Notion page/row title from its properties (the sole `title` prop)."""
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            return rich_text_to_plain(prop.get("title")) or "Untitled"
    return "Untitled"
