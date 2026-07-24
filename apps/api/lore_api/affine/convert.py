"""Pure translator: AFFiNE/BlockSuite blocks -> Lore's BlockNote blocks. No I/O —
the adapter decodes the snapshot (see snapshot.py) and drives this; the block
accessors here take a decoded `blocks` Y.Map and walk the tree by id.

Cross-doc links (`affine:embed-linked-doc`/`embed-synced-doc` and inline
`reference` runs) become `affine-doc:{pageId}` placeholders, resolved to Lore page
ids in the engine's second pass. Images/attachments become `affine-blob:{sourceId}`
refs the adapter re-hosts from the snapshot's blob table."""

from __future__ import annotations

import uuid
from typing import Any

from pycrdt import Map

from . import snapshot as snap

AFFINE_LINK_SCHEME = "affine-doc:"
ATTACHMENT_REF = "affine-blob:"

# Edgeless-canvas / non-document flavours we never emit into a linear doc.
_SKIP_FLAVOURS = {"affine:surface", "affine:frame", "affine:edgeless-text"}
_MEDIA_FLAVOURS = {"affine:image", "affine:attachment"}


def _new_id() -> str:
    return str(uuid.uuid4())


def _run(text: str, styles: dict[str, Any]) -> dict[str, Any]:
    return {"type": "text", "text": text, "styles": styles}


def _make(btype: str, props: dict | None = None, content: Any = None, children: list | None = None) -> dict:
    b: dict[str, Any] = {"id": _new_id(), "type": btype, "props": props or {}}
    b["content"] = content if content is not None else []
    if children:
        b["children"] = children
    return b


# --- inline ---


def _styles(attrs: dict | None) -> dict[str, Any]:
    styles: dict[str, Any] = {}
    if not attrs:
        return styles
    if attrs.get("bold"):
        styles["bold"] = True
    if attrs.get("italic"):
        styles["italic"] = True
    if attrs.get("underline"):
        styles["underline"] = True
    if attrs.get("strike") or attrs.get("strikethrough"):
        styles["strike"] = True
    if attrs.get("code"):
        styles["code"] = True
    return styles


def _inline(delta: list[tuple[str, dict | None]], doc_titles: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    for text, attrs in delta:
        attrs = attrs or {}
        # Inline mention of another doc -> internal link.
        ref = attrs.get("reference")
        if ref and ref.get("pageId"):
            page_id = ref["pageId"]
            label = doc_titles.get(page_id) or (text.strip() or "linked page")
            out.append({
                "type": "link",
                "href": f"{AFFINE_LINK_SCHEME}{page_id}",
                "content": [_run(label, {})],
            })
            continue
        if not text:
            continue
        styles = _styles(attrs)
        link = attrs.get("link")
        if link:
            out.append({"type": "link", "href": link, "content": [_run(text, styles)]})
        else:
            out.append(_run(text, styles))
    return out


# --- blocks ---


def _link_paragraph(url: str, title: str) -> dict:
    return _make("paragraph", content=[{"type": "link", "href": url,
                                        "content": [_run(title or url, {})]}])


def _convert_block(blocks: Map, bid: str, doc_titles: dict[str, str]) -> dict | None:
    if bid not in blocks:
        return None
    block = blocks[bid]
    fl = snap.flavour(block)
    if fl in _SKIP_FLAVOURS:
        return None

    children = _convert_children(blocks, snap.children_ids(block), doc_titles)

    def make(btype: str, props: dict | None = None, content: Any = None) -> dict:
        return _make(btype, props, content if content is not None
                     else _inline(snap.text_delta(block), doc_titles), children or None)

    if fl == "affine:paragraph":
        ptype = snap.prop(block, "prop:type", "text")
        if ptype and ptype.startswith("h") and ptype[1:].isdigit():
            return make("heading", {"level": min(int(ptype[1:]), 3)})
        if ptype == "quote":
            return make("quote")
        return make("paragraph")
    if fl == "affine:list":
        ptype = snap.prop(block, "prop:type", "bulleted")
        if ptype == "todo":
            return make("checkListItem", {"checked": bool(snap.prop(block, "prop:checked"))})
        if ptype == "numbered":
            return make("numberedListItem")
        return make("bulletListItem")
    if fl == "affine:code":
        lang = (snap.prop(block, "prop:language") or "text")
        return make("codeBlock", {"language": str(lang).lower()})
    if fl == "affine:divider":
        return None
    if fl in _MEDIA_FLAVOURS:
        source_id = snap.prop(block, "prop:sourceId")
        if not source_id:
            return None
        btype = "image" if fl == "affine:image" else "file"
        props: dict[str, Any] = {"url": f"{ATTACHMENT_REF}{source_id}"}
        caption = snap.prop(block, "prop:caption") or snap.prop(block, "prop:name")
        if caption:
            props["caption"] = caption
        return _make(btype, props, content=[], children=children or None)
    if fl in ("affine:bookmark", "affine:embed-youtube"):
        url = snap.prop(block, "prop:url", "")
        return _link_paragraph(url, snap.prop(block, "prop:title", "")) if url else None
    if fl in ("affine:embed-linked-doc", "affine:embed-synced-doc"):
        page_id = snap.prop(block, "prop:pageId")
        if not page_id:
            return None
        label = doc_titles.get(page_id) or "linked page"
        return _make("paragraph", content=[{
            "type": "link", "href": f"{AFFINE_LINK_SCHEME}{page_id}", "content": [_run(label, {})],
        }])
    if fl == "affine:latex":
        expr = snap.prop(block, "prop:latex", "")
        return _make("paragraph", content=[_run(expr, {"code": True})]) if expr else None
    if fl in ("affine:database", "affine:table"):
        # Deferred: keep a visible placeholder so content isn't silently dropped.
        title = snap.prop(block, "prop:title", "") or ("Table" if fl == "affine:table" else "Database")
        return _make("paragraph", content=[_run(f"[{title}]", {"italic": True})])

    # Unknown: salvage any text.
    text = _inline(snap.text_delta(block), doc_titles)
    return _make("paragraph", content=text, children=children or None) if text else None


def _convert_children(blocks: Map, ids: list[str], doc_titles: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    for cid in ids:
        b = _convert_block(blocks, cid, doc_titles)
        if b is not None:
            out.append(b)
    return out


def page_to_blocks(blocks: Map, doc_titles: dict[str, str]) -> list[dict]:
    """Convert one page's `blocks` map to BlockNote blocks. Content lives under the
    `affine:page` root's `affine:note` children whose displayMode isn't edgeless
    (edgeless-only notes and the surface are canvas, not document, content)."""
    root_id = next(
        (bid for bid in blocks.to_py() if snap.flavour(blocks[bid]) == "affine:page"), None
    )
    if root_id is None:
        return []
    out: list[dict] = []
    for note_id in snap.children_ids(blocks[root_id]):
        note = blocks[note_id]
        if snap.flavour(note) != "affine:note":
            continue
        if snap.prop(note, "prop:displayMode") == "edgeless" or snap.prop(note, "prop:hidden"):
            continue
        out.extend(_convert_children(blocks, snap.children_ids(note), doc_titles))
    return out
