"""Pure translators: Confluence ADF (Atlassian Document Format) -> Lore's
BlockNote blocks. No network here — the adapter drives fetching, attachment
resolution, and asset re-hosting, and calls these functions.

Internal Confluence page links become placeholder hrefs `confluence-page:{id}`
(resolved to Lore page ids in the engine's second pass). Media nodes become image
blocks whose `props.url` is an `attachment:{fileId}` ref the adapter re-hosts."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

# Placeholder scheme for links to other Confluence pages, resolved in pass 2.
CONFLUENCE_LINK_SCHEME = "confluence-page:"
# Prefix marking a media block whose bytes come from a Confluence attachment.
ATTACHMENT_REF = "attachment:"

# Confluence panel type -> a leading emoji (BlockNote has no panel/callout block,
# so panels become quotes, mirroring how Notion callouts are handled).
_PANEL_EMOJI = {
    "info": "ℹ️",
    "note": "📝",
    "tip": "💡",
    "success": "✅",
    "warning": "⚠️",
    "error": "🚫",
}

# Confluence page URLs embed the numeric page id: .../pages/{id}/Title
_PAGE_URL_RE = re.compile(r"/pages/(\d+)")


def _new_id() -> str:
    return str(uuid.uuid4())


def _text_run(text: str, styles: dict[str, Any]) -> dict[str, Any]:
    return {"type": "text", "text": text, "styles": styles}


def _make(btype: str, props: dict | None = None, content: Any = None, children: list | None = None) -> dict:
    b: dict[str, Any] = {"id": _new_id(), "type": btype, "props": props or {}}
    b["content"] = content if content is not None else []
    if children:
        b["children"] = children
    return b


# --- inline content ---


def _styles(marks: list[dict] | None) -> dict[str, Any]:
    """ADF text marks -> BlockNote inline styles. Color marks are dropped: ADF
    carries hex values while BlockNote's default schema expects named colors."""
    styles: dict[str, Any] = {}
    for m in marks or []:
        t = m.get("type")
        if t == "strong":
            styles["bold"] = True
        elif t == "em":
            styles["italic"] = True
        elif t == "underline":
            styles["underline"] = True
        elif t in ("strike", "strikethrough"):
            styles["strike"] = True
        elif t == "code":
            styles["code"] = True
    return styles


def _rewrite_href(href: str) -> str:
    """Turn an internal Confluence page URL into a `confluence-page:{id}`
    placeholder; leave external links untouched."""
    m = _PAGE_URL_RE.search(href or "")
    return f"{CONFLUENCE_LINK_SCHEME}{m.group(1)}" if m else href


def _fmt_date(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).date().isoformat()
    except (ValueError, TypeError, OSError):
        return ""


def _inline(nodes: list[dict] | None) -> list[dict]:
    out: list[dict] = []
    for n in nodes or []:
        t = n.get("type")
        if t == "text":
            text = n.get("text", "")
            marks = n.get("marks", [])
            link = next((m for m in marks if m.get("type") == "link"), None)
            styles = _styles([m for m in marks if m.get("type") != "link"])
            if link:
                href = _rewrite_href(link.get("attrs", {}).get("href", ""))
                out.append({"type": "link", "href": href, "content": [_text_run(text, styles)]})
            elif text:
                out.append(_text_run(text, styles))
        elif t == "hardBreak":
            out.append(_text_run("\n", {}))
        elif t == "mention":
            txt = n.get("attrs", {}).get("text") or "@mention"
            out.append(_text_run(txt, {}))
        elif t == "emoji":
            txt = n.get("attrs", {}).get("text") or n.get("attrs", {}).get("shortName", "")
            if txt:
                out.append(_text_run(txt, {}))
        elif t == "date":
            d = _fmt_date(n.get("attrs", {}).get("timestamp"))
            if d:
                out.append(_text_run(d, {}))
        elif t == "status":
            txt = n.get("attrs", {}).get("text", "")
            if txt:
                out.append(_text_run(txt, {}))
        elif t == "inlineCard":
            url = n.get("attrs", {}).get("url", "")
            if url:
                out.append({"type": "link", "href": _rewrite_href(url), "content": [_text_run(url, {})]})
    return out


def _plain(node: dict) -> str:
    if node.get("type") == "text":
        return node.get("text", "")
    return "".join(_plain(c) for c in node.get("content", []) or [])


