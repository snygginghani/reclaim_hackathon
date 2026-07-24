"""Pure translator: Obsidian Markdown -> Lore's BlockNote blocks. No I/O here —
the adapter reads the vault, resolves wikilink/attachment names to paths, and
re-hosts assets; it passes resolver callbacks into `markdown_to_blocks`.

Obsidian internal links `[[Note]]` become `obsidian-note:{path}` placeholders
(resolved to Lore page ids in the engine's second pass). Image embeds `![[img]]`
and Markdown images become `vault:{path}` refs the adapter re-hosts."""

from __future__ import annotations

import re
from typing import Any, Callable

# Placeholder scheme for links to other vault notes, resolved in pass 2.
OBSIDIAN_LINK_SCHEME = "obsidian-note:"
# Prefix marking a media block whose bytes come from a vault file.
ATTACHMENT_REF = "vault:"

LinkResolver = Callable[[str], str]      # note name/path -> href
EmbedResolver = Callable[[str], str | None]  # target -> props.url, or None to drop

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TASK_RE = re.compile(r"^\[([ xX])\]\s+(.*)$")
_HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([^\s`]*)")
_EMBED_LINE_RE = re.compile(r"^!\[\[([^\]]+)\]\]$")
_IMAGE_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")

# Inline tokens handled atomically (before emphasis is applied to plain runs).
_INLINE_RE = re.compile(
    r"(?P<code>`[^`]+`)"
    r"|(?P<embed>!\[\[[^\]]+\]\])"
    r"|(?P<wikilink>\[\[[^\]]+\]\])"
    r"|(?P<image>!\[[^\]]*\]\([^)]+\))"
    r"|(?P<link>\[[^\]]*\]\([^)]+\))"
)

_EMPHASIS = [
    (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), "bold"),
    (re.compile(r"__(.+?)__", re.DOTALL), "bold"),
    (re.compile(r"~~(.+?)~~", re.DOTALL), "strike"),
    (re.compile(r"\*(.+?)\*", re.DOTALL), "italic"),
    (re.compile(r"(?<!\w)_(.+?)_(?!\w)", re.DOTALL), "italic"),
]


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())


def _run(text: str, styles: dict[str, Any]) -> dict[str, Any]:
    return {"type": "text", "text": text, "styles": dict(styles)}


def _make(btype: str, props: dict | None = None, content: Any = None, children: list | None = None) -> dict:
    b: dict[str, Any] = {"id": _new_id(), "type": btype, "props": props or {}}
    b["content"] = content if content is not None else []
    if children:
        b["children"] = children
    return b


def _is_image(target: str) -> bool:
    base = target.split("|", 1)[0].split("#", 1)[0].strip().lower()
    return any(base.endswith(ext) for ext in _IMAGE_EXTS)


# --- inline ---


def _emphasis(text: str, styles: dict[str, Any]) -> list[dict]:
    earliest: tuple[re.Match, str] | None = None
    for pat, style in _EMPHASIS:
        m = pat.search(text)
        if m and (earliest is None or m.start() < earliest[0].start()):
            earliest = (m, style)
    if earliest is None:
        return [_run(text, styles)] if text else []
    m, style = earliest
    out: list[dict] = []
    if m.start() > 0:
        out.extend(_emphasis(text[: m.start()], styles))
    out.extend(_emphasis(m.group(1), {**styles, style: True}))
    out.extend(_emphasis(text[m.end():], styles))
    return out


def _inline(text: str, resolve_link: LinkResolver, resolve_embed: EmbedResolver) -> list[dict]:
    out: list[dict] = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            out.extend(_emphasis(text[pos: m.start()], {}))
        pos = m.end()
        kind = m.lastgroup
        tok = m.group()
        if kind == "code":
            out.append(_run(tok[1:-1], {"code": True}))
        elif kind == "wikilink":
            out.append(_wikilink_run(tok[2:-2], resolve_link))
        elif kind == "link":
            lm = re.match(r"\[([^\]]*)\]\(([^)]+)\)", tok)
            if lm:
                content = _emphasis(lm.group(1) or lm.group(2), {}) or [_run(lm.group(2), {})]
                out.append({"type": "link", "href": lm.group(2), "content": content})
        elif kind in ("embed", "image"):
            # Inline embeds/images can't live inside BlockNote inline content;
            # fall back to their alt/target text so nothing is dropped silently.
            alt = tok[3:-2] if kind == "embed" else (re.match(r"!\[([^\]]*)\]", tok).group(1))
            if alt:
                out.append(_run(alt, {}))
    if pos < len(text):
        out.extend(_emphasis(text[pos:], {}))
    return out


def _wikilink_run(inner: str, resolve_link: LinkResolver) -> dict:
    target, _, alias = inner.partition("|")
    target = target.split("#", 1)[0].strip()
    display = alias.strip() or inner.strip()
    return {"type": "link", "href": resolve_link(target), "content": [_run(display, {})]}


# --- blocks ---


def _media_block(target: str, alt: str, resolve_embed: EmbedResolver) -> dict | None:
    if target.startswith(("http://", "https://")):
        url: str | None = target
    else:
        url = resolve_embed(target)
    if not url:
        return None
    props: dict[str, Any] = {"url": url}
    if alt:
        props["caption"] = alt
    return _make("image", props, content=[])


def _consume_fence(lines: list[str], i: int) -> tuple[dict, int]:
    m = _FENCE_RE.match(lines[i])
    fence = m.group(2)[0]
    lang = (m.group(3) or "text").lower()
    body: list[str] = []
    i += 1
    while i < len(lines) and not re.match(rf"^\s*{re.escape(fence)}{{3,}}\s*$", lines[i]):
        body.append(lines[i])
        i += 1
    i += 1  # skip closing fence
    code = "\n".join(body)
    return _make("codeBlock", {"language": lang}, content=[_run(code, {})] if code else []), i


def _consume_blockquote(lines: list[str], i: int, rl: LinkResolver, re_: EmbedResolver) -> tuple[dict, int]:
    parts: list[str] = []
    while i < len(lines) and lines[i].lstrip().startswith(">"):
        parts.append(re.sub(r"^\s*>\s?", "", lines[i]))
        i += 1
    content: list[dict] = []
    for j, p in enumerate(x for x in parts if x.strip() != ""):
        if j > 0:
            content.append(_run("\n", {}))
        content.extend(_inline(p, rl, re_))
    return _make("quote", content=content), i


def _consume_table(lines: list[str], i: int, rl: LinkResolver, re_: EmbedResolver) -> tuple[dict, int]:
    def cells(row: str) -> list[str]:
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        return [c.strip() for c in row.split("|")]

    rows: list[dict] = []
    header = cells(lines[i])
    rows.append({"cells": [_inline(c, rl, re_) for c in header]})
    i += 2  # header + separator
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        rows.append({"cells": [_inline(c, rl, re_) for c in cells(lines[i])]})
        i += 1
    return {"id": _new_id(), "type": "table", "props": {}, "content": {"type": "tableContent", "rows": rows}}, i


def _list_item_block(ordered: bool, text: str, rl: LinkResolver, re_: EmbedResolver) -> dict:
    task = _TASK_RE.match(text)
    if task:
        checked = task.group(1).lower() == "x"
        return _make("checkListItem", {"checked": checked}, content=_inline(task.group(2), rl, re_))
    btype = "numberedListItem" if ordered else "bulletListItem"
    return _make(btype, content=_inline(text, rl, re_))


def _consume_list(lines: list[str], i: int, rl: LinkResolver, re_: EmbedResolver) -> tuple[list[dict], int]:
    items: list[tuple[int, bool, str]] = []
    while i < len(lines):
        m = _LIST_RE.match(lines[i])
        if m:
            indent = len(m.group(1).replace("\t", "    "))
            ordered = m.group(2)[0] not in "-*+"
            items.append((indent, ordered, m.group(3)))
            i += 1
        elif lines[i].strip() == "" and i + 1 < len(lines) and _LIST_RE.match(lines[i + 1]):
            i += 1  # blank line between items
        else:
            break

    root: list[dict] = []
    stack: list[tuple[int, list[dict]]] = [(-1, root)]
    for indent, ordered, text in items:
        block = _list_item_block(ordered, text, rl, re_)
        block["children"] = []
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        stack[-1][1].append(block)
        stack.append((indent, block["children"]))
    _prune_children(root)
    return root, i


def _prune_children(blocks: list[dict]) -> None:
    for b in blocks:
        kids = b.get("children")
        if kids:
            _prune_children(kids)
        elif "children" in b:
            del b["children"]


def _strip_frontmatter(lines: list[str]) -> list[str]:
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                return lines[j + 1:]
    return lines


def markdown_to_blocks(
    text: str,
    resolve_link: LinkResolver | None = None,
    resolve_embed: EmbedResolver | None = None,
) -> list[dict]:
    rl = resolve_link or (lambda name: f"{OBSIDIAN_LINK_SCHEME}{name}")
    re_ = resolve_embed or (lambda target: f"{ATTACHMENT_REF}{target}")

    lines = _strip_frontmatter(text.replace("\r\n", "\n").split("\n"))
    out: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == "":
            i += 1
            continue
        if _FENCE_RE.match(line):
            block, i = _consume_fence(lines, i)
            out.append(block)
            continue
        if _HR_RE.match(line):
            i += 1
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            level = min(len(heading.group(1)), 3)
            out.append(_make("heading", {"level": level}, content=_inline(heading.group(2), rl, re_)))
            i += 1
            continue
        embed = _EMBED_LINE_RE.match(line.strip())
        if embed:
            target = embed.group(1)
            if _is_image(target):
                block = _media_block(target.split("|", 1)[0], "", re_)
                if block:
                    out.append(block)
            else:  # note transclusion -> a link to the note
                out.append(_make("paragraph", content=[_wikilink_run(target, rl)]))
            i += 1
            continue
        image = _IMAGE_LINE_RE.match(line.strip())
        if image:
            block = _media_block(image.group(2), image.group(1), re_)
            if block:
                out.append(block)
            i += 1
            continue
        if line.lstrip().startswith(">"):
            block, i = _consume_blockquote(lines, i, rl, re_)
            out.append(block)
            continue
        if "|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            block, i = _consume_table(lines, i, rl, re_)
            out.append(block)
            continue
        if _LIST_RE.match(line):
            blocks, i = _consume_list(lines, i, rl, re_)
            out.extend(blocks)
            continue
        # Paragraph: gather consecutive plain lines.
        para: list[str] = []
        while i < n and lines[i].strip() != "" and not _is_block_start(lines, i):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append(_make("paragraph", content=_inline(" ".join(para), rl, re_)))
    return out


def _is_block_start(lines: list[str], i: int) -> bool:
    line = lines[i]
    if _FENCE_RE.match(line) or _HEADING_RE.match(line) or _HR_RE.match(line) or _LIST_RE.match(line):
        return True
    if line.lstrip().startswith(">"):
        return True
    if _EMBED_LINE_RE.match(line.strip()) or _IMAGE_LINE_RE.match(line.strip()):
        return True
    if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
        return True
    return False