def _flatten_inline(nodes: list[dict] | None) -> list[dict]:
    """Collapse a list of block nodes (as found inside quotes/panels/table cells)
    into a single inline run list, joining paragraphs with newlines."""
    out: list[dict] = []
    for i, child in enumerate(nodes or []):
        if child.get("type") == "paragraph":
            if i > 0:
                out.append(_text_run("\n", {}))
            out.extend(_inline(child.get("content", [])))
        else:
            txt = _plain(child)
            if txt:
                out.append(_text_run(txt, {}))
    return out


# --- block content ---


def _list_items(node: dict, item_type: str) -> list[dict]:
    out: list[dict] = []
    for li in node.get("content", []):
        if li.get("type") != "listItem":
            continue
        content: list[dict] = []
        children: list[dict] = []
        for i, child in enumerate(li.get("content", [])):
            if i == 0 and child.get("type") == "paragraph":
                content = _inline(child.get("content", []))
            else:
                children.extend(_blocks([child]))
        out.append(_make(item_type, content=content, children=children or None))
    return out


def _task_items(node: dict) -> list[dict]:
    out: list[dict] = []
    for ti in node.get("content", []):
        if ti.get("type") != "taskItem":
            continue
        checked = ti.get("attrs", {}).get("state") == "DONE"
        out.append(_make("checkListItem", {"checked": checked}, content=_inline(ti.get("content", []))))
    return out


def _table_block(node: dict) -> dict:
    rows = []
    for row in node.get("content", []):
        if row.get("type") != "tableRow":
            continue
        cells = [
            _flatten_inline(cell.get("content", []))
            for cell in row.get("content", [])
            if cell.get("type") in ("tableCell", "tableHeader")
        ]
        rows.append({"cells": cells})
    return {"id": _new_id(), "type": "table", "props": {}, "content": {"type": "tableContent", "rows": rows}}


def _media_blocks(node: dict) -> list[dict]:
    out: list[dict] = []
    for media in node.get("content", []):
        if media.get("type") != "media":
            continue
        attrs = media.get("attrs", {})
        alt = attrs.get("alt", "")
        # External media carries a direct URL; attachment media references a fileId
        # the adapter resolves to a download link.
        if attrs.get("type") == "external" and attrs.get("url"):
            url = attrs["url"]
        elif attrs.get("id"):
            url = f"{ATTACHMENT_REF}{attrs['id']}"
        else:
            continue
        props: dict[str, Any] = {"url": url}
        if alt:
            props["caption"] = alt
        out.append(_make("image", props, content=[]))
    return out


def _block(n: dict) -> dict | list[dict] | None:
    t = n.get("type")
    if t == "paragraph":
        return _make("paragraph", content=_inline(n.get("content", [])))
    if t == "heading":
        level = min(max(int(n.get("attrs", {}).get("level", 1)), 1), 3)
        return _make("heading", {"level": level}, content=_inline(n.get("content", [])))
    if t == "bulletList":
        return _list_items(n, "bulletListItem")
    if t == "orderedList":
        return _list_items(n, "numberedListItem")
    if t == "taskList":
        return _task_items(n)
    if t == "codeBlock":
        lang = n.get("attrs", {}).get("language") or "text"
        return _make("codeBlock", {"language": str(lang).lower()}, content=_inline(n.get("content", [])))
    if t == "blockquote":
        return _make("quote", content=_flatten_inline(n.get("content", [])))
    if t == "panel":
        ptype = n.get("attrs", {}).get("panelType", "info")
        content = _flatten_inline(n.get("content", []))
        emoji = _PANEL_EMOJI.get(ptype)
        if emoji:
            content = [_text_run(f"{emoji} ", {})] + content
        return _make("quote", content=content)
    if t == "table":
        return _table_block(n)
    if t in ("mediaSingle", "mediaGroup"):
        return _media_blocks(n)
    if t in ("expand", "nestedExpand"):
        title = n.get("attrs", {}).get("title", "")
        children = _blocks(n.get("content", []))
        return _make("paragraph", content=[_text_run(title, {})] if title else [], children=children or None)
    if t == "rule":
        return None

    # Unknown/other: salvage any text so nothing is silently dropped.
    text = _plain(n)
    return _make("paragraph", content=[_text_run(text, {})]) if text else None


def _blocks(nodes: list[dict] | None) -> list[dict]:
    out: list[dict] = []
    for n in nodes or []:
        b = _block(n)
        if isinstance(b, list):
            out.extend(b)
        elif b is not None:
            out.append(b)
    return out


def adf_to_blocks(adf: dict | None) -> list[dict]:
    """Convert an ADF document node to a list of BlockNote blocks."""
    return _blocks((adf or {}).get("content", []))
